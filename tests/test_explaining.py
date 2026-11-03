import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from githug.explaining import explain, explainable, explanation_input, cache_key

class ExplainTests(unittest.TestCase):
    def test_settings_and_databases_excluded(self):
        for name in ['.env','settings.json','madobe.json','keys/private.pem','data.sqlite','api_key.txt']:
            self.assertFalse(explainable(name))
        self.assertTrue(explainable('githug/core.py'))
        with self.assertRaises(ValueError): explanation_input({'files':['.env'],'summary':'x','patch':'x'})

    def test_summary_is_default_and_large_diffs_require_smaller_selection(self):
        preview = {'files':['core.py'], 'summary':'2\t1\tcore.py\n', 'patch':'+implementation detail\n'}
        self.assertNotIn('implementation detail', explanation_input(preview))
        self.assertIn('implementation detail', explanation_input(preview, True))
        preview['patch'] = 'x'*60001
        with self.assertRaises(ValueError): explanation_input(preview, True)

    def test_network_request_only_contains_approved_text_and_header_key(self):
        response = io.StringIO(json.dumps({'candidates':[{'content':{'parts':[{'text':'内部','thought':True},{'text':'説明です'}]}}]}))
        with patch('githug.explaining.urlopen', return_value=response) as call:
            result = explain('private-key', 'test-model', 'approved diff')
        self.assertEqual(result, '説明です')
        request = call.call_args.args[0]
        self.assertNotIn('private-key', request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'), 'private-key')
        self.assertEqual(json.loads(request.data)['contents'][0]['parts'][0]['text'], 'approved diff')

    def test_http_failure_redacts_key_and_is_not_retried(self):
        with patch('githug.explaining.urlopen', side_effect=HTTPError('url',429,'secret-key',None,None)) as call:
            with self.assertRaises(RuntimeError) as caught: explain('secret-key','test-model','x')
        self.assertNotIn('secret-key',str(caught.exception))
        self.assertEqual(call.call_count,1)
        self.assertNotEqual(cache_key('model-a','x'),cache_key('model-b','x'))

class KeyInputTests(unittest.TestCase):
    def test_printable_symbols_are_preserved_and_not_rejected_as_spaces(self):
        from githug.explaining import normalize_api_key
        value='test-only.AQ+/=:~!'
        self.assertEqual(normalize_api_key('  '+value+'\r\n'),value)
        response=io.StringIO(json.dumps({'candidates':[{'content':{'parts':[{'text':'ok'}]}}]}))
        with patch('githug.explaining.urlopen',return_value=response) as call:
            self.assertEqual(explain(value,'test-model','test'),'ok')
        self.assertEqual(call.call_args.args[0].get_header('X-goog-api-key'),value)

    def test_whitespace_and_header_injection_never_reach_network_or_echo_key(self):
        for value in ('abc def','abc\r\nx-inject: y','abc\u200bdef','abc\x00def','ＡＢＣ'):
            with self.subTest(value=repr(value)),patch('githug.explaining.urlopen') as call:
                with self.assertRaises(ValueError) as caught:explain(value,'test-model','test')
                call.assert_not_called()
                self.assertNotIn(value,str(caught.exception))
