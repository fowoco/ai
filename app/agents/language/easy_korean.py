from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from app.agents.language.context_pack import (
    ContextPack,
    ContextPackSelection,
    load_context_pack,
)
from app.agents.language.contracts import (
    ComponentGenerationStatus,
    ComponentValidation,
    FrozenContract,
    LanguageExecutionPolicy,
    RequestContext,
    WarningCode,
    WarningItem,
)
from app.agents.language.generation.models import (
    EasyKoreanDraft,
    StructuredGenerator,
)
from app.agents.language.ports import SemanticValidationPort
from app.agents.language.protected_facts import ProtectedFacts
from app.agents.language.validation import BoundedCorrectionController


class EasyKoreanResult(FrozenContract):
    text: str
    status: ComponentGenerationStatus
    validation: ComponentValidation
    warnings: tuple[WarningItem, ...]
    attempt_count: int = Field(ge=0, le=3)
    used_standard_fallback: bool
    context_pack_version: str
    prompt_version: str


class EasyBranchInput(TypedDict):
    request_context: RequestContext
    protected_facts: ProtectedFacts
    standard_korean_text: str


class EasyBranchOutput(TypedDict):
    easy_result: EasyKoreanResult


class EasyBranchState(TypedDict, total=False):
    request_context: RequestContext
    protected_facts: ProtectedFacts
    standard_korean_text: str
    context_pack: ContextPack | None
    context_selection: ContextPackSelection | None
    context_pack_version: str
    easy_result: EasyKoreanResult


def render_easy_korean_text(draft: EasyKoreanDraft, context: RequestContext) -> str:
    """Render field-wise Easy Korean draft into canonical structured Markdown text."""
    lines = [
        f"신청 사유: {draft.request_reason}",
        "필요한 서류:",
    ]
    for item in draft.requested_items:
        lines.append(f"- {item}")
    lines.append(f"제출 기한: {context.deadline.isoformat()}")
    lines.append(f"제출 방법: {draft.submission_method}")
    return "\n".join(lines)


