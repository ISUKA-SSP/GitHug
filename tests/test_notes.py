from pathlib import Path
import tempfile
import unittest
from githug.notes import Notes, folder_key, short_note

class NotesTests(unittest.TestCase):
    def test_notes_are_local_separate_and_persist_after_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'project' / 'snapshots' / 'version'
            folder.mkdir(parents=True)
            notes = Notes(root / 'project')
            notes.set('history', 'a'*40, 'history note\nsecond line')
            notes.set('folders', str(folder), 'folder note')
            reloaded = Notes(root / 'project')
            self.assertEqual(reloaded.get('history', 'a'*40), 'history note\nsecond line')
            self.assertEqual(reloaded.get('folders', str(folder)), 'folder note')
            self.assertEqual(list(folder.iterdir()), [])
            self.assertEqual(short_note(reloaded.get('history','a'*40)), 'history note second line')

    def test_empty_clears_only_selected_note_and_projects_are_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Notes(Path(temporary)/'one'), Notes(Path(temporary)/'two')
            first.set('history', 'a'*40, 'one')
            first.set('history', 'b'*40, 'keep')
            second.set('history', 'a'*40, 'two')
            first.set('history', 'a'*40, '  ')
            self.assertEqual(first.get('history','a'*40),'')
            self.assertEqual(first.get('history','b'*40),'keep')
            self.assertEqual(second.get('history','a'*40),'two')

    def test_invalid_note_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            notes = Notes(temporary)
            notes.path.write_text('{invalid', encoding='utf-8')
            with self.assertRaises(ValueError): notes.set('history','a'*40,'new')
            self.assertEqual(notes.path.read_text(),'{invalid')

    def test_folder_keys_are_canonical_and_full_text_remains_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)/'folder'
            notes = Notes(temporary)
            text = '長いメモ'*100
            notes.set('folders', str(folder), text)
            self.assertEqual(notes.get('folders', str(folder/'..'/'folder')), text)
            self.assertEqual(len(short_note(text)), 100)
