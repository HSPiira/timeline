"""OAuth provider configuration and authorization API"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.external.email.envelope_encryption import (
    EnvelopeEncryptor, OAuthStateManager)
from src.infrastructure.external.email.oauth_drivers import OAuthDriverRegistry
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.models.email_account import EmailAccount
from src.infrastructure.persistence.models.subject import Subject
from src.infrastructure.persistence.repositories.oauth_provider_config_repo import (
    OAuthAuditLogRepository, OAuthProviderConfigRepository,
    OAuthStateRepository)
from src.presentation.api.dependencies import get_current_user
from src.presentation.api.v1.schemas.oauth_provider import (
    OAuthAuditLogResponse, OAuthAuthorizeRequest, OAuthAuthorizeResponse,
    OAuthCallbackResponse, OAuthProviderConfigCreate,
    OAuthProviderConfigResponse, OAuthProviderConfigUpdate,
    OAuthProviderHealthCheck, OAuthProviderListResponse, OAuthProviderMetadata,
    OAuthRotateCredentialsRequest, OAuthRotateCredentialsResponse)
from src.presentation.api.v1.schemas.token import TokenPayload
from src.shared.enums import OAuthStatus
from src.shared.telemetry.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/oauth-providers", tags=["OAuth Providers"])


# Helper to check admin permissions
async def require_admin(current_user: TokenPayload = Depends(get_current_user)):
    """Require admin role for provider configuration"""
    # TODO: Implement proper admin check
    # For now, all authenticated users can manage OAuth configs
    # In production, check user.role == 'admin' or similar
    return current_user


# Provider Configuration Management


@router.post("", response_model=OAuthProviderConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_provider_config(
    data: OAuthProviderConfigCreate,
    current_user: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Register new OAuth provider configuration.

    Requires admin role. Creates initial version (v1) of provider config.
    Client credentials are encrypted using envelope encryption.
    """
    repo = OAuthProviderConfigRepository(db)
    audit_repo = OAuthAuditLogRepository(db)
    encryptor = EnvelopeEncryptor()

    # Check if provider already exists
    existing = await repo.get_active_config(current_user.tenant_id, data.provider_type)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active {data.provider_type} provider already configured. "
            f"Use PATCH to update or POST /{existing.id}/rotate to rotate credentials.",
        )

    # Get provider metadata from driver registry
    try:
        metadata = OAuthDriverRegistry.get_provider_metadata(data.provider_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Use provider's default scopes if not specified
    scopes = data.scopes or metadata.get("default_scopes", [])
    if data.provider_type == "gmail" and not data.scopes:
        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ]
    elif data.provider_type == "outlook" and not data.scopes:
        scopes = [
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.ReadWrite",
            "offline_access",
        ]
    elif data.provider_type == "yahoo" and not data.scopes:
        scopes = ["mail-r", "mail-w"]

    # Encrypt credentials with envelope encryption
    client_id_encrypted = encryptor.encrypt(data.client_id)
    client_secret_encrypted = encryptor.encrypt(data.client_secret)
    encryption_key_id = encryptor.extract_key_id(client_id_encrypted)

    # Create provider config
    config = await repo.create_new_version(
        tenant_id=current_user.tenant_id,
        provider_type=data.provider_type,
        client_id_encrypted=client_id_encrypted,
        client_secret_encrypted=client_secret_encrypted,
        encryption_key_id=encryption_key_id,
        redirect_uri=data.redirect_uri,
        scopes=scopes,
        created_by=current_user.sub,
    )

    # Audit log
    await audit_repo.log_action(
        tenant_id=current_user.tenant_id,
        provider_config_id=config.id,
        actor_user_id=current_user.sub,
        action="create",
        changes={
            "provider_type": {"old": None, "new": data.provider_type},
            "redirect_uri": {"old": None, "new": data.redirect_uri},
            "version": {"old": None, "new": str(config.version)},
        },
    )

    await db.commit()
    await db.refresh(config)

    logger.info(
        f"Created OAuth provider config: {config.provider_type} "
        f"v{config.version} for tenant {current_user.tenant_id}"
    )

    return config


