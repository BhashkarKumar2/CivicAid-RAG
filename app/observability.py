import logging
import os
import time
import uuid
from contextvars import ContextVar
from contextlib import contextmanager, nullcontext
from typing import Any

from langfuse.types import TraceContext


_active_trace_id: ContextVar[str | None] = ContextVar("civicaid_langfuse_trace_id", default=None)
_active_observation_stack: ContextVar[tuple[str, ...]] = ContextVar("civicaid_langfuse_observation_stack", default=())
_active_execution_log: ContextVar[list[dict[str, Any]] | None] = ContextVar("civicaid_execution_log", default=None)
_active_log_stack: ContextVar[tuple[dict[str, Any], ...]] = ContextVar("civicaid_execution_log_stack", default=())
logger = logging.getLogger(__name__)


def langfuse_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        and os.getenv("LANGFUSE_SECRET_KEY")
        and os.getenv("LANGFUSE_BASE_URL")
    )


def profile_for_trace(profile: Any) -> dict[str, Any]:
    data = profile.model_dump() if hasattr(profile, "model_dump") else dict(profile or {})
    return {key: value for key, value in data.items() if value is not None}


def _trace_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _trace_payload(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _trace_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_trace_payload(item) for item in value]
    if isinstance(value, set):
        return sorted(_trace_payload(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _merge_trace_value(existing: Any, new_value: Any) -> Any:
    if isinstance(existing, dict) and isinstance(new_value, dict):
        return {**existing, **new_value}
    return new_value


class LangfuseTracer:
    def __init__(self):
        self.enabled = langfuse_enabled()
        self._client = None
        if self.enabled:
            try:
                from langfuse import get_client

                self._client = get_client()
            except Exception:
                self.enabled = False

    @contextmanager
    def observation(self, name: str, as_type: str = "span", **kwargs):
        if not self.enabled or not self._client:
            yield None
            return

        if _active_trace_id.get() is not None:
            with self._collapsed_observation(name, as_type, **kwargs) as observation:
                yield observation
            return

        trace_token = None
        stack_token = None
        log_token = None
        trace_context = kwargs.pop("trace_context", None)
        active_trace_id = _active_trace_id.get()
        observation_stack = _active_observation_stack.get()

        if trace_context is None:
            if active_trace_id is None:
                active_trace_id = uuid.uuid4().hex
                trace_token = _active_trace_id.set(active_trace_id)
                log_token = _active_execution_log.set([])

            trace_context = TraceContext(trace_id=active_trace_id)
            if observation_stack:
                trace_context["parent_span_id"] = observation_stack[-1]
        elif trace_context.get("trace_id") and active_trace_id is None:
            trace_token = _active_trace_id.set(trace_context["trace_id"])
            log_token = _active_execution_log.set([])

        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type=as_type,
                trace_context=trace_context,
                **kwargs,
            ) as observation:
                observation_id = getattr(observation, "id", None)
                if observation_id:
                    stack_token = _active_observation_stack.set((*observation_stack, observation_id))
                yield observation
        except TypeError:
            with self._client.start_as_current_observation(
                name=name,
                as_type=as_type,
                trace_context=trace_context,
            ) as observation:
                observation_id = getattr(observation, "id", None)
                if observation_id:
                    stack_token = _active_observation_stack.set((*observation_stack, observation_id))
                yield observation
        except Exception:
            with nullcontext() as empty:
                yield empty
        finally:
            if stack_token is not None:
                _active_observation_stack.reset(stack_token)
            if log_token is not None:
                _active_execution_log.reset(log_token)
            if trace_token is not None:
                _active_trace_id.reset(trace_token)

    @contextmanager
    def _collapsed_observation(self, name: str, as_type: str = "span", **kwargs):
        execution_log = _active_execution_log.get()
        if execution_log is None:
            yield None
            return

        log_stack = _active_log_stack.get()
        entry: dict[str, Any] = {
            "sequence": len(execution_log) + 1,
            "name": name,
            "type": as_type,
            "status": "started",
        }
        if log_stack:
            entry["parent"] = log_stack[-1]["name"]
        for field in ("input", "metadata", "model"):
            if field in kwargs:
                entry[field] = _trace_payload(kwargs[field])

        started_at = time.perf_counter()
        execution_log.append(entry)
        stack_token = _active_log_stack.set((*log_stack, entry))
        try:
            yield entry
            entry["status"] = "completed"
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            entry["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
            _active_log_stack.reset(stack_token)

    def update_current(self, **kwargs):
        if not self.enabled or not self._client:
            return
        log_stack = _active_log_stack.get()
        if log_stack:
            current_entry = log_stack[-1]
            for key, value in kwargs.items():
                payload = _trace_payload(value)
                current_entry[key] = _merge_trace_value(current_entry.get(key), payload)
            return
        try:
            self._client.update_current_span(**kwargs)
        except Exception as exc:
            logger.debug("Langfuse span update failed: %s", exc)

    def execution_log(self) -> list[dict[str, Any]]:
        return _trace_payload(_active_execution_log.get() or [])

    def trace_url(self) -> str | None:
        if not self.enabled or not self._client:
            return None
        try:
            return self._client.get_trace_url(trace_id=_active_trace_id.get())
        except Exception:
            return None

    def flush(self):
        if not self.enabled or not self._client:
            return
        try:
            self._client.flush()
        except Exception as exc:
            logger.debug("Langfuse flush failed: %s", exc)


tracer = LangfuseTracer()
