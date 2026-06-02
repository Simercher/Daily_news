def detect_language(text: str | None, default: str = "unknown") -> str:
    if not text:
        return default
    # Lightweight MVP heuristic; production can replace with a model/service.
    return "en" if text.isascii() else default

__all__ = ["detect_language"]
