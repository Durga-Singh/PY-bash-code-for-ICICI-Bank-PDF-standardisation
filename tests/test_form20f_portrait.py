"""Regression checks against the fully rebuilt supplied report.
Set PDF_FORM20F_RESULT to a fresh annual_report.py output.
"""
import os,json,unittest
from pathlib import Path
import fitz
@unittest.skipUnless(os.environ.get('PDF_FORM20F_RESULT'),'Set PDF_FORM20F_RESULT to the rebuilt Form 20-F PDF.')
class Form20FLayoutTests(unittest.TestCase):
 def setUp(self):
  self.path=Path(os.environ['PDF_FORM20F_RESULT']);self.doc=fitz.open(self.path);self.addCleanup(self.doc.close);self.report=json.loads(Path(str(self.path)+'.json').read_text())
 def test_orientation_and_font(self):
  r=self.report;self.assertEqual(r['source_pages'],230);self.assertEqual(r['original_rows_verified'],8873)
  self.assertLess(len(r['landscape_source_pages']),len(r['page_map'])/4)
  for m in r['page_map']:
   for i in range(m['output_start']-1,m['output_end']):
    page=self.doc[i];self.assertEqual(page.rect.width>page.rect.height,m['source_page'] in r['landscape_source_pages'])
    for b in page.get_text('dict')['blocks']:
     for line in b.get('lines',[]):
      for s in line['spans']:
       if 'Mulish' in s['font']:
        self.assertAlmostEqual(s['size'],11,places=2)
        self.assertGreaterEqual(s['bbox'][0],1.88*72/2.54-1)
        self.assertLessEqual(s['bbox'][2],page.rect.width-1.89*72/2.54+1)
 def test_contents_numbers_and_click_targets(self):
  entries=self.report['contents_entries'];self.assertGreater(len(entries),35)
  for entry in entries:
   page=self.doc[entry['page']];rect=fitz.Rect(page.rect.width-1.89*72/2.54-33,entry['top'],page.rect.width,entry['top']+entry['height'])
   self.assertEqual(page.get_text(clip=rect).strip(),str(entry['target_page']))
   self.assertTrue(any(link['page']==entry['target_page']-1 and abs(link['from'].y0-entry['top'])<1 for link in page.get_links()))
 def test_footer_and_inventory_checks(self):
  self.assertEqual(self.report['text_overlap_check'],'passed')
  self.assertEqual(len(self.doc.get_toc()),230)
  for page in self.doc:
   footer=page.get_text(clip=fitz.Rect(0,page.rect.height-72,page.rect.width,page.rect.height))
   self.assertNotIn('Source page',footer);self.assertIn(f'{page.number+1} | {len(self.doc)}',footer)
if __name__=='__main__':unittest.main()
