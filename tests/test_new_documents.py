import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from converter import convert,ReviewRequired

@unittest.skipUnless(os.environ.get('PDF_TEST_DIRECTORY'),'Set PDF_TEST_DIRECTORY to the folder with the three supplied PDFs.')
class DocumentTests(unittest.TestCase):
    def check(self,name,pages,headers,borders):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'result.pdf'
            report=convert(Path(os.environ['PDF_TEST_DIRECTORY'])/name,dest)
            self.assertEqual(report['output_pages'],pages)
            self.assertEqual(report['old_headers_removed'],headers)
            self.assertEqual(report['page_borders_removed'],borders)
            self.assertEqual(report['body_font_sizes_pt'],[11.0])
            with fitz.open(dest)as doc:
                self.assertTrue(all(len(p.get_image_info())==1 for p in doc),'Only the new banner should remain.')
    def test_legacy_header(self):self.check('INE090A08KY7.pdf',3,1,0)
    def test_page_borders(self):self.check('dctoc.pdf',17,0,16)
    def test_complex_report_preserves_rows_and_lists_chart_exceptions(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'result.pdf'
            report=convert(Path(os.environ['PDF_TEST_DIRECTORY'])/'form20f.pdf',dest)
            self.assertEqual(report['source_pages'],230)
            self.assertEqual(report['original_rows_verified'],8873)
            self.assertEqual(report['text_overlap_check'],'passed')
            self.assertGreater(report['repeated_heading_rows'],0)
            self.assertEqual([e['source_page']for e in report['exceptions']],[27,59])
            self.assertTrue(all(f['size_pt']==11 for f in report['font_spans'] if 'Mulish' in f['font']))
            with fitz.open(dest) as doc:
                self.assertAlmostEqual(doc[0].rect.width,595.2756,places=2)
                self.assertEqual(report['page_map'][0]['output_end'],1)
                self.assertLess(len(report['landscape_source_pages']),58)
                self.assertLess(doc[1].rect.width,doc[1].rect.height)
                self.assertGreater(len(report['contents_entries']),35)
                self.assertEqual(len(doc.get_toc()),230)

    def test_trade_form_symbols_and_writing_space(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'converted.pdf'
            report=convert(Path(os.environ['PDF_TEST_DIRECTORY'])/'Trade-Online-Application-Form-and-TnC.pdf',dest)
            self.assertTrue(report['form_writing_space_preserved'])
            self.assertEqual(report['body_font_sizes_pt'],[11.0])
            self.assertEqual(report['page_borders_removed'],0)
            with fitz.open(dest) as doc:
                text=''.join(page.get_text() for page in doc)
                self.assertEqual(text.count('➢'),4)
                self.assertEqual(text.count('4909-2207-7970'),1)
                symbols=[s for page in doc for b in page.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans'] if '➢' in s['text']]
                self.assertTrue(all(s['size']==11 and 'DejaVu' in s['font'] for s in symbols))
                for title,opening in [('AUTHORISED USER ACKNOWLEDGEMENT*','The person(s)'),('AUTHORISED SIGNATORY ACKNOWLEDGEMENT*','I/We acknowledge')]:
                    pages=[page for page in doc if title in page.get_text()]
                    self.assertEqual(len(pages),1)
                    self.assertIn(opening,pages[0].get_text())

    def test_canada_files(self):
        for name,pages in [('money2india-canada-new-customer-offer-terms-and-conditions.pdf',2),('seniors-advantage-gics-terms-and-conditions.pdf',2),('tc-faq-hello-canada-and-rbc-referral-program.pdf',3)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                dest=Path(td)/'converted.pdf';report=convert(Path(os.environ['PDF_TEST_DIRECTORY'])/name,dest)
                self.assertEqual(report['output_pages'],pages)
                self.assertEqual(report['body_font_sizes_pt'],[11.0])
                with fitz.open(dest) as doc:self.assertTrue(all(len(p.get_image_info())==1 for p in doc))

if __name__=='__main__':unittest.main()
