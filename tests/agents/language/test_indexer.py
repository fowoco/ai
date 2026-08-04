import hashlib
import json
from pathlib import Path

import pytest

from app.agents.language.ports import EpsIndexStore
from app.agents.language.retrieval.indexer import (
    CollectionSpec,
    EpsCleaningResult,
    build_index_plan,
    clean_eps_data,
    compute_point_id,
    generate_collection_name,
)
from app.agents.language.retrieval.models import ExpectedIndexContract


class FakeEpsIndexStore(EpsIndexStore):
    def __init__(self) -> None:
        self.collections: dict[str, CollectionSpec] = {}
        self.points: dict[str, list[dict[str, object]]] = {}
        self.payload_indexes: dict[str, list[str]] = {}
        self.aliases: dict[str, str] = {}
        self.fail_verification: bool = False

    def create_collection(self, collection_name: str, spec: CollectionSpec) -> None:
        self.collections[collection_name] = spec
        if collection_name not in self.points:
            self.points[collection_name] = []

    def ensure_payload_indexes(
        self, collection_name: str, fields: tuple[str, ...]
    ) -> None:
        self.payload_indexes[collection_name] = list(fields)

    def upsert_batch(
        self, collection_name: str, points: tuple[dict[str, object], ...]
    ) -> None:
        if collection_name not in self.points:
            self.points[collection_name] = []
        self.points[collection_name].extend(points)

    def verify_collection(
        self,
        collection_name: str,
        expected_count: int,
        spec: CollectionSpec,
        expected_languages: tuple[str, ...],
        expected_contract: ExpectedIndexContract,
    ) -> None:
        if self.fail_verification:
            raise ValueError("Verification failed: simulated failure")
        points = self.points.get(collection_name, [])
        if len(points) != expected_count:
            raise ValueError(
                f"Count mismatch: expected {expected_count}, got {len(points)}"
            )

        for pt in points:
            payload = pt.get("payload", {})
            if (
                payload.get("embedding_model_repo")
                != expected_contract.embedding_model_repo
            ):
                raise ValueError("Model repo mismatch")
            if (
                payload.get("embedding_model_revision")
                != expected_contract.embedding_model_revision
            ):
                raise ValueError("Model revision mismatch")
            if (
                payload.get("index_contract_version")
                != expected_contract.index_contract_version
            ):
                raise ValueError("Index contract version mismatch")

    def swap_alias(self, alias_name: str, collection_name: str) -> None:
        self.aliases[alias_name] = collection_name


@pytest.fixture
def minimal_fixture_path() -> Path:
    return Path("tests/fixtures/language/eps_minimal.json")


