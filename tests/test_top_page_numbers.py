import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from converter import convert,spans_of
class TopNumberTests(unittest.TestCase):
 def test_repeated_top_numbers_removed_body_numbers_kept(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'source.pdf';b=Path(td)/'out.pdf'
   with fitz.open() as doc:
    for i in range(3):
     p=doc.new_page();p.insert_text((294,45),str(i+1));p.insert_text((60,110),'Body number 2 and 3 must remain.')
    doc.save(a)
   convert(a,b)
   with fitz.open(b) as doc:
    for p in doc:self.assertTrue(p.get_text().startswith('Body number 2'));self.assertIn('and 3 must remain',p.get_text())
 def test_single_top_number_not_guessed(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'source.pdf';b=Path(td)/'out.pdf'
   with fitz.open() as doc:
    p=doc.new_page();p.insert_text((294,45),'1');p.insert_text((60,110),'One page content');doc.save(a)
   convert(a,b)
   with fitz.open(b) as doc:self.assertTrue(doc[0].get_text().startswith('1'))
