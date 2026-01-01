"""Email integration package"""
from src.infrastructure.external.email.protocols import (
    EmailMessage,
    EmailProviderConfig,
    IEmailProvider,
)

__all__ = ["IEmailProvider", "EmailMessage", "EmailProviderConfig"]
