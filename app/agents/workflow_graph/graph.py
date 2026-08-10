# 재갱신 LangGraph — load → 슈퍼바이저 → 안내문/OCR/초안/대기

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.db.memory import InMemoryDb
from app.db.protocols import IdentityStore, WorkerCompanyLookup

from .nodes.actions import (
    apply_supervisor,
    load_context,
    mark_out_of_scope,
    mark_ask_hr,
    mark_ask_worker,
    mark_guide_placeholder,
    route_from_supervisor,
)
from .nodes.document_generator import DocumentGenerator
from .protocols import LanguageNode, OcrNode
from .state import RenewalState
from .subgraphs import (
    build_document_subgraph,
    build_language_subgraph,
    build_ocr_subgraph,
)


# 재갱신 메인 그래프 생성·컴파일 (서브그래프 + 슈퍼바이저)
def build_renewal_graph(
    *,
    language_node: LanguageNode | None = None,
    ocr_node: OcrNode | None = None,
    guide_node: Any | None = None,
    lookup: WorkerCompanyLookup | None = None,
    store: IdentityStore | None = None,
    document_generator: DocumentGenerator | None = None,
) -> Any:
    db_lookup = lookup or InMemoryDb()
    db_store = store or db_lookup
    language_sg = build_language_subgraph(language_node=language_node)
    ocr_sg = build_ocr_subgraph(ocr_node=ocr_node, store=db_store)
    document_sg = build_document_subgraph(document_generator=document_generator)

    # 컨텍스트 로드 + Intent·Slot (슈퍼바이저 입력)
    def node_load(state: RenewalState) -> dict[str, Any]:
        ctx = load_context(state, lookup=db_lookup)
        merged: RenewalState = {**state, **ctx}  # type: ignore[typeddict-item]
        analysis = language_sg.invoke(merged)
        return {**ctx, **analysis}

    def node_supervisor(state: RenewalState) -> dict[str, Any]:
        return apply_supervisor(state)

    # 안내문 · 태정 Language Assistant (미주입 시 placeholder)
    def node_guide(state: RenewalState) -> dict[str, Any]:
        if guide_node is not None:
            return guide_node(state)
        return mark_guide_placeholder(state)

    def node_ocr(state: RenewalState) -> dict[str, Any]:
        return ocr_sg.invoke(state)

    def node_generate(state: RenewalState) -> dict[str, Any]:
        return document_sg.invoke(state)

    def after_supervisor(state: RenewalState) -> str:
        return route_from_supervisor(state)

    graph: StateGraph = StateGraph(RenewalState)
    graph.add_node("load_context", node_load)
    graph.add_node("supervisor", node_supervisor)
    graph.add_node("guide", node_guide)
    graph.add_node("ask_hr", mark_ask_hr)
    graph.add_node("ask_worker", mark_ask_worker)
    graph.add_node("out_of_scope", mark_out_of_scope)
    graph.add_node("ocr", node_ocr)
    graph.add_node("generate", node_generate)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        after_supervisor,
        {
            "ask_hr": "ask_hr",
            "ask_worker": "guide",
            "generate": "generate",
            "ocr": "ocr",
            "out_of_scope": "out_of_scope",
        },
    )
    graph.add_edge("guide", "ask_worker")
    graph.add_edge("ask_hr", END)
    graph.add_edge("ask_worker", END)
    graph.add_edge("out_of_scope", END)
    graph.add_edge("ocr", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


@lru_cache
# 기본 stub 서브그래프로 컴파일된 메인 그래프 싱글톤
def get_renewal_graph() -> Any:
    return build_renewal_graph()
