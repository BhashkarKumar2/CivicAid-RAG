import os
from contextlib import contextmanager, nullcontext
from typing import Any


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

        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type=as_type,
                **kwargs,
            ) as observation:
                yield observation
        except TypeError:
            with self._client.start_as_current_observation(name=name, as_type=as_type) as observation:
                yield observation
        except Exception:
            with nullcontext() as empty:
                yield empty

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
            return self._client.get_trace_url()
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
