import json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((ROOT/'data/concerts.json').read_text(encoding='utf-8'))
        cls.s=json.loads((ROOT/'data/setlists.json').read_text(encoding='utf-8'))
    def test_volume(self): self.assertGreaterEqual(len(self.c),1678)
    def test_core_locations(self):
        self.assertFalse([x for x in self.c if not x.get('city') or not x.get('venue') or not x.get('country')])
    def test_unique_primary_ids(self): self.assertEqual(len({x['id'] for x in self.c}),len(self.c))
    def test_setlist_rows(self): self.assertGreater(len(self.s),30000)
    def test_nimes_2026(self):
        n=[x for x in self.c if x.get('date') in {'2026-07-24','2026-07-25','2026-07-26'}]
        self.assertEqual(len(n),3)
        self.assertTrue(all(x.get('city')=='Nîmes' for x in n))
