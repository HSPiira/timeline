"""Email provider factory for instantiating providers"""
from typing import ClassVar 
from integrations.email.protocols import IEmailProvider, EmailProviderConfig
from integrations.email.providers.gmail_provider import GmailProvider
from integrations.email.providers.imap_provider import IMAPProvider
from integrations.email.providers.outlook_provider import OutlookProvider
from core.logging import get_logger

logger = get_logger(__name__)


class EmailProviderFactory:
    """Factory for creating email provider instances"""

    _providers: ClassVar[dict[str, type[IEmailProvider]]] = {
        'gmail': GmailProvider,
        'outlook': OutlookProvider,
        'imap': IMAPProvider,
        'icloud': IMAPProvider,  # iCloud uses IMAP
        'yahoo': IMAPProvider,   # Yahoo uses IMAP
    }

    @classmethod
    def create_provider(cls, config: EmailProviderConfig) -> IEmailProvider:
        """
        Create provider instance based on config.

        Args:
            config: Email provider configuration

        Returns:
            Provider instance (GmailProvider, IMAPProvider, OutlookProvider)

        Raises:
            ValueError: If provider_type is not supported
        """
        provider_type = config.provider_type.lower()
        provider_class = cls._providers.get(provider_type)

        if not provider_class:
            raise ValueError(
                f"Unsupported provider: {config.provider_type}. "
                f"Supported: {list(cls._providers.keys())}"
            )

        logger.info(f"Creating {provider_class.__name__} for {config.email_address}")
        return provider_class()

    @classmethod
    def register_provider(cls, provider_type: str, provider_class: type[IEmailProvider]) -> None:
        """
        Register a custom email provider.

        Args:
            provider_type: Provider type identifier (e.g., 'custom_imap')
            provider_class: Provider class implementing IEmailProvider
        """
        cls._providers[provider_type.lower()] = provider_class
        logger.info(f"Registered custom provider: {provider_type}")

    @classmethod
    def list_supported_providers(cls) -> list[str]:
        """Get list of supported provider types"""
        return list(cls._providers.keys())
