import hashlib
import json
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agents.language.codes import _LANGUAGE_ROWS
from app.agents.language.contracts import EpsLanguageCode, SupportedLanguage
from app.agents.language.ports import EpsIndexStore
from app.agents.language.retrieval.models import ExpectedIndexContract

EPS_UUID_NAMESPACE = uuid.UUID("9a528e10-4f51-4d37-9759-38b71d607f2c")

EPS_CODE_TO_TARGET_LANG: dict[EpsLanguageCode, SupportedLanguage] = {
    row.eps_code: row.canonical_code for row in _LANGUAGE_ROWS
}


@dataclass(frozen=True)
class CollectionSpec:
    dense_vector_name: str = "korean_dense"
    dense_vector_size: int = 1024
    dense_distance: str = "cosine"
    sparse_vector_name: str = "korean_sparse"


@dataclass
class EpsCleaningResult:
    total_source_rows: int = 0
    blank_korean_removed: int = 0
    blank_translation_removed: int = 0
    invalid_eps_code_removed: int = 0
    invalid_page_removed: int = 0
    duplicates_removed: int = 0
    usable_records: list[dict[str, Any]] = field(default_factory=list)


def compute_content_hash(
    eps_code: str, korean_text: str, translated_text: str
) -> str:
    eps_code_clean = eps_code.strip()
    korean_clean = unicodedata.normalize("NFC", korean_text.strip())
    translation_clean = unicodedata.normalize("NFC", translated_text.strip())
    raw = json.dumps(
        [eps_code_clean, korean_clean, translation_clean],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_point_id(
    eps_code: str, korean_text: str, translated_text: str
) -> str:
    chash = compute_content_hash(eps_code, korean_text, translated_text)
    return str(uuid.uuid5(EPS_UUID_NAMESPACE, chash))


def generate_collection_name(dataset_sha: str, encoder_revision: str) -> str:
    ds_prefix = dataset_sha.removeprefix("sha256:")[:12]
    enc_prefix = encoder_revision[:12]
    return f"eps_language_phrases_{ds_prefix}_{enc_prefix}"


def clean_eps_data(
    raw_data: Sequence[dict[str, Any]],
    dataset_revision: str | None = None,
) -> EpsCleaningResult:
    if dataset_revision is None:
        raw_bytes = json.dumps(
            raw_data, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        dataset_sha = hashlib.sha256(raw_bytes).hexdigest()
        dataset_revision = f"sha256:{dataset_sha}"

    result = EpsCleaningResult(total_source_rows=len(raw_data))
    seen_records: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in raw_data:
        eps_code = str(row.get("lang_code", "")).strip()
        if eps_code not in EPS_CODE_TO_TARGET_LANG:
            result.invalid_eps_code_removed += 1
            continue

        raw_page = row.get("page")
        if not isinstance(raw_page, int) or raw_page <= 0:
            result.invalid_page_removed += 1
            continue
        page = raw_page

        korean_raw = str(row.get("korean", ""))
        korean_norm = unicodedata.normalize("NFC", korean_raw.strip())
        if not korean_norm:
            result.blank_korean_removed += 1
            continue

        translation_raw = str(row.get("foreign_translation", ""))
        translation_norm = unicodedata.normalize("NFC", translation_raw.strip())
        if not translation_norm:
            result.blank_translation_removed += 1
            continue

        dedupe_key = (eps_code, korean_norm, translation_norm)
        if dedupe_key in seen_records:
            result.duplicates_removed += 1
            existing = seen_records[dedupe_key]
            if page < existing["source_page"]:
                existing["source_page"] = page
            continue

        target_lang = EPS_CODE_TO_TARGET_LANG[eps_code]
        chash = compute_content_hash(eps_code, korean_norm, translation_norm)
        pid = str(uuid.uuid5(EPS_UUID_NAMESPACE, chash))

        record = {
            "point_id": pid,
            "source_record_id": pid,
            "eps_language_code": eps_code,
            "korean_text": korean_norm,
            "translated_text": translation_norm,
            "target_language": target_lang,
            "source_page": page,
            "dataset_revision": dataset_revision,
            "content_hash": chash,
            "quality_status": "verified",
            "source": "EPS",
            "source_url": None,
            "embedding_model_repo": "BAAI/bge-m3",
            "embedding_model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
            "index_contract_version": "eps-language-index-v1",
        }
        seen_records[dedupe_key] = record

    result.usable_records = list(seen_records.values())
    return result


def build_index_plan(
    *,
    store: EpsIndexStore,
    collection_name: str,
    records: Sequence[dict[str, Any]],
    expected_contract: ExpectedIndexContract,
    switch_alias: bool = False,
    alias_name: str = "eps_language_phrases",
    spec: CollectionSpec | None = None,
) -> None:
    if spec is None:
        spec = CollectionSpec()
    store.create_collection(collection_name, spec)

    store.ensure_payload_indexes(
        collection_name,
        ("eps_language_code", "target_language", "quality_status"),
    )

    points = tuple({"id": r["point_id"], "payload": r} for r in records)
    store.upsert_batch(collection_name, points)

    expected_count = (
        expected_contract.point_count
        if expected_contract.point_count is not None
        else len(records)
    )
    expected_languages = (
        tuple(
            sorted(
                {
                    str(r["target_language"])
                    for r in records
                    if "target_language" in r
                }
            )
        )
        if records
        else ()
    )

    store.verify_collection(
        collection_name,
        expected_count=expected_count,
        spec=spec,
        expected_languages=expected_languages,
        expected_contract=expected_contract,
    )

    if switch_alias:
        store.swap_alias(alias_name, collection_name)
