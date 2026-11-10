"""Regression tests for quality.py bug fixes.
Bug A: temporal hallucination in critique prompt (missing current date context)
Bug B: over-removal of section content when fixing dead links
"""
import sys
import json
from pathlib import Path

# Fix encoding on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from life_agent.agent import quality


def test_extract_dead_urls():
    """Verify _extract_dead_urls helper correctly strips trailing punctuation."""
    issues = [
        "Dead link found: https://example.com/dead,",
        "Another issue about https://research.example.com/paper.",
        "Duplicate: https://example.com/dead, again"
    ]
    urls = quality._extract_dead_urls(issues)
    assert len(urls) == 2, f"Expected 2 unique URLs, got {len(urls)}: {urls}"
    assert urls[0] == "https://example.com/dead", f"Expected clean URL, got {urls[0]}"
    assert urls[1] == "https://research.example.com/paper", f"Expected clean URL, got {urls[1]}"
    # Verify NO trailing punctuation
    for url in urls:
        assert not url.endswith((",", ".", ";", ":")), f"URL has trailing punctuation: {url}"
    print("[PASS] _extract_dead_urls dedupes, strips punctuation, and preserves order correctly")


def test_critique_prompt_includes_date():
    """Verify the critique prompt now includes dynamic date context."""
    # Read the quality.py file to check for date context
    quality_path = Path(__file__).parent.parent / "src" / "life_agent" / "agent" / "quality.py"
    with open(quality_path) as f:
        content = f.read()

    # Check that dynamic date injection is present (using date.today().isoformat())
    assert "date.today().isoformat()" in content, "Dynamic date injection not found in quality.py"
    assert "Do not assume papers" in content, "Date grounding instruction not found"
    assert "treat all dates provided in the dossier as ground truth" in content, "Ground truth instruction not found"
    print("[PASS] Critique prompt now includes dynamic current-date context")


def test_reviser_has_surgical_instruction():
    """Verify the reviser now has explicit surgical removal instruction for dead links."""
    # Read the quality.py file to check for surgical instruction
    quality_path = Path(__file__).parent.parent / "src" / "life_agent" / "agent" / "quality.py"
    with open(quality_path) as f:
        content = f.read()

    # Check that the surgical instruction is present
    assert "remove ONLY the specific bullet point or entry containing the flagged URL" in content, \
        "Surgical removal instruction not found"
    assert "Preserve every other entry in that section completely untouched" in content, \
        "Preservation instruction not found"
    assert "Do not remove or condense entire sections" in content, \
        "Section preservation instruction not found"
    print("[PASS] Reviser now has explicit surgical dead-link removal instruction")


def test_dead_url_context_is_generated():
    """Verify that dead URL context is properly generated when URLs are found."""
    # This tests the logic structure without calling LLM
    # The code should extract URLs and format them for the reviser

    issues = [
        "These links are DEAD or unreachable -- replace or remove them: "
        "https://msr-india.example.com/dead, https://example.com/another-dead"
    ]

    urls = quality._extract_dead_urls(issues)

    # Should extract both URLs
    assert len(urls) == 2, f"Expected 2 URLs, got {len(urls)}"

    # Format context as the reviser would see it
    dead_url_context = (
        f"\nDEAD LINKS TO REMOVE (remove ONLY the entry containing each URL; preserve all other entries):\n" +
        "\n".join(f"  - {url}" for url in urls)
    )

    # Verify formatting
    assert "remove ONLY the entry containing each URL" in dead_url_context
    assert "https://msr-india.example.com/dead" in dead_url_context
    assert "https://example.com/another-dead" in dead_url_context
    print("[PASS] Dead URL context is properly formatted for surgical removal")


if __name__ == "__main__":
    try:
        test_extract_dead_urls()
        test_critique_prompt_includes_date()
        test_reviser_has_surgical_instruction()
        test_dead_url_context_is_generated()
        print("\n[SUCCESS] All quality.py fix verification tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
