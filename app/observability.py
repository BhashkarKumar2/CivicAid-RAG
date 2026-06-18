import os
import uuid
from contextvars import ContextVar
from contextlib import contextmanager, nullcontext
from typing import Any

from langfuse.types import TraceContext


_active_trace_id: ContextVar[str | None] = ContextVar("civicaid_langfuse_trace_id", default=None)
_active_observation_stack: ContextVar[tuple[str, ...]] = ContextVar("civicaid_langfuse_observation_stack", default=())


def langfuse_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        and os.getenv("LANGFUSE_SECRET_KEY")
        and os.getenv("LANGFUSE_BASE_URL")
    )


def profile_for_trace(profile: Any) -> dict[str, Any]:
    data = profile.model_dump() if hasattr(profile, "model_dump") else dict(profile or {})
    return {key: value for key, value in data.items() if value is not None}


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

        trace_token = None
        stack_token = None
        trace_context = kwargs.pop("trace_context", None)
        active_trace_id = _active_trace_id.get()
        observation_stack = _active_observation_stack.get()

        if trace_context is None:
            if active_trace_id is None:
                active_trace_id = uuid.uuid4().hex
                trace_token = _active_trace_id.set(active_trace_id)

            trace_context = TraceContext(trace_id=active_trace_id)
            if observation_stack:
                trace_context["parent_span_id"] = observation_stack[-1]
        elif trace_context.get("trace_id") and active_trace_id is None:
            trace_token = _active_trace_id.set(trace_context["trace_id"])

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
            if trace_token is not None:
                _active_trace_id.reset(trace_token)

    def update_current(self, **kwargs):
        if not self.enabled or not self._client:
            return
        try:
            self._client.update_current_span(**kwargs)
        except Exception:
            pass

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
        except Exception:
            pass


tracer = LangfuseTracer()
