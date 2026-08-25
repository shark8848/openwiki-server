from __future__ import annotations

import pytest

from openwiki_server_sdk.errors import (
    OpenWikiServerBusinessError,
    OpenWikiServerConflictError,
    OpenWikiServerNotFoundError,
    OpenWikiServerSystemError,
    OpenWikiServerValidationError,
    exception_from_code,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("200001", OpenWikiServerValidationError),
        ("200404", OpenWikiServerNotFoundError),
        ("200409", OpenWikiServerConflictError),
        ("200500", OpenWikiServerSystemError),
        ("299999", OpenWikiServerBusinessError),
    ],
)
def test_exception_from_code_mapping(code, expected):
    exc = exception_from_code(code, "msg", "trace-1")
    assert isinstance(exc, expected)
    assert exc.err_code == code
    assert exc.err_msg == "msg"
    assert exc.trace_id == "trace-1"
