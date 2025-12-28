"""Utility functions and decorators for distributed tracing"""
import logging
from collections.abc import Callable
from functools import wraps

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)


def traced(operation_name=str | None, attributes=None):
    """
    Decorator to create a span for a function

    Usage:
        @traced("user_authentication")
        async def authenticate_user(username: str, password: str):
            # Function code
            pass

        @traced(attributes={"custom.attribute": "value"})
        def process_data(data: dict):
            # Function code
            pass

    Args:
        operation_name: Name of the operation (defaults to function name)
        attributes: Additional attributes to add to the span
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            span_name = operation_name or f"{func.__module__}.{func.__name__}"

            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add function arguments as attributes (be careful with sensitive data)
                if kwargs:
                    for key, value in kwargs.items():
                        if not key.startswith("_") and key not in [
                            "password",
                            "token",
                            "secret",
                        ]:
                            span.set_attribute(f"arg.{key}", str(value))

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            span_name = operation_name or f"{func.__module__}.{func.__name__}"

            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add function arguments
                if kwargs:
                    for key, value in kwargs.items():
                        if not key.startswith("_") and key not in [
                            "password",
                            "token",
                            "secret",
                        ]:
                            span.set_attribute(f"arg.{key}", str(value))

                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def add_span_attributes(**attributes):
    """
    Add attributes to the current span

    Usage:
        add_span_attributes(user_id="123", tenant_id="tenant-456")
    """
    span = trace.get_current_span()
    if span:
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_span_event(name: str, attributes: dict | None = None):
    """
    Add an event to the current span

    Usage:
        add_span_event("user_logged_in", {"method": "oauth"})
    """
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes=attributes or {})


def set_span_error(exception: Exception):
    """
    Mark the current span as error and record the exception

    Usage:
        try:
            risky_operation()
        except Exception as e:
            set_span_error(e)
            raise
    """
    span = trace.get_current_span()
    if span:
        span.set_status(Status(StatusCode.ERROR, str(exception)))
        span.record_exception(exception)


def get_trace_id() -> str | None:
    """
    Get the current trace ID

    Useful for logging correlation and error reporting

    Returns:
        Trace ID as hex string or None if no active span
    """
    span = trace.get_current_span()
    if span:
        trace_id = span.get_span_context().trace_id
        return format(trace_id, "032x")  # Convert to 32-char hex string
    return None


def get_span_id() -> str | None:
    """
    Get the current span ID

    Returns:
        Span ID as hex string or None if no active span
    """
    span = trace.get_current_span()
    if span:
        span_id = span.get_span_context().span_id
        return format(span_id, "016x")  # Convert to 16-char hex string
    return None


class TracedOperation:
    """
    Context manager for creating a traced operation

    Usage:
        with TracedOperation("complex_operation", {"custom_attr": "value"}):
            # Your code here
            pass

        async with TracedOperation("async_operation"):
            await some_async_function()
    """

    def __init__(self, operation_name: str, attributes: dict | None = None):
        self.operation_name = operation_name
        self.attributes = attributes or {}
        self.tracer = trace.get_tracer(__name__)
        self.span = None

    def __enter__(self):
        self.span = self.tracer.start_span(self.operation_name)
        assert self.span is not None
        self.span.__enter__()
        for key, value in self.attributes.items():
            self.span.set_attribute(key, value)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self.span is not None
        if exc_type is not None:
            self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self.span.record_exception(exc_val)
        else:
            self.span.set_status(Status(StatusCode.OK))
        self.span.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
