"""
Request context management using contextvars.

Provides thread-safe, async-safe storage for request-scoped data
like the current user. Similar to Flask's `g` or Django's `request.user`.

Usage:
    # In middleware or dependency injection:
    set_current_user(user_id="user123", actor_type=ActorType.USER)

    # In any code that needs the current user:
    user_id = get_current_actor_id()  # Returns "user123" or None
    actor_type = get_current_actor_type()  # Returns ActorType.USER

    # Context is automatically reset per request due to contextvars
"""

from contextvars import ContextVar
from dataclasses import dataclass

from src.shared.enums import ActorType

# Context variables for request-scoped user data
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
_current_actor_type: ContextVar[ActorType] = ContextVar("current_actor_type", default=ActorType.SYSTEM)
_current_ip_address: ContextVar[str | None] = ContextVar("current_ip_address", default=None)
_current_user_agent: ContextVar[str | None] = ContextVar("current_user_agent", default=None)


@dataclass(frozen=True)
class ActorContext:
    """Immutable snapshot of the current actor context."""

    user_id: str | None
    actor_type: ActorType
    ip_address: str | None = None
    user_agent: str | None = None


def set_current_user(
    user_id: str | None,
    actor_type: ActorType = ActorType.USER,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """
    Set the current user context for this request.

    Call this in middleware or dependency injection after authentication.
    The context is automatically scoped to the current async task/thread.
    """
    _current_user_id.set(user_id)
    _current_actor_type.set(actor_type)
    _current_ip_address.set(ip_address)
    _current_user_agent.set(user_agent)


def clear_current_user() -> None:
    """Clear the current user context."""
    _current_user_id.set(None)
    _current_actor_type.set(ActorType.SYSTEM)
    _current_ip_address.set(None)
    _current_user_agent.set(None)


def get_current_actor_id() -> str | None:
    """Get the current user ID, or None if not authenticated."""
    return _current_user_id.get()


def get_current_actor_type() -> ActorType:
    """Get the current actor type (defaults to SYSTEM if not set)."""
    return _current_actor_type.get()


def get_current_ip_address() -> str | None:
    """Get the current request IP address."""
    return _current_ip_address.get()


def get_current_user_agent() -> str | None:
    """Get the current request user agent."""
    return _current_user_agent.get()


def get_actor_context() -> ActorContext:
    """Get a snapshot of the current actor context."""
    return ActorContext(
        user_id=_current_user_id.get(),
        actor_type=_current_actor_type.get(),
        ip_address=_current_ip_address.get(),
        user_agent=_current_user_agent.get(),
    )
