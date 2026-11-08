"""Reviewed printed CGAS form profiles; source wording and field associations retained.
The profile is fingerprinted because PDF vector borders alone cannot identify form semantics.
"""
from pathlib import Path
from io import BytesIO
from contextlib import ExitStack
from xml.sax.saxutils import escape
from collections import Counter
import hashlib,json,re,tempfile,base64
from functools import lru_cache
from PIL import Image,ImageDraw
import fitz
from fontTools.ttLib import TTFont as FontInspector
from reportlab.platypus import Paragraph,Table,TableStyle,Spacer,SimpleDocTemplate,Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT,TA_CENTER

ROOT=Path(__file__).resolve().parent
LEAD=re.compile(r'_{3,}|\.{5,}|…{3,}')

def matches(source):
    profiles=json.loads((ROOT/'assets'/'cgas-profiles.json').read_text())
    return profiles.get(hashlib.sha256(Path(source).read_bytes()).hexdigest())

def semantic(text):
    return Counter(ch for ch in LEAD.sub('',text) if not ch.isspace() and ch!='\xad')

def source_spans(page,c):
    fonts={}
    for f in page.get_fonts():
        font=FontInspector(BytesIO(page.parent.extract_font(f[0])[3]))
        fonts[f[3]]=font['name'].getDebugName(6) or f[3]
    spans=c.spans_of(page)
    for s in spans:s['font']=fonts.get(s['font'],s['font'])
    return spans

class DateBoxes(Flowable):
    def __init__(self):super().__init__();self.width=132;self.height=23
    def draw(self):
        self.canv.setStrokeColorRGB(.2,.2,.2);self.canv.setLineWidth(.5)
        self.canv.setFont('Mulish-SemiBold',11)
        for i,ch in enumerate('DDMMYY'):
            self.canv.rect(i*22,0,22,23);self.canv.drawCentredString(i*22+11,8,ch)

class FieldParagraph(Paragraph):
    pass

@lru_cache(maxsize=2048)
def field_markup(kind,width):
    height=9 if kind=='box' else 16 if kind=='grid' else .65
    width=9 if kind=='box' else 144 if kind=='grid' else width
    valign='-1' if kind!='grid' else '-2'
    path=escape(str(ROOT/'assets'/'form_fields'/(kind+'.png')),{'"':'&quot;'})
    if kind=='dots':
        height=1
        im=Image.new('RGBA',(max(4,round(width*4)),4),(255,255,255,0));draw=ImageDraw.Draw(im)
        for x in range(0,im.width,6):draw.ellipse((x,0,x+2,3),fill='black')
        buf=BytesIO();im.save(buf,format='PNG');path='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode('ascii')
    return f'<img src="{path}" width="{width:.3f}" height="{height}" valign="{valign}"/>'

def markup(spans,c,scale,maxwidth):
    # Let writing rules absorb width changes before wrapping their labels.
    # This preserves a source row's field/caption relationship at 11pt.
    fixed=0;leader_widths=[]
    for sp in spans:
        if sp.get('field'):fixed+=12 if sp['field']=='box' else 148
        else:
            fixed+=pdfmetrics.stringWidth(LEAD.sub('  ',sp['text']),'Mulish-Black' if c.is_bold(sp) else 'Mulish-SemiBold',11)
            for match in LEAD.finditer(sp['text']):
                w=(sp['bbox'][2]-sp['bbox'][0])*len(match.group())/max(1,len(sp['text']))*scale*.90
                leader_widths.append(min(maxwidth*.8,max(20,w)))
        fixed+=pdfmetrics.stringWidth(' ','Mulish-SemiBold',11)
    rule_scale=1
    if leader_widths and fixed<maxwidth*.92:
        rule_scale=min(1,max(0,(maxwidth-fixed-3)/sum(leader_widths)))
    parts=[];last=None;last_y=None
    for s in spans:
        if last is not None and (s['bbox'][0]-last>1 or abs(s['origin'][1]-last_y)>2):parts.append(' ')
        last=s['bbox'][2];last_y=s['origin'][1]
        if s.get('field'):
            parts.append(field_markup(s['field'],12 if s['field']=='box' else 144));continue
        text=s['text'];at=0;bits=[]
        for m in LEAD.finditer(text):
            bits.append(escape(text[at:m.start()]))
            fraction=len(m.group())/max(1,len(text))
            width=(s['bbox'][2]-s['bbox'][0])*fraction*scale*.90
            width=max(12,min(maxwidth*.8,max(20,width))*rule_scale)
            bits.append(' '+field_markup('line' if m.group()[0]=='_' else 'dots',width)+' ');at=m.end()
        bits.append(escape(text[at:]));value=''.join(bits)
        if c.is_bold(s):value='<b>'+value+'</b>'
        if s.get('color',0):value='<font color="#%06x">'%s['color']+value+'</font>'
        parts.append(value)
    return ''.join(parts)

