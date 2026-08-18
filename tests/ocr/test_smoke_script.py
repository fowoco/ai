import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = [
    pytest.mark.windows_ocr,
    pytest.mark.skipif(
        shutil.which("powershell") is None and shutil.which("pwsh") is None,
        reason="PowerShell is unavailable on this operating system",
    ),
]


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    assert executable is not None
    return executable


def _script() -> Path:
    return Path(__file__).parents[2] / "scripts" / "smoke_clova_ocr.ps1"


def test_smoke_script_stops_before_network_when_required_environment_is_missing() -> None:
    environment = os.environ.copy()
    for name in (
        "FOWOCO_INTERNAL_API_TOKEN",
        "OCR_SAMPLE_FILE",
        "OCR_WORKER_DOCUMENT_ID",
        "OCR_DOCUMENT_TYPE",
        "OCR_COUNTRY_CODE",
    ):
        environment.pop(name, None)

    result = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(_script())],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "FOWOCO_INTERNAL_API_TOKEN" in result.stdout + result.stderr


class _RecordingHandler(BaseHTTPRequestHandler):
    headers_received = None
    body_received = b""
    path_received = ""

    def do_POST(self) -> None:  # noqa: N802
        type(self).headers_received = self.headers
        type(self).path_received = self.path
        type(self).body_received = self.rfile.read(int(self.headers["Content-Length"]))
        response = (
            b'{"request_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",'
            b'"worker_document_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",'
            b'"ocr_status":"SUCCEEDED","matched_template_id":43019,'
            b'"document_side":null,"fields":{"passport_number":"SENSITIVE-123"},'
            b'"field_confidences":{"passport_number":0.99},"review_reasons":[]}'
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def test_smoke_script_sends_stateless_contract_without_printing_sensitive_values(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.png"
    sample.write_bytes(b"synthetic-image-bytes")
    _RecordingHandler.headers_received = None
    _RecordingHandler.body_received = b""
    _RecordingHandler.path_received = ""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = os.environ.copy()
    environment.update(
        {
            "FOWOCO_INTERNAL_API_TOKEN": "internal-test-token",
            "FOWOCO_AI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "OCR_SAMPLE_FILE": str(sample),
            "OCR_WORKER_DOCUMENT_ID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "OCR_DOCUMENT_TYPE": "PASSPORT_COPY",
            "OCR_COUNTRY_CODE": "KOR",
        }
    )
    environment.pop("OCR_WORKER_ID", None)
    environment.pop("OCR_COMPANY_ID", None)

    try:
        result = subprocess.run(
            [
                _powershell(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_script()),
            ],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=10,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _RecordingHandler.path_received == (
        "/internal/v1/ocr/worker-documents/"
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    )
    assert _RecordingHandler.headers_received["Authorization"] == (
        "Bearer internal-test-token"
    )
    request_id = _RecordingHandler.headers_received["X-Request-Id"]
    UUID(request_id)
    body = _RecordingHandler.body_received
    assert request_id.encode() in body
    assert b"name=request_id" in body
    assert b"name=document_type" in body
    assert b"name=country_code" in body
    assert b"name=file" in body
    assert b"name=worker_id" not in body
    assert b"name=company_id" not in body
    assert "field_count: 1" in result.stdout
    assert "SENSITIVE-123" not in result.stdout + result.stderr
    assert "0.99" not in result.stdout + result.stderr
