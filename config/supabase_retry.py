"""
Supabase Retry Mixin — Production-grade retry logic for all Supabase operations.

P2 FIX #12: All Supabase calls previously used bare try/except with no retry logic.
A temporary Supabase outage would silently drop ALL events. This module provides
a decorator and mixin class for exponential backoff retries.
"""

import functools
import logging
import time
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Maximum retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.5   # seconds
DEFAULT_MAX_DELAY = 5.0    # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


def with_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retryable_exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator that retries a function with exponential backoff.
    
    Usage:
        @with_retry(max_retries=3, base_delay=0.5)
        def insert_record(self, data) -> Any:
            return self.client.table('records').insert(data).execute()
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay cap (seconds)
        backoff_factor: Multiplier for delay after each retry
        retryable_exceptions: Tuple of exception types to retry on
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = base_delay
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"[Retry] {func.__qualname__} failed after {max_retries} attempts: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"[Retry] {func.__qualname__} attempt {attempt}/{max_retries} "
                        f"failed: {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            raise last_exception  # Should never reach here
        return wrapper
    return decorator


class SupabaseRetryMixin:
    """
    Mixin class that adds retry-wrapped Supabase operations.
    
    Classes that inherit from this mixin get self._retry_insert(),
    self._retry_upsert(), self._retry_update(), and self._retry_select()
    methods that automatically retry on failure.
    
    Requires: self.client (Supabase client instance)
    """
    
    def _retry_insert(self, table: str, data: dict, max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
        """Insert with retry."""
        return self._retry_operation(
            lambda: self.client.table(table).insert(data).execute(),
            f"INSERT into {table}",
            max_retries,
        )
    
    def _retry_upsert(self, table: str, data: dict, on_conflict: str = '', max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
        """Upsert with retry."""
        builder = self.client.table(table).upsert(data)
        if on_conflict:
            builder = self.client.table(table).upsert(data, on_conflict=on_conflict)
        return self._retry_operation(
            lambda: builder.execute(),
            f"UPSERT into {table}",
            max_retries,
        )
    
    def _retry_update(self, table: str, data: dict, filters: dict, max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
        """Update with retry."""
        def do_update() -> Any:
            query = self.client.table(table).update(data)
            for col, val in filters.items():
                query = query.eq(col, val)
            return query.execute()
        
        return self._retry_operation(do_update, f"UPDATE {table}", max_retries)
    
    def _retry_select(self, table: str, columns: str = '*', filters: dict = None, max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
        """Select with retry."""
        def do_select() -> Any:
            query = self.client.table(table).select(columns)
            if filters:
                for col, val in filters.items():
                    query = query.eq(col, val)
            return query.execute()
        
        return self._retry_operation(do_select, f"SELECT from {table}", max_retries)
    
    def _retry_operation(self, operation: Callable, description: str, max_retries: int) -> Any:
        """Execute a Supabase operation with exponential backoff retry."""
        last_exception = None
        delay = DEFAULT_BASE_DELAY
        
        for attempt in range(1, max_retries + 1):
            try:
                return operation()
            except Exception as e:
                last_exception = e
                if attempt == max_retries:
                    logger.error(f"[Retry] {description} failed after {max_retries} attempts: {e}")
                    raise
                
                logger.warning(
                    f"[Retry] {description} attempt {attempt}/{max_retries} "
                    f"failed: {e}. Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay = min(delay * DEFAULT_BACKOFF_FACTOR, DEFAULT_MAX_DELAY)
        
        raise last_exception
