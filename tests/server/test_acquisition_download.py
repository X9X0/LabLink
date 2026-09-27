"""Export sends the file to the client, rather than writing it there.

POST /export asks the server to write a path. That is right for an
unattended export into the server's own store, and wrong for a GUI:
the file chooser runs on the operator's machine, so the path it
produces only means something there.

On the bench the operator chose C:/LabLinkTest/9009.csv and the Pi
answered

    [Errno 2] No such file or directory: 'C:/LabLinkTest/9009.csv'

having tried to create a directory called "C:". No retry could have
made that path exist on Linux; the request was impossible as posed.

GET /session/{id}/download exports into a temporary file on the server
and streams it back, so the client writes it with the filesystem that
actually has the path.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    FASTAPI = True
except ImportError:
    FASTAPI = False

pytestmark = pytest.mark.skipif(not FASTAPI, reason="fastapi is required")

if FASTAPI:
    from server.api.acquisition import router


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A server whose exporter writes a small file wherever it is told."""
    written = {}

    class Manager:
        async def export_data(self, acquisition_id, format, filepath):
            if acquisition_id == "missing":
                raise ValueError(f"Acquisition {acquisition_id} not found")
            if acquisition_id == "empty":
                raise ValueError("No data to export")
            # newline="" so the fixture writes exactly these bytes on
            # Windows too. Without it "\n" becomes "\r\n" and the test
            # compares the platform rather than the endpoint.
            with open(filepath, "w", encoding="utf-8", newline="") as out:
                out.write("timestamp,CH1\n1.0,2.5\n")
            written["path"] = filepath
            return filepath

    import server.api.acquisition as module

    monkeypatch.setattr(module, "acquisition_manager", Manager())

    app = FastAPI()
    app.include_router(router, prefix="/api/acquisition")
    made = TestClient(app)
    made.written = written
    return made


class TestTheFileComesBack:
    def test_the_body_is_the_exported_data(self, client):
        answer = client.get("/api/acquisition/session/acq-7/download",
                            params={"format": "csv"})
        assert answer.status_code == 200, answer.text
        assert answer.text == "timestamp,CH1\n1.0,2.5\n"

    def test_it_is_named_and_typed(self, client):
        answer = client.get("/api/acquisition/session/acq-7/download",
                            params={"format": "csv"})
        assert "text/csv" in answer.headers["content-type"]
        assert "acq-7.csv" in answer.headers.get("content-disposition", "")

    def test_the_server_wrote_somewhere_of_its_own(self, client):
        """Not to a path the caller supplied -- there is no longer one
        to supply, which is the whole point.

        Checked as "inside the server's temp directory" rather than
        "does not start with C:", because the server's own temp
        directory starts with C: on Windows and the first version of
        this assertion therefore failed for the very reason it was
        written to rule out.
        """
        import tempfile

        client.get("/api/acquisition/session/acq-7/download",
                   params={"format": "csv"})
        written = os.path.realpath(client.written["path"])
        assert written.startswith(os.path.realpath(tempfile.gettempdir())), (
            written)
        assert "lablink-export-" in written, written

    @pytest.mark.parametrize("fmt,media", [
        ("csv", "text/csv"),
        ("json", "application/json"),
        ("hdf5", "application/x-hdf5"),
    ])
    def test_each_format_says_what_it_is(self, client, fmt, media):
        answer = client.get(f"/api/acquisition/session/acq-7/download",
                            params={"format": fmt})
        assert media in answer.headers["content-type"], answer.headers


class TestItStillRefusesProperly:
    def test_an_unknown_session_is_404(self, client):
        answer = client.get("/api/acquisition/session/missing/download")
        assert answer.status_code == 404
        assert "not found" in answer.json()["detail"].lower()

    def test_a_session_with_no_data_says_so(self, client):
        """The bench case that started all of this: the reason must
        survive, because "No data to export" tells the operator to run
        the acquisition first and a status code does not."""
        answer = client.get("/api/acquisition/session/empty/download")
        assert answer.status_code == 404
        assert answer.json()["detail"] == "No data to export"
