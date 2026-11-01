import tempfile
import unittest
from pathlib import Path
from githug.core import Project, git, validate_url, ComparisonCancelled

class SnapshotTests(unittest.TestCase):
    def test_url_rejects_commands_and_other_hosts(self):
        for url in ['--upload-pack=bad', 'https://example.com/a/b', 'https://github.com/a/../']:
            with self.assertRaises(ValueError): validate_url(url)
        self.assertEqual(validate_url('https://github.com/ISUKA-SSP/GitHug.git')[1], 'ISUKA-SSP__GitHug')

    def test_snapshots_independent_and_comparison_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            git('init', source)
            git('config', 'user.name', 'Test', cwd=source)
            git('config', 'user.email', 'test@example.com', cwd=source)
            (source / 'hello.txt').write_text('first', encoding='utf-8')
            git('add', '.', cwd=source)
            git('commit', '-m', 'first', cwd=source)
            sha = git('rev-parse', 'HEAD', cwd=source).strip()
            project = Project(root / 'managed', 'https://github.com/test/project')
            project.base.mkdir(parents=True)
            git('clone', '--mirror', source, project.cache)
            first = Path(project.snapshot(sha))
            (first / 'hello.txt').write_text('my edit', encoding='utf-8')
            second = Path(project.snapshot(sha))
            self.assertNotEqual(first, second)
            self.assertEqual((second / 'hello.txt').read_text(), 'first')
            self.assertEqual(project.compare(sha, first), [('内容が異なる', 'hello.txt')])
            self.assertEqual((first / 'hello.txt').read_text(), 'my edit')
            self.assertEqual(len(project.snapshots()), 2)
            progress = []
            project.compare(sha, first, progress=lambda *args: progress.append(args))
            self.assertTrue(any(row[0] == '履歴と内容を比較' and row[2] == 1 for row in progress))
            self.assertEqual(progress[-1][0], '比較完了')
            with self.assertRaises(ComparisonCancelled):
                project.compare(sha, first, cancelled=lambda: True)
            self.assertEqual((first / 'hello.txt').read_text(), 'my edit')
            with self.assertRaises(ValueError): project.snapshot('--all')

if __name__ == '__main__': unittest.main()
