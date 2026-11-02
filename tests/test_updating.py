import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from githug.core import Project, git
from githug.updating import inspect_update, apply_update, UpdateConflict, UpdateNotAllowed, atomic_json, authorize_update, disable_update, inventory

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
        self.assertEqual((self.target / 'private.db').read_bytes(), b'database')
        self.assertEqual(result['retained'], 1)
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
        (self.target / 'private.db').write_bytes(b'private')
        plan = inspect_update(self.project, self.target, self.new)
        result = apply_update(self.project, plan, keep_backup=False, preserve_local_only=False)
        self.assertFalse((self.target / 'private.db').exists())
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

    def test_unknown_work_folder_cannot_be_replaced_even_for_authorization(self):
        folder = self.root / 'work'
        folder.mkdir()
        (folder / 'personal.txt').write_text('mine')
        for options in ({}, {'for_authorization': True}):
            with self.assertRaises(UpdateNotAllowed): inspect_update(self.project, folder, self.new, **options)
        self.assertEqual((folder / 'personal.txt').read_text(), 'mine')
        self.assertFalse((self.project.base / 'updates').exists())

    def test_known_work_folder_requires_explicit_authorization(self):
        folder = self.root / 'work'
        shutil.copytree(self.target, folder)
        before = inventory(folder)
        with self.assertRaises(UpdateNotAllowed): inspect_update(self.project, folder, self.new)
        plan = inspect_update(self.project, folder, self.new, for_authorization=True)
        with self.assertRaises(UpdateNotAllowed): apply_update(self.project, plan)
        authorize_update(self.project, plan)
        self.assertEqual(inventory(folder), before)
        allowed = inspect_update(self.project, folder, self.new)
        apply_update(self.project, allowed)
        self.assertEqual((folder / 'hello.txt').read_text(), 'new')
        self.assertEqual(len(self.project.snapshots()), 1)
        self.assertEqual(len(self.project.folder_versions()), 2)

    def test_revoked_permission_is_rechecked_before_replacement(self):
        folder = self.root / 'work'
        shutil.copytree(self.target, folder)
        authorization = inspect_update(self.project, folder, self.new, for_authorization=True)
        authorize_update(self.project, authorization)
        plan = inspect_update(self.project, folder, self.new)
        disable_update(self.project, folder)
        with self.assertRaises(UpdateNotAllowed): apply_update(self.project, plan)
        self.assertEqual((folder / 'hello.txt').read_text(), 'old')

    def test_personal_folder_note_survives_same_path_update(self):
        from githug.notes import Notes
        notes = Notes(self.project.base)
        notes.set('folders', str(self.target), '普段使いの作業場所')
        notes.set('history', self.old, '元の版を確認済み')
        plan = inspect_update(self.project, self.target, self.new)
        apply_update(self.project, plan)
        reloaded = Notes(self.project.base)
        self.assertEqual(reloaded.get('folders', str(self.target)), '普段使いの作業場所')
        self.assertEqual(reloaded.get('history', self.old), '元の版を確認済み')
        self.assertFalse((self.target / 'personal_notes.json').exists())

    def test_protected_directories_and_links_refused(self):
        for folder in (self.project.base, self.project.cache, self.project.base.parent):
            with self.assertRaises(UpdateConflict): inspect_update(self.project, folder, self.new)
        try:
            (self.target / 'link').symlink_to(self.root / 'source', target_is_directory=True)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314: self.skipTest('Windows symlink privilege unavailable')
            raise
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

    def test_default_no_backup_preserves_local_files_but_discards_tracked_edits(self):
        (self.target / 'hello.txt').write_text('my code change')
        (self.target / 'notes').mkdir()
        (self.target / 'notes' / 'mine.txt').write_text('keep notes')
        (self.target / 'empty_local').mkdir()
        plan = inspect_update(self.project, self.target, self.new)
        result = apply_update(self.project, plan, keep_backup=False)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'new')
        self.assertFalse((self.target / 'old_only.txt').exists())
        self.assertEqual((self.target / 'notes' / 'mine.txt').read_text(), 'keep notes')
        self.assertTrue((self.target / 'empty_local').is_dir())
        self.assertEqual(result['retained'], 1)
        self.assertEqual(result['backup'], '')

    def test_local_file_colliding_with_new_tracked_file_stops_without_backup_or_swap(self):
        (self.target / 'new_only.txt').write_text('mine')
        plan = inspect_update(self.project, self.target, self.new)
        self.assertIn('new_only.txt', plan.collisions)
        with self.assertRaises(UpdateConflict): apply_update(self.project, plan, keep_backup=False)
        self.assertEqual((self.target / 'new_only.txt').read_text(), 'mine')
        self.assertEqual((self.target / 'hello.txt').read_text(), 'old')
        self.assertFalse((self.project.base / 'backups').exists())

    def test_case_insensitive_and_file_directory_collisions(self):
        (self.target / 'NEW_ONLY.TXT').write_text('Windows case')
        plan = inspect_update(self.project, self.target, self.new)
        self.assertIn('NEW_ONLY.TXT', plan.collisions)
        with self.assertRaises(UpdateConflict): apply_update(self.project, plan)
        (self.target / 'NEW_ONLY.TXT').unlink()
        (self.target / 'new_only.txt').mkdir()
        (self.target / 'new_only.txt' / 'data').write_text('nested')
        plan = inspect_update(self.project, self.target, self.new)
        self.assertIn('new_only.txt', plan.collisions)
        self.assertIn('new_only.txt/data', plan.collisions)
        with self.assertRaises(UpdateConflict): apply_update(self.project, plan)

    def test_locally_added_file_is_preserved_even_if_added_to_index(self):
        (self.target / 'added.txt').write_text('new local file')
        git('add', 'added.txt', cwd=self.target)
        plan = inspect_update(self.project, self.target, self.new)
        self.assertIn('added.txt', plan.local_files)
        apply_update(self.project, plan, keep_backup=False)
        self.assertEqual((self.target / 'added.txt').read_text(), 'new local file')

    def test_copy_failure_leaves_original_untouched(self):
        (self.target / 'private.txt').write_text('private')
        plan = inspect_update(self.project, self.target, self.new)
        with patch('githug.updating.shutil.copy2', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): apply_update(self.project, plan)
        self.assertEqual((self.target / 'hello.txt').read_text(), 'old')
        self.assertEqual((self.target / 'private.txt').read_text(), 'private')
        self.assertEqual(self.project.snapshots()[0]['sha'], self.old)

    def test_incomplete_update_blocks_another_replacement(self):
        journal = self.project.base / 'updates' / 'pending.json'
        atomic_json(journal, {'state': 'previous_moved', 'original': str(self.target)})
        with self.assertRaises(UpdateConflict): inspect_update(self.project, self.target, self.new)