@router.get("", response_model=OAuthProviderListResponse)
async def list_provider_configs(
    include_inactive: bool = Query(False, description="Include inactive configs"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all OAuth provider configurations for tenant"""
    repo = OAuthProviderConfigRepository(db)
    configs = await repo.list_configs(
        tenant_id=current_user.tenant_id,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )

    return OAuthProviderListResponse(
        providers=[OAuthProviderConfigResponse.model_validate(c) for c in configs],
        total=len(configs),
    )


@router.get("/{config_id}", response_model=OAuthProviderConfigResponse)
async def get_provider_config(
    config_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get specific OAuth provider configuration"""
    repo = OAuthProviderConfigRepository(db)
    config = await repo.get_by_id(config_id)

    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    return config


@router.patch("/{config_id}", response_model=OAuthProviderConfigResponse)
async def update_provider_config(
    config_id: str,
    data: OAuthProviderConfigUpdate,
    current_user: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Update OAuth provider configuration.

    Note: Updating client_id or client_secret creates a new version.
    Use POST /{id}/rotate for explicit credential rotation.
    """
    repo = OAuthProviderConfigRepository(db)
    audit_repo = OAuthAuditLogRepository(db)
    config = await repo.get_by_id(config_id)

    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    changes = {}

    # Check if credentials are being updated (requires rotation)
    if data.client_id or data.client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To update credentials, use POST /{id}/rotate endpoint for proper versioning",
        )

    # Update simple fields
    if data.redirect_uri is not None:
        changes["redirect_uri"] = {"old": config.redirect_uri, "new": data.redirect_uri}
        config.redirect_uri = data.redirect_uri

    if data.is_active is not None:
        changes["is_active"] = {
            "old": str(config.is_active),
            "new": str(data.is_active),
        }
        config.is_active = data.is_active

    if data.rate_limit_connections_per_hour is not None:
        changes["rate_limit"] = {
            "old": str(config.rate_limit_connections_per_hour),
            "new": str(data.rate_limit_connections_per_hour),
        }
        config.rate_limit_connections_per_hour = data.rate_limit_connections_per_hour

    if data.scopes is not None:
        changes["tenant_configured_scopes"] = {
            "old": str(config.tenant_configured_scopes),
            "new": str(data.scopes),
        }
        config.tenant_configured_scopes = data.scopes

    # Audit log
    if changes:
        await audit_repo.log_action(
            tenant_id=current_user.tenant_id,
            provider_config_id=config.id,
            actor_user_id=current_user.sub,
            action="update",
            changes=changes,
        )

    await db.commit()
    await db.refresh(config)

    logger.info(f"Updated OAuth provider config: {config.id}")

    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_config(
    config_id: str,
    current_user: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft delete OAuth provider configuration.

    Existing email accounts will continue to work with their bound version.
    """
    repo = OAuthProviderConfigRepository(db)
    audit_repo = OAuthAuditLogRepository(db)
    config = await repo.get_by_id(config_id)

    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    # Soft delete
    config.deleted_at = datetime.now(UTC)
    config.deleted_by = current_user.sub
    config.is_active = False

    # Audit log
    await audit_repo.log_action(
        tenant_id=current_user.tenant_id,
        provider_config_id=config.id,
        actor_user_id=current_user.sub,
        action="delete",
        changes={"deleted": {"old": "false", "new": "true"}},
    )

    await db.commit()

    logger.info(f"Deleted OAuth provider config: {config.id}")


# OAuth Authorization Flow


@router.post("/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def authorize_provider(
    provider: str,
    data: OAuthAuthorizeRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate OAuth authorization flow.

    Returns authorization URL for user to visit. After consent,
    user will be redirected to callback endpoint with authorization code.
    """
    repo = OAuthProviderConfigRepository(db)
    state_repo = OAuthStateRepository(db)

    # Get active provider config
    config = await repo.get_active_config(current_user.tenant_id, provider)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth provider '{provider}' not configured for this tenant",
        )

    # Check rate limit
    if not await repo.increment_connection_count(config.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {config.rate_limit_connections_per_hour} "
            f"connections per hour allowed.",
        )

    # Decrypt credentials
    encryptor = EnvelopeEncryptor()
    try:
        client_id = encryptor.decrypt(config.client_id_encrypted)
        client_secret = encryptor.decrypt(config.client_secret_encrypted)
    except Exception as e:
        logger.error(f"Failed to decrypt OAuth credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt OAuth credentials",
        ) from e

    # Get OAuth driver
    try:
        driver = OAuthDriverRegistry.get_driver(
            provider_type=config.provider_type,
            client_id=str(client_id),
            client_secret=str(client_secret),
            redirect_uri=config.redirect_uri,
            scopes=config.tenant_configured_scopes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Create OAuth state
    nonce = secrets.token_urlsafe(32)
    state_manager = OAuthStateManager()

    state_record = await state_repo.create_state(
        tenant_id=current_user.tenant_id,
        user_id=current_user.sub,
        provider_config_id=config.id,
        nonce=nonce,
        signature="",  # Will be set below
        return_url=data.return_url,
        ttl_minutes=10,
    )

    # Sign state
    signed_state = state_manager.create_signed_state(state_record.id)
    state_record.signature = signed_state.split(":")[1]

    # Build authorization URL
    auth_url = driver.build_authorization_url(state=signed_state)

    await db.commit()

    logger.info(
        f"Generated OAuth authorization URL for {provider} "
        f"(user={current_user.sub}, state={state_record.id})"
    )

    return OAuthAuthorizeResponse(
        auth_url=auth_url,
        state=signed_state,
        expires_at=state_record.expires_at,
        provider=provider,
    )


@router.get("/{provider}/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="OAuth state parameter"),
    error: str | None = Query(None, description="Error from provider"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from provider.

    Exchanges authorization code for tokens and creates EmailAccount.
    """
    if error:
        logger.warning(f"OAuth error from {provider}: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authorization failed: {error}",
        )

    state_repo = OAuthStateRepository(db)
    config_repo = OAuthProviderConfigRepository(db)
    state_manager = OAuthStateManager()

    # Verify and extract state
    try:
        state_id = state_manager.verify_and_extract(state)
    except ValueError as e:
        logger.error(f"Invalid OAuth state: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter - possible CSRF attack",
        ) from e

    # Consume state (replay protection)
    state_record = await state_repo.consume_state(state_id)
    if not state_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state - authorization timed out or already used",
        )

    # Get provider config
    config = await config_repo.get_by_id(state_record.provider_config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider configuration not found",
        )

    # Decrypt credentials
    encryptor = EnvelopeEncryptor()
    try:
        client_id = encryptor.decrypt(config.client_id_encrypted)
        client_secret = encryptor.decrypt(config.client_secret_encrypted)
    except Exception as e:
        logger.error(f"Failed to decrypt OAuth credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt OAuth credentials",
        ) from e

    # Get OAuth driver
    driver = OAuthDriverRegistry.get_driver(
        provider_type=config.provider_type,
        client_id=str(client_id),
        client_secret=str(client_secret),
        redirect_uri=config.redirect_uri,
        scopes=config.tenant_configured_scopes,
    )

    # Exchange code for tokens
    try:
        tokens = await driver.exchange_code_for_tokens(code)
    except ValueError as e:
        logger.error(f"Token exchange failed: {e}")
        await config_repo.update_health_status(
            config.id, "unhealthy", f"Token exchange failed: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange authorization code: {str(e)}",
        ) from e

    # Get user info
    try:
        user_info = await driver.get_user_info(tokens.access_token)
    except ValueError as e:
        logger.error(f"Failed to get user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve user information: {str(e)}",
        ) from e

    # Update provider health
    await config_repo.update_health_status(config.id, "healthy")

    # Create or get subject for email account
    from sqlalchemy import select

    result = await db.execute(
        select(Subject).where(
            Subject.tenant_id == state_record.tenant_id,
            Subject.subject_type == "email_account",
            Subject.external_ref == user_info.email,
        )
    )
    subject = result.scalar_one_or_none()

    if not subject:
        subject = Subject(
            tenant_id=state_record.tenant_id,
            subject_type="email_account",
            external_ref=user_info.email,
            metadata={
                "email": user_info.email,
                "provider": provider,
                "name": user_info.name,
            },
        )
        db.add(subject)
        await db.flush()

    # Encrypt credentials for storage
    from integrations.email.encryption import CredentialEncryptor

    credential_encryptor = CredentialEncryptor()
    credentials = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
        "expires_at": tokens.expires_at.isoformat(),
        "scope": tokens.scope,
    }
    credentials_encrypted = credential_encryptor.encrypt(credentials)

    # Check if email account already exists
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.tenant_id == state_record.tenant_id,
            EmailAccount.email_address == user_info.email,
            EmailAccount.provider_type == provider,
        )
    )
    email_account = result.scalar_one_or_none()

    if email_account:
        # Update existing account
        email_account.credentials_encrypted = credentials_encrypted
        email_account.is_active = True
        email_account.oauth_provider_config_id = config.id
        email_account.oauth_provider_config_version = config.version
        email_account.granted_scopes = tokens.scope.split(" ") if tokens.scope else []
        email_account.oauth_status = OAuthStatus.ACTIVE.value
        email_account.oauth_error_count = 0
        email_account.oauth_next_retry_at = None
        email_account.last_auth_error = None
        email_account.last_auth_error_at = None
        email_account.token_last_refreshed_at = datetime.now(UTC)
        logger.info(f"Updated email account: {user_info.email}")
    else:
        # Create new email account
        email_account = EmailAccount(
            tenant_id=state_record.tenant_id,
            subject_id=subject.id,
            provider_type=provider,
            email_address=user_info.email,
            credentials_encrypted=credentials_encrypted,
            is_active=True,
            oauth_provider_config_id=config.id,
            oauth_provider_config_version=config.version,
            granted_scopes=tokens.scope.split(" ") if tokens.scope else [],
            oauth_status=OAuthStatus.ACTIVE.value,
            token_last_refreshed_at=datetime.now(UTC),
        )
        db.add(email_account)
        logger.info(f"Created new email account: {user_info.email}")

    await db.commit()
    await db.refresh(email_account)

    return OAuthCallbackResponse(
        success=True,
        email_account_id=email_account.id,
        email_address=user_info.email,
        provider=provider,
        has_refresh_token=bool(tokens.refresh_token),
        return_url=state_record.return_url,
    )


