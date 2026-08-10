"""T13 — compose 설정 통합 테스트 (파일 파싱, 외부 서버 연결 없음).

compose.yml: Qdrant 1.18.3 내부전용 서비스, 볼륨 분리 검증.
compose.test.yml: 테스트용 독립 Qdrant 볼륨 검증.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("compose_file", ("compose.yml", "compose.test.yml"))
def test_qdrant_healthcheck_uses_available_bash_tcp_probe(
    compose_file: str,
) -> None:
    import yaml

    data = yaml.safe_load((ROOT / compose_file).read_text())
    command = data["services"]["qdrant"]["healthcheck"]["test"]

    assert command[:2] == ["CMD", "/bin/bash"]
    assert "/dev/tcp/127.0.0.1/6333" in command[-1]
    assert "wget" not in " ".join(command)


class TestComposeProdConfig:
    """compose.yml 구조 검증 — 파일 파싱만, 외부 연결 없음."""

    def test_compose_yml_exists(self) -> None:
        assert (ROOT / "compose.yml").exists()

    def test_compose_yml_has_qdrant_service(self) -> None:
        import yaml

        data = yaml.safe_load((ROOT / "compose.yml").read_text())
        assert "qdrant" in data["services"], "qdrant 서비스 없음"

    def test_qdrant_service_uses_pinned_image(self) -> None:
        import yaml

        data = yaml.safe_load((ROOT / "compose.yml").read_text())
        qdrant_image = data["services"]["qdrant"].get("image", "")
        assert "1.18.3" in qdrant_image, f"Qdrant 이미지 미고정: {qdrant_image!r}"

    def test_qdrant_service_no_external_ports(self) -> None:
        """Qdrant는 내부전용 — 호스트 포트 노출 금지."""
        import yaml

        data = yaml.safe_load((ROOT / "compose.yml").read_text())
        ports = data["services"]["qdrant"].get("ports", [])
        assert ports == [], f"Qdrant 외부 포트 노출됨: {ports}"

    def test_qdrant_volume_separate_from_document_volume(self) -> None:
        import yaml

        data = yaml.safe_load((ROOT / "compose.yml").read_text())
        volumes = set(data.get("volumes", {}).keys())
        # Qdrant 데이터 볼륨과 문서 볼륨이 별도여야 함
        assert any("qdrant" in v for v in volumes), f"Qdrant 볼륨 없음: {volumes}"
        assert any("document" in v for v in volumes), f"문서 볼륨 없음: {volumes}"

    def test_ai_service_has_qdrant_url_env(self) -> None:
        import yaml

        data = yaml.safe_load((ROOT / "compose.yml").read_text())
        ai_env = data["services"]["ai"].get("environment", {})
        # dict 또는 list 형식 모두 허용
        if isinstance(ai_env, dict):
            keys = set(ai_env.keys())
        else:
            keys = {e.split("=")[0] for e in ai_env}
        assert "FOWOCO_QDRANT_URL" in keys, f"FOWOCO_QDRANT_URL 환경변수 없음: {keys}"


class TestComposeTestConfig:
    """compose.test.yml 구조 검증."""

    def test_compose_test_yml_exists(self) -> None:
        assert (ROOT / "compose.test.yml").exists()

    def test_compose_test_has_qdrant_service(self) -> None:
        import yaml

        data = yaml.safe_load((ROOT / "compose.test.yml").read_text())
        assert "qdrant" in data["services"]

    def test_compose_test_qdrant_uses_separate_volume(self) -> None:
        """테스트용 Qdrant 볼륨이 프로덕션과 다른 이름 사용."""
        import yaml

        prod = yaml.safe_load((ROOT / "compose.yml").read_text())
        test = yaml.safe_load((ROOT / "compose.test.yml").read_text())

        prod_qdrant_vols = set(prod.get("volumes", {}).keys())
        test_qdrant_vols = set(test.get("volumes", {}).keys())

        prod_qdrant = {v for v in prod_qdrant_vols if "qdrant" in v}
        test_qdrant = {v for v in test_qdrant_vols if "qdrant" in v}

        # 이름이 겹치면 안 됨 (볼륨 격리)
        assert prod_qdrant.isdisjoint(test_qdrant), (
            f"프로덕션/테스트 Qdrant 볼륨 충돌: {prod_qdrant & test_qdrant}"
        )
