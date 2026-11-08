import os,sys,tempfile,unittest
from pathlib import Path
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from converter import LEFT,RIGHT,TOP,BOTTOM,A4
from batch import Runner
import json

@unittest.skipUnless(os.environ.get('PDF_TEST_DIRECTORY'),'Set PDF_TEST_DIRECTORY for supplied PDFs.')
class CGASTests(unittest.TestCase):
    def check_form(self,name,pages,boxes,lines,dates,account_grids):
        with tempfile.TemporaryDirectory() as td:
            runner=Runner(td)
            try:
                source=Path(os.environ['PDF_TEST_DIRECTORY'])/name
                result=runner.process(source)
                self.assertEqual(result['status'],'CONVERTED_REVIEW_LAYOUT',result['detail'])
                self.assertEqual(runner.process(source)['status'],'ALREADY_PROCESSED')
                dest=Path(result['output']);report=json.loads(Path(str(dest)+'.json').read_text())
            finally:runner.close()
            self.assertEqual(report['output_pages'],pages)
            actual_boxes=actual_lines=actual_dates=actual_grids=0
            with fitz.open(dest) as doc:
                for page in doc:
                    self.assertAlmostEqual(page.rect.width,A4[0],places=2)
                    self.assertAlmostEqual(page.rect.height,A4[1],places=2)
                    spans=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans']]
                    self.assertTrue(all(abs(s['size']-11)<.01 and 'Mulish' in s['font'] for s in spans))
                    body_images=[im for im in page.get_image_info() if im['bbox'][1]>TOP-1]
                    for im in body_images:
                        r=fitz.Rect(im['bbox'])
                        self.assertGreaterEqual(r.x0,LEFT-.5);self.assertLessEqual(r.x1,A4[0]-RIGHT+.5)
                        self.assertLessEqual(r.y1,A4[1]-BOTTOM+.5)
                        actual_boxes+=abs(r.width-9)<.1 and abs(r.height-9)<.1
                        actual_lines+=r.height<1.1
                        actual_grids+=abs(r.width-144)<.1 and abs(r.height-16)<.1
                    for dr in page.get_drawings():
                        r=dr['rect'];actual_dates+=abs(r.width-22)<.1 and abs(r.height-23)<.1
            self.assertEqual((actual_boxes,actual_lines,actual_dates,actual_grids),(boxes,lines,dates*6,account_grids))
    def test_form_a(self):self.check_form('cgas-form-a.pdf',3,17,30,3,1)
    def test_form_b(self):self.check_form('cgas-form-b.pdf',3,0,62,0,0)

if __name__=='__main__':unittest.main()
