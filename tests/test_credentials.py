import os
import unittest
import uuid
from githug.credentials import CredentialStore, CredentialError

class CredentialTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows native credential store')
    def test_isolated_roundtrip_and_delete(self):
        store=CredentialStore('GitHug/Test/'+uuid.uuid4().hex)
        try:
            self.assertEqual(store.read(),'')
            store.write('test-key_123-symbols!')
            self.assertEqual(store.read(),'test-key_123-symbols!')
            store.write('replacement')
            self.assertEqual(store.read(),'replacement')
            store.delete();self.assertEqual(store.read(),'')
            store.delete()  # Already absent is a successful delete.
        finally:store.delete()

    def test_empty_and_oversized_are_not_saved(self):
        store=CredentialStore('GitHug/Test/never-used')
        for value in ('','x'*2561):
            with self.assertRaises(CredentialError):store.write(value)

    @unittest.skipIf(os.name=='nt','non-Windows behavior')
    def test_unsupported_platform_does_not_write_file(self):
        store=CredentialStore();self.assertFalse(store.available)
        self.assertEqual(store.read(),'')
        with self.assertRaises(CredentialError):store.write('fake-key')
        store.delete()
