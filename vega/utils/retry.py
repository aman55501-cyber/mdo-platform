"""Async retry decorator with exponential backoff."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, TypeVar

from ..utils.logging import get_logger

F = TypeVar("F", bound=Callable[..., Any])
log = get_logger("retry")


def async_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = backoff_base * (2 ** (attempt - 1))
                    log.warning(
                        "retry_attempt",
                        func=func.__name__,
                        attempt=attempt,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
