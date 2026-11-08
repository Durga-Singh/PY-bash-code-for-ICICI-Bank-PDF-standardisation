import os,sys,json,tempfile,unittest
from pathlib import Path
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from batch import Runner

@unittest.skipUnless(os.environ.get('PDF_TEST_DIRECTORY'),'Set PDF_TEST_DIRECTORY for supplied PDFs.')
class BonusTermsTests(unittest.TestCase):
    def test_queue_tables_and_actual_fonts(self):
        with tempfile.TemporaryDirectory() as td:
            runner=Runner(td)
            try:
                source=Path(os.environ['PDF_TEST_DIRECTORY'])/'Bonus-Interest-Rate-Offer-Terms-andC-onditions.pdf'
                result=runner.process(source)
                self.assertEqual(result['status'],'CONVERTED_REVIEW_LAYOUT',result['detail'])
                self.assertEqual(runner.process(source)['status'],'ALREADY_PROCESSED')
            finally:runner.close()
            dest=Path(result['output']);report=json.loads(Path(str(dest)+'.json').read_text())
            self.assertEqual(report['numeric_rows_verified'],16)
            self.assertEqual(report['output_pages'],6)
            with fitz.open(dest) as doc:
                self.assertNotIn('Exciting News',''.join(p.get_text()for p in doc))
                for page in doc:
                    self.assertEqual(len(page.get_image_info()),1,'Only the reference banner should remain.')
                    spans=[s for b in page.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans']]
                    self.assertTrue(all(abs(s['size']-11)<.01 and 'Mulish' in s['font'] for s in spans))
                calculation=[page for page in doc if '120.56' in page.get_text()]
                self.assertEqual(len(calculation),1)
                self.assertIn('Illustrative Example',calculation[0].get_text())
                table=next(t for t in calculation[0].find_tables().tables if t.col_count==7)
                actual=[row[1:] for row in table.extract()[1:] if row[1] is not None]
                self.assertEqual(actual,[
                    ['10,000','0','0','10,000','0','0.00'],
                    ['10,000','40,000','0','50,000','40,000','5.48'],
                    ['50,000','0','0','50,000','40,000','5.48'],
                    ['50,000','0','0','50,000','40,000','5.48'],
                    ['50,000','30,000','0','80,000','70,000','9.59'],
                    ['80,000','0','70,000','10,000','0','0.00'],
                    ['10,000','0','10,000','0','0','0.00'],
                    ['0','0','0','0','0','0.00'],
                    ['0','50,000','0','50,000','40,000','5.48'],
                    ['50,000','0','0','50,000','40,000','120.56#']])
                usd=[page for page in doc if 'US Dollar' in page.get_text()]
                self.assertEqual(len(usd),1)
                self.assertIn('E-HiSAVE Savings',usd[0].get_text())

if __name__=='__main__':unittest.main()
