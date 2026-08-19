from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from app.agents.language.contracts import (
    ComponentGenerationStatus,
    ComponentValidation,
    FrozenContract,
    LanguageExecutionPolicy,
    RequestContext,
    SupportedLanguage,
    WarningCode,
    WarningItem,
)
from app.agents.language.generation.models import (
    StructuredGenerator,
    TranslationDraft,
)
from app.agents.language.ports import EpsRetriever, SemanticValidationPort
from app.agents.language.protected_facts import ProtectedFacts
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import RetrievalResult
from app.agents.language.validation import BoundedCorrectionController


class TranslationResult(FrozenContract):
    text: str | None
    status: ComponentGenerationStatus
    validation: ComponentValidation
    warnings: tuple[WarningItem, ...]
    attempt_count: int = Field(ge=0, le=3)
    retrieval: RetrievalResult
    prompt_version: str


class TranslationBranchInput(TypedDict):
    request_context: RequestContext
    target_language: SupportedLanguage
    protected_facts: ProtectedFacts
    standard_korean_text: str


class TranslationBranchOutput(TypedDict):
    translation_result: TranslationResult


class TranslationBranchState(TypedDict, total=False):
    request_context: RequestContext
    target_language: SupportedLanguage
    protected_facts: ProtectedFacts
    standard_korean_text: str
    search_queries: tuple[SearchQuery, ...]
    retrieval_result: RetrievalResult
    translation_result: TranslationResult


def build_translation_queries(
    context: RequestContext, standard_korean_text: str
) -> tuple[SearchQuery, ...]:
    """Construct 3 multi-strategy search queries for EPS retrieval."""
    q_canonical = SearchQuery(kind="canonical", text=standard_korean_text)

    items_str = " ".join(context.requested_items)
    q_reason_items = SearchQuery(
        kind="reason_items",
        text=f"{context.request_reason} {items_str}".strip(),
    )

    q_action_deadline = SearchQuery(
        kind="action_deadline",
        text=f"{context.submission_method} {context.deadline.isoformat()}".strip(),
    )

    return (q_canonical, q_reason_items, q_action_deadline)


def render_translation_text(
    draft: TranslationDraft,
    context: RequestContext,
    target_language: SupportedLanguage,
) -> str:
    """Render field-wise translated draft into canonical structured Markdown text."""
    lines = [
        f"Reason: {draft.translated_reason}",
        "Requested Items:",
    ]
    for item in draft.translated_items:
        lines.append(f"- {item}")
    lines.append(f"Deadline: {context.deadline.isoformat()}")
    lines.append(f"Submission Method: {draft.translated_submission_method}")
    return "\n".join(lines)


