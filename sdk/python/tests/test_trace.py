from __future__ import annotations

from openwiki_server_sdk.trace import ensure_trace_id, generate_trace_id


def test_generate_trace_id_is_23_digits():
    trace_id = generate_trace_id()
    assert len(trace_id) == 23
    assert trace_id.isdigit()


def test_generate_trace_id_unique():
    assert len({generate_trace_id() for _ in range(100)}) == 100


def test_ensure_trace_id_reuses_explicit():
    assert ensure_trace_id("fixed") == "fixed"
    generated = ensure_trace_id(None)
    assert generated.isdigit() and len(generated) == 23
