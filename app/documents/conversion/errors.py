"""Errors shared by conversion orchestration and external engines."""


class DocumentConversionError(RuntimeError):
    """Base error for cross-format conversion failures."""


class ConversionNotSupportedError(DocumentConversionError):
    """No converter is registered for a requested source/target pair."""


class ConversionEngineUnavailableError(DocumentConversionError):
    """A configured external conversion engine cannot be started."""


__all__ = [
    "ConversionEngineUnavailableError",
    "ConversionNotSupportedError",
    "DocumentConversionError",
]
