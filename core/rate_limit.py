"""Shared rate limiter instance for the application"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Single limiter instance used throughout the application
limiter = Limiter(key_func=get_remote_address)
