import unittest

from tools.source_notes import source_notes


class SourceNotesTest(unittest.TestCase):
    def test_moves_records_and_deduplicates_them(self):
        record = "[来源: https://example.org/a；已验证: src/main.cpp @ v1]"
        result = source_notes(f"第一句。{record}\n第二句。{record}\n")
        self.assertEqual(result.count("[^source-audit-note-1]"), 3)
        self.assertIn("<https://example.org/a>", result)
        self.assertIn("已验证: src/main.cpp @ v1", result)
        self.assertNotIn(record, result)
        self.assertEqual(source_notes(result), result)

    def test_preserves_fenced_indented_and_inline_code(self):
        source = ("`[来源: inline]`\n\n```text\n[来源: fenced]\n```\n"
                  "    [来源: indented]\n正常文字。[已验证: `path`]\n")
        result = source_notes(source)
        self.assertIn("`[来源: inline]`", result)
        self.assertIn("```text\n[来源: fenced]\n```", result)
        self.assertIn("    [来源: indented]", result)
        self.assertIn("正常文字。[^source-audit-note-1]", result)
        self.assertIn("已验证: `path`", result)

    def test_preserves_explicit_links_and_existing_footnotes(self):
        source = "[来源: link](https://example.org) 和既有注释[^source-audit-note-1]。\n[来源: other]\n"
        result = source_notes(source)
        self.assertIn("[来源: link](https://example.org)", result)
        self.assertIn("[^source-audit-notex-1]: 来源: other", result)


if __name__ == "__main__":
    unittest.main()
