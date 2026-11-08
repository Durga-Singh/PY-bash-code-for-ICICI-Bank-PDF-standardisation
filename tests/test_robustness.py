import io,json,os,re,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from PIL import Image,ImageDraw
from fontTools.ttLib import TTFont as InspectFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table,TableStyle,SimpleDocTemplate
import converter as c
import adaptive as a
import quality_gate,layout_core,brand_cleanup

class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.src=self.root/'source.pdf';self.out=self.root/'out.pdf';c.setup_fonts()

    def obscure_font_names(self):
        renamed=self.root/'renamed.pdf'
        with fitz.open(self.src) as doc:
            seen=set()
            for page in doc:
                for xref,ext,*_ in page.get_fonts():
                    if xref in seen or ext!='ttf':continue
                    seen.add(xref);alias=f'/CIDFont+F{xref+700}'
                    doc.xref_set_key(xref,'BaseFont',alias)
                    kind,value=doc.xref_get_key(xref,'FontDescriptor')
                    if kind=='xref':
                        fd=int(value.split()[0]);doc.xref_set_key(fd,'FontName',alias);doc.xref_set_key(fd,'Flags','4')
            doc.save(renamed)
        self.src=renamed

    def test_opaque_font_names_recover_all_four_styles(self):
        cv=Canvas(str(self.src))
        for i,(font,text) in enumerate([('Mulish-SemiBold','Normal'),('Mulish-Black','Strong'),('Mulish-SemiBoldItalic','Italic'),('Mulish-BlackItalic','Both')]):
            cv.setFont(font,11);cv.drawString(60,700-i*30,text)
        cv.save();self.obscure_font_names();result=c.convert(self.src,self.out,strict=True)
        self.assertTrue(result['verification']['passed'])
        with fitz.open(self.out) as doc:
            values={s['text']:s['font'] for p in doc for s in c.spans_of(p)}
        self.assertEqual(values['Normal'],'Mulish-SemiBold');self.assertEqual(values['Strong'],'Mulish-Black')
        self.assertEqual(values['Italic'],'Mulish-SemiBoldItalic');self.assertEqual(values['Both'],'Mulish-BlackItalic')

    def test_private_symbol_bullet_under_opaque_font_name(self):
        fn=self.root/'symbol.ttf'
        with InspectFont(c.ROOT/'assets/Mulish-SemiBold.ttf') as font:
            glyph=font.getBestCmap()[0x2022]
            for table in font['cmap'].tables:
                if table.isUnicode():table.cmap[0xf0b7]=glyph
            for record in font['name'].names:
                if record.nameID in (1,4,6):record.string='SymbolFixture'.encode(record.getEncoding())
            font.save(fn)
        pdfmetrics.registerFont(TTFont('PrivateSymbolFixture',str(fn)))
        cv=Canvas(str(self.src));cv.setFont('PrivateSymbolFixture',11);cv.drawString(60,700,'\uf0b7')
        cv.setFont('Helvetica',11);cv.drawString(82,700,'Bullet text remains readable.');cv.save()
        self.obscure_font_names();result=c.convert(self.src,self.out,strict=True)
        self.assertEqual(result['preserved_source_pages'],[])
        with fitz.open(self.out) as doc:self.assertIn('•',doc[0].get_text());self.assertNotIn('\uf0b7',doc[0].get_text())

    def test_resized_recompressed_banner_is_removed(self):
        image=Image.open(c.ROOT/'assets/header.jpg').crop((420,15,1235,170)).resize((360,70))
        jpg=self.root/'logo.jpg';image.save(jpg,quality=45)
        cv=Canvas(str(self.src));cv.drawImage(str(jpg),150,640,width=300,height=60);cv.drawString(70,570,'Actual content');cv.save()
        with fitz.open(self.src) as doc:self.assertEqual(len(c.legacy_header_boxes(doc[0])),1)
        c.convert(self.src,self.out,strict=True)
        with fitz.open(self.out) as doc:self.assertEqual(len(doc[0].get_image_info()),1)

    def test_orange_artwork_is_not_deleted_as_a_logo(self):
        image=Image.new('RGB',(420,86),(220,75,20));ImageDraw.Draw(image).text((60,30),'AN UNRELATED DIAGRAM',fill='white')
        buffer=io.BytesIO();image.save(buffer,format='PNG');pix=fitz.Pixmap(buffer.getvalue())
        self.assertFalse(brand_cleanup.matches(pix,c.ROOT/'assets/header.jpg'))

    def test_bottom_page_numbers_removed_in_preserved_pages(self):
        cv=Canvas(str(self.src),pagesize=(612,792))
        for i in range(2):
            cv.setFont('Helvetica',11);cv.drawString(60,650,'Vector diagram');cv.circle(220,400,40);cv.drawCentredString(306,68,str(i+1));cv.showPage()
        cv.save();result=c.convert(self.src,self.out);self.assertFalse(result['verification']['passed'])
        with fitz.open(self.out) as doc:
            for p in doc:
                body=[s for s in c.spans_of(p) if s['bbox'][1]<p.rect.height-c.BOTTOM]
                self.assertFalse(any(s['text'] in ('1','2') for s in body))

    def test_cell_audit_rejects_swapped_values(self):
        cv=Canvas(str(self.src),pagesize=(600,800));cv.drawString(60,700,'200');cv.drawString(240,700,'100');cv.save()
        proofs=[(('left','100'),0,(55,80,180,115)),(('right','200'),0,(230,80,360,115))]
        with self.assertRaises(ValueError):layout_core.verify_cells(self.src.read_bytes(),proofs,c)

    def test_decimal_and_raised_footnote_keep_separate_positions(self):
        cv=Canvas(str(self.src),pagesize=(600,800))
        for x in (60,260,460):cv.line(x,600,x,700)
        for y in (600,650,700):cv.line(60,y,460,y)
        cv.setFont('Helvetica',11.25);cv.drawString(70,675,'Value');cv.drawString(270,675,'Note')
        cv.drawString(70,625,'0.0');end=70+pdfmetrics.stringWidth('0.0','Helvetica',11.25)
        cv.setFont('Helvetica',6.75);cv.drawString(end,628.75,'1');cv.setFont('Helvetica',11.25);cv.drawString(270,625,'Footnote');cv.save()
        c.convert(self.src,self.out,strict=True)
        with fitz.open(self.out) as doc:
            ss=c.spans_of(doc[0]);value=next(s for s in ss if s['text']=='0.0');marker=next(s for s in ss if s['text']=='1' and s['bbox'][0]>value['bbox'][0] and s['bbox'][0]<250)
            self.assertLess(marker['origin'][1],value['origin'][1]);self.assertAlmostEqual(marker['size'],11,places=2)

    def test_filled_border_strips_are_not_cell_backgrounds(self):
        cv=Canvas(str(self.src),pagesize=(600,800));cv.setFont('Helvetica',11)
        # One compound PDF path whose union bbox contains the entire table.
        path=cv.beginPath()
        for x,y,w,h in [(60,600,400,.5),(60,650,400,.5),(60,700,400,.5),(60,600,.5,100),(260,600,.5,100),(460,600,.5,100)]:path.rect(x,y,w,h)
        cv.drawPath(path,fill=1,stroke=0)
        for x,y,text in [(70,675,'Label'),(270,675,'Value'),(70,625,'Alpha'),(270,625,'123')]:cv.drawString(x,y,text)
        cv.save();c.convert(self.src,self.out,strict=True)
        with fitz.open(self.out) as doc:
            self.assertFalse(any(dr.get('fill') and min(dr['fill'])<.1 and dr['rect'].height>2 and dr['rect'].width>2 for dr in doc[0].get_drawings()))

    def test_white_background_patches_do_not_create_a_table(self):
        cv=Canvas(str(self.src),pagesize=(600,800));cv.setFillColorRGB(1,1,1)
        cv.rect(140,640,320,18,fill=1,stroke=0);cv.rect(70,622,220,18,fill=1,stroke=0)
        cv.setFillColorRGB(0,0,0);cv.setFont('Helvetica',11)
        cv.drawString(70,646,'A normal paragraph with words across a white patch.')
        cv.drawString(70,628,'More prose across the next white patch.');cv.save()
        result=c.convert(self.src,self.out,strict=True)
        self.assertEqual(result['pages'][0]['tables'],0)
        with fitz.open(self.out) as doc:self.assertEqual(len(doc[0].find_tables().tables),0)

    def test_dark_table_background_and_white_text_retained(self):
        table=Table([['Heading','Value'],['Alpha','123']],colWidths=[180,180]);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,'black'),('BACKGROUND',(0,0),(-1,0),'#123456'),('TEXTCOLOR',(0,0),(-1,0),'white')]))
        SimpleDocTemplate(str(self.src)).build([table]);c.convert(self.src,self.out,strict=True)
        with fitz.open(self.out) as doc:
            self.assertTrue(any(s['text']=='Heading' and s['color']==0xffffff for s in c.spans_of(doc[0])))
            self.assertTrue(any(dr.get('fill') and max(dr['fill'])<.5 and dr['rect'].height>3 for dr in doc[0].get_drawings()))

    def test_final_gate_measures_fonts_not_report_claim(self):
        cv=Canvas(str(self.src));cv.setFont('Helvetica',9);cv.drawString(60,700,'Bad font');cv.save()
        report={'font':'Mulish','font_pt':11,'pages':[]}
        self.assertFalse(quality_gate.inspect(self.src,report)['passed'])

    def test_version_mismatch_blocks_conversion_before_download(self):
        from native_host import validate_client_version
        from release import VERSION
        for version in (None,'2.0.4'):
            with self.assertRaisesRegex(ValueError,'version mismatch'):
                validate_client_version({'action':'start','client_version':version})
        validate_client_version({'action':'start','client_version':VERSION})
        validate_client_version({'action':'list'})

    def test_reconverting_generated_output_is_blocked(self):
        cv=Canvas(str(self.src));cv.drawString(60,700,'Original document');cv.save();c.convert(self.src,self.out)
        protected=self.root/'protected.pdf';protected.write_bytes(b'existing result')
        with self.assertRaises(a.BlockedPDF):c.convert(self.out,protected)
        self.assertEqual(protected.read_bytes(),b'existing result')

    def test_strict_rejection_does_not_overwrite_result(self):
        cv=Canvas(str(self.src));cv.drawString(60,700,'Keep diagram');cv.circle(200,400,50);cv.save();self.out.write_bytes(b'existing result')
        with self.assertRaises(c.ReviewRequired):c.convert(self.src,self.out,strict=True)
        self.assertEqual(self.out.read_bytes(),b'existing result')

    def test_partial_batch_uses_review_folder_and_report_link(self):
        from url_batch import Engine
        engine=Engine(self.root/'batches');batch=engine.create(['https://example.invalid/file.pdf']);folder=engine.folder(batch['id'])
        original=folder/'originals/source.pdf';cv=Canvas(str(original));cv.drawString(60,700,'Keep diagram');cv.circle(200,400,50);cv.save()
        batch['jobs'][0].update(original='originals/source.pdf',download='Downloaded');engine.save(batch);job=engine.run(batch['id'])['jobs'][0]
        self.assertEqual(job['status'],'PARTIAL_REVIEW_REQUIRED');self.assertTrue(job['converted'].startswith('review/'))
        self.assertTrue((folder/job['validation_report']).is_file());self.assertFalse(list((folder/'converted').glob('*.pdf')))
        from openpyxl import load_workbook
        book=load_workbook(folder/'conversion_status.xlsx');self.assertEqual(book.active['M2'].hyperlink.target,job['validation_report'])

