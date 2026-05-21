import functools
import inspect
import json
import sqlite3
import time
import traceback
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

MAX_RESULT_SUMMARY = 500


def _summarize(value: Any) -> str:
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = repr(value)
    return s[:MAX_RESULT_SUMMARY]


def audit(conn_getter: Callable[[], sqlite3.Connection], tool_name: str) -> Callable[[F], F]:
    """Decorator that records each call to `tool_audit`. `conn_getter` is invoked per call."""

    def decorator(func: F) -> F:
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(*args, **kwargs)
            args_json = json.dumps(dict(bound.arguments), ensure_ascii=False, default=str)
            start = time.monotonic()
            error: str | None = None
            result: Any = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
                raise
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                try:
                    conn = conn_getter()
                    conn.execute(
                        "INSERT INTO tool_audit "
                        "(tool_name, arguments_json, result_summary, error, duration_ms) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (tool_name, args_json, _summarize(result) if error is None else None,
                         error, duration_ms),
                    )
                except Exception:
                    pass

        return wrapper  # type: ignore[return-value]

    return decorator
