import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from app.agents.language.retrieval.encoder import (
    BgeM3Encoder,
    FlagEmbeddingBgeM3Backend,
)
from app.agents.language.retrieval.indexer import (
    build_embedded_index_plan,
    clean_eps_data,
    generate_collection_name,
)
from app.agents.language.retrieval.manifest import (
    BGE_M3_REVISION,
    EPS_DATASET_REVISION,
    QDRANT_COLLECTION_ALIAS,
    build_expected_index_contract,
)
from app.agents.language.retrieval.qdrant_store import QdrantStore


def main() -> None:
    parser = argparse.ArgumentParser(description="EPS Language Indexing CLI")
    parser.add_argument("--source", type=str, default="data/eps_language_db.json")
    parser.add_argument("--qdrant-url", type=str, default="http://localhost:6333")
    parser.add_argument(
        "--collection-alias", type=str, default=QDRANT_COLLECTION_ALIAS
    )
    parser.add_argument(
        "--embedding-model-path",
        type=str,
        default=f"/data/model-cache/bge-m3/{BGE_M3_REVISION}",
    )
    parser.add_argument(
        "--embedding-model-revision",
        type=str,
        default=BGE_M3_REVISION,
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--use-fp16", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--switch-alias", action="store_true")

    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    raw_bytes = source_path.read_bytes()
    dataset_sha = hashlib.sha256(raw_bytes).hexdigest()
    dataset_revision = f"sha256:{dataset_sha}"
    if dataset_revision != EPS_DATASET_REVISION:
        print(
            f"Dataset revision mismatch: {dataset_revision}",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_data = json.loads(raw_bytes)
    cleaning_res = clean_eps_data(raw_data, dataset_revision=dataset_revision)

    coll_name = generate_collection_name(
        dataset_sha, args.embedding_model_revision
    )

    print("=== EPS Indexing Job Summary ===")
    print(f"Source file: {source_path}")
    print(f"Dataset Revision: {dataset_revision}")
    print(f"Total source rows: {cleaning_res.total_source_rows}")
    print(f"Usable unique records: {len(cleaning_res.usable_records)}")
    print(f"Target collection: {coll_name}")
    print(f"Switch alias: {args.switch_alias}")

    if args.dry_run:
        print("Dry-run complete. Exiting without model load or Qdrant mutation.")
        return

    model_path = Path(args.embedding_model_path)
    if not model_path.exists():
        print(f"Embedding model not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    qdrant_client = QdrantClient(
        url=args.qdrant_url,
        api_key=os.getenv("FOWOCO_QDRANT_API_KEY"),
        check_compatibility=False,
    )
    store = QdrantStore(
        client=qdrant_client,
        collection_alias=args.collection_alias,
    )
    encoder = BgeM3Encoder(
        backend=FlagEmbeddingBgeM3Backend(
            str(model_path),
            use_fp16=args.use_fp16,
        )
    )
    print("Executing full indexing plan...")
    build_embedded_index_plan(
        store=store,
        encoder=encoder,
        collection_name=coll_name,
        records=cleaning_res.usable_records,
        expected_contract=build_expected_index_contract(),
        batch_size=args.batch_size,
        switch_alias=args.switch_alias,
        alias_name=args.collection_alias,
    )
    print(
        f"Indexing completed successfully: {coll_name} "
        f"({len(cleaning_res.usable_records)} points)"
    )


if __name__ == "__main__":
    main()
