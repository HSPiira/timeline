"""Gmail OAuth 2.0 flow endpoints"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
from urllib.parse import urlencode
import httpx

from core.database import get_db
from api.deps import get_current_user, get_current_tenant
from models.tenant import Tenant
from models.user import User
from models.email_account import EmailAccount
from models.subject import Subject
from integrations.email.encryption import CredentialEncryptor
from schemas.token import TokenPayload
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth/gmail", tags=["Gmail OAuth"])


# OAuth configuration from environment
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/auth/gmail/callback")
GMAIL_SCOPES = os.getenv(
    "GMAIL_SCOPES",
    "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.modify"
)

# OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/authorize")
async def gmail_authorize(
    current_user: TokenPayload = Depends(get_current_user)
):
    """
    Initiate Gmail OAuth flow.

    Redirects user to Google's OAuth consent screen.
    """
    if not GMAIL_CLIENT_ID or not GMAIL_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gmail OAuth not configured. Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env"
        )

    # Build OAuth authorization URL
    params = {
        "client_id": GMAIL_CLIENT_ID,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Force consent to get refresh token
        "state": current_user.sub,  # Pass user ID for callback (sub is user_id)
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    logger.info(f"Redirecting user {current_user.sub} to Gmail OAuth")

    return {
        "auth_url": auth_url,
        "message": "Visit auth_url to authorize Gmail access"
    }


@router.get("/callback")
async def gmail_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="User ID from state parameter"),
    error: str = Query(None, description="Error from Google"),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Gmail OAuth callback.

    Exchanges authorization code for access and refresh tokens,
    then creates email account in database.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authorization failed: {error}"
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authorization code received"
        )

    try:
        # Exchange authorization code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GMAIL_CLIENT_ID,
                    "client_secret": GMAIL_CLIENT_SECRET,
                    "redirect_uri": GMAIL_REDIRECT_URI,
                    "grant_type": "authorization_code",
                }
            )

            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange authorization code: {token_response.text}"
                )

            tokens = token_response.json()

            # Get user info to retrieve email address
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )

            if userinfo_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to retrieve user information"
                )

            userinfo = userinfo_response.json()
            email_address = userinfo.get("email")

            if not email_address:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not retrieve email address from Google"
                )

        # Get user from state
        result = await db.execute(
            select(User).where(User.id == state)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Create or get subject for this email account
        result = await db.execute(
            select(Subject).where(
                Subject.tenant_id == user.tenant_id,
                Subject.subject_type == 'email_account',
                Subject.external_ref == email_address
            )
        )
        subject = result.scalar_one_or_none()

        if not subject:
            subject = Subject(
                tenant_id=user.tenant_id,
                subject_type='email_account',
                external_ref=email_address,
                metadata={'email': email_address, 'provider': 'gmail'}
            )
            db.add(subject)
            await db.flush()

        # Encrypt credentials
        encryptor = CredentialEncryptor()
        credentials = {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token'),
            'client_id': GMAIL_CLIENT_ID,
            'client_secret': GMAIL_CLIENT_SECRET,
            'token_expiry': tokens.get('expires_in'),  # Seconds until expiry
        }
        credentials_encrypted = encryptor.encrypt(credentials)

        # Check if email account already exists
        result = await db.execute(
            select(EmailAccount).where(
                EmailAccount.tenant_id == user.tenant_id,
                EmailAccount.email_address == email_address,
                EmailAccount.provider_type == 'gmail'
            )
        )
        email_account = result.scalar_one_or_none()

        if email_account:
            # Update existing account with new credentials
            email_account.credentials_encrypted = credentials_encrypted
            email_account.is_active = True
            logger.info(f"Updated Gmail account: {email_address}")
        else:
            # Create new email account
            email_account = EmailAccount(
                tenant_id=user.tenant_id,
                subject_id=subject.id,
                provider_type='gmail',
                email_address=email_address,
                credentials_encrypted=credentials_encrypted
            )
            db.add(email_account)
            logger.info(f"Created new Gmail account: {email_address}")

        await db.commit()
        await db.refresh(email_account)

        return {
            "success": True,
            "message": f"Gmail account {email_address} authorized successfully",
            "email_account_id": email_account.id,
            "email_address": email_address,
            "has_refresh_token": bool(tokens.get('refresh_token'))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gmail OAuth callback error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete OAuth flow: {str(e)}"
        )


@router.post("/refresh/{email_account_id}")
async def refresh_gmail_token(
    email_account_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually refresh Gmail OAuth tokens for an email account.

    This is useful for testing or forcing a token refresh.
    """
    # Get email account
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == email_account_id,
            EmailAccount.tenant_id == current_user.tenant_id
        )
    )
    email_account = result.scalar_one_or_none()

    if not email_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found"
        )

    if email_account.provider_type != 'gmail':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint only works for Gmail accounts"
        )

    try:
        # Decrypt credentials
        encryptor = CredentialEncryptor()
        credentials = encryptor.decrypt(email_account.credentials_encrypted)

        if not credentials.get('refresh_token'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No refresh token available. Re-authorize the account."
            )

        # Refresh the token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": credentials['client_id'],
                    "client_secret": credentials['client_secret'],
                    "refresh_token": credentials['refresh_token'],
                    "grant_type": "refresh_token",
                }
            )

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to refresh token: {response.text}"
                )

            new_tokens = response.json()

            # Update credentials with new access token
            credentials['access_token'] = new_tokens['access_token']
            credentials['token_expiry'] = new_tokens.get('expires_in')

            # Encrypt and save
            email_account.credentials_encrypted = encryptor.encrypt(credentials)
            await db.commit()

            logger.info(f"Refreshed tokens for {email_account.email_address}")

            return {
                "success": True,
                "message": "Tokens refreshed successfully",
                "email_address": email_account.email_address
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh token: {str(e)}"
        )
