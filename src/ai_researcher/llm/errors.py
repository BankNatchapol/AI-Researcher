"""Named failures raised by the model gateway."""


class ModelCallError(RuntimeError):
    """Raised when a model CLI cannot complete successfully."""


class ModelTimeoutError(ModelCallError):
    """Raised when a model CLI exceeds its configured timeout."""


class ModelOutputError(ModelCallError):
    """Raised when a model CLI returns output the gateway cannot parse."""