ETHICS_SOURCE=os.environ.get('ETHICS_SOURCE')
ETHICS_RESULT=os.environ.get('ETHICS_RESULT')
@unittest.skipUnless(ETHICS_SOURCE and ETHICS_RESULT,'Set ETHICS_SOURCE and ETHICS_RESULT for actual-file verification')
class EthicsFileTests(unittest.TestCase):
    def test_all_pages_symbols_styles_and_layout(self):
        report=json.loads(Path(ETHICS_RESULT+'.json').read_text());self.assertTrue(report['verification']['passed']);self.assertEqual(report['preserved_source_pages'],[])
        with fitz.open(ETHICS_SOURCE) as source,fitz.open(ETHICS_RESULT) as result:
            c.mark_source_page_numbers(source)
            for record in report['pages']:
                before=a.content_spans(source[record['source_page']-1])[0]
                after=[s for n in range(record['output_start']-1,record['output_end']) for s in c.spans_of(result[n])]
                self.assertFalse(a.inventory(''.join(s['text'] for s in before))-a.inventory(''.join(s['text'] for s in after)))
                self.assertEqual(sum(s['text']=='•' for s in before),sum(s['text']=='•' for s in after))
                for sp in after:self.assertIn('Mulish',sp['font']);self.assertAlmostEqual(sp['size'],11,places=2)
            self.assertEqual(len(result[0].get_image_info()),1)
            self.assertEqual(report['pages'][5]['tables'],0)
            # Complete source disciplinary table, compared cell-by-cell.
            original=source[27].find_tables().tables[0].extract()
            outpage=result[report['pages'][27]['output_start']-1];actual=outpage.find_tables().tables[0].extract()
            clean=lambda rows:[[''.join((cell or '').split()) for cell in row] for row in rows]
            self.assertEqual(clean(original),clean(actual))
            for dr in outpage.get_drawings():
                self.assertFalse(dr.get('fill') and min(dr['fill'])<.1 and dr['rect'].height>2 and dr['rect'].width>2)
            # Each contents row keeps its original page reference at the right.
            expected=['02','03','07','10','11','13','14','15','16','19','20','21','22','25','29','32','34']
            nums=[s['text'] for s in c.spans_of(result[1]) if s['bbox'][0]>500 and s['bbox'][1]<700 and re.fullmatch(r'\d+',s['text'])]
            self.assertEqual(nums,expected)

if __name__=='__main__':unittest.main()
