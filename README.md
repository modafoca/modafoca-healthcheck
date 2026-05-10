# modafoca-healthcheck

Standardized `/health` endpoint library for MODAFOCA services. Declare your dependencies, expose a uniform JSON shape, let Mission Control read the truth.

**Why:** Liveness ≠ readiness. A service is only healthy if its critical dependencies are healthy. Returning 200 from `/health` while Supabase is paused is lying-by-omission monitoring. This library probes the real deps in parallel and returns 503 the moment any of them fails — Mission Control's pulse picks that up automatically.

## Install

```bash
# FastAPI service:
pip install "git+https://github.com/modafoca/modafoca-healthcheck.git@v0.1.0#egg=modafoca-healthcheck[fastapi]"
```

> v0.1.0 ships `http_check` (generic) + the FastAPI router.
> v0.2.0 will add Supabase, Pinecone, Anthropic, Postgres, Redis checks behind extras.

## Quickstart (FastAPI)

```python
from fastapi import FastAPI
from modafoca_healthcheck import HealthCheck
from modafoca_healthcheck.checks import http_check
from modafoca_healthcheck.fastapi import register_health_router

app = FastAPI()

health = HealthCheck(service="my-service", version="1.0.0", cache_ttl=30)
health.add("upstream-api", http_check("https://upstream.example.com/ping"))

register_health_router(app, health)
```

`GET /health` now returns:

```json
{
  "status": "ok",
  "service": "my-service",
  "version": "1.0.0",
  "timestamp": "2026-05-10T15:42:11Z",
  "duration_ms": 187,
  "checks": {
    "upstream-api": {"status": "ok", "duration_ms": 102}
  },
  "failed": []
}
```

If anything fails:

```json
{
  "status": "degraded",
  "service": "my-service",
  "version": "1.0.0",
  "timestamp": "2026-05-10T15:42:11Z",
  "duration_ms": 5187,
  "checks": {
    "upstream-api": {"status": "fail", "duration_ms": 5000, "error": "timeout after 5s"}
  },
  "failed": ["upstream-api"]
}
```

…with HTTP **503**.

Bypass the cache for a one-off deep probe:

```bash
curl https://my-service.example.com/health?fresh=1
```

## API

### `HealthCheck(service, version="unknown", cache_ttl=0)`

Registry + parallel runner.

- `service`: name reported in the JSON `service` field.
- `version`: free-form version string. Convention: read from `os.getenv("SERVICE_VERSION")` so deploys self-identify.
- `cache_ttl`: seconds. With `> 0`, repeated calls within TTL return the cached payload. Recommended `30` for production endpoints under load.

### `health.add(name, check_fn)`

Register a check. `name` becomes the JSON key in `checks`. `check_fn` is a callable returning `(status: str, error: Optional[str])` where status is `"ok"` or `"fail"`. Duplicates raise. Returns `self` for chaining.

### `health.run(fresh=False)`

Execute all registered checks in parallel and return the standard payload dict. With cache enabled and `fresh=False`, may return a cached payload. Used internally by the router.

### `register_health_router(app, health, path="/health")`

Attach the standard `/health` route to a FastAPI app. Returns 200/503 based on `status`. Handles `?fresh=1` to bypass cache.

## Available checks

| Check | Probes | Args | Extra |
|---|---|---|---|
| `http_check` | Generic HTTP GET, expects 2xx/3xx | `url`, `timeout`, `expected_status_codes`, `method` | (none) |

v0.2.0 will add: `supabase_check`, `pinecone_check`, `anthropic_check`, `postgres_check`, `redis_check`.

## Writing your own check

A check is a *factory* — call it with config, get back a no-arg callable that returns `(status, error)`:

```python
def my_check(api_key: str, timeout: float = 5.0):
    def check():
        try:
            r = requests.get("https://upstream.example/ping",
                             headers={"X-API-Key": api_key},
                             timeout=timeout)
            if r.status_code == 200:
                return ("ok", None)
            return ("fail", f"HTTP {r.status_code}")
        except requests.Timeout:
            return ("fail", f"timeout after {timeout}s")
        except Exception as e:
            return ("fail", type(e).__name__)
    return check

health.add("my-thing", my_check(api_key=...))
```

Three rules:

1. **Set the timeout in the underlying client**, not at the executor level. Stuck threads on hung sockets are bad news.
2. **Never raise.** If something unexpected happens, catch it and return `("fail", reason)`.
3. **Return short reasons.** "timeout after 5s", "HTTP 503", "auth error" — not stack traces. The library will sanitize and truncate, but be a good citizen.

## Design notes

- **Parallel by default.** N checks → min(N, 8) workers. 5 dep checks complete in ~max(latency), not ~sum(latency).
- **Fail-soft.** A raising check is captured as a fail. Siblings still run. Endpoint never crashes.
- **Cache to protect dependencies.** Without TTL, `/health` becomes a denial-of-service vector against your own deps — every load-balancer probe spawns N upstream calls.
- **Sanitized errors.** Strips Bearer tokens, `sk-*` keys, GitHub PATs, and DSN-with-credentials before returning. Truncates at 200 chars.
- **Forward-compat with Mission Control.** Mission Control's pulse classifies dots from HTTP status. 200 = green, 503 = red. The richer JSON inside is for richer tooltips later — works today regardless.

## Development

```bash
git clone https://github.com/modafoca/modafoca-healthcheck.git
cd modafoca-healthcheck
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest
```

## License

MIT — see `LICENSE`.
