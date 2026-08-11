from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.feedback import MappingFeedbackRecord
from app.documents.dynamic_automation.qwen import (
    QWEN3_EMBEDDING_CACHE_NAME,
    QWEN3_EMBEDDING_REVISION,
)
from app.documents.dynamic_automation.training import (
    build_hard_negatives,
    build_training_split,
)
from scripts import train_dynamic_mapping_models as training_cli

ROOT = Path(__file__).parents[3]
FEEDBACK_PATH = ROOT / "tests/fixtures/dynamic_automation/approved_feedback.jsonl"
CATALOG_PATH = (
    ROOT / "app/documents/dynamic_automation/resources/canonical_fields.v1.yaml"
)


def load_feedback_fixture() -> tuple[MappingFeedbackRecord, ...]:
    return tuple(
        MappingFeedbackRecord.model_validate_json(line)
        for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def test_layout_hash_never_crosses_train_and_test() -> None:
    split = build_training_split(load_feedback_fixture())

    train_layouts = {item.document_layout_hash for item in split.train}
    test_layouts = {item.document_layout_hash for item in split.test}

    assert train_layouts
    assert test_layouts
    assert train_layouts.isdisjoint(test_layouts)


def test_all_required_group_identities_are_disjoint_across_split() -> None:
    split = build_training_split(load_feedback_fixture())

    for attribute in (
        "document_layout_hash",
        "document_kind",
        "document_version",
        "source_institution",
    ):
        train_values = {getattr(item, attribute) for item in split.train}
        test_values = {getattr(item, attribute) for item in split.test}
        assert train_values.isdisjoint(test_values)


def test_training_split_keeps_transitively_connected_groups_together() -> None:
    base = load_feedback_fixture()[0]
    records = (
        base.model_copy(
            update={
                "layout_hash": "1" * 64,
                "field_context_hash": "1" * 64,
                "field_id": "bridge-a",
                "document_kind": "shared-kind",
                "document_version": "version-a",
                "source_institution": "institution-a",
            }
        ),
        base.model_copy(
            update={
                "layout_hash": "2" * 64,
                "field_context_hash": "2" * 64,
                "field_id": "bridge-b",
                "document_kind": "shared-kind",
                "document_version": "version-b",
                "source_institution": "shared-institution",
            }
        ),
        base.model_copy(
            update={
                "layout_hash": "3" * 64,
                "field_context_hash": "3" * 64,
                "field_id": "bridge-c",
                "document_kind": "kind-c",
                "document_version": "version-c",
                "source_institution": "shared-institution",
            }
        ),
        base.model_copy(
            update={
                "layout_hash": "4" * 64,
                "field_context_hash": "4" * 64,
                "field_id": "independent",
                "document_kind": "kind-d",
                "document_version": "version-d",
                "source_institution": "institution-d",
            }
        ),
    )

    split = build_training_split(records)
    train_ids = {item.field_id for item in split.train}
    test_ids = {item.field_id for item in split.test}
    bridge_ids = {"bridge-a", "bridge-b", "bridge-c"}

    assert bridge_ids <= train_ids or bridge_ids <= test_ids
    assert "independent" in train_ids | test_ids


def test_training_split_is_reproducible_and_preserves_corrected_labels() -> None:
    records = load_feedback_fixture()

    first = build_training_split(records)
    second = build_training_split(tuple(reversed(records)))

    assert first == second
    corrected = next(
        item
        for item in (*first.train, *first.test)
        if item.field_id == "company_phone"
    )
    assert corrected.canonical_field_id == "company.phone"


def test_training_split_revalidates_input_and_rejects_db_values() -> None:
    payload = load_feedback_fixture()[0].model_dump(mode="json")
    payload["db_value"] = "+82-10-1234-5678"

    with pytest.raises(ValueError, match="forbidden key|Extra inputs"):
        build_training_split([payload])


def test_feedback_fixture_contains_only_sanitized_mapping_records() -> None:
    records = load_feedback_fixture()
    raw = [json.loads(line) for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()]

    assert len(records) == 10
    assert all("db_value" not in record and "resolved_value" not in record for record in raw)


def test_hard_negatives_are_type_compatible_and_prioritize_entity_confusions() -> None:
    worker_phone = next(
        record for record in load_feedback_fixture() if record.field_id == "worker_phone"
    )
    split = build_training_split([worker_phone])
    catalog = CanonicalCatalog.load(CATALOG_PATH)

    pairs = build_hard_negatives(split, catalog)

    assert pairs
    assert pairs[0].positive_canonical_field_id == "worker.phone"
    assert pairs[0].negative_canonical_field_id == "company.phone"
    assert all(
        set(catalog.get(pair.positive_canonical_field_id).compatible_field_types)
        & set(catalog.get(pair.negative_canonical_field_id).compatible_field_types)
        for pair in pairs
    )


def test_passport_and_registration_ids_are_prioritized_hard_negatives() -> None:
    passport = next(
        record
        for record in load_feedback_fixture()
        if record.field_id == "passport_identifier"
    )
    split = build_training_split([passport])
    catalog = CanonicalCatalog.load(CATALOG_PATH)

    pairs = build_hard_negatives(split, catalog)

    assert pairs[0].positive_canonical_field_id == "identity.passport_number"
    assert (
        pairs[0].negative_canonical_field_id
        == "identity.alien_registration_number"
    )


def test_training_cli_refuses_to_download_when_pinned_cache_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(tmp_path / "missing-cache"))
    output_dir = tmp_path / "output"

    exit_code = training_cli.main(
        [
            "--feedback",
            str(FEEDBACK_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(output_dir),
            "--seed",
            "42",
            "--model-kind",
            "bi-encoder",
        ]
    )

    assert exit_code == 1
    assert not output_dir.exists()


def test_training_cli_rejects_feedback_from_a_different_catalog_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payloads = [
        record.model_dump(mode="json") for record in load_feedback_fixture()
    ]
    payloads[-1]["catalog_version"] = "v2"
    feedback_path = tmp_path / "mixed-feedback.jsonl"
    feedback_path.write_text(
        "".join(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            for payload in payloads
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(tmp_path / "missing-cache"))
    output_dir = tmp_path / "output"

    exit_code = training_cli.main(
        [
            "--feedback",
            str(feedback_path),
            "--catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(output_dir),
            "--seed",
            "42",
            "--model-kind",
            "bi-encoder",
        ]
    )

    assert exit_code == 1
    assert "feedback catalog_version v2 does not match loaded catalog v1" in capsys.readouterr().err
    assert not output_dir.exists()


def test_training_cli_rejects_config_only_cache_without_model_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_cache = tmp_path / "model-cache"
    pinned_model = model_cache / QWEN3_EMBEDDING_CACHE_NAME / QWEN3_EMBEDDING_REVISION
    pinned_model.mkdir(parents=True)
    (pinned_model / "config.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(model_cache))
    output_dir = tmp_path / "output"

    exit_code = training_cli.main(
        [
            "--feedback",
            str(FEEDBACK_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(output_dir),
            "--seed",
            "42",
            "--model-kind",
            "bi-encoder",
        ]
    )

    assert exit_code == 1
    assert not output_dir.exists()


def test_training_script_refuses_config_only_cache_without_import_path_errors(
    tmp_path: Path,
) -> None:
    model_cache = tmp_path / "model-cache"
    pinned_model = model_cache / QWEN3_EMBEDDING_CACHE_NAME / QWEN3_EMBEDDING_REVISION
    pinned_model.mkdir(parents=True)
    (pinned_model / "config.json").write_text("{}\n", encoding="utf-8")
    output_dir = tmp_path / "subprocess-output"
    environment = os.environ.copy()
    environment["FOWOCO_MODEL_CACHE_DIR"] = str(model_cache)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/train_dynamic_mapping_models.py",
            "--feedback",
            str(FEEDBACK_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(output_dir),
            "--seed",
            "42",
            "--model-kind",
            "bi-encoder",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "ModuleNotFoundError" not in completed.stderr
    assert "model weights" in completed.stderr
    assert not output_dir.exists()
