"""Load a prompt template from prompts/ and fill {{PLACEHOLDERS}}."""
from pathlib import Path

def _prompts_dir() -> Path:
    root_prompts = Path(__file__).resolve().parents[3] / "prompts"
    if root_prompts.is_dir():
        return root_prompts
    package_prompts = Path(__file__).parent / "prompts"
    if package_prompts.is_dir():
        return package_prompts
    return Path("prompts")


PROMPTS_DIR = _prompts_dir()


def load(name: str, **placeholders: str) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
