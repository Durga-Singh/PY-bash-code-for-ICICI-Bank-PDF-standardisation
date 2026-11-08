"""Generated layout cases; outputs checked against source text and rendered fonts."""
import unittest,tempfile,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4,landscape
from converter import convert,spans_of
from adaptive import inventory

class AdaptiveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.src=self.root/'source.pdf';self.out=self.root/'output.pdf'
 def tearDown(self):self.temp.cleanup()
 def make(self,kind):
  cv=canvas.Canvas(str(self.src),pagesize=landscape(A4) if kind=='landscape' else A4)
  if kind=='blank':cv.showPage()
  elif kind=='vector':
   cv.drawString(60,700,'Diagram values 100 200');cv.circle(140,500,40);cv.line(180,500,300,500)
  elif kind=='borderless':
   for i in range(12):
    for x,t in [(60,'Account '+str(i)),(270,str(1000+i)),(400,str(2000+i))]:cv.drawString(x,700-i*25,t)
  elif kind=='long_word':cv.setFont('Helvetica',4);cv.drawString(60,700,'X'*140)
  else:
   cv.setFont('Helvetica-Bold',12);cv.drawString(60,700 if kind!='landscape' else 500,'Document heading')
   cv.setFont('Helvetica',10)
   for i in range(12):cv.drawString(60,(675 if kind!='landscape' else 475)-i*22,'Line '+str(i)+' retains amount '+str(1234+i)+'.')
   if kind=='border':cv.rect(25,25,545,790)
  cv.save()
 def check(self,expected='CONVERTED_REVIEW_LAYOUT'):
  result=convert(self.src,self.out);self.assertEqual(result['status'],expected)
  with fitz.open(self.out) as doc:
   self.assertEqual(len(doc),result['output_pages'])
   for p in doc:self.assertAlmostEqual(min(p.rect.width,p.rect.height),A4[0],places=2);self.assertAlmostEqual(max(p.rect.width,p.rect.height),A4[1],places=2)
   if expected=='CONVERTED_REVIEW_LAYOUT':
    with fitz.open(self.src) as src:
     missing=inventory(''.join(p.get_text() for p in src))-inventory(''.join(p.get_text() for p in doc));self.assertFalse(missing)
    for p in doc:
     for sp in spans_of(p):self.assertIn('Mulish',sp['font']);self.assertAlmostEqual(sp['size'],11,places=2)
  return result
 def test_prose_and_landscape_and_border(self):
  for kind in ['prose','landscape','border']:
   with self.subTest(kind=kind):self.make(kind);self.check()
 def test_borderless(self):self.make('borderless');self.check()
 def test_vector_scan_blank_longword(self):
  for kind in ['vector','blank','long_word']:
   with self.subTest(kind=kind):self.make(kind);self.check('PARTIAL_REVIEW_REQUIRED')
  self.make('prose')
  with fitz.open(self.src) as doc:pix=doc[0].get_pixmap()
  with fitz.open() as doc:
   p=doc.new_page();p.insert_image(p.rect,stream=pix.tobytes('png'));doc.save(self.root/'scan.pdf')
  self.src=self.root/'scan.pdf';self.check('PARTIAL_REVIEW_REQUIRED')
 def test_rotation(self):
  self.make('prose')
  with fitz.open(self.src) as doc:doc[0].set_rotation(90);doc.save(self.root/'rotated.pdf')
  self.src=self.root/'rotated.pdf';self.check('PARTIAL_REVIEW_REQUIRED')
 def test_annotated(self):
  self.make('prose')
  with fitz.open(self.src) as doc:doc[0].add_text_annot((100,100),'Keep this comment');doc.save(self.root/'annotated.pdf')
  self.src=self.root/'annotated.pdf';r=self.check('PARTIAL_REVIEW_REQUIRED');self.assertIn('flattened',r['pages'][0]['reason'])
 def test_forms_encrypted_malformed_atomic(self):
  self.make('prose')
  with fitz.open(self.src) as doc:
   w=fitz.Widget();w.field_name='Name';w.field_type=fitz.PDF_WIDGET_TYPE_TEXT;w.rect=fitz.Rect(100,100,250,125);doc[0].add_widget(w);doc.save(self.root/'form.pdf')
  with fitz.open(self.src) as doc:doc.save(self.root/'encrypted.pdf',encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='reader')
  (self.root/'malformed.pdf').write_bytes(b'%PDF-1.7 invalid')
  for kind in ['form','encrypted','malformed']:
   with self.subTest(kind=kind):
    self.out.write_bytes(b'existing output');self.src=self.root/(kind+'.pdf')
    with self.assertRaises(Exception):convert(self.src,self.out)
    self.assertEqual(self.out.read_bytes(),b'existing output')
 def test_ruled_merged_and_long_tables(self):
  for kind in ['ruled','merged','long']:
   with self.subTest(kind=kind):
    rows=[['Account','Amount','Status']]+[[str(i),str(1000+i),'Unlimited'] for i in range(65 if kind=='long' else 8)]
    table=Table(rows,colWidths=[100,100,180]);commands=[('GRID',(0,0),(-1,-1),.5,'black')]
    if kind=='merged':rows[2][2]='';table=Table(rows,colWidths=[100,100,180]);commands+=[('SPAN',(2,1),(2,2)),('ALIGN',(2,1),(2,2),'CENTER'),('VALIGN',(2,1),(2,2),'MIDDLE')]
    table.setStyle(TableStyle(commands));SimpleDocTemplate(str(self.src)).build([table]);self.check()
 def test_wide_table(self):
  data=[['Column '+str(i) for i in range(9)]]+[[str(123456789+i+j) for i in range(9)] for j in range(4)]
  t=Table(data,colWidths=[80]*9);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,'black')]))
  SimpleDocTemplate(str(self.src),pagesize=landscape(A4),leftMargin=30,rightMargin=30).build([t]);r=self.check('PARTIAL_REVIEW_REQUIRED');self.assertEqual(r['pages'][0]['orientation'],'portrait')
 def test_tall_cell(self):
  style=getSampleStyleSheet()['BodyText'];p=Paragraph(' '.join('word'+str(i) for i in range(420)),style)
  t=Table([['Label',p]],colWidths=[70,400],splitInRow=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,'black')]))
  SimpleDocTemplate(str(self.src),pagesize=(595,1800)).build([t]);self.check()
 def test_unsupported_script_and_mixed(self):
  with fitz.open() as doc:
   p=doc.new_page();p.insert_text((80,100),'中文測試',fontname='china-s')
   p=doc.new_page();p.insert_text((80,100),'Ordinary English page 123')
   doc.save(self.src)
  r=self.check('PARTIAL_REVIEW_REQUIRED');self.assertEqual(r['preserved_source_pages'],[1]);self.assertEqual(r['reflowed_source_pages'],1)
 def test_strict_mode(self):
  self.make('vector')
  with self.assertRaises(Exception):convert(self.src,self.out,strict=True)
  self.assertFalse(self.out.exists())
if __name__=='__main__':unittest.main()
