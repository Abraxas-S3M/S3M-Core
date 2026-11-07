"""Isolation runtime errors for defensive agent sandboxing."""


class IsolationUnavailableError(RuntimeError):
    """
    Raised when production mode cannot obtain a real isolation runtime.

    Tactical context:
    Proceeding without a sandbox in contested environments expands blast radius;
    production deployments must fail closed instead of silently degrading.
    """
