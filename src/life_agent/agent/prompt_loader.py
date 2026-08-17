"""Load a prompt template from prompts/ and fill {{PLACEHOLDERS}}."""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load(name: str, **placeholders: str) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
