import pathlib
import tempfile
import unittest

from life_agent.metrics import master_checklist


SAMPLE = """# Life OS — Master Architecture

## 5. What changed

Some other section.

---

## 6. Master sequencing checklist

- [ ] Job OS Phase 2 corrected (Beghou eligibility/relevance conflation fixed, deadline extraction diagnosed) — **awaiting return/review**
- [x] Job OS Phase 3 (classification audit) run and approved
- [ ] People Discovery fetchability check (all 3 sources) completed and reported

No step above may be skipped or reordered without the user explicitly saying so.

---

## 7. Explicit permanent exclusions

- Autonomous application submission or message sending of any kind.
"""


class TestMasterChecklist(unittest.TestCase):
    def test_parses_only_section_six(self):
        items = master_checklist.read_master_checklist(path=pathlib.Path("n/a") if False else self._write(SAMPLE))
        # §7 bullets must not leak in
        self.assertEqual(len(items), 3)
        self.assertTrue(all("Autonomous application submission" not in i["label"] for i in items))

    def test_done_flags_and_notes(self):
        items = master_checklist.read_master_checklist(self._write(SAMPLE))
        self.assertFalse(items[0]["done"])
        self.assertTrue(items[1]["done"])
        self.assertEqual(items[0]["note"], "awaiting return/review")
        self.assertEqual(items[1]["note"], "")

    def test_workstreams_status_summary(self):
        status = master_checklist.workstreams_status(self._write(SAMPLE))
        self.assertEqual(status["total"], 3)
        self.assertEqual(status["done"], 1)
        self.assertEqual(status["current"], "Job OS Phase 2 corrected (Beghou eligibility/relevance conflation fixed, deadline extraction diagnosed)")
        self.assertFalse(status["complete"])

    def test_missing_document_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "nope.md"
            with self.assertRaises(FileNotFoundError):
                master_checklist.read_master_checklist(missing)

    def test_real_document_parses(self):
        # The actual doc in this repo must parse to 8 ordered steps.
        items = master_checklist.read_master_checklist()
        self.assertEqual(len(items), 8)
        self.assertTrue(all(set(i) == {"label", "done", "note"} for i in items))
        self.assertFalse(any(i["done"] for i in items))

    @staticmethod
    def _write(content: str) -> pathlib.Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        tmp.write(content)
        tmp.close()
        return pathlib.Path(tmp.name)


if __name__ == "__main__":
    unittest.main()
