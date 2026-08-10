from app.agents.language.retrieval.models import ExpectedIndexContract

QDRANT_COLLECTION_ALIAS = "eps_language_phrases_active"
EPS_DATASET_REVISION = (
    "sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d"
)
BGE_M3_MODEL_REPO = "BAAI/bge-m3"
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
INDEX_CONTRACT_VERSION = "eps-language-index-v1"
EPS_POINT_COUNT = 17_902


def build_expected_index_contract() -> ExpectedIndexContract:
    return ExpectedIndexContract(
        dataset_revision=EPS_DATASET_REVISION,
        embedding_model_repo=BGE_M3_MODEL_REPO,
        embedding_model_revision=BGE_M3_REVISION,
        index_contract_version=INDEX_CONTRACT_VERSION,
        point_count=EPS_POINT_COUNT,
    )


__all__ = [
    "BGE_M3_MODEL_REPO",
    "BGE_M3_REVISION",
    "EPS_DATASET_REVISION",
    "EPS_POINT_COUNT",
    "INDEX_CONTRACT_VERSION",
    "QDRANT_COLLECTION_ALIAS",
    "build_expected_index_contract",
]
