import unittest
from githug.reading import formatted_lines

class ReadingTests(unittest.TestCase):
    def test_headings_lists_and_emphasis(self):
        rows=list(formatted_lines('### 見出し\n* **重要**な説明と `code.py`'))
        self.assertEqual(rows[0],[('heading','見出し')])
        self.assertEqual(''.join(t for _,t in rows[1]),'• 重要な説明と code.py')
        self.assertIn(('bold','重要'),rows[1])

    def test_code_remains_literal_and_html_is_never_interpreted(self):
        rows=list(formatted_lines('```python\n# literal **x**\n```\n<script>x</script>'))
        self.assertEqual(rows[0],[('code','# literal **x**')])
        self.assertEqual(rows[1],[('','<script>x</script>')])