def build_translation_subgraph(
    *,
    retriever: EpsRetriever,
    generator: StructuredGenerator,
    validator: SemanticValidationPort,
    policy: LanguageExecutionPolicy | None = None,
) -> CompiledStateGraph:
    """Build and compile the Native-Translation Subgraph."""
    exec_policy = policy or LanguageExecutionPolicy()

    def build_multi_queries_node(state: TranslationBranchState) -> dict[str, object]:
        queries = build_translation_queries(
            state["request_context"],
            state["standard_korean_text"],
        )
        return {"search_queries": queries}

    def hybrid_retrieve_node(state: TranslationBranchState) -> dict[str, object]:
        queries = state["search_queries"]
        ret_result = retriever.retrieve(
            queries=queries,
            standard_korean_text=state["standard_korean_text"],
            target_language=state["target_language"],
        )
        return {"retrieval_result": ret_result}

    def generate_translation_node(state: TranslationBranchState) -> dict[str, object]:
        context = state["request_context"]
        target_lang = state["target_language"]
        ret_result = state["retrieval_result"]

        # Limit EPS contexts to top 5 and format as untrusted reference
        top_contexts = ret_result.contexts[:5]
        eps_refs = [
            {
                "point_id": c.reference.point_id,
                "korean_text": c.reference.korean_text,
                "translated_text": c.reference.translated_text,
                "target_language": c.reference.target_language,
                "untrusted_reference": True,
            }
            for c in top_contexts
        ]

        def generate_fn(is_correction: bool, payload: dict[str, object]) -> TranslationDraft:
            if is_correction:
                corr_payload = {
                    **payload,
                    "target_language": target_lang,
                    "eps_references": eps_refs,
                }
                return generator.generate(
                    operation="correction",
                    payload=corr_payload,
                    response_model=TranslationDraft,
                )

            gen_payload = {
                "request_context": {
                    "request_reason": context.request_reason,
                    "requested_items": list(context.requested_items),
                    "deadline": context.deadline.isoformat(),
                    "submission_method": context.submission_method,
                },
                "target_language": target_lang,
                "standard_korean_text": state["standard_korean_text"],
                "eps_references": eps_refs,
            }
            return generator.generate(
                operation="translation",
                payload=gen_payload,
                response_model=TranslationDraft,
            )

        controller = BoundedCorrectionController(policy=exec_policy)
        correction_result = controller.run(
            component="translation",
            request_context=context,
            target_language=target_lang,
            generate_fn=generate_fn,
            validator=validator,
            draft_model=TranslationDraft,
        )

        # Merge warnings deterministically
        warnings_list: list[WarningItem] = list(ret_result.warnings)

        if ret_result.fallback_used:
            has_fallback_warning = any(
                w.code == WarningCode.TRANSLATION_FALLBACK_USED for w in warnings_list
            )
            if not has_fallback_warning:
                warnings_list.append(
                    WarningItem(
                        component="translation",
                        code=WarningCode.TRANSLATION_FALLBACK_USED,
                        message="EPS context omitted, used general LLM translation fallback",
                    )
                )

        if correction_result.draft is None:
            # Generation failed hard after attempts
            warnings_list.append(
                WarningItem(
                    component="translation",
                    code=WarningCode.TRANSLATION_GENERATION_FAILED,
                    message=(
                        "Translation generation failed: "
                        f"{correction_result.generation_error_code or 'GENERATION_FAILED'}"
                    ),
                )
            )
            translation_result = TranslationResult(
                text=None,
                status="failed",
                validation=ComponentValidation(status="not_run", retry_count=0),
                warnings=tuple(warnings_list),
                attempt_count=correction_result.retry_count,
                retrieval=ret_result,
                prompt_version="translation.v1",
            )
            return {"translation_result": translation_result}

        # Render draft text
        rendered_text = render_translation_text(
            correction_result.draft,  # type: ignore[arg-type]
            context,
            target_lang,
        )

        status: ComponentGenerationStatus = "success"

        if correction_result.status == "passed":
            status = "success"
            val_status = ComponentValidation(
                status="passed",
                retry_count=correction_result.retry_count,
            )
        elif correction_result.status == "failed":
            status = "warning"
            val_status = ComponentValidation(
                status="failed",
                failed_checks=correction_result.failed_checks,
                retry_count=correction_result.retry_count,
            )
            warnings_list.append(
                WarningItem(
                    component="translation",
                    code=WarningCode.VALIDATION_RETRY_EXCEEDED,
                    message="Validation retry limit reached",
                )
            )
        else:
            status = "warning"
            val_status = ComponentValidation(
                status="inconclusive",
                inconclusive_checks=correction_result.inconclusive_checks,
                retry_count=correction_result.retry_count,
            )
            if WarningCode.SEMANTIC_VALIDATION_INCONCLUSIVE in correction_result.warnings:
                warnings_list.append(
                    WarningItem(
                        component="translation",
                        code=WarningCode.SEMANTIC_VALIDATION_INCONCLUSIVE,
                        message="Semantic validation inconclusive",
                    )
                )

        if correction_result.time_budget_exceeded:
            warnings_list.append(
                WarningItem(
                    component="translation",
                    code=WarningCode.GENERATION_TIME_BUDGET_EXCEEDED,
                    message="Generation time budget exceeded",
                )
            )

        translation_result = TranslationResult(
            text=rendered_text,
            status=status,
            validation=val_status,
            warnings=tuple(warnings_list),
            attempt_count=correction_result.retry_count,
            retrieval=ret_result,
            prompt_version="translation.v1",
        )
        return {"translation_result": translation_result}

    builder = StateGraph(
        TranslationBranchState,
        input_schema=TranslationBranchInput,
        output_schema=TranslationBranchOutput,
    )
    builder.add_node("build_multi_queries", build_multi_queries_node)
    builder.add_node("hybrid_retrieve", hybrid_retrieve_node)
    builder.add_node("generate_translation", generate_translation_node)

    builder.add_edge(START, "build_multi_queries")
    builder.add_edge("build_multi_queries", "hybrid_retrieve")
    builder.add_edge("hybrid_retrieve", "generate_translation")
    builder.add_edge("generate_translation", END)

    return builder.compile()


__all__ = [
    "TranslationBranchInput",
    "TranslationBranchOutput",
    "TranslationBranchState",
    "TranslationResult",
    "build_translation_queries",
    "build_translation_subgraph",
    "render_translation_text",
]
