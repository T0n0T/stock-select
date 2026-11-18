from __future__ import annotations

SUPPORTED_METHODS = ("b2", "scm", "pbm")


def validate_method(method: str) -> str:
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"unsupported method: {method}; expected b2, scm, or pbm")
    return method
