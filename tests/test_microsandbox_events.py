from __future__ import annotations

from types import SimpleNamespace

from sandbox_service.runtime.microsandbox import _exec_event_kind


def test_exec_event_kind_prefers_event_type() -> None:
    event = SimpleNamespace(event_type="stdout", data=b"hi\n")
    assert _exec_event_kind(event) == "stdout"


def test_exec_event_kind_exited() -> None:
    event = SimpleNamespace(event_type="exited", code=0)
    assert _exec_event_kind(event) == "exited"


def test_exec_event_kind_unknown() -> None:
    assert _exec_event_kind(SimpleNamespace()) is None
