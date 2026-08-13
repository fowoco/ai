"""T13 — 모델 캐시 무결성 RED 테스트.

scripts/download_language_models.py: 리비전 고정 다운로드 및 매니페스트 검증.
"""

from pathlib import Path


class TestModelManifest:
    """모델 캐시 매니페스트 파일 구조 검증."""

    def test_manifest_constants_defined(self) -> None:
        from app.agents.language.retrieval.manifest import (
            BGE_M3_REVISION,
            BGE_RERANKER_MODEL_REPO,
            BGE_RERANKER_REVISION,
        )
        from scripts.download_language_models import MODEL_SPECS

        assert BGE_M3_REVISION == "5617a9f61b028005a4858fdac845db406aefb181"
        assert BGE_RERANKER_MODEL_REPO == "BAAI/bge-reranker-v2-m3"
        assert BGE_RERANKER_REVISION == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
        assert MODEL_SPECS[1]["revision"] == BGE_RERANKER_REVISION

    def test_model_specs_have_required_fields(self) -> None:
        from scripts.download_language_models import MODEL_SPECS

        assert len(MODEL_SPECS) >= 2
        for spec in MODEL_SPECS:
            assert "repo" in spec
            assert "revision" in spec
            assert "name" in spec

    def test_bge_m3_spec_present(self) -> None:
        from scripts.download_language_models import MODEL_SPECS

        repos = [s["repo"] for s in MODEL_SPECS]
        assert "BAAI/bge-m3" in repos

    def test_bge_reranker_spec_present(self) -> None:
        from scripts.download_language_models import MODEL_SPECS

        repos = [s["repo"] for s in MODEL_SPECS]
        assert "BAAI/bge-reranker-v2-m3" in repos


class TestModelCacheVerify:
    """캐시 디렉터리 무결성 검사 함수."""

    def test_verify_cache_returns_missing_list_when_empty(
        self, tmp_path: Path
    ) -> None:
        from scripts.download_language_models import verify_model_cache

        missing = verify_model_cache(cache_dir=tmp_path)
        # 빈 캐시 디렉터리 → 모든 모델이 누락으로 보고
        assert len(missing) >= 2

    def test_verify_cache_returns_empty_when_all_present(
        self, tmp_path: Path
    ) -> None:
        from scripts.download_language_models import MODEL_SPECS, verify_model_cache

        # 각 모델 디렉터리에 최소 파일 생성 (실제 가중치 없음)
        for spec in MODEL_SPECS:
            model_dir = tmp_path / spec["name"] / spec["revision"]
            model_dir.mkdir(parents=True)
            # config.json 최소 존재 시뮬레이션
            (model_dir / "config.json").write_text("{}")

        missing = verify_model_cache(cache_dir=tmp_path)
        assert missing == []

    def test_verify_cache_reports_partial_missing(self, tmp_path: Path) -> None:
        from scripts.download_language_models import MODEL_SPECS, verify_model_cache

        # 첫 번째 모델만 캐시
        spec = MODEL_SPECS[0]
        model_dir = tmp_path / spec["name"] / spec["revision"]
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}")

        missing = verify_model_cache(cache_dir=tmp_path)
        assert len(missing) == len(MODEL_SPECS) - 1