def build_easy_korean_subgraph(
    *,
    generator: StructuredGenerator,
    validator: SemanticValidationPort,
    policy: LanguageExecutionPolicy | None = None,
    allow_draft_context_pack: bool = False,
) -> CompiledStateGraph:
    """Build and compile the Easy-Korean Subgraph."""
    exec_policy = policy or LanguageExecutionPolicy()

    def select_context_pack_node(state: EasyBranchState) -> dict[str, object]:
        try:
            pack = load_context_pack(allow_draft=allow_draft_context_pack)
            selection = pack.select_context(state["standard_korean_text"])
            return {
                "context_pack": pack,
                "context_selection": selection,
                "context_pack_version": pack.pack_version,
            }
        except Exception:
            # Unapproved or unavailable context pack -> instant fallback without provider call
            fallback_result = EasyKoreanResult(
                text=state["standard_korean_text"],
                status="warning",
                validation=ComponentValidation(status="not_run", retry_count=0),
                warnings=(
                    WarningItem(
                        component="easy_korean",
                        code=WarningCode.EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE,
                        message="Context Pack unavailable or unapproved",
                    ),
                    WarningItem(
                        component="easy_korean",
                        code=WarningCode.STANDARD_KOREAN_FALLBACK,
                        message="Using Standard Korean fallback",
                    ),
                ),
                attempt_count=0,
                used_standard_fallback=True,
                context_pack_version="unavailable",
                prompt_version="easy_korean.v1",
            )
            return {
                "context_pack": None,
                "context_selection": None,
                "context_pack_version": "unavailable",
                "easy_result": fallback_result,
            }

    def generate_easy_korean_node(state: EasyBranchState) -> dict[str, object]:
        context = state["request_context"]
        selection = state.get("context_selection")
        pack_version = state.get("context_pack_version", "easy-ko-v1.0.0")

        pack_dict = {}
        if selection:
            pack_dict = {
                "selected_terms": selection.selected_terms,
                "selected_rules": [r.get("description", "") for r in selection.selected_rules],
                "selected_examples": [
                    f"원문: {e.get('input', '')} -> 쉬운말: {e.get('output', '')}"
                    for e in selection.selected_examples
                ],
                "pack_version": pack_version,
            }

        def generate_fn(is_correction: bool, payload: dict[str, object]) -> EasyKoreanDraft:
            if is_correction:
                corr_payload = {
                    **payload,
                    "context_pack": pack_dict,
                }
                return generator.generate(
                    operation="correction",
                    payload=corr_payload,
                    response_model=EasyKoreanDraft,
                )

            gen_payload = {
                "request_context": {
                    "request_reason": context.request_reason,
                    "requested_items": list(context.requested_items),
                    "deadline": context.deadline.isoformat(),
                    "submission_method": context.submission_method,
                },
                "standard_korean_text": state["standard_korean_text"],
                "context_pack": pack_dict,
            }
            return generator.generate(
                operation="easy_korean",
                payload=gen_payload,
                response_model=EasyKoreanDraft,
            )

        controller = BoundedCorrectionController(policy=exec_policy)
        correction_result = controller.run(
            component="easy_korean",
            request_context=context,
            target_language=None,
            generate_fn=generate_fn,
            validator=validator,
            draft_model=EasyKoreanDraft,
        )

        if correction_result.draft is None:
            # Generation failed hard after attempts
            easy_result = EasyKoreanResult(
                text=state["standard_korean_text"],
                status="warning",
                validation=ComponentValidation(status="not_run", retry_count=0),
                warnings=(
                    WarningItem(
                        component="easy_korean",
                        code=WarningCode.EASY_KOREAN_GENERATION_FAILED,
                        message="Easy Korean generation failed",
                    ),
                    WarningItem(
                        component="easy_korean",
                        code=WarningCode.STANDARD_KOREAN_FALLBACK,
                        message="Using Standard Korean fallback",
                    ),
                ),
                attempt_count=correction_result.retry_count,
                used_standard_fallback=True,
                context_pack_version=pack_version,
                prompt_version="easy_korean.v1",
            )
            return {"easy_result": easy_result}

        # Render draft text
        rendered_text = render_easy_korean_text(
            correction_result.draft,  # type: ignore[arg-type]
            context,
        )

        status: ComponentGenerationStatus = "success"
        warnings_list: list[WarningItem] = []

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
                    component="easy_korean",
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
                        component="easy_korean",
                        code=WarningCode.SEMANTIC_VALIDATION_INCONCLUSIVE,
                        message="Semantic validation inconclusive",
                    )
                )

        if correction_result.time_budget_exceeded:
            warnings_list.append(
                WarningItem(
                    component="easy_korean",
                    code=WarningCode.GENERATION_TIME_BUDGET_EXCEEDED,
                    message="Generation time budget exceeded",
                )
            )

        easy_result = EasyKoreanResult(
            text=rendered_text,
            status=status,
            validation=val_status,
            warnings=tuple(warnings_list),
            attempt_count=correction_result.retry_count,
            used_standard_fallback=False,
            context_pack_version=pack_version,
            prompt_version="easy_korean.v1",
        )
        return {"easy_result": easy_result}

    builder = StateGraph(
        EasyBranchState,
        input_schema=EasyBranchInput,
        output_schema=EasyBranchOutput,
    )
    builder.add_node("select_context_pack", select_context_pack_node)
    builder.add_node("generate_easy_korean", generate_easy_korean_node)

    builder.add_edge(START, "select_context_pack")
    builder.add_conditional_edges(
        "select_context_pack",
        lambda state: "END" if "easy_result" in state else "generate_easy_korean",
        {"END": END, "generate_easy_korean": "generate_easy_korean"},
    )
    builder.add_edge("generate_easy_korean", END)

    return builder.compile()


__all__ = [
    "EasyBranchInput",
    "EasyBranchOutput",
    "EasyBranchState",
    "EasyKoreanResult",
    "build_easy_korean_subgraph",
    "render_easy_korean_text",
]
