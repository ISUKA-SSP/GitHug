import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from githug.core import git
from githug.inspection import file_input,history_input
from githug.folder_tree import children

class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_directory_reads_one_level_and_omits_git(self):
        (self.root/'.git').mkdir();(self.root/'folder').mkdir();(self.root/'folder'/'nested.txt').write_text('x')
        (self.root/'z.txt').write_text('x')
        rows=children(self.root)
        self.assertEqual([r[0] for r in rows],['folder','z.txt'])
        self.assertTrue(rows[0][2])
        with self.assertRaises(ValueError):children(self.root,limit=1)

    def test_file_requires_explicit_content_and_rejects_sensitive_binary_and_large(self):
        path=self.root/'example.py';path.write_text('private implementation',encoding='utf-8')
        self.assertNotIn('private implementation',file_input(path))
        self.assertIn('private implementation',file_input(path,True))
        settings=self.root/'settings.json';settings.write_text('{}')
        with self.assertRaises(ValueError):file_input(settings)
        path.write_bytes(b'x\0y')
        with self.assertRaises(ValueError):file_input(path,True)
        path.write_bytes(b'x'*60001)
        with self.assertRaises(ValueError):file_input(path,True)

    def test_commit_and_branch_inputs_have_pinned_baselines_and_filter_secrets(self):
        git('init','-b','main',self.root)
        git('config','user.name','Test',cwd=self.root);git('config','user.email','test@example.invalid',cwd=self.root)
        (self.root/'code.py').write_text('first\n')
        git('add','.',cwd=self.root);git('commit','-m','first',cwd=self.root)
        initial=git('rev-parse','HEAD',cwd=self.root).strip()
        project=SimpleNamespace(cache=self.root)
        self.assertIn(initial,history_input(project,initial))
        git('checkout','-b','feature',cwd=self.root)
        (self.root/'code.py').write_text('second\n')
        (self.root/'settings.json').write_text('secret-value')
        git('add','.',cwd=self.root);git('commit','-m','next',cwd=self.root)
        tip=git('rev-parse','HEAD',cwd=self.root).strip()
        text=history_input(project,tip,'main',True)
        self.assertIn(initial,text);self.assertIn(tip,text);self.assertIn('+second',text)
        self.assertNotIn('secret-value',text);self.assertNotIn('settings.json',text)
        self.assertNotIn('+second',history_input(project,tip))
        with self.assertRaises(Exception):history_input(project,tip,'--evil')
