"""Pinecone health check — describe index stats.

Uses the modern (v3+) Pinecone SDK — same class shape as RAYO uses
(``pinecone>=5.0``). The old ``pinecone-client`` package and its
``pinecone.init(...)`` style is NOT supported by this check.

``describe_index_stats()`` validates:

* the API key is valid
* the named index exists and is reachable
* Pinecone's regional control plane is up

Requires the ``[pinecone]`` extra. Import is lazy so consumers can
import ``pinecone_check`` without installing the SDK — they only hit
the ImportError when they actually call the factory's returned check.
"""
from __future__ import annotations

from typing import Optional

from .base import CheckFn


def pinecone_check(api_key: str, index: str, timeout: float = 5.0) -> CheckFn:
    """Return a check that probes a Pinecone index.

    Args:
        api_key: Pinecone API key.
        index: name of the index to probe (must already exist).
        timeout: per-request seconds. The SDK has its own default; this
            argument is forwarded best-effort but Pinecone may not honor
            it precisely.

    Returns:
        A no-arg callable returning (status, error).
    """
    if not api_key:
        raise ValueError("api_key is required")
    if not index:
        raise ValueError("index is required")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    def check() -> tuple[str, Optional[str]]:
        try:
            from pinecone import Pinecone  # type: ignore[import-not-found]
        except ImportError:
            return (
                "fail",
                "pinecone extra not installed; "
                "pip install 'modafoca-healthcheck[pinecone]'",
            )

        try:
            pc = Pinecone(api_key=api_key)
            idx = pc.Index(index)
            idx.describe_index_stats()
        except Exception as e:
            # Pinecone surfaces many exception types depending on the SDK
            # version: NotFoundException, PineconeApiException,
            # ConnectionError, etc. Normalize to a short reason.
            name = type(e).__name__
            msg = str(e)[:80]
            return ("fail", f"{name}: {msg}" if msg else name)
        return ("ok", None)

    return check
