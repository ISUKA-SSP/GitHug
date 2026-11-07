import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from githug.core import Project, git
from githug.notes import Notes
from githug.project_storage import relocate_project
from githug.updating import atomic_json


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.project = Project(root / 'old', 'https://github.com/example/project')
        self.old = self.project.base
        self.new = root / 'renamed project'
        self.external = root / 'external'
        self.copy = self.old / 'snapshots' / 'first'
        self.copy.mkdir(parents=True)
        self.external.mkdir()
        git('init', '--bare', self.project.cache)
        git('remote', 'add', 'origin', self.project.url, cwd=self.project.cache)
        self.sha = 'a' * 40
        self.write('records/first.json', {'folder': str(self.copy), 'sha': self.sha})
        self.write('backups/first.json', {
            'folder': str(self.copy), 'archive': str(self.old / 'backups' / 'first.zip'),
        })
        self.write('local-records/first/record.json', {'folder': str(self.copy)})
        notes = Notes(self.old)
        notes.set('history', self.sha, 'history memo')
        notes.set('folders', self.copy, 'snapshot memo')
        notes.set('folders', self.external, 'work memo')

    def write(self, name, data):
        atomic_json(self.old / name, data)

    def read(self, name):
        return json.loads((self.new / name).read_text(encoding='utf-8'))

    def test_move_preserves_history_and_reconnects_folder_notes_and_records(self):
        self.old.rename(self.new)
        base, work = relocate_project(self.project, self.new, [str(self.copy), str(self.external)], ())
        copy = base / 'snapshots' / 'first'
        self.assertEqual(work, [str(copy), str(self.external)])
        active = Project.registered(self.old.parent, {'url': self.project.url, 'base': str(base)})
        self.assertEqual(active.cache, self.new / 'history.git')
        notes = Notes(active.base)
        self.assertEqual(notes.get('history', self.sha), 'history memo')
        self.assertEqual(notes.get('folders', copy), 'snapshot memo')
        self.assertEqual(notes.get('folders', self.external), 'work memo')
        for name in ('records/first.json', 'backups/first.json', 'local-records/first/record.json'):
            self.assertEqual(self.read(name)['folder'], str(copy))
        self.assertEqual(self.read('backups/first.json')['archive'], str(base / 'backups' / 'first.zip'))
        self.assertFalse(self.old.exists())
        # Retrying after an interrupted settings save must leave the same records.
        self.assertEqual(relocate_project(self.project, self.new, [str(self.copy), str(self.external)], ()), (base, work))

    def test_same_folder_and_wrong_remote_do_not_modify_metadata(self):
        before = (self.old / 'personal_notes.json').read_bytes()
        self.assertEqual(relocate_project(self.project, self.old, [], ()), (self.old, []))
        self.old.rename(self.new)
        git('remote', 'set-url', 'origin', 'https://github.com/other/project', cwd=self.new / 'history.git')
        with self.assertRaisesRegex(ValueError, '別のGitHubプロジェクト'):
            relocate_project(self.project, self.new, [], ())
        self.assertEqual((self.new / 'personal_notes.json').read_bytes(), before)

    def test_write_error_rolls_back_previous_changes(self):
        self.old.rename(self.new)
        def fail_backup(path, data):
            if path.parent.name == 'backups':
                raise PermissionError('test write failure')
            atomic_json(path, data)
        with patch('githug.project_storage.atomic_json', side_effect=fail_backup):
            with self.assertRaises(PermissionError):
                relocate_project(self.project, self.new, [], ())
        self.assertEqual(self.read('records/first.json')['folder'], str(self.copy))


class ProjectStorageUiTests(unittest.TestCase):
    def test_storage_picker_ignores_the_drag_overlay_but_blocks_dialogs(self):
        import tkinter as tk
        from githug.__main__ import App

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('Tk display unavailable')
        with tempfile.TemporaryDirectory() as directory:
            try:
                root._githug_smoke = True
                root._githug_smoke_dir = directory
                app = App(root)
                app.project = Project(directory, 'https://github.com/example/project')
                app.current = {'url': app.project.url, 'work': []}
                app.config.update(root=directory, projects=[app.current])
                root.update()
                with patch('githug.__main__.filedialog.askdirectory', return_value='') as picker, \
                     patch('githug.__main__.messagebox.showinfo') as info:
                    app.choose_root()
                    picker.assert_called_once()
                    info.assert_not_called()

                    dialog = tk.Toplevel(root)
                    try:
                        picker.reset_mock()
                        app.choose_root()
                        picker.assert_not_called()
                        info.assert_called_once()
                    finally:
                        dialog.destroy()
            finally:
                for timer in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.tk.call('after', 'cancel', timer)
                root.destroy()
