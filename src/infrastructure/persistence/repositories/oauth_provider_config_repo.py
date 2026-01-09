"""Repository for OAuth provider configuration"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.oauth_provider_config import (
    OAuthAuditLog, OAuthProviderConfig, OAuthState)
from src.infrastructure.persistence.repositories.auditable_repo import AuditableRepository
from src.shared.enums import AuditAction
from src.shared.utils.generators import generate_cuid

if TYPE_CHECKING:
    from src.application.services.system_audit_service import SystemAuditService


class OAuthProviderConfigRepository(AuditableRepository[OAuthProviderConfig]):
    """Repository for OAuth provider configuration with versioning support and audit tracking."""

    def __init__(
        self,
        db: AsyncSession,
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ) -> None:
        super().__init__(db, OAuthProviderConfig, audit_service, enable_audit=enable_audit)

    # Auditable implementation
    def _get_entity_type(self) -> str:
        return "oauth_provider"

    def _get_tenant_id(self, obj: OAuthProviderConfig) -> str:
        return obj.tenant_id

    def _serialize_for_audit(self, obj: OAuthProviderConfig) -> dict[str, Any]:
        return {
            "id": obj.id,
            "provider_type": obj.provider_type,
            "display_name": obj.display_name,
            "version": obj.version,
            "is_active": obj.is_active,
            "health_status": obj.health_status,
            # Note: encrypted credentials are excluded for security
        }

    async def get_active_config(
        self, tenant_id: str, provider_type: str
    ) -> OAuthProviderConfig | None:
        """Get active configuration for provider"""
        result = await self.db.execute(
            select(OAuthProviderConfig).where(
                and_(
                    OAuthProviderConfig.tenant_id == tenant_id,
                    OAuthProviderConfig.provider_type == provider_type,
                    OAuthProviderConfig.is_active.is_(True),
                    OAuthProviderConfig.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_config_by_version(
        self, tenant_id: str, provider_type: str, version: int
    ) -> OAuthProviderConfig | None:
        """Get specific version of configuration"""
        result = await self.db.execute(
            select(OAuthProviderConfig).where(
                and_(
                    OAuthProviderConfig.tenant_id == tenant_id,
                    OAuthProviderConfig.provider_type == provider_type,
                    OAuthProviderConfig.version == version,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_configs(
        self,
        tenant_id: str,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OAuthProviderConfig]:
        """List all OAuth provider configs for tenant"""
        query = select(OAuthProviderConfig).where(
            and_(
                OAuthProviderConfig.tenant_id == tenant_id,
                OAuthProviderConfig.deleted_at.is_(None),
            )
        )

        if not include_inactive:
            query = query.where(OAuthProviderConfig.is_active.is_(True))

        query = (
            query.offset(skip)
            .limit(limit)
            .order_by(OAuthProviderConfig.provider_type, OAuthProviderConfig.version.desc())
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_new_version(
        self,
        tenant_id: str,
        provider_type: str,
        client_id_encrypted: str,
        client_secret_encrypted: str,
        encryption_key_id: str,
        redirect_uri: str,
        scopes: list[str],
        created_by: str,
    ) -> OAuthProviderConfig:
        """
        Create new version of OAuth config (credential rotation).

        Deactivates previous version and creates new active version.
        """
        # Get current active config
        current = await self.get_active_config(tenant_id, provider_type)

        if current:
            # Deactivate current version
            current.is_active = False
            new_version = current.version + 1

            # Create new version
            new_config = OAuthProviderConfig(
                tenant_id=tenant_id,
                provider_type=provider_type,
                display_name=current.display_name,
                version=new_version,
                is_active=True,
                client_id_encrypted=client_id_encrypted,
                client_secret_encrypted=client_secret_encrypted,
                encryption_key_id=encryption_key_id,
                redirect_uri=redirect_uri,
                redirect_uri_whitelist=current.redirect_uri_whitelist,
                allowed_scopes=scopes,
                default_scopes=scopes,
                tenant_configured_scopes=scopes,
                authorization_endpoint=current.authorization_endpoint,
                token_endpoint=current.token_endpoint,
                provider_metadata=current.provider_metadata,
                created_by=created_by,
            )

            # Link versions
            current.superseded_by_id = new_config.id

        else:
            # First version for this provider
            new_config = OAuthProviderConfig(
                tenant_id=tenant_id,
                provider_type=provider_type,
                display_name=self._get_display_name(provider_type),
                version=0,
                is_active=True,
                client_id_encrypted=client_id_encrypted,
                client_secret_encrypted=client_secret_encrypted,
                encryption_key_id=encryption_key_id,
                redirect_uri=redirect_uri,
                redirect_uri_whitelist=[redirect_uri],
                allowed_scopes=scopes,
                default_scopes=scopes,
                tenant_configured_scopes=scopes,
                authorization_endpoint=self._get_auth_endpoint(provider_type),
                token_endpoint=self._get_token_endpoint(provider_type),
                created_by=created_by,
            )

        await self.create(new_config)

        # Emit custom audit for credential rotation if this is a version upgrade
        if current:
            await self.emit_custom_audit(
                new_config,
                AuditAction.STATUS_CHANGED,
                metadata={
                    "operation": "credential_rotation",
                    "previous_version": current.version,
                    "new_version": new_config.version,
                    "previous_config_id": current.id,
                },
            )

        return new_config

    async def increment_connection_count(self, config_id: str) -> bool:
        """Increment hourly connection counter for rate limiting"""
        config = await self.get_by_id(config_id)
        if not config:
            return False

        now = datetime.now(UTC)

        # Reset counter if hour has passed
        if config.rate_limit_reset_at and now > config.rate_limit_reset_at:
            config.current_hour_connections = 0
            config.rate_limit_reset_at = now + timedelta(hours=1)

        # Initialize if not set
        if not config.rate_limit_reset_at:
            config.rate_limit_reset_at = now + timedelta(hours=1)

        # Check rate limit
        if (
            config.rate_limit_connections_per_hour
            and config.current_hour_connections >= config.rate_limit_connections_per_hour
        ):
            return False

        # Increment counter
        config.current_hour_connections += 1
        await self.db.flush()
        return True

    async def update_health_status(
        self,
        config_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update provider health status"""
        config = await self.get_by_id(config_id)
        if config:
            config.health_status = status
            config.last_health_check_at = datetime.now(UTC)
            if error:
                config.last_health_error = error
            await self.db.flush()

    def _get_display_name(self, provider_type: str) -> str:
        """Get display name for provider"""
        names = {
            "gmail": "Gmail",
            "outlook": "Microsoft 365",
            "yahoo": "Yahoo Mail",
        }
        return names.get(provider_type, provider_type.title())

    def _get_auth_endpoint(self, provider_type: str) -> str:
        """Get authorization endpoint for provider"""
        endpoints = {
            "gmail": "https://accounts.google.com/o/oauth2/v2/auth",
            "outlook": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "yahoo": "https://api.login.yahoo.com/oauth2/request_auth",
        }
        return endpoints[provider_type]

    def _get_token_endpoint(self, provider_type: str) -> str:
        """Get token endpoint for provider"""
        endpoints = {
            "gmail": "https://oauth2.googleapis.com/token",
            "outlook": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "yahoo": "https://api.login.yahoo.com/oauth2/get_token",
        }
        return endpoints[provider_type]


