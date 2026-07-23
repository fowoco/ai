"""Application-facing errors for HWP5 template and generation workflows."""


class Hwp5TemplateError(ValueError):
    """A template map is invalid or does not match the selected HWP file."""


class Hwp5TemplateNotFoundError(Hwp5TemplateError):
    """No bundled template matches a requested ID or source file."""


__all__ = ["Hwp5TemplateError", "Hwp5TemplateNotFoundError"]
