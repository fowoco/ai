from typing import TypedDict

from .contracts import (
    ComponentValidation,
    LanguageAssistantInput,
    LanguageAssistantOutput,
    SupportedLanguage,
    WarningItem,
)
from .easy_korean import EasyKoreanResult
from .protected_facts import ProtectedFacts
from .translation import TranslationResult


class LanguageAssistantState(TypedDict, total=False):
    input: LanguageAssistantInput
    target_language: SupportedLanguage
    normalization_warnings: tuple[WarningItem, ...]
    protected_facts: ProtectedFacts
    standard_korean_text: str
    standard_validation: ComponentValidation
    easy_result: EasyKoreanResult
    translation_result: TranslationResult
    output: LanguageAssistantOutput