class OAuthStateRepository:
    """Repository for OAuth state management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_state(
        self,
        tenant_id: str,
        user_id: str,
        provider_config_id: str,
        nonce: str,
        signature: str,
        return_url: str | None = None,
        ttl_minutes: int = 10,
    ) -> OAuthState:
        """Create new OAuth state"""
        now = datetime.now(UTC)
        state = OAuthState(
            id=generate_cuid(),
            tenant_id=tenant_id,
            user_id=user_id,
            provider_config_id=provider_config_id,
            nonce=nonce,
            signature=signature,
            created_at=now,
            expires_at=now + timedelta(minutes=ttl_minutes),
            consumed=False,
            return_url=return_url,
        )
        self.db.add(state)
        await self.db.flush()
        await self.db.refresh(state)
        return state

    async def get_state(self, state_id: str) -> OAuthState | None:
        """Get OAuth state by ID"""
        result = await self.db.execute(select(OAuthState).where(OAuthState.id == state_id))
        return result.scalar_one_or_none()

    async def consume_state(self, state_id: str) -> OAuthState | None:
        """
        Mark state as consumed (replay protection).

        Returns state if valid and not yet consumed, None otherwise.
        """
        state = await self.get_state(state_id)
        if not state:
            return None

        now = datetime.now(UTC)

        # Check if expired
        if now > state.expires_at:
            return None

        # Check if already consumed
        if state.consumed:
            return None

        # Consume state
        state.consumed = True
        state.consumed_at = now
        state.callback_received_at = now
        await self.db.flush()
        await self.db.refresh(state)
        return state

    async def cleanup_expired_states(self) -> int:
        """Delete expired OAuth states (cleanup job)"""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(OAuthState).where(
                and_(
                    OAuthState.expires_at < now,
                    OAuthState.consumed.is_(True),
                )
            )
        )
        states = result.scalars().all()

        for state in states:
            await self.db.delete(state)

        await self.db.flush()
        return len(states)


class OAuthAuditLogRepository:
    """Repository for OAuth audit logging"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        tenant_id: str,
        provider_config_id: str,
        actor_user_id: str,
        action: str,
        changes: dict[str, Any],
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthAuditLog:
        """Create audit log entry"""
        log = OAuthAuditLog(
            id=generate_cuid(),
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
            action=action,
            timestamp=datetime.now(UTC),
            changes=changes,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def get_config_history(
        self,
        tenant_id: str,
        provider_config_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OAuthAuditLog]:
        """Get audit history for config"""
        result = await self.db.execute(
            select(OAuthAuditLog)
            .where(
                and_(
                    OAuthAuditLog.tenant_id == tenant_id,
                    OAuthAuditLog.provider_config_id == provider_config_id,
                )
            )
            .order_by(OAuthAuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
