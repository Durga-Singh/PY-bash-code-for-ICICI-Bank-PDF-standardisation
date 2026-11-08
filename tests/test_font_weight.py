import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from converter import is_bold,convert,spans_of
from reportlab.pdfgen.canvas import Canvas
import fitz
class WeightTests(unittest.TestCase):
 def test_explicit_weight_overrides_wrong_flags(self):
  for name in ['Mulish-SemiBold','ABCDEF+Mulish-SemiBold','Mulish-Regular','ArialMT']:
   self.assertFalse(is_bold({'font':name,'flags':20 if 'Mulish' in name else 0}))
  for name in ['Arial-BoldMT','Zurich Blk BT','Mulish-Black']:
   self.assertTrue(is_bold({'font':name,'flags':0}))
  self.assertTrue(is_bold({'font':'UnknownFace','flags':16}))
 def test_mixed_bold_rendering(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'source.pdf';b=Path(td)/'out.pdf';cv=Canvas(str(a));cv.setFont('Helvetica-Bold',11);cv.drawString(60,700,'Bold heading');cv.setFont('Helvetica',11);cv.drawString(60,670,'Normal paragraph');cv.save();convert(a,b)
   with fitz.open(b) as d:
    ss=spans_of(d[0]);self.assertTrue(all('Black' in s['font'] for s in ss if s['text'] in ['Bold','heading']));self.assertTrue(all('SemiBold' in s['font'] for s in ss if s['text'] in ['Normal','paragraph']))
