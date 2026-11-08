import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from converter import convert,spans_of
from reportlab.pdfgen.canvas import Canvas
class FormattingTests(unittest.TestCase):
 def test_decoration_color_and_clickable_url(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'a.pdf';b=Path(td)/'b.pdf';cv=Canvas(str(a));cv.setFont('Helvetica',11)
   cv.drawString(60,700,'Underlined title');cv.line(60,698,140,698)
   cv.setFillColorRGB(0,0,1);cv.drawString(60,670,'Visit website');cv.linkURL('https://example.com/a?x=1&y=2',(60,668,140,681),relative=0)
   cv.setFillColorRGB(0,0,0);cv.drawString(60,640,'Old text');cv.line(60,644,100,644);cv.save()
   r=convert(a,b);self.assertEqual(r['status'],'CONVERTED_REVIEW_LAYOUT')
   with fitz.open(b) as doc:
    words=spans_of(doc[0]);self.assertTrue(next(s for s in words if s['text']=='Underlined')['underline']);self.assertTrue(next(s for s in words if s['text']=='Old')['strike']);self.assertEqual(next(s for s in words if s['text']=='Visit')['color'],255)
    self.assertIn('https://example.com/a?x=1&y=2',{l.get('uri') for l in doc[0].get_links()})
 def test_internal_link_remapped(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'a.pdf';b=Path(td)/'b.pdf'
   with fitz.open() as d:
    d.new_page();d.new_page();d[0].insert_text((60,100),'Go to second page');d[1].insert_text((60,100),'Destination');d[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(60,85,170,105),'page':1});d.save(a)
   r=convert(a,b)
   with fitz.open(b) as d:self.assertEqual(d[0].get_links()[0]['page'],r['pages'][1]['output_start']-1)
 def test_italics_not_silently_removed(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'a.pdf';b=Path(td)/'b.pdf';cv=Canvas(str(a));cv.setFont('Helvetica-Oblique',11);cv.drawString(60,700,'Italic emphasis');cv.save();r=convert(a,b)
   self.assertEqual(r['preserved_source_pages'],[])
   self.assertEqual(r['font_compliance'],'ALL_REBUILT_TEXT_11PT_MULISH')
   with fitz.open(b) as d:self.assertTrue(any('Italic' in s['font'] and 'Mulish' in s['font'] and abs(s['size']-11)<.02 for s in spans_of(d[0])))
 def test_four_weights_and_styles_remain_distinct(self):
  with tempfile.TemporaryDirectory() as td:
   a=Path(td)/'a.pdf';b=Path(td)/'b.pdf';cv=Canvas(str(a))
   for index,(font,word) in enumerate([('Helvetica','Normal'),('Helvetica-Bold','Emphasis'),('Helvetica-Oblique','Italic'),('Helvetica-BoldOblique','Both')]):
    cv.setFont(font,10);cv.drawString(60,700-index*30,word)
   cv.save();r=convert(a,b);self.assertEqual(r['preserved_source_pages'],[])
   with fitz.open(b) as d:
    found={s['text']:s['font'] for p in d for s in spans_of(p)}
    self.assertEqual(found['Normal'],'Mulish-SemiBold');self.assertEqual(found['Emphasis'],'Mulish-Black')
    self.assertEqual(found['Italic'],'Mulish-SemiBoldItalic');self.assertEqual(found['Both'],'Mulish-BlackItalic')
