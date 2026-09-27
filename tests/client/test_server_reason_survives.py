"""A refusal must carry the server's reason, not just its status code.

FastAPI answers a refusal with {"detail": "..."} saying what was
actually wrong. requests' raise_for_status builds its message from the
status code and response.reason alone, so every call site in this
client -- all of which use raise_for_status -- reported "404 Client
Error: Not Found for url: ..." and threw the sentence away.

Seen on the bench: exporting a session that had recorded nothing. The
server said "No data to export". The panel said "Failed to export: 404
Client Error", which does not tell an operator to start the
acquisition first, so the button was pressed three more times.

The detail is folded into reason inside the session, so every existing
raise_for_status carries it without sixty call sites changing.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    import requests  # noqa: F401

    REQUESTS = True
except ImportError:
    REQUESTS = False

pytestmark = pytest.mark.skipif(not REQUESTS, reason="requests is required")

if REQUESTS:
    import requests

    from client.api.client import _TimeoutSession


def response_of(status, payload, reason="Not Found"):
    made = requests.Response()
    made.status_code = status
    made.reason = reason
    if payload is not None:
        import json

        made._content = json.dumps(payload).encode()
        made.headers["Content-Type"] = "application/json"
    else:
        made._content = b"<html>gateway</html>"
    made.url = "http://bench:8000/api/acquisition/export"
    return made


class TestTheReasonIsKept:
    def test_the_detail_replaces_the_generic_reason(self):
        answer = response_of(404, {"detail": "No data to export"})
        _TimeoutSession._keep_the_servers_reason(answer)
        assert answer.reason == "No data to export"

    def test_it_reaches_the_raised_error(self):
        """The whole point: raise_for_status is what every call site
        uses, and its message is built from reason."""
        answer = response_of(404, {"detail": "No data to export"})
        _TimeoutSession._keep_the_servers_reason(answer)

        with pytest.raises(requests.HTTPError) as raised:
            answer.raise_for_status()
        assert "No data to export" in str(raised.value)

    def test_the_bench_case_in_full(self):
        answer = response_of(
            404, {"detail": "No equipment 'load_b8929b78' is registered, so "
                            "there is nothing to lock."})
        _TimeoutSession._keep_the_servers_reason(answer)
        with pytest.raises(requests.HTTPError) as raised:
            answer.raise_for_status()
        assert "nothing to lock" in str(raised.value)

    def test_a_validation_list_is_flattened(self):
        """Pydantic answers with a list of dicts, and str() on that is
        unreadable."""
        answer = response_of(422, {"detail": [
            {"loc": ["body", "format"], "msg": "field required"},
            {"loc": ["body", "filepath"], "msg": "not a valid path"},
        ]})
        _TimeoutSession._keep_the_servers_reason(answer)
        assert "field required" in answer.reason
        assert "not a valid path" in answer.reason


class TestItLeavesEverythingElseAlone:
    def test_a_success_is_untouched(self):
        answer = response_of(200, {"detail": "ignore me"}, reason="OK")
        _TimeoutSession._keep_the_servers_reason(answer)
        assert answer.reason == "OK", (
            "a 200 carrying a detail field must not be rewritten")

    def test_a_non_json_error_is_untouched(self):
        answer = response_of(502, None, reason="Bad Gateway")
        _TimeoutSession._keep_the_servers_reason(answer)
        assert answer.reason == "Bad Gateway"

    def test_an_error_without_a_detail_is_untouched(self):
        answer = response_of(500, {"error": "boom"}, reason="Server Error")
        _TimeoutSession._keep_the_servers_reason(answer)
        assert answer.reason == "Server Error"

    def test_an_empty_detail_is_untouched(self):
        answer = response_of(404, {"detail": ""}, reason="Not Found")
        _TimeoutSession._keep_the_servers_reason(answer)
        assert answer.reason == "Not Found"
