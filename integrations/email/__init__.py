"""Email integration package"""
from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig

__all__ = ['IEmailProvider', 'EmailMessage', 'EmailProviderConfig']
