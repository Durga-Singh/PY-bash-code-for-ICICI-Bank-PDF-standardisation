import unittest, tempfile, sys, threading, io, json, struct
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate
from converter import build_table,spans_of,setup_fonts,WIDTH
from url_batch import Engine
from native_host import read_message

class ExtensionTests(unittest.TestCase):
 def test_url_batch_and_report(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);pdf=root/'source.pdf';c=canvas.Canvas(str(pdf));c.drawString(60,700,'A simple source document with preserved content.');c.save();data=pdf.read_bytes()
   class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
     if self.path=='/redirect':self.send_response(302);self.send_header('Location','/ok.pdf');self.end_headers();return
     self.send_response(404 if self.path=='/missing' else 200);self.end_headers();self.wfile.write(data if self.path in ('/ok.pdf','/bad.pdf') else b'<html>Sign in</html>')
    def log_message(self,*a):pass
   server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
   try:
    base=f'http://127.0.0.1:{server.server_port}';engine=Engine(root/'batches');b=engine.create([base+'/ok.pdf',base+'/redirect',base+'/missing',base+'/html',base+'/ok.pdf']);b=engine.run(b['id'])
    self.assertEqual([j['status'] for j in b['jobs']],['CONVERTED_REVIEW_LAYOUT']*2+['Failed']*2+['CONVERTED_REVIEW_LAYOUT'])
    self.assertEqual(len({j['original'] for j in b['jobs'] if j['original']}),3)
    from openpyxl import load_workbook
    book=load_workbook(engine.folder(b['id'])/'conversion_status.xlsx');sheet=book.active
    self.assertEqual(sheet.max_row,6);self.assertEqual(sheet['F2'].hyperlink.target,b['jobs'][0]['original']);self.assertEqual(sheet['G2'].hyperlink.target,b['jobs'][0]['converted']);self.assertIsNone(sheet['G4'].hyperlink)
    path=engine.folder(b['id'])/b['jobs'][0]['converted'];stamp=path.stat().st_mtime_ns;engine.run(b['id']);self.assertEqual(path.stat().st_mtime_ns,stamp)
    self.assertTrue(b['jobs'][1]['final_url'].endswith('/ok.pdf'))
    old=engine.load(b['id']);old['jobs'][0]['conversion_version']='1.8';engine.save(old);upgraded=engine.run(b['id']);self.assertEqual(upgraded['jobs'][0]['conversion_version'],'2.1.0');self.assertNotEqual(path.stat().st_mtime_ns,stamp)
   finally:server.shutdown();server.server_close()
 def test_partial_status_excel_and_resume(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);engine=Engine(root/'batches');b=engine.create(['https://example.invalid/chart.pdf'])
   folder=engine.folder(b['id']);source=folder/'originals/chart.pdf';cv=canvas.Canvas(str(source));cv.drawString(60,700,'Diagram 42');cv.circle(200,400,50);cv.save()
   b['jobs'][0].update(original='originals/chart.pdf',download='Downloaded');engine.save(b)
   b=engine.run(b['id']);job=b['jobs'][0];self.assertEqual(job['status'],'PARTIAL_REVIEW_REQUIRED');self.assertEqual(job['preserved_pages'],'1');self.assertEqual(engine.snapshot(b)['partial_count'],1)
   from openpyxl import load_workbook
   book=load_workbook(folder/'conversion_status.xlsx');self.assertEqual(book.active['K2'].value,'PARTIAL');self.assertEqual(book.active['L2'].value,'1')
   target=folder/job['converted'];stamp=target.stat().st_mtime_ns;engine.run(b['id']);self.assertEqual(stamp,target.stat().st_mtime_ns)
 def test_native_framing(self):
  payload=json.dumps({'url':'https://example.com/é.pdf'}).encode();self.assertEqual(read_message(io.BytesIO(struct.pack('<I',len(payload))+payload))['url'],'https://example.com/é.pdf')
  with self.assertRaises(ValueError):read_message(io.BytesIO(b'xx'))
 def test_merged_cell_render_alignment(self):
  setup_fonts()
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'grid.pdf';dest=Path(tmp)/'output.pdf';c=canvas.Canvas(str(source),pagesize=(600,800));xs=[40,80,300,420,560];ys=[700,670,640,610,580,550]
   for x in xs:c.line(x,ys[-1],x,ys[0])
   for i,y in enumerate(ys):
    if i in (2,4):c.line(40,y,300,y);c.line(420,y,560,y)
    else:c.line(40,y,560,y)
   c.setFont('Helvetica',10)
   for x,t in zip(xs,['SN','Card','Access','List']):c.drawString(x+5,680,t)
   for i in range(4):c.drawString(45,650-i*30,str(i+1));c.drawString(85,650-i*30,'Card variant '+str(i+1));c.drawString(425,650-i*30,'List A')
   c.drawCentredString(360,637,'Unlimited');c.drawCentredString(360,577,'2');c.save()
   with fitz.open(source) as doc:
    page=doc[0];tab=page.find_tables().tables[0];table,_,_=build_table(tab,spans_of(page),520,page.get_drawings());SimpleDocTemplate(str(dest),pagesize=(600,800)).build([table])
   with fitz.open(dest) as doc:
    p=doc[0];tables=p.find_tables().tables;self.assertEqual(len(tables),1)
    for text in ['Unlimited','2']:
     matches=p.search_for(text);box=next(r for r in matches if r.x0>250)
     cells=[fitz.Rect(cell) for cell in tables[0].cells if cell and fitz.Rect(cell).contains(box)]
     cell=min(cells,key=lambda r:r.get_area());self.assertLess(abs((box.x0+box.x1-cell.x0-cell.x1)/2),1);self.assertLess(abs((box.y0+box.y1-cell.y0-cell.y1)/2),5)
if __name__=='__main__':unittest.main()