def test_indexer_drops_blank_translation(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    assert res.blank_translation_removed == 1


def test_indexer_drops_blank_korean(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    assert res.blank_korean_removed == 1


def test_indexer_deduplicates_exact_records(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    assert res.duplicates_removed == 1
    # Page should retain smallest numeric page (5 < 10)
    assert res.usable_records[0]["source_page"] == 5


def test_indexer_rejects_unknown_eps_code(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    assert res.invalid_eps_code_removed == 1


def test_indexer_rejects_invalid_source_page(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    assert res.invalid_page_removed == 1


def test_point_ids_are_deterministic() -> None:
    pid1 = compute_point_id("01", "고맙습니다.", "Thank you")
    pid2 = compute_point_id("01", "고맙습니다.", "Thank you")
    assert pid1 == pid2
    assert len(pid1) == 36


def test_payload_has_dataset_and_content_hash(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    rec = res.usable_records[0]
    assert "content_hash" in rec
    assert "dataset_revision" in rec


def test_payload_has_exact_encoder_and_index_contract_provenance(
    minimal_fixture_path: Path,
) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    rec = res.usable_records[0]
    assert rec["embedding_model_repo"] == "BAAI/bge-m3"
    assert rec["index_contract_version"] == "eps-language-index-v1"


def test_payload_has_no_pronunciation(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res = clean_eps_data(raw)
    for rec in res.usable_records:
        assert "pronunciation" not in rec


def test_source_record_order_does_not_change_ids() -> None:
    pid1 = compute_point_id("01", "안녕", "Hello")
    pid2 = compute_point_id("01", "안녕", "Hello")
    assert pid1 == pid2


def test_reindex_is_idempotent(minimal_fixture_path: Path) -> None:
    raw = json.loads(minimal_fixture_path.read_text(encoding="utf-8"))
    res1 = clean_eps_data(raw)
    res2 = clean_eps_data(raw)
    assert [r["point_id"] for r in res1.usable_records] == [
        r["point_id"] for r in res2.usable_records
    ]


def test_new_collection_is_verified_before_alias_switch() -> None:
    store = FakeEpsIndexStore()
    contract = ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=1,
    )
    records = [
        {
            "point_id": compute_point_id("01", "고맙습니다.", "Thank you"),
            "eps_language_code": "01",
            "korean_text": "고맙습니다.",
            "translated_text": "Thank you",
            "source_record_id": compute_point_id("01", "고맙습니다.", "Thank you"),
            "target_language": "en",
            "source_page": 1,
            "dataset_revision": (
                "sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d"
            ),
            "content_hash": "dummy",
            "quality_status": "verified",
            "source": "EPS",
            "source_url": None,
            "embedding_model_repo": "BAAI/bge-m3",
            "embedding_model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
            "index_contract_version": "eps-language-index-v1",
        }
    ]
    coll_name = generate_collection_name(
        "29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        "5617a9f61b028005a4858fdac845db406aefb181",
    )
    build_index_plan(
        store=store,
        collection_name=coll_name,
        records=records,
        expected_contract=contract,
        switch_alias=True,
        alias_name="eps_language_phrases",
    )
    assert store.aliases.get("eps_language_phrases") == coll_name


def test_failed_verification_keeps_old_alias() -> None:
    store = FakeEpsIndexStore()
    store.aliases["eps_language_phrases"] = "old_collection"
    store.fail_verification = True
    contract = ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=1,
    )
    with pytest.raises(ValueError, match="Verification failed"):
        build_index_plan(
            store=store,
            collection_name="new_collection",
            records=[],
            expected_contract=contract,
            switch_alias=True,
            alias_name="eps_language_phrases",
        )
    assert store.aliases["eps_language_phrases"] == "old_collection"


def test_expected_count_must_match() -> None:
    store = FakeEpsIndexStore()
    contract = ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=10,
    )
    with pytest.raises(ValueError, match="Count mismatch"):
        build_index_plan(
            store=store,
            collection_name="c1",
            records=[],
            expected_contract=contract,
            switch_alias=False,
        )


def test_payload_indexes_are_requested() -> None:
    store = FakeEpsIndexStore()
    contract = ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=0,
    )
    build_index_plan(
        store=store,
        collection_name="c1",
        records=[],
        expected_contract=contract,
        switch_alias=False,
    )
    assert "eps_language_code" in store.payload_indexes["c1"]


def test_index_verification_requires_one_exact_provenance_for_every_point() -> None:
    store = FakeEpsIndexStore()
    contract = ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=1,
    )
    bad_record = {
        "point_id": "p1",
        "embedding_model_repo": "WRONG",
        "embedding_model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "index_contract_version": "eps-language-index-v1",
    }
    with pytest.raises(ValueError, match="Model repo mismatch"):
        build_index_plan(
            store=store,
            collection_name="c1",
            records=[bad_record],
            expected_contract=contract,
            switch_alias=False,
        )


def test_full_eps_dry_run() -> None:
    db_path = Path("data/eps_language_db.json")
    assert db_path.exists()
    content = db_path.read_bytes()
    sha256_hash = hashlib.sha256(content).hexdigest()
    assert (
        sha256_hash
        == "29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d"
    )

    raw_data = json.loads(content)
    assert len(raw_data) == 17925

    res: EpsCleaningResult = clean_eps_data(raw_data)
    assert res.total_source_rows == 17925
    assert res.blank_korean_removed == 0
    assert res.blank_translation_removed == 10
    assert res.duplicates_removed == 13
    assert len(res.usable_records) == 17902

    languages = {r["eps_language_code"] for r in res.usable_records}
    assert len(languages) == 15
