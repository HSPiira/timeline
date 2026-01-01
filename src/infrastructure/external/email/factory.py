"""Email provider factory for instantiating providers"""

from typing import ClassVar

from src.infrastructure.external.email.protocols import (
    EmailProviderConfig,
    IEmailProvider,
)
from src.infrastructure.external.email.providers import (
    GmailProvider,
    IMAPProvider,
    OutlookProvider
)
from src.shared.telemetry.logging import get_logger

logger = get_logger(__name__)


class EmailProviderFactory:
    """Factory for creating email provider instances"""

    _providers: ClassVar[dict[str, type[IEmailProvider]]] = {
        "gmail": GmailProvider,
        "outlook": OutlookProvider,
        "imap": IMAPProvider,
        "icloud": IMAPProvider,  # iCloud uses IMAP
        "yahoo": IMAPProvider,  # Yahoo uses IMAP
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
                "Unsupported provider: %s. Supported: %s",
                config.provider_type,
                list(cls._providers.keys())
            )

        logger.info("Creating %s for %s", provider_class.__name__, config.email_address)
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
        logger.info("Registered custom provider: %s", provider_type)

    @classmethod
    def list_supported_providers(cls) -> list[str]:
        """Get list of supported provider types"""
        return list(cls._providers.keys())
