"""Common error types exposed across application boundaries."""


class StagedServiceError(RuntimeError):
    """Expected service failure with a stable processing-stage identifier."""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.code = code or stage
        self.retryable = retryable
