"""Errors written for an LLM reader: say what went wrong AND what to try next."""


class _LLMReadableError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        self.hint = hint
        text = message if not hint else f"{message} Hint: {hint}"
        super().__init__(text)


class ToolInputError(_LLMReadableError, ValueError):
    """The caller passed bad arguments."""


class ToolExecutionError(_LLMReadableError, RuntimeError):
    """The arguments were fine, but the operation failed."""