def style(c,indent=0,center=False):
    return ParagraphStyle('form',fontName='Mulish-SemiBold',fontSize=11,leading=13.75,
        leftIndent=indent,alignment=TA_CENTER if center else TA_LEFT,splitLongWords=False,
        allowWidows=0,allowOrphans=0,spaceAfter=1)

def checkbox_spans(page):
    result=[]
    for dr in page.get_drawings():
        r=dr['rect']
        if 8<r.width<11 and 8<r.height<12:
            result.append({'text':'','field':'box','bbox':tuple(r),'origin':(r.x0,r.y1-1),
                           'size':8,'font':'Mulish-Regular','flags':0,'color':0})
    return result

def paragraph_rows(spans,c,source_left,source_width,meta):
    scale=c.WIDTH/source_width;items=[]
    # Group each checkbox with its nearest text baseline, rather than letting its
    # vector rectangle's lower edge create a separate row.
    textrows=c.rows_of([s for s in spans if not s.get('field')])
    for field in [s for s in spans if s.get('field')]:
        near=min(textrows,key=lambda row:abs(row[0]-field['origin'][1]))
        near[1].append(field);near[1].sort(key=lambda s:s['bbox'][0])
    merged=[];in_notes=False
    for baseline,row in textrows:
        raw=c.plain([sp for sp in row if not sp.get('field')]).strip()
        if raw.startswith('Notes'):in_notes=True
        starts=raw.startswith('Notes') or bool(re.match(r'^\*{0,2}\d+\.',raw))
        if in_notes and not starts and merged:
            merged[-1][1].extend(row)
        else:merged.append((baseline,row))
    for _,ss in merged:
        top=min(s['bbox'][1]for s in ss);bottom=max(s['bbox'][3]for s in ss)
        # Preserve genuinely separate caption/signature columns; ordinary justified
        # text stays in one paragraph instead of being mistaken for table columns.
        groups=[ss]
        raw=c.plain([s for s in ss if not s.get('field')])
        caption=(('[' in raw or ']' in raw) and len(raw)<100) or raw.strip().startswith('Date :') or raw.strip().startswith('Place :')
        if caption:
            groups=[]
            for s in ss:
                if groups and s['bbox'][0]-groups[-1][-1]['bbox'][2]<25:groups[-1].append(s)
                else:groups.append([s])
        objects=[];widths=[];xstart=max(0,(ss[0]['bbox'][0]-source_left)*scale)
        for gi,g in enumerate(groups):
            x=max(0,(g[0]['bbox'][0]-source_left)*scale)
            right=(groups[gi+1][0]['bbox'][0]-source_left)*scale-3 if gi+1<len(groups) else c.WIDTH
            width=right-x
            # Center headings; keep signature blocks in their source column.
            plain=c.plain([s for s in g if not s.get('field')])
            heading=plain.strip().startswith(('CAPITAL GAINS ACCOUNT','FORM A','FORM B','FOR THE USE OF DEPOSIT OFFICE','Application for conversion','Scheme, 1988'))
            centered=heading and len(groups)==1
            if centered:x=0;width=c.WIDTH;xstart=0
            p=FieldParagraph(markup(g,c,scale,width),style(c,center=centered))
            if p.minWidth()>width+.1:
                extra=p.minWidth()-width+.5
                room=x if not widths else max(0,widths[-1]-objects[-1].minWidth()-8)
                if extra<=room:
                    x-=extra;width+=extra
                    if widths:widths[-1]-=extra
                    else:xstart=x
                else:raise c.ReviewRequired('CGAS form field or word cannot fit at 11pt: '+plain[:90])
            p.keepWithNext=heading
            objects.append(p);widths.append(width)
        if len(objects)==1:
            p=objects[0]
            p.style.leftIndent=xstart
            obj=p
        else:
            obj=Table([objects],colWidths=widths,hAlign='RIGHT')
            obj.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
        obj.form_plain=raw
        obj.has_field=any(s.get('field') or LEAD.search(s['text']) for s in ss)
        items.append((top,bottom,obj))
    return items

