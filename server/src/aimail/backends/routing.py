"""Backend selection scoped to one request/task, never a process-wide env mutation.

Async tasks copy their caller's context. A newly started worker thread must explicitly
capture the backend name at enqueue time and enter its own selection context.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

SUPPORTED_BACKENDS = frozenset({"local", "claude", "codex_cli", "claude_code_cli"})
MAILBOX_PROVIDERS = ("codex_cli", "claude_code_cli", "local")
_selection: ContextVar[str | None] = ContextVar("aimail_model_backend", default=None)
_model: ContextVar[str | None] = ContextVar("aimail_model_id", default=None)


class SelectionError(ValueError):
    """An invalid provider id; the supplied value never enters error messages."""


def validate(name: str) -> str:
    if not isinstance(name, str) or name not in SUPPORTED_BACKENDS:
        raise SelectionError("模型后端只能是 local、claude、codex_cli 或 claude_code_cli")
    return name


def selected(default: str) -> str:
    override = _selection.get()
    return validate(override if override is not None else default.strip().lower())


def selected_model() -> str | None:
    return _model.get()


def selected_override() -> str | None:
    return _selection.get()


@contextmanager
def use_backend(name: str, *, model: str | None = None) -> Iterator[str]:
    token = _selection.set(validate(name))
    model_token = _model.set(model)
    try:
        yield name
    finally:
        _model.reset(model_token)
        _selection.reset(token)
