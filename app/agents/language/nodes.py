from app.agents.language.codes import resolve_target_language
from app.agents.language.contracts import (
    ComponentStatus,
    ComponentValidation,
    GenerationStatus,
    LanguageAssistantOutput,
    LanguageExecutionPolicy,
    RetrievalMetadata,
    ValidationSummary,
    WarningCode,
    WarningItem,
)
from app.agents.language.easy_korean import EasyKoreanResult, build_easy_korean_subgraph
from app.agents.language.formatting import (
    assert_standard_formatter_invariants,
    format_standard_korean,
)
from app.agents.language.generation.models import StructuredGenerator
from app.agents.language.observability import with_fault_isolation
from app.agents.language.ports import EpsRetriever, SemanticValidationPort, TraceSink
from app.agents.language.protected_facts import ProtectedFacts
from app.agents.language.retrieval.models import RetrievalResult
from app.agents.language.state import LanguageAssistantState
from app.agents.language.translation import TranslationResult, build_translation_subgraph


class LanguageNodeSet:
    def __init__(
        self,
        *,
        retriever: EpsRetriever,
        generator: StructuredGenerator,
        semantic_validator: SemanticValidationPort,
        trace_sink: TraceSink,
        execution_policy: LanguageExecutionPolicy,
        allow_draft_context_pack: bool = False,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.semantic_validator = semantic_validator
        self.trace_sink = trace_sink
        self.execution_policy = execution_policy

        self.easy_subgraph = build_easy_korean_subgraph(
            generator=generator,
            validator=semantic_validator,
            policy=execution_policy,
            allow_draft_context_pack=allow_draft_context_pack,
        )

        self.translation_subgraph = build_translation_subgraph(
            retriever=retriever,
            generator=generator,
            validator=semantic_validator,
            policy=execution_policy,
        )

    def validate_and_normalize(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        res = resolve_target_language(inp.preferred_language, inp.nationality_code)
        return {
            "target_language": res.canonical_code,
            "normalization_warnings": res.warnings,
        }

    def resolve_target_language(self, state: LanguageAssistantState) -> dict[str, object]:
        return {}

    def build_protected_facts(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        facts = ProtectedFacts.from_request_context(inp.request_context)
        return {"protected_facts": facts}

    def compose_standard_korean(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        facts = state["protected_facts"]
        std_text = format_standard_korean(inp.request_context, facts)
        std_val = assert_standard_formatter_invariants(inp.request_context, std_text, facts)

        return {
            "standard_korean_text": std_text,
            "standard_validation": std_val,
        }

    def run_easy_branch(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        facts = state["protected_facts"]
        std_text = state["standard_korean_text"]

        branch_input = {
            "request_context": inp.request_context,
            "protected_facts": facts,
            "standard_korean_text": std_text,
        }
        res_dict, warning = with_fault_isolation("easy_korean")(self.easy_subgraph.invoke)(
            branch_input
        )
        if res_dict is not None and "easy_result" in res_dict:
            return {"easy_result": res_dict["easy_result"]}

        fallback_warning = warning or WarningItem(
            component="easy_korean",
            code=WarningCode.EASY_KOREAN_GENERATION_FAILED,
            message="Unhandled exception in easy_korean",
        )
        easy_res = EasyKoreanResult(
            text=std_text,
            status="failed",
            validation=ComponentValidation(
                status="failed",
                missing_items=(),
                corrupted_dates=(),
                corrupted_cardinality=(),
                unauthorized_modifications=(),
                semantic_passed=False,
                failure_reasons=("Subgraph exception isolated",),
            ),
            warnings=(fallback_warning,),
            attempt_count=0,
            used_standard_fallback=True,
            context_pack_version="unknown",
            prompt_version="easy_korean.v1",
        )
        return {"easy_result": easy_res}

    def run_translation_branch(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        facts = state["protected_facts"]
        std_text = state["standard_korean_text"]
        target_lang = state["target_language"]

        branch_input = {
            "request_context": inp.request_context,
            "target_language": target_lang,
            "protected_facts": facts,
            "standard_korean_text": std_text,
        }
        res_dict, warning = with_fault_isolation("translation")(self.translation_subgraph.invoke)(
            branch_input
        )
        if res_dict is not None and "translation_result" in res_dict:
            return {"translation_result": res_dict["translation_result"]}

        fallback_warning = warning or WarningItem(
            component="translation",
            code=WarningCode.TRANSLATION_GENERATION_FAILED,
            message="Unhandled exception in translation",
        )
        empty_retrieval = RetrievalResult(
            query_strategies=(),
            candidates=(),
            contexts=(),
            warnings=(fallback_warning,),
            degraded_components=("retrieval",),
            fallback_used=True,
            dataset_version="eps_language_db_v1",
        )
        trans_res = TranslationResult(
            text=None,
            status="failed",
            validation=ComponentValidation(
                status="failed",
                missing_items=(),
                corrupted_dates=(),
                corrupted_cardinality=(),
                unauthorized_modifications=(),
                semantic_passed=False,
                failure_reasons=("Subgraph exception isolated",),
            ),
            warnings=(fallback_warning,),
            attempt_count=0,
            retrieval=empty_retrieval,
            prompt_version="translation.v1",
        )
        return {"translation_result": trans_res}

    def assemble_output(self, state: LanguageAssistantState) -> dict[str, object]:
        inp = state["input"]
        target_lang = state["target_language"]
        std_text = state["standard_korean_text"]
        std_val = state["standard_validation"]
        easy_res = state["easy_result"]
        trans_res = state["translation_result"]
        norm_warnings = state.get("normalization_warnings", ())

        # Calculate overall status
        if trans_res.text is None or trans_res.status == "failed":
            overall_status: GenerationStatus = "failed"
        elif (
            easy_res.status == "success"
            and trans_res.status == "success"
            and not easy_res.used_standard_fallback
            and not trans_res.retrieval.fallback_used
            and not easy_res.warnings
            and not trans_res.warnings
        ):
            overall_status = "success"
        else:
            overall_status = "warning"

        requires_review = overall_status != "success"

        # Deduplicate warnings deterministically preserving order
        merged_warnings: list[WarningItem] = list(norm_warnings)
        for w in easy_res.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)
        for w in trans_res.warnings:
            if w not in merged_warnings:
                merged_warnings.append(w)

        top_contexts = trans_res.retrieval.contexts[:5]
        ref_ids = tuple(c.reference.point_id for c in top_contexts)

        retrieval_meta = RetrievalMetadata(
            dataset_version=trans_res.retrieval.dataset_version,
            query_strategies=trans_res.retrieval.query_strategies,
            reference_ids=ref_ids,
            reference_count=len(ref_ids),
            fallback_used=trans_res.retrieval.fallback_used,
            degraded_components=trans_res.retrieval.degraded_components,
        )

        output = LanguageAssistantOutput(
            worker_id=inp.worker_id,
            target_language=target_lang,
            generation_status=overall_status,
            requires_human_review=requires_review,
            standard_korean_text=std_text,
            easy_korean_text=easy_res.text,
            translated_text=trans_res.text,
            component_status=ComponentStatus(
                standard_korean="success",
                easy_korean=easy_res.status,
                translation=trans_res.status,
            ),
            validation=ValidationSummary(
                standard_korean=std_val,
                easy_korean=easy_res.validation,
                translation=trans_res.validation,
            ),
            warnings=tuple(merged_warnings),
            retrieval_metadata=retrieval_meta,
        )
        return {"output": output}


def build_language_nodes(
    *,
    retriever: EpsRetriever,
    generator: StructuredGenerator,
    semantic_validator: SemanticValidationPort,
    trace_sink: TraceSink,
    execution_policy: LanguageExecutionPolicy,
    allow_draft_context_pack: bool = False,
) -> LanguageNodeSet:
    return LanguageNodeSet(
        retriever=retriever,
        generator=generator,
        semantic_validator=semantic_validator,
        trace_sink=trace_sink,
        execution_policy=execution_policy,
        allow_draft_context_pack=allow_draft_context_pack,
    )
