"""Built-in checks for common dependencies.

Each check is a *factory* that returns a parameterless callable conforming
to the CheckFn protocol — ``() -> (status, error)``. Pass it to
``HealthCheck.add(name, factory(...))``.

In v0.1.0 only ``http_check`` ships. v0.2.0 adds Supabase / Pinecone /
Anthropic / Postgres / Redis as optional extras.
"""
from .base import CheckFn
from .http import http_check

__all__ = ["CheckFn", "http_check"]