def build_story(src,profile,c):
    story=[];expected=[];meta={'checkboxes':0,'date_grids':0,'account_digit_grids':0,'section_tables':0,'writing_lines':0}
    for pn,page in enumerate(src):
        spans=source_spans(page,c);expected.extend(s['text']for s in spans)
        meta['writing_lines']+=sum(len(LEAD.findall(s['text']))for s in spans)
        source_left=min(s['bbox'][0]for s in spans);source_right=max(s['bbox'][2]for s in spans)
        source_width=source_right-source_left;items=[]
        if profile=='a':
            boxes=checkbox_spans(page);meta['checkboxes']+=len(boxes);spans+=boxes
            tabs=page.find_tables().tables
            section_tabs=[t for t in tabs if len(t.cells)==12 and t.bbox[1]<250]
            for tab in section_tabs:
                table_rows=[]
                for row in tab.rows:
                    data=[]
                    for cell in row.cells:
                        r=fitz.Rect(cell);selected=[s for s in spans if r.contains(fitz.Point((s['bbox'][0]+s['bbox'][2])/2,s['origin'][1]-s['size']*.3))]
                        spans=[s for s in spans if s not in selected]
                        data.append(FieldParagraph(markup(sorted(selected,key=lambda s:(round(s['origin'][1]/2),s['bbox'][0])),c,1,340),style(c)))
                    table_rows.append(data)
                table=Table(table_rows,colWidths=[75,c.WIDTH-150,75],hAlign='LEFT',splitByRow=1,repeatRows=0)
                table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,'#333333'),('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),'#eeeeee'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                # Two adjacent source tables are independent lists of tax sections.
                # Stack them at full width so 11pt descriptions remain readable.
                items.append((tab.bbox[1]+len(items)*.01,tab.bbox[3],table));meta['section_tables']+=1
            for tab in [t for t in tabs if len(t.cells)==6]:
                r=fitz.Rect(tab.bbox);letters=[s for s in spans if r.contains(fitz.Point((s['bbox'][0]+s['bbox'][2])/2,s['origin'][1]-s['size']*.3))]
                nearby=[s for s in spans if abs(s['origin'][1]-letters[0]['origin'][1])<8 and s['bbox'][2]<r.x0 and s not in letters]
                selected=letters+nearby;spans=[s for s in spans if s not in selected]
                label=FieldParagraph(markup(nearby,c,1,200),style(c))
                obj=Table([[label,DateBoxes()]],colWidths=[190,132],hAlign='LEFT')
                obj.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
                items.append((r.y0,r.y1,obj));meta['date_grids']+=1
            if pn==0:
                r=fitz.Rect(243.48,363.72,417.84,376.08)
                spans.append({'text':'','field':'grid','bbox':tuple(r),'origin':(r.x0,r.y1-2),'size':8,'font':'Mulish-Regular','flags':0,'color':0});meta['account_digit_grids']=1
        items.extend(paragraph_rows(spans,c,source_left,source_width,meta));items.sort(key=lambda x:x[0])
        last=None
        for i,(top,bottom,obj) in enumerate(items):
            if last is not None and top-last>4:
                gap=Spacer(1,min(32,(top-last)*c.WIDTH/source_width));gap.keepWithNext=True;story.append(gap)
            # Captions belong to the line they describe. Keep small signature
            # blocks together and preserve the blank space above their lines.
            if i+1<len(items):
                nexttext=getattr(items[i+1][2],'form_plain','').strip()
                if nexttext.startswith('[') or (getattr(obj,'has_field',False) and ('Signature' in nexttext or 'Ofﬁcer-in-charge' in nexttext)):
                    obj.keepWithNext=True
            story.append(obj);last=max(bottom,last or bottom)
        story.append(Spacer(1,12))
    return story,' '.join(expected),meta

def convert(source,destination):
    import converter as c
    source=Path(source);destination=Path(destination);profile=matches(source)
    if not profile:raise c.ReviewRequired('Unrecognized CGAS form version.')
    c.setup_fonts()
    with ExitStack() as stack:
        src=stack.enter_context(fitz.open(source))
        if src.is_form_pdf:raise c.ReviewRequired('Interactive forms require a separate field-preserving workflow.')
        story,expected,meta=build_story(src,profile,c)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as td,ExitStack() as handles:
            body=Path(td)/'body.pdf'
            doc=SimpleDocTemplate(str(body),pagesize=A4,leftMargin=c.LEFT-6,rightMargin=c.RIGHT-6,topMargin=c.TOP-6,bottomMargin=c.BOTTOM-6,title='CGAS Form '+profile.upper()+' - A4 Mulish 11pt')
            doc.build(story)
            bodydoc=handles.enter_context(fitz.open(body));out=handles.enter_context(fitz.open())
            actual=''.join(p.get_text() for p in bodydoc)
            if semantic(expected)!=semantic(actual):
                raise c.ReviewRequired('CGAS text inventory mismatch: missing '+str(semantic(expected)-semantic(actual))+'; extra '+str(semantic(actual)-semantic(expected)))
            for pn,p in enumerate(bodydoc):
                dest=out.new_page(width=A4[0],height=A4[1]);sp=c.spans_of(p)
                rects=[fitz.Rect(s['bbox'])for s in sp]+[dr['rect'] for dr in p.get_drawings()]+[fitz.Rect(im['bbox'])for im in p.get_image_info()]
                shift=c.TOP-min(r.y0 for r in rects)
                if min(r.x0 for r in rects)<c.LEFT-.5 or max(r.x1 for r in rects)>A4[0]-c.RIGHT+.5:raise c.ReviewRequired('CGAS field or table exceeded horizontal margins.')
                if max(r.y1 for r in rects)+shift>A4[1]-c.BOTTOM+.5:raise c.ReviewRequired('CGAS body exceeded bottom margin.')
                dest.show_pdf_page(fitz.Rect(0,shift,A4[0],A4[1]+shift),bodydoc,pn)
                dest.insert_image(fitz.Rect(0,0,A4[0],c.HEADER),filename=str(ROOT/'assets'/'header.jpg'))
            font=fitz.Font(fontfile=str(ROOT/'assets'/'Mulish-SemiBold.ttf'))
            for pn,page in enumerate(out):
                page.insert_font(fontname='Mulish',fontfile=str(ROOT/'assets'/'Mulish-SemiBold.ttf'))
                label='P a g e';count=f'{pn+1} | {len(out)}';w=font.text_length(label,fontsize=11);last=font.text_length(count,fontsize=11)
                x=531.315/595.32*A4[0]-w-4-last;y=A4[1]-(841.92-786.696)
                page.insert_text((x,y),label,fontname='Mulish',fontsize=11,color=(.19,.51,.85))
                page.insert_text((x+w+4,y),count,fontname='Mulish',fontsize=11,color=(.15,.21,.28))
                ss=[s for s in c.spans_of(page)if s['bbox'][1]<A4[1]-c.BOTTOM]
                if any(s['bbox'][0]<c.LEFT-.5 or s['bbox'][2]>A4[0]-c.RIGHT+.5 for s in ss):raise c.ReviewRequired('CGAS text exceeded horizontal margins.')
                if any(abs(s['size']-11)>.01 for s in ss):raise c.ReviewRequired('CGAS font size mismatch.')
            out.save(destination,garbage=4,deflate=True)
            report={'input':source.name,'source_pages':len(src),'output_pages':len(out),'page_size':'A4','font':'Mulish','font_pt':11,'body_font_sizes_pt':[11.0],'top_margin_cm':3,'left_margin_cm':1.88,'right_margin_cm':1.89,'bottom_margin_cm':2.55,'profile':'CGAS '+profile.upper(),'status':'CONVERTED_REVIEW_LAYOUT','tables':meta['section_tables']+meta['date_grids'],'form_elements':meta,'character_inventory':'passed; decorative writing leaders rendered as graphic rules','notes':['Printed form: no interactive fields in source.','Writing leaders resized to fit fields; all wording and numeric content retained.','Section tables stacked vertically at 11pt; rows kept together.' if profile=='a' else 'Dotted writing lines resized within the original field rows.','Original outer frame/logo replaced by reference banner and footer.']}
    Path(str(destination)+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report
