import json
import pathlib
import unittest
from unittest.mock import patch
from datetime import date
from scripts.collect import parse_dates, parsed_price, classify, parse_structured_page, build_event

SOURCE={'id':'ecpe','name':'ECPE','url':'https://www.ecpe.org/events/workshops-tutorials/all/','collection':'structured'}

class CollectorTests(unittest.TestCase):
    def test_numeric_and_german_dates(self):
        self.assertEqual(parse_dates('10/11/2026 - 11/11/2026'),('2026-11-10','2026-11-11'))
        self.assertEqual(parse_dates('10. März 2027'),('2027-03-10','2027-03-10'))
        self.assertEqual(parse_dates('18. Feb 2027'),('2027-02-18','2027-02-18'))

    def test_english_date_ranges(self):
        self.assertEqual(parse_dates('November 24th - 27th 2026'),('2026-11-24','2026-11-27'))
        self.assertEqual(parse_dates('November 30th - December 3rd 2026'),('2026-11-30','2026-12-03'))
        self.assertEqual(parse_dates('May 31 - Jun 2, 2027'),('2027-05-31','2027-06-02'))
        self.assertEqual(parse_dates('November 18, 2026'),('2026-11-18','2026-11-18'))

    def test_prices(self):
        self.assertEqual(parsed_price('€2,950.00','biricha'),2950)
        self.assertEqual(parsed_price('EUR 1.510,00','biricha'),1510)
        self.assertEqual(parsed_price('free webinar','wuerth'),0)
        self.assertIsNone(parsed_price('on demand','ecpe'))

    def test_categories(self):
        self.assertEqual(classify('GaN based power design'),'SiC / GaN')
        self.assertEqual(classify('EMC Filter Design Workshop'),'EMC / EMI')

    def test_cards_and_old_courses(self):
        html='''<html><div class="card"><h3><a href="/events/one">Capacitors in Power Electronics</a></h3><span>Hamburg, Germany</span><span>09/12/2026 - 10/12/2026</span></div></html>'''
        # mocked date to make tests robust after the event in future years:
        class FixedDate(date):
            @classmethod
            def today(cls): return cls(2026,10,29)
        with patch('scripts.collect.date',FixedDate):
            rows=parse_structured_page(SOURCE,html)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['start_date'],'2026-12-09')
        self.assertEqual(rows[0]['city'],'Hamburg')

    def test_seed_integrity(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        sources=json.loads((root/'data/sources.json').read_text())
        data=json.loads((root/'data/courses.json').read_text())
        self.assertGreaterEqual(len(sources),10)
        self.assertGreaterEqual(len(data['courses']),20)
        valid={s['id'] for s in sources}
        for c in data['courses']:
            self.assertIn(c['source_id'],valid)
            self.assertTrue(c['url'].startswith('https://'))
            self.assertLessEqual(c['start_date'],c['end_date'])
        self.assertEqual(len(set(c['id'] for c in data['courses'])),len(data['courses']))

if __name__=='__main__':unittest.main()