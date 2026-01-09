"""Input sanitization utilities."""

import html
import re
from typing import Any


class InputSanitizer:
    """Sanitize user inputs to prevent XSS and injection attacks."""

    # Allowed HTML tags (empty for strict sanitization)
    ALLOWED_TAGS: list[str] = []

    # Allowed HTML attributes
    ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}

    # Regex for validating identifiers
    IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    # Regex for SQL-safe strings
    SQL_SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\s]+$")

    @classmethod
    def sanitize_html(cls, value: str) -> str:
        """Remove all HTML tags and entities."""
        if not value:
            return value

        # Remove HTML tags using regex
        cleaned = re.sub(r"<[^>]+>", "", value)

        # Escape HTML entities
        return html.escape(cleaned)

    @classmethod
    def sanitize_identifier(cls, value: str) -> str:
        """
        Sanitize identifiers (IDs, codes, etc.).

        Only allows alphanumeric characters, underscores, and hyphens.
        """
        if not value:
            return value

        if not cls.IDENTIFIER_PATTERN.match(value):
            raise ValueError(f"Invalid identifier format: {value}")

        return value

    @classmethod
    def sanitize_sql_string(cls, value: str) -> str:
        """
        Basic SQL injection prevention.

        Note: Always use parameterized queries as primary defense.
        """
        if not value:
            return value

        # Remove SQL keywords and special characters
        dangerous_patterns = [
            r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|EXECUTE)\b",
            r"[;\'\"\\]",
            r"--",
            r"/\*.*?\*/",
        ]

        sanitized = value
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        return sanitized.strip()

    @classmethod
    def sanitize_dict(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively sanitize dictionary values."""
        sanitized = {}

        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = cls.sanitize_html(value)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = cls.sanitize_list(value)
            else:
                sanitized[key] = value

        return sanitized

    @classmethod
    def sanitize_list(cls, data: list[Any]) -> list[Any]:
        """Recursively sanitize list values."""
        sanitized = []

        for item in data:
            if isinstance(item, str):
                sanitized.append(cls.sanitize_html(item))
            elif isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item))
            else:
                sanitized.append(item)

        return sanitized


# Convenience functions
def sanitize_input(value: str | dict | list) -> str | dict | list:
    """Sanitize any input value."""
    if isinstance(value, str):
        return InputSanitizer.sanitize_html(value)
    elif isinstance(value, dict):
        return InputSanitizer.sanitize_dict(value)
    elif isinstance(value, list):
        return InputSanitizer.sanitize_list(value)
    return value


def validate_identifier(value: str) -> str:
    """Validate and return identifier."""
    return InputSanitizer.sanitize_identifier(value)
