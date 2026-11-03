import unittest
from githug.listing import date_value, visible_rows

class ListingTests(unittest.TestCase):
    def row(self, ident, date, text):
        shown, stamp = date_value(date)
        return {'id': ident, 'search': ident + ' ' + shown + ' ' + text,
                'sort': {'date': stamp, 'message': text.casefold()}}

    def test_dates_compare_instants_across_timezones(self):
        a = self.row('a', '2026-11-01T10:00:00+09:00', 'Alpha')
        b = self.row('b', '2026-11-01T03:00:00+00:00', 'Beta')
        self.assertEqual([r['id'] for r in visible_rows([a,b], '', 'date', True)], ['b','a'])
        self.assertEqual([r['id'] for r in visible_rows([a,b], '', 'date', False)], ['a','b'])

    def test_search_then_sort_and_clear_preserve_original_rows(self):
        rows = [self.row('sha1', '2026-11-01T10:00:00+09:00', 'GUI 日本語'),
                self.row('sha2', '2026-11-02T10:00:00+09:00', 'Other')]
        self.assertEqual([r['id'] for r in visible_rows(rows, 'gui', 'date', True)], ['sha1'])
        self.assertEqual([r['id'] for r in visible_rows(rows, '日本語', 'date', True)], ['sha1'])
        self.assertEqual([r['id'] for r in visible_rows(rows, 'sha2', 'date', True)], ['sha2'])
        self.assertEqual(visible_rows(rows, 'missing', 'date', True), [])
        self.assertEqual(len(visible_rows(rows, '', 'date', True)), 2)
        self.assertEqual(rows[0]['id'], 'sha1')

    def test_missing_creation_date_is_blank_and_last_when_newest_first(self):
        rows = [self.row('work', '', 'registered'), self.row('snapshot', '2026-11-01T10:00:00', 'snapshot')]
        self.assertEqual(date_value('')[0], '')
        self.assertEqual([r['id'] for r in visible_rows(rows, '', 'date', True)], ['snapshot','work'])

    def test_large_filtered_list_keeps_identity(self):
        rows = [self.row(str(i), '2026-11-01T10:00:00+09:00', 'match' if i%2 else 'other') for i in range(400)]
        visible = visible_rows(rows, 'match', 'message', False)
        self.assertEqual(len(visible), 200)
        self.assertTrue(all(int(row['id'])%2 for row in visible))

class PinnedRowsTests(unittest.TestCase):
    def test_work_rows_remain_first_in_both_sort_directions_and_search(self):
        work = {'id':'work','pinned':True,'search':'project','sort':{'value':2}}
        older = {'id':'older','search':'project','sort':{'value':1}}
        newer = {'id':'newer','search':'project','sort':{'value':3}}
        for descending, expected in [(True,['work','newer','older']),(False,['work','older','newer'])]:
            shown = visible_rows([older,newer,work], 'project', 'value', descending, pinned_first=True)
            self.assertEqual([r['id'] for r in shown], expected)
