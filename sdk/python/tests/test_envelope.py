from __future__ import annotations

import pytest

from openwiki_server_sdk.envelope import Envelope, parse_envelope
from openwiki_server_sdk.errors import OpenWikiServerProtocolError


def test_success_code_is_zero():
    assert Envelope(err_code="0", err_msg="", data={}).ok
    assert not Envelope(err_code="200404", err_msg="", data=None).ok


def test_parse_envelope_success():
    envelope = parse_envelope('{"traceId":"123","errCode":"0","errMsg":"","data":{"total":1}}')
    assert envelope.ok
    assert envelope.trace_id == "123"
    assert envelope.data == {"total": 1}


def test_parse_envelope_not_json():
    with pytest.raises(OpenWikiServerProtocolError):
        parse_envelope("oops")


def test_parse_envelope_missing_err_code():
    with pytest.raises(OpenWikiServerProtocolError):
        parse_envelope('{"data":{}}')


def test_parse_envelope_data_none():
    envelope = parse_envelope('{"traceId":"1","errCode":"0","errMsg":"","data":null}')
    assert envelope.data is None
