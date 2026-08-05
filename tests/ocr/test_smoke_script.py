import os
import shutil
import subprocess
from pathlib import Path


def test_smoke_script_stops_before_network_when_required_environment_is_missing() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    assert powershell is not None
    script = Path(__file__).parents[2] / "scripts" / "smoke_clova_ocr.ps1"
    environment = os.environ.copy()
    for name in (
        "FOWOCO_INTERNAL_API_TOKEN",
        "OCR_SAMPLE_FILE",
        "OCR_WORKER_DOCUMENT_ID",
        "OCR_WORKER_ID",
        "OCR_COMPANY_ID",
        "OCR_DOCUMENT_TYPE",
        "OCR_COUNTRY_CODE",
    ):
        environment.pop(name, None)

    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "FOWOCO_INTERNAL_API_TOKEN" in result.stdout + result.stderr
