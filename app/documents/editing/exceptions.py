"""Errors raised by format-dispatching document editing workflows."""


class DocumentEditingError(ValueError):
    """A document cannot be edited or generated with the supplied command."""


class DocumentTemplateNotFoundError(DocumentEditingError):
    """A requested or uploaded document template is not registered."""


class DocumentEditingNotSupportedError(DocumentEditingError):
    """The detected document format does not support structured editing."""


__all__ = [
    "DocumentEditingError",
    "DocumentEditingNotSupportedError",
    "DocumentTemplateNotFoundError",
]
