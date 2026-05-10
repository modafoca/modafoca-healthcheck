"""HealthCheck — registry, parallel runner, cache, sanitizer.

Designed to be the single building block any MODAFOCA service uses. Three
moves: instantiate, register checks, expose via the framework adapter.

    health = HealthCheck(service="rayo", version="1.4.2", cache_ttl=30)
    health.add("supabase", supabase_check(url=..., key=...))
    health.add("pinecone", pinecone_check(api_key=..., index=...))
    register_health_router(app, health)  # FastAPI

Notes on design choices:

* **Parallel by default.** ThreadPoolExecutor with workers = min(N, 8).
  Each check should set its own timeout via the underlying client (e.g.
  requests.get(timeout=5)) — the pool does NOT enforce a wall-clock
  timeout, because doing so leaves stuck threads behind on hung sockets.
* **Fail-soft.** A check that raises is captured as ("fail", error). It
  never crashes the endpoint or its sibling checks.
* **Cached results.** Production /health endpoints get hammered by load
  balancers and uptime monitors. With cache_ttl > 0, run() returns the
  most recent payload if it's younger than TTL. Bypass with fresh=True
  (the FastAPI router maps ?fresh=1 to this).
* **Sanitized errors.** Exception messages can leak credentials. The
  _sanitize() helper redacts known patterns (Bearer tokens, sk-* keys,
  DSN-with-password URLs, GitHub PATs) and truncates over-long messages.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

# A check function returns (status, error). status is "ok" or "fail";
# error is None when ok, a short reason string when fail.
CheckFn = Callable[[], Tuple[str, Optional[str]]]

_MAX_ERROR_LEN = 200
_REDACT = "[REDACTED]"

# Patterns that suggest sensitive data — redact before returning.
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),         # Anthropic / OpenAI
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),     # Anthropic explicit
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),           # GitHub classic PAT
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),   # GitHub fine-grained
    re.compile(r"eyJ[A-Za-z0-9._\-]{20,}"),        # JWT-shaped tokens
    re.compile(r"://[^:@/\s]+:[^@/\s]+@"),         # any URL with user:pass@
]


def _now_iso() -> str:
    """UTC ISO-8601 timestamp with 'Z' suffix — same shape mission-control writes."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitize(message: Optional[str]) -> Optional[str]:
    """Redact credential-looking patterns and truncate over-long error strings.

    Conservative: applies known patterns only. Does not blanket-redact
    long base64 (would catch innocuous payloads).
    """
    if not message:
        return message
    redacted = message
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(_REDACT, redacted)
    if len(redacted) > _MAX_ERROR_LEN:
        redacted = redacted[: _MAX_ERROR_LEN - 3] + "..."
    return redacted


class HealthCheck:
    """Registry + runner for one service's dependency checks.

    Attributes are public-readable; mutating them after `add()` calls is
    not supported (would race with concurrent run()).
    """

    def __init__(
        self,
        service: str,
        version: str = "unknown",
        cache_ttl: float = 0,
    ) -> None:
        if not service:
            raise ValueError("service name is required")
        if cache_ttl < 0:
            raise ValueError("cache_ttl must be >= 0")
        self.service = service
        self.version = version
        self.cache_ttl = cache_ttl
        self._checks: dict[str, CheckFn] = {}
        self._cached_payload: Optional[dict] = None
        self._cached_at: float = 0.0
        self._lock = threading.Lock()

    def add(self, name: str, check: CheckFn) -> "HealthCheck":
        """Register a check. Returns self for chaining."""
        if not name:
            raise ValueError("check name is required")
        if name in self._checks:
            raise ValueError(f"check {name!r} already registered")
        self._checks[name] = check
        return self

    def run(self, fresh: bool = False) -> dict:
        """Execute all registered checks in parallel; return the standard payload.

        With cache_ttl > 0, repeated calls within the TTL return the cached
        payload. Pass fresh=True to bypass the cache (e.g. for ?fresh=1).
        """
        if not fresh and self.cache_ttl > 0:
            with self._lock:
                if (
                    self._cached_payload is not None
                    and (time.monotonic() - self._cached_at) < self.cache_ttl
                ):
                    return self._cached_payload

        started = time.monotonic()
        results: dict[str, dict] = {}

        if self._checks:
            workers = min(len(self._checks), 8)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._safe_run_one, name, fn): name
                    for name, fn in self._checks.items()
                }
                for future in as_completed(futures):
                    name = futures[future]
                    results[name] = future.result()

        failed = [name for name, r in results.items() if r["status"] != "ok"]
        duration_ms = int((time.monotonic() - started) * 1000)

        payload = {
            "status": "ok" if not failed else "degraded",
            "service": self.service,
            "version": self.version,
            "timestamp": _now_iso(),
            "duration_ms": duration_ms,
            "checks": results,
            "failed": failed,
        }

        with self._lock:
            self._cached_payload = payload
            self._cached_at = time.monotonic()
        return payload

    @staticmethod
    def _safe_run_one(name: str, fn: CheckFn) -> dict:
        """Wrap a single check: time it, catch anything, normalize the shape."""
        started = time.monotonic()
        try:
            result = fn()
        except Exception as e:
            duration_ms = int((time.monotonic() - started) * 1000)
            return {
                "status": "fail",
                "duration_ms": duration_ms,
                "error": _sanitize(f"{type(e).__name__}: {e}"),
            }

        duration_ms = int((time.monotonic() - started) * 1000)

        # Validate the contract: must be (status, error).
        if (
            not isinstance(result, tuple)
            or len(result) != 2
            or result[0] not in ("ok", "fail")
        ):
            return {
                "status": "fail",
                "duration_ms": duration_ms,
                "error": f"check {name!r} returned malformed result; expected (status, error) tuple",
            }

        status, error = result
        entry: dict = {"status": status, "duration_ms": duration_ms}
        if status != "ok" and error:
            entry["error"] = _sanitize(error)
        return entry
