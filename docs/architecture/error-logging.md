# Error Logging Architecture

> Last updated: 2026-07-07.
>
> Source of truth for the unified error / log pipeline that covers both the
> Python FastAPI backend and the React front end. If the implementation
> drifts from this doc, the code wins and a follow-up PR should reconcile.

## Goals

1. **Hierarchical categorization.** Every error record carries:
   - `error_code` — machine-readable identifier (e.g. `validation_error`)
   - `severity` — five-level ladder (`debug` → `info` → `warning` → `error`
     → `fatal`) mirroring Python `logging` levels
   - `category` — module/layer tag (e.g. `routers.library`,
     `pipeline.runner`)
   - `context` — arbitrary JSON-serializable dict
2. **Inspectable at runtime.** A 500-deep ring buffer keeps the most recent
   errors in process memory, exposed through `/api/v1/diagnostics/*`. Same
   buffer also receives front-end caught errors so operators see a unified
   timeline.
3. **Structured log file.** When `setup_logging(json_mode=True)` is enabled,
   the rotating log file becomes single-line JSON; default console output
   remains human-readable.

## Layer diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (React)                                                   │
│  ┌─────────────────────┐    ┌──────────────────────────────────┐    │
│  │  AppError + Severity │◀──▶│  httpFetch → JSON body surfaced  │    │
│  └─────────────────────┘    └──────────────────────────────────┘    │
│           ▲                                                            │
│           │ ErrorBoundary.componentDidCatch                            │
│           ▼                                                            │
│  ┌─────────────────────┐                                              │
│  │  useErrorReport     │                                              │
│  │   (debounce 1.5s,   │                                              │
│  │    keepalive POST)  │                                              │
│  └──────────┬──────────┘                                              │
└─────────────┼─────────────────────────────────────────────────────────┘
              │ HTTP POST /api/v1/diagnostics/errors
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI main app (src/mbforge/app.py)                              │
│                                                                     │
│   _request_path_middleware ─── sets ContextVar request_path         │
│                                                                     │
│   ┌────────────────────────┐    ┌──────────────────────────────┐     │
│   │  _mbforge_error_handler │───▶│ DiagnosticRingHandler.push  │     │
│   │  (MBForgeError)         │    │ + logger.log with extras     │     │
│   └────────────────────────┘    └──────────────────────────────┘     │
│                                                                     │
│   ┌────────────────────────┐    ┌──────────────────────────────┐     │
│   │  _unhandled_error_handler│───▶│  same ring buffer + logger  │     │
│   │  (Exception catch-all)  │    │  + severity=fatal            │     │
│   └────────────────────────┘    └──────────────────────────────┘     │
│                                                                     │
│   /api/v1/diagnostics/{errors,errors/{id},stats}  ←── GET           │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  In-process state                                                   │
│                                                                     │
│   root_logger ─▶ StreamHandler  (human console)                     │
│             ─▶ RotatingFileHandler (file, optional JSON)            │
│             ─▶ DiagnosticRingHandler (deque maxlen=500)             │
│                                                                     │
│   threading.Lock around deque.append / list-snapshot                 │
└─────────────────────────────────────────────────────────────────────┘
```

## JSON schema (file log + ring buffer + diagnostics endpoints)

```json
{
  "ts": "2026-07-07T12:34:56.789Z",
  "level": "ERROR",
  "logger": "mbforge.app.exception_handler",
  "pid": 1234,
  "tid": "MainThread",
  "message": "MBForgeError on /api/v1/library/open: root path is required [validation_error/mbforge.utils.helpers]",
  "exception": "Traceback (most recent call last):\n  ...",
  "error_code": "validation_error",
  "status_code": 422,
  "severity": "warning",
  "category": "mbforge.utils.helpers",
  "context": { "field": "root" },
  "request_path": "/api/v1/library/open",
  "seq": 42
}
```

The `seq` field is the ring buffer's monotonic sequence number, used by
clients to do `?since=<seq>` incremental pagination.

## API: `/api/v1/diagnostics/*`

| Endpoint | Method | Purpose |
|---|---|---|
| `/errors` | GET | List recent records. Query: `since`, `level`, `category`, `error_code`, `limit` (≤ 1000). |
| `/errors/{seq_id}` | GET | Look up a single record. Returns `{ "success": false, ... }` when missing. |
| `/stats` | GET | Aggregate counts: by_level / by_category / by_error_code / total / capacity / last_seen. |
| `/errors` | POST | Front-end error ingestion. Body: `{ "errors": ClientErrorItem[] }`. Returns 204. |

## Severity mapping

| HTTP status | Severity (default) |
|---|---|
| 400, 401, 403, 409, 422 | `warning` |
| 404 | `info` |
| 500, 502, 503, 504 | `error` |
| 5xx other / unhandled | `fatal` |

Override by passing `severity=` to `MBForgeError(...)`. The front end
echoes the same mapping via `severityFromHttpStatus(status)` for parity.

## Mounted sub-app caveat

`app.mount("/api/v1/models", model_server)` is a separate Starlette graph.
Exception handlers in `server.py:117,127` cover only this sub-app; the
handlers defined in `app.py` cover every `include_router(...)` route
(17/18 production routers). Keep both sets — they don't conflict, but they
are not interchangeable.

## Configuration knobs

| Knob | Source | Default | Notes |
|---|---|---|---|
| Log level | `MBFORGE_LOG_LEVEL` env (read by `get_logger`) | `INFO` | Not a global-config field; runtime override only. |
| JSON file output | `setup_logging(json_mode=True)` | `False` | Called by app factory when an env flag requests it (future). |
| Ring buffer cap | `_RING_CAPACITY` in `utils/logger.py` | `500` | Hard-coded; no env knob. |
| Front-end flush delay | `FLUSH_DELAY_MS` in `useErrorReport.ts` | `1500` | Coalesces burst errors into one POST. |

## When to extend

- **Add a new MBForgeError subclass** → the subclass inherits the
  `severity`/`category`/`context` defaults. Override category by passing
  `category=` explicitly when raising.
- **Add a new ErrorCode** → mirror it in `backendCodeToErrorCode` so the
  front end maps backend codes correctly.
- **Add a new diagnostics endpoint** → new route in
  `routers/diagnostics.py`, registered in `app.py:create_app()`. The
  `push_diagnostic` helper is your friend.
