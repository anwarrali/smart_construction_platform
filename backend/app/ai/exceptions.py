class AIServiceError(Exception):
    """Base exception safe to translate into an API error."""


class AIConfigurationError(AIServiceError):
    pass


class InvalidAudioError(AIServiceError):
    pass


class AIProviderError(AIServiceError):
    pass


class AIProviderTimeoutError(AIProviderError):
    pass
