import importlib.resources


def load_prompt(operation: str) -> str:
    """Load versioned system prompt for a generation operation using importlib.resources."""
    filename = f"{operation}.v1.md"
    resource_path = importlib.resources.files("app.agents.language.resources.prompts").joinpath(
        filename
    )
    if not resource_path.is_file():
        raise FileNotFoundError(f"Prompt file for operation '{operation}' not found: {filename}")
    return resource_path.read_text(encoding="utf-8")


__all__ = ["load_prompt"]
