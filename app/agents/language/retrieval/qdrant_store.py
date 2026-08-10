from collections.abc import Sequence
from typing import Any

from app.agents.language.contracts import SupportedLanguage
from app.agents.language.ports import EpsIndexStore, HybridSearchStore
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.indexer import CollectionSpec
from app.agents.language.retrieval.models import (
    EpsReference,
    ExpectedIndexContract,
    HybridVector,
    PerQueryRanking,
    RankedCandidate,
    VerifiedCollectionHandle,
)

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models as qmodels
except ImportError:
    class _MockQModels:
        class Distance:
            COSINE = "COSINE"

        class PayloadSchema:
            KEYWORD = "keyword"

        class Fusion:
            RRF = "rrf"

        def VectorParams(self, **kwargs: Any) -> Any:
            return kwargs

        def SparseVectorParams(self, **kwargs: Any) -> Any:
            return kwargs

        def SparseVector(self, **kwargs: Any) -> Any:
            return kwargs

        def PointStruct(self, **kwargs: Any) -> Any:
            return kwargs

        def Filter(self, **kwargs: Any) -> Any:
            return kwargs

        def FieldCondition(self, **kwargs: Any) -> Any:
            return kwargs

        def MatchValue(self, **kwargs: Any) -> Any:
            return kwargs

        def Prefetch(self, **kwargs: Any) -> Any:
            return kwargs

        def QueryRequest(self, **kwargs: Any) -> Any:
            return kwargs

        def FusionQuery(self, **kwargs: Any) -> Any:
            return kwargs

        def CreateAliasOperation(self, **kwargs: Any) -> Any:
            return kwargs

        def CreateAlias(self, **kwargs: Any) -> Any:
            return kwargs

    QdrantClient = Any
    qmodels = _MockQModels()


