"""Redis health check — PING.

Requires the ``[redis]`` extra. PING is the canonical Redis liveness
probe — a single command, no key access, succeeds in microseconds on
a warm connection. Auth failures and connection errors are reported as
distinct reasons.
"""
from __future__ import annotations

from typing import Optional

from .base import CheckFn


def redis_check(url: str, timeout: float = 5.0) -> CheckFn:
    """Return a check that opens a Redis connection and pings it.

    Args:
        url: ``redis://``, ``rediss://`` (TLS), or ``unix://`` URL. May
            embed credentials (``redis://default:password@host:port/0``).
        timeout: both socket-connect and socket-read timeout, in seconds.
            Default 5.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not url:
        raise ValueError("url is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    def check() -> tuple[str, Optional[str]]:
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError:
            return (
                "fail",
                "redis extra not installed; "
                "pip install 'modafoca-healthcheck[redis]'",
            )

        try:
            client = redis.from_url(
                url,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            pong = client.ping()
        except redis.AuthenticationError:
            return ("fail", "auth failed")
        except redis.ConnectionError as e:
            return ("fail", "connection error")
        except redis.TimeoutError:
            return ("fail", f"timeout after {timeout}s")
        except redis.RedisError as e:
            return ("fail", type(e).__name__)
        except Exception as e:
            return ("fail", type(e).__name__)

        if not pong:
            return ("fail", "PING returned falsy")
        return ("ok", None)

    return check
