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

    def test_moves_explicit_links_and_preserves_existing_footnotes(self):
        source = "[来源: link](https://example.org/a#method()) 和既有注释[^source-audit-note-1]。\n[来源: other]\n"
        result = source_notes(source)
        self.assertIn("[^source-audit-notex-1]: [来源: link](https://example.org/a#method())", result)
        self.assertIn("[^source-audit-notex-2]: 来源: other", result)
        self.assertEqual(source_notes(result), result)

    def test_nested_links_stay_in_the_footnote(self):
        source = "解释。[来源: [图形系统](https://example.org/a)] [已验证: [`Surface.java`](https://example.org/b)。]\n"
        result = source_notes(source)
        self.assertIn("解释。[^source-audit-note-1] [^source-audit-note-2]", result)
        self.assertIn("[图形系统](https://example.org/a)", result)
        self.assertIn("[`Surface.java`](https://example.org/b)", result)
        self.assertEqual(source_notes(result), result)

    def test_frontmatter_is_unchanged(self):
        frontmatter = '---\ntitle: "[来源: metadata]"\n---\n'
        result = source_notes(frontmatter + '正文。[来源: body]\n')
        self.assertTrue(result.startswith(frontmatter))
        self.assertIn('正文。[^source-audit-note-1]', result)
        self.assertIn('[^source-audit-note-1]: 来源: body', result)


if __name__ == "__main__":
    unittest.main()