class QdrantStore(HybridSearchStore, EpsIndexStore):
    def __init__(self, client: Any) -> None:
        self.client = client

    def create_collection(
        self, collection_name: str, spec: CollectionSpec | None = None
    ) -> None:
        if spec is None:
            spec = CollectionSpec()

        if self.client.collection_exists(collection_name):
            return

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                spec.dense_vector_name: qmodels.VectorParams(
                    size=spec.dense_vector_size,
                    distance=qmodels.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                spec.sparse_vector_name: qmodels.SparseVectorParams()
            },
        )

    def ensure_payload_indexes(
        self, collection_name: str, fields: tuple[str, ...]
    ) -> None:
        for field in fields:
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=qmodels.PayloadSchema.KEYWORD,
            )

    def upsert_batch(
        self, collection_name: str, points: tuple[dict[str, Any], ...]
    ) -> None:
        qpoints = []
        for pt in points:
            qpoints.append(
                qmodels.PointStruct(
                    id=pt["id"],
                    vector={
                        "korean_dense": pt["payload"].get("dense", [0.0] * 1024),
                        "korean_sparse": qmodels.SparseVector(
                            indices=pt["payload"].get("sparse_indices", [1]),
                            values=pt["payload"].get("sparse_values", [1.0]),
                        ),
                    },
                    payload={
                        k: v
                        for k, v in pt["payload"].items()
                        if k not in ("dense", "sparse_indices", "sparse_values")
                    },
                )
            )
        self.client.upsert(collection_name=collection_name, points=qpoints)

    def verify_contract(
        self, *, expected: ExpectedIndexContract
    ) -> VerifiedCollectionHandle:
        try:
            aliases = self.client.get_aliases()
            target_coll = None
            for a in aliases.aliases:
                if a.alias_name == "eps_language_phrases":
                    target_coll = a.collection_name
                    break

            if target_coll is None:
                if self.client.collection_exists("eps_language_phrases"):
                    target_coll = "eps_language_phrases"
                else:
                    raise ValueError("RETRIEVAL_UNAVAILABLE")

            info = self.client.get_collection(collection_name=target_coll)
        except ValueError:
            raise
        except Exception as err:
            raise ValueError("RETRIEVAL_UNAVAILABLE") from err

        # Verify vectors schema
        vconfig = info.config.params.vectors
        if isinstance(vconfig, dict) and "korean_dense" in vconfig:
            dense_param = vconfig["korean_dense"]
            dist_str = str(getattr(dense_param, "distance", "")).upper()
            if (
                dense_param.size != 1024
                or ("COSINE" not in dist_str)
            ):
                raise ValueError("RETRIEVAL_SCHEMA_MISMATCH")
        else:
            raise ValueError("RETRIEVAL_SCHEMA_MISMATCH")

        sparse_config = info.config.params.sparse_vectors
        if not (isinstance(sparse_config, dict) and "korean_sparse" in sparse_config):
            raise ValueError("RETRIEVAL_SCHEMA_MISMATCH")

        point_count = info.points_count or 0
        if point_count <= 0:
            raise ValueError("RETRIEVAL_UNAVAILABLE")

        # Exact provenance filters verification
        ds_count = self.client.count(
            collection_name=target_coll,
            count_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="dataset_revision",
                        match=qmodels.MatchValue(value=expected.dataset_revision),
                    )
                ]
            ),
        ).count

        if ds_count != point_count:
            raise ValueError("RETRIEVAL_DATASET_MISMATCH")

        prov_count = self.client.count(
            collection_name=target_coll,
            count_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="embedding_model_repo",
                        match=qmodels.MatchValue(value=expected.embedding_model_repo),
                    ),
                    qmodels.FieldCondition(
                        key="embedding_model_revision",
                        match=qmodels.MatchValue(
                            value=expected.embedding_model_revision
                        ),
                    ),
                    qmodels.FieldCondition(
                        key="index_contract_version",
                        match=qmodels.MatchValue(
                            value=expected.index_contract_version
                        ),
                    ),
                ]
            ),
        ).count

        if prov_count != point_count:
            raise ValueError("RETRIEVAL_INDEX_PROVENANCE_MISMATCH")

        return VerifiedCollectionHandle(
            collection_name=target_coll,
            dataset_version=expected.dataset_revision,
            embedding_model_repo=expected.embedding_model_repo,
            embedding_model_revision=expected.embedding_model_revision,
            index_contract_version=expected.index_contract_version,
            point_count=point_count,
        )

    def search_many(
        self,
        queries: Sequence[tuple[SearchQuery, HybridVector]],
        *,
        target_language: SupportedLanguage,
        collection: VerifiedCollectionHandle,
    ) -> tuple[PerQueryRanking, ...]:
        requests = []
        for _sq, vector in queries:
            filter_conditions = [
                qmodels.FieldCondition(
                    key="target_language",
                    match=qmodels.MatchValue(value=target_language),
                ),
                qmodels.FieldCondition(
                    key="quality_status",
                    match=qmodels.MatchValue(value="verified"),
                ),
                qmodels.FieldCondition(
                    key="dataset_revision",
                    match=qmodels.MatchValue(value=collection.dataset_version),
                ),
            ]
            qfilter = qmodels.Filter(must=filter_conditions)

            prefetch = [
                qmodels.Prefetch(
                    query=vector.dense,
                    using="korean_dense",
                    limit=40,
                    filter=qfilter,
                ),
                qmodels.Prefetch(
                    query=qmodels.SparseVector(
                        indices=list(vector.sparse_indices),
                        values=list(vector.sparse_values),
                    ),
                    using="korean_sparse",
                    limit=40,
                    filter=qfilter,
                ),
            ]

            req = qmodels.QueryRequest(
                prefetch=prefetch,
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=30,
                with_payload=[
                    "source_record_id",
                    "korean_text",
                    "translated_text",
                    "target_language",
                    "eps_language_code",
                    "source_page",
                    "dataset_revision",
                    "content_hash",
                    "quality_status",
                    "source",
                    "source_url",
                ],
                with_vector=False,
            )
            requests.append(req)

        results = self.client.query_batch_points(
            collection_name=collection.collection_name, requests=requests
        )

        rankings = []
        for (sq, _), batch_res in zip(queries, results, strict=True):
            candidates = []
            for rank, pt in enumerate(batch_res.points):
                p = pt.payload or {}
                ref = EpsReference(
                    point_id=str(pt.id),
                    source_record_id=str(p.get("source_record_id", pt.id)),
                    korean_text=str(p.get("korean_text", "")),
                    translated_text=str(p.get("translated_text", "")),
                    target_language=p.get("target_language", target_language),
                    eps_language_code=p.get("eps_language_code", "01"),
                    source_page=int(p.get("source_page", 1)),
                    dataset_revision=str(p.get("dataset_revision", "")),
                    content_hash=str(p.get("content_hash", "")),
                    quality_status=str(p.get("quality_status", "verified")),
                    source="EPS",
                    source_url=str(p.get("source_url") or "https://eps.go.kr"),
                )
                cand = RankedCandidate(
                    reference=ref, rank=rank, score=float(pt.score or 0.0)
                )
                candidates.append(cand)
            rankings.append(
                PerQueryRanking(query_kind=sq.kind, candidates=tuple(candidates))
            )

        return tuple(rankings)

    def swap_alias(self, alias_name: str, collection_name: str) -> None:
        self.client.update_collection_aliases(
            change_aliases=[
                qmodels.CreateAliasOperation(
                    create_alias=qmodels.CreateAlias(
                        collection_name=collection_name, alias_name=alias_name
                    )
                )
            ]
        )
