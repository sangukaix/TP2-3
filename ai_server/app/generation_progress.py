"""Per-job progress notification; isolated across concurrent async jobs."""
from contextvars import ContextVar
from contextlib import contextmanager

_listener = ContextVar('generation_progress_listener', default=None)


@contextmanager
def track_progress(listener):
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)


def notify_progress(step, message):
    listener = _listener.get()
    if listener:
        listener(step, message)
