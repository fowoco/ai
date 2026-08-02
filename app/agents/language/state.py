from typing import TypedDict

from .contracts import (
    LanguageAssistantInput,
    LanguageAssistantOutput,
    SupportedLanguage,
    WarningItem,
)


class LanguageAssistantState(TypedDict, total=False):
    input: LanguageAssistantInput
    target_language: SupportedLanguage
    normalization_warnings: tuple[WarningItem, ...]
    output: LanguageAssistantOutput
