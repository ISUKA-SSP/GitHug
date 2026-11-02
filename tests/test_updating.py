import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from githug.core import Project, git
from githug.updating import inspect_update, apply_update, UpdateConflict, atomic_json

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / 'source'
        self.source = source
        source.mkdir()
        git('init', source)
        git('config', 'user.name', 'Test', cwd=source)
        git('config', 'user.email', 'test@example.com', cwd=source)
        (source / 'hello.txt').write_text('old', encoding='utf-8')
        (source / 'old_only.txt').write_text('old file', encoding='utf-8')
        git('add', '.', cwd=source)
        git('commit', '-m', 'old', cwd=source)
        self.old = git('rev-parse', 'HEAD', cwd=source).strip()
        (source / 'hello.txt').write_text('new', encoding='utf-8')
        (source / 'new_only.txt').write_text('new file', encoding='utf-8')
        (source / 'old_only.txt').unlink()
        git('add', '-A', cwd=source)
        git('commit', '-m', 'new', cwd=source)
        self.new = git('rev-parse', 'HEAD', cwd=source).strip()
        self.project = Project(self.root / 'managed', 'https://github.com/test/project')
        self.project.base.mkdir(parents=True)
        git('clone', '--mirror', source, self.project.cache)
        self.target = Path(self.project.snapshot(self.old))

    def tearDown(self):
        self.temporary.cleanup()

    def test_backup_replacement_keeps_local_data_and_same_path(self):
        (self.target / 'hello.txt').write_text('my edit', encoding='utf-8')
        (self.target / 'private.db').write_bytes(b'database')
        plan = inspect_update(self.project, self.target, self.new)
        self.assertTrue(plan.differences)
        result = apply_update(self.project, plan, keep_backup=True)
        self.assertEqual(Path(result['folder']), self.target)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'new')
        self.assertFalse((self.target / 'old_only.txt').exists())
        self.assertFalse((self.target / 'private.db').exists())
        self.assertTrue((self.target / 'new_only.txt').exists())
        with zipfile.ZipFile(result['backup']) as archive:
            self.assertEqual(archive.read('hello.txt'), b'my edit')
            self.assertEqual(archive.read('private.db'), b'database')
            self.assertIn('.git/HEAD', archive.namelist())
        records = self.project.snapshots()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['sha'], self.new)
        self.assertTrue(all(json.loads(path.read_text())['state'] == 'completed' for path in (self.project.base / 'updates').glob('*.json')))

    def test_explicit_discard_creates_no_archive(self):
        plan = inspect_update(self.project, self.target, self.new)
        result = apply_update(self.project, plan, keep_backup=False)
        self.assertEqual(result['backup'], '')
        self.assertFalse((self.project.base / 'backups').exists())
        self.assertEqual((self.target / 'hello.txt').read_text(), 'new')

    def test_edit_after_confirmation_refuses_update(self):
        plan = inspect_update(self.project, self.target, self.new)
        (self.target / 'hello.txt').write_text('late edit', encoding='utf-8')
        with self.assertRaises(UpdateConflict): apply_update(self.project, plan)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'late edit')

    def test_install_rename_failure_rolls_back(self):
        plan = inspect_update(self.project, self.target, self.new)
        original = Path.rename
        def rename(path, destination):
            if path.name.startswith('.githug-staged-') and Path(destination) == self.target:
                raise PermissionError('in use')
            return original(path, destination)
        with patch('pathlib.Path.rename', rename):
            with self.assertRaises(PermissionError): apply_update(self.project, plan)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'old')
        self.assertEqual(self.project.snapshots()[0]['sha'], self.old)

    def test_metadata_failure_rolls_back_files_and_record(self):
        plan = inspect_update(self.project, self.target, self.new)
        def write(path, data):
            if Path(path) == plan.record_path and data.get('sha') == self.new:
                raise OSError('disk full')
            return atomic_json(path, data)
        with patch('githug.updating.atomic_json', side_effect=write):
            with self.assertRaises(OSError): apply_update(self.project, plan)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'old')
        self.assertEqual(self.project.snapshots()[0]['sha'], self.old)

    def test_unknown_work_folder_preserved_and_version_recorded(self):
        folder = self.root / 'work'
        folder.mkdir()
        (folder / 'personal.txt').write_text('mine')
        plan = inspect_update(self.project, folder, self.new)
        self.assertTrue(plan.unknown)
        result = apply_update(self.project, plan)
        with zipfile.ZipFile(result['backup']) as archive:
            self.assertEqual(archive.read('personal.txt'), b'mine')
        self.assertEqual(len(self.project.snapshots()), 1)  # Work folder does not become duplicate snapshot row.
        self.assertEqual(len(self.project.folder_versions()), 2)
        again = inspect_update(self.project, folder, self.old)
        self.assertEqual(again.baseline, self.new)
        self.assertFalse(again.unknown)

    def test_protected_directories_and_links_refused(self):
        for folder in (self.project.base, self.project.cache, self.project.base.parent):
            with self.assertRaises(UpdateConflict): inspect_update(self.project, folder, self.new)
        (self.target / 'link').symlink_to(self.root / 'source', target_is_directory=True)
        with self.assertRaises(UpdateConflict): inspect_update(self.project, self.target, self.new)

    def test_ignored_files_are_included_in_backup_and_warning(self):
        (self.target / '.gitignore').write_text('private.db\n')
        (self.target / 'private.db').write_bytes(b'local data')
        plan = inspect_update(self.project, self.target, self.new)
        self.assertTrue(any(name == 'private.db' for _, name in plan.differences))
        result = apply_update(self.project, plan)
        with zipfile.ZipFile(result['backup']) as archive:
            self.assertEqual(archive.read('private.db'), b'local data')

    def test_crlf_conversion_is_not_a_local_edit(self):
        (self.source / 'lines.txt').write_bytes(b'first\nsecond\n')
        (self.source / '.gitattributes').write_text('*.txt text\n')
        git('add', '.', cwd=self.source)
        git('commit', '-m', 'text attributes', cwd=self.source)
        commit = git('rev-parse', 'HEAD', cwd=self.source).strip()
        git('fetch', 'origin', cwd=self.project.cache)
        folder = Path(self.project.snapshot(commit))
        git('config', 'core.autocrlf', 'true', cwd=folder)
        (folder / 'lines.txt').write_bytes(b'first\r\nsecond\r\n')
        plan = inspect_update(self.project, folder, self.old)
        self.assertFalse(any(name == 'lines.txt' for _, name in plan.differences))

    def test_change_while_staging_is_not_overwritten(self):
        plan = inspect_update(self.project, self.target, self.new)
        from githug.updating import git as original_git
        def command(*args, **kwargs):
            result = original_git(*args, **kwargs)
            if args[0] == 'clone':
                (self.target / 'hello.txt').write_text('changed while preparing')
            return result
        with patch('githug.updating.git', side_effect=command):
            with self.assertRaises(UpdateConflict): apply_update(self.project, plan)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'changed while preparing')
        self.assertEqual(self.project.snapshots()[0]['sha'], self.old)

    def test_incomplete_update_blocks_another_replacement(self):
        journal = self.project.base / 'updates' / 'pending.json'
        atomic_json(journal, {'state': 'previous_moved', 'original': str(self.target)})
        with self.assertRaises(UpdateConflict): inspect_update(self.project, self.target, self.new)