# Credential Rotation


@router.post("/{config_id}/rotate", response_model=OAuthRotateCredentialsResponse)
async def rotate_credentials(
    config_id: str,
    data: OAuthRotateCredentialsRequest,
    current_user: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate OAuth credentials (create new version).

    Existing EmailAccounts remain bound to old version and continue working.
    New connections will use the new credentials.
    """
    repo = OAuthProviderConfigRepository(db)
    audit_repo = OAuthAuditLogRepository(db)
    config = await repo.get_by_id(config_id)

    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    # Encrypt new credentials
    encryptor = EnvelopeEncryptor()
    client_id_encrypted = encryptor.encrypt(data.new_client_id)
    client_secret_encrypted = encryptor.encrypt(data.new_client_secret)
    encryption_key_id = encryptor.extract_key_id(client_id_encrypted)

    # Count affected accounts
    from sqlalchemy import func, select

    result = await db.execute(
        select(func.count(EmailAccount.id)).where(
            EmailAccount.tenant_id == current_user.tenant_id,
            EmailAccount.provider_type == config.provider_type,
        )
    )
    affected_count = result.scalar() or 0

    # Create new version
    old_version = config.version
    new_config = await repo.create_new_version(
        tenant_id=current_user.tenant_id,
        provider_type=config.provider_type,
        client_id_encrypted=client_id_encrypted,
        client_secret_encrypted=client_secret_encrypted,
        encryption_key_id=encryption_key_id,
        redirect_uri=config.redirect_uri,
        scopes=config.tenant_configured_scopes,
        created_by=current_user.sub,
    )

    # Audit log
    await audit_repo.log_action(
        tenant_id=current_user.tenant_id,
        provider_config_id=new_config.id,
        actor_user_id=current_user.sub,
        action="rotate",
        changes={
            "version": {"old": str(old_version), "new": str(new_config.version)},
            "credentials": {"old": "rotated", "new": "new"},
        },
        reason=data.reason,
    )

    await db.commit()

    logger.info(
        f"Rotated OAuth credentials for {config.provider_type}: "
        f"v{old_version} -> v{new_config.version}"
    )

    return OAuthRotateCredentialsResponse(
        old_version=old_version,
        new_version=new_config.version,
        provider_config_id=new_config.id,
        migration_required=False,  # Old accounts continue working
        affected_accounts=affected_count,
    )


# Monitoring & Audit


@router.get("/{config_id}/health", response_model=OAuthProviderHealthCheck)
async def check_provider_health(
    config_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check OAuth provider health status"""
    repo = OAuthProviderConfigRepository(db)
    config = await repo.get_by_id(config_id)

    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    is_operational = config.health_status in ("healthy", "unknown")

    return OAuthProviderHealthCheck(
        provider_type=config.provider_type,
        health_status=config.health_status,
        last_check_at=config.last_health_check_at,
        last_error=config.last_health_error,
        is_operational=is_operational,
    )


@router.get("/{config_id}/audit", response_model=list[OAuthAuditLogResponse])
async def get_audit_history(
    config_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get audit history for provider configuration"""
    repo = OAuthProviderConfigRepository(db)
    audit_repo = OAuthAuditLogRepository(db)

    # Verify ownership
    config = await repo.get_by_id(config_id)
    if not config or config.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth provider config not found",
        )

    # Get audit logs
    logs = await audit_repo.get_config_history(
        tenant_id=current_user.tenant_id,
        provider_config_id=config_id,
        skip=skip,
        limit=limit,
    )

    return [OAuthAuditLogResponse.model_validate(log) for log in logs]


@router.get("/metadata/providers", response_model=list[OAuthProviderMetadata])
async def list_available_providers():
    """List all available OAuth providers and their metadata"""
    providers = OAuthDriverRegistry.list_providers()
    metadata_list = []

    for provider_type in providers:
        try:
            metadata = OAuthDriverRegistry.get_provider_metadata(provider_type)
            # Add default scopes
            default_scopes = []
            if provider_type == "gmail":
                default_scopes = [
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.modify",
                ]
            elif provider_type == "outlook":
                default_scopes = [
                    "https://graph.microsoft.com/Mail.Read",
                    "https://graph.microsoft.com/Mail.ReadWrite",
                    "offline_access",
                ]
            elif provider_type == "yahoo":
                default_scopes = ["mail-r", "mail-w"]

            metadata_list.append(
                OAuthProviderMetadata(
                    **metadata,
                    default_scopes=default_scopes,
                )
            )
        except Exception as e:
            logger.error(f"Failed to get metadata for {provider_type}: {e}")

    return metadata_list
