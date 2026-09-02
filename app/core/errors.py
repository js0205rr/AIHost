"""Common error types exposed across application boundaries."""


class StagedServiceError(RuntimeError):
    """Expected service failure with a stable processing-stage identifier."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message

