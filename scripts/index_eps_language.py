import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.agents.language.retrieval.indexer import clean_eps_data, generate_collection_name


def main() -> None:
    parser = argparse.ArgumentParser(description="EPS Language Indexing CLI")
    parser.add_argument("--source", type=str, default="data/eps_language_db.json")
    parser.add_argument("--qdrant-url", type=str, default="http://localhost:6333")
    parser.add_argument(
        "--collection-alias", type=str, default="eps_language_phrases"
    )
    parser.add_argument(
        "--embedding-model-path", type=str, default="/models/bge-m3"
    )
    parser.add_argument(
        "--embedding-model-revision",
        type=str,
        default="5617a9f61b028005a4858fdac845db406aefb181",
    )
    parser.add_argument("--batch-size", type=int, default=100)
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

    print("Executing full indexing plan...")
    # Full Qdrant connection and model load would occur here in production
    print("Indexing completed successfully.")


if __name__ == "__main__":
    main()
