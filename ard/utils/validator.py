"""Input validation — checks that the Rough Idea is a non-empty string before graph execution."""


def validate_input(rough_idea: str) -> str:
    """Validate that the rough idea is a non-empty string.

    Returns the stripped input on success.
    Raises ValueError if input is empty or whitespace-only.
    """
    if not isinstance(rough_idea, str) or not rough_idea.strip():
        raise ValueError("Rough idea must be a non-empty string.")
    return rough_idea.strip()
