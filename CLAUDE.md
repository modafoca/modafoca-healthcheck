# CLAUDE.md — modafoca-healthcheck

A standard health-check library for MODAFOCA services. Drop into any
project, register your dependencies, expose a uniform `/health` endpoint
that Mission Control can read.

## Architecture

- `modafoca_healthcheck/core.py` — `HealthCheck`: registry + parallel runner + cache + sanitizer
- `modafoca_healthcheck/checks/` — one module per dependency type, each exporting a factory function `name_check(...)` that returns a no-arg callable
- `modafoca_healthcheck/fastapi.py` — drop-in FastAPI router

## Standard response shape

See [README.md](README.md). This shape is a contract with Mission Control's `pulse.py`. **Do not change it without updating mission-control in lockstep.**

## When adding a new check type

1. Create `modafoca_healthcheck/checks/{name}.py` exporting a factory `{name}_check(...)`
2. Factory returns a callable `() -> (status, error)` that probes the service
3. Add the dep to `pyproject.toml` as an optional extra (`[project.optional-dependencies]`)
4. Add tests with mocked responses under `tests/test_checks/test_{name}.py`
5. Update README.md's check table
6. Bump version in `pyproject.toml` AND `modafoca_healthcheck/__init__.py.__version__`
7. Tag release after merge

## DON'T

- **Don't break the standard JSON shape** — Mission Control depends on it
- **Don't make checks raise exceptions** — always return `("fail", reason)`. The library catches and normalizes anyway, but well-behaved checks return cleanly.
- **Don't add real API calls to tests** — mock with `responses` (HTTP) or library-specific test doubles
- **Don't enforce timeouts at the executor level** — every check sets its own via the underlying client (`requests.get(timeout=5)`, `psycopg.connect(connect_timeout=5)`, etc.). Stuck threads on hung sockets are bad news.
- **Don't push to main.** Use PRs.

## Conventions

- Python 3.11+
- `requests` is the only mandatory dependency; per-check libs are extras
- Tag releases as `vMAJOR.MINOR.PATCH`. Consumers pin via `git+https://...@vX.Y.Z`.

## Why this lib exists

Mission Control reports services as healthy as long as their HTTP root returns 2xx/3xx. That's lying-by-omission monitoring — the day Supabase paused, RAYO showed green while the actual product was broken. This library fixes that by probing real dependencies and returning 503 the moment any of them fails.

ADR (when written): `decisions/records/2026-05-10-healthcheck-library.md` in modafoca-lab.
