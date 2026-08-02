import json
from pathlib import Path

from pydantic import BaseModel

from app.agents.language.contracts import LanguageAssistantInput, LanguageAssistantOutput

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "contracts"


def write_schema(model: type[BaseModel], path: Path) -> None:
    path.write_text(
        json.dumps(
            model.model_json_schema(mode="validation"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    write_schema(
        LanguageAssistantInput,
        SCHEMA_DIR / "language-assistant-input.schema.json",
    )
    write_schema(
        LanguageAssistantOutput,
        SCHEMA_DIR / "language-assistant-output.schema.json",
    )


if __name__ == "__main__":
    main()
