from typing import TypedDict

from .contracts import (
    ComponentValidation,
    LanguageAssistantInput,
    LanguageAssistantOutput,
    SupportedLanguage,
    WarningItem,
)
from .protected_facts import ProtectedFacts


class LanguageAssistantState(TypedDict, total=False):
    input: LanguageAssistantInput
    target_language: SupportedLanguage
    normalization_warnings: tuple[WarningItem, ...]
    protected_facts: ProtectedFacts
    standard_korean_text: str
    standard_validation: ComponentValidation
    output: LanguageAssistantOutput
