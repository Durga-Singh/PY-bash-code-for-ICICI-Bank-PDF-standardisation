"""Local PDF reflow tool. Originals are never modified. See README before batch use."""
from pathlib import Path
from contextlib import ExitStack
from io import BytesIO
from types import SimpleNamespace
import re, json, collections, argparse, tempfile, hashlib
from xml.sax.saxutils import escape
import fitz
from fontTools.ttLib import TTFont as FontInspector
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Spacer, Image, Flowable, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import Color

ROOT=Path(__file__).resolve().parent
CM=72/2.54
SIZE=11.0 # Word font size 11 (points)
LEFT=1.88*CM; RIGHT=1.89*CM; BOTTOM=2.55*CM
HEADER=64.64996337890625
TOP=3*CM
WIDTH=A4[0]-LEFT-RIGHT

class ReviewRequired(Exception): pass

def setup_fonts():
    for name in ('Mulish-SemiBold','Mulish-Black','Mulish-SemiBoldItalic','Mulish-BlackItalic'):
        pdfmetrics.registerFont(TTFont(name,str(ROOT/'assets'/f'{name}.ttf')))
    pdfmetrics.registerFont(TTFont('PDF-Symbols',str(ROOT/'assets'/'DejaVuSans-Symbols.ttf')))
    pdfmetrics.registerFontFamily('Mulish-SemiBold',normal='Mulish-SemiBold',bold='Mulish-Black',italic='Mulish-SemiBoldItalic',boldItalic='Mulish-BlackItalic')

def style(bold=False,align=TA_LEFT):
    return ParagraphStyle('body',fontName='Mulish-Black' if bold else 'Mulish-SemiBold',fontSize=SIZE,leading=SIZE*1.25,alignment=align,spaceAfter=0,spaceBefore=0,splitLongWords=False,allowWidows=0,allowOrphans=0)

def para(text,bold=False,align=TA_LEFT):
    return Paragraph(escape(text).replace('\n','<br/>'),style(bold,align))

def canonical(text):
    # A multiset, insensitive to wrapping and PDF extraction order; includes punctuation/digits.
    return collections.Counter(c for c in text if not c.isspace() and c!='\xad')

@__import__('functools').lru_cache(maxsize=16)
def visible_glyphs(path):
    f=FontInspector(path);c=f.getBestCmap();g=f['glyf']
    return {chr(k) for k,v in c.items() if g[v].numberOfContours!=0}|set(' \n\r\t')

def is_bold(s):
    name=s['font']
    # Explicit font weight names take precedence over unreliable PDF bold flags.
    normalized=re.sub(r'[^a-z]', '', name.lower())
    if any(weight in normalized for weight in ('semibold','demibold','regular','normal','medium','light','book')):return False
    return bool(s.get('flags',0)&16) or any(weight in normalized for weight in ('black','bold','heavy')) or ' Blk' in name

def spans_of(page):
    out=[]
    for b in page.get_text('rawdict')['blocks']:
        for line in b.get('lines',[]):
            for span in line['spans']:
                chars=[]
                def flush():
                    if not chars:return
                    s={k:v for k,v in span.items() if k!='chars'}
                    s['text']=''.join(c['c']for c in chars)
                    s['origin']=chars[0]['origin']
                    s['bbox']=(min(c['bbox'][0]for c in chars),min(c['bbox'][1]for c in chars),max(c['bbox'][2]for c in chars),max(c['bbox'][3]for c in chars))
                    out.append(s);chars.clear()
                for ch in span['chars']:
                    if ch['c'].isspace():flush()
                    else:
                        if chars and ch['bbox'][0]-chars[-1]['bbox'][2]>2:flush()
                        chars.append(ch)
                flush()
    # PDF underlines are often graphics rather than text attributes.
    rules=[];vertical=[]
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0]=='re':box=fitz.Rect(item[1])
            elif item[0]=='l':box=fitz.Rect(item[1],item[2]).normalize()
            else:continue
            if box.height<=1.5 and box.width>2:rules.append(box)
            if box.width<=1.5 and box.height>3:vertical.append(box)
    links=page.get_links()
    for sp in out:
        box=fitz.Rect(sp['bbox']);base=sp['origin'][1];size=sp['size']
        for rule in rules:
            # Connected grid edges are table rules, not text decoration.
            if any(abs(v.x0-rule.x0)<2 or abs(v.x0-rule.x1)<2 for v in vertical if v.y0-2<=rule.y0<=v.y1+2):continue
            coverage=max(0,min(box.x1,rule.x1)-max(box.x0,rule.x0))/max(box.width,.01)
            if coverage<.85:continue
            y=(rule.y0+rule.y1)/2
            if -.03*size<=y-base<=.25*size:sp['underline']=True
            if -.45*size<=y-base<=-.18*size:sp['strike']=True
        for link in links:
            lr=fitz.Rect(link['from'])
            if lr.contains(fitz.Point((box.x0+box.x1)/2,base-size*.35)) and link.get('kind')==fitz.LINK_URI:
                sp['uri']=link['uri'];break
    from pdf_preflight import resolve_spans
    return resolve_spans(page,out)

def is_footer(s,page):
    # Only remove a bare page number in the bottom 4%; retain other footer/legal text.
    return re.fullmatch(r'\s*(?:Page\s*)?\d+\s*',s['text']) is not None and (s['bbox'][1]>page.rect.height*.96 or (s['color']==0xffffff and s['size']<5))

def rows_of(spans):
    rows=[]
    def baseline(s):return s['origin'][1]+(s['size']*.55 if s.get('flags',0)&1 else (3 if s['size']<5.4 else 0))
    for s in sorted(spans,key=lambda z:(baseline(z),z['bbox'][0])):
        if rows and abs(rows[-1][0]-baseline(s))<2.2:rows[-1][1].append(s)
        else:rows.append((baseline(s),[s]))
    return [(y,sorted(ss,key=lambda z:z['bbox'][0]))for y,ss in rows]

def plain(spans):
    rows=[]
    for _,ss in rows_of(spans):
        line='';last=None
        for s in ss:
            text=s['text'].strip()
            if last is not None and s['bbox'][0]-last>1.0:line+=' '
            line+=text;last=s['bbox'][2]
        rows.append(line)
    return '\n'.join(rows)

def markup(spans):
    result=[]
    for _,ss in rows_of(spans):
        bits=[];last=None
        for s in ss:
            v=escape(s['text'].strip()).replace('➢','<font name="PDF-Symbols">➢</font>')
            if s.get('flags',0)&1 or s['size']<5.4:v=f'<super size="{SIZE}" rise="2.5">{v}</super>'
            if is_bold(s):v='<b>'+v+'</b>'
            if s.get('flags',0)&2 or 'italic' in s['font'].lower() or 'oblique' in s['font'].lower():v='<i>'+v+'</i>'
            if s.get('underline'):v='<u>'+v+'</u>'
            if s.get('strike'):v='<strike>'+v+'</strike>'
            if s.get('color',0):v=f'<font color="#{s["color"]:06x}">{v}</font>'
            if s.get('uri'):v='<link href="'+escape(s['uri'], {'"':'&quot;'})+'">'+v+'</link>'
            if last is not None and s['bbox'][0]-last>1:bits.append(' ')
            bits.append(v);last=s['bbox'][2]
        result.append(''.join(bits))
    return '<br/>'.join(result)

class PositionedRow(Flowable):
    """Reflow each original horizontal text group, retaining its column position."""
    def __init__(self,groups,x0,source_width):
        super().__init__();self.groups=groups;self.x0=x0;self.source_width=source_width
    def wrap(self,availWidth,availHeight):
        self.parts=[];height=0
        for i,g in enumerate(self.groups):
            x=max(0,(g[0]['bbox'][0]-self.x0)/self.source_width*WIDTH)
            end=(max(x+15,(self.groups[i+1][0]['bbox'][0]-self.x0)/self.source_width*WIDTH-4) if i+1<len(self.groups) else WIDTH)
            p=Paragraph(markup(g),style())
            w,h=p.wrap(max(15,end-x),availHeight)
            self.parts.append((x,p,w,h));height=max(height,h)
        self.width=WIDTH;self.height=height;return WIDTH,height
    def draw(self):
        for x,p,w,h in self.parts:p.drawOn(self.canv,x,self.height-h)

class FormCell(Flowable):
    """Retain blank entry/signature space and original columns inside form cells."""
    def __init__(self,spans,box):
        super().__init__();self.spans=spans;self.box=box
    def wrap(self,availWidth,availHeight):
        self.parts=[];self.height=self.box.height;last_bottom=0
        for _,ss in rows_of(self.spans):
            groups=[]
            for sp in ss:
                if groups and sp['bbox'][0]-groups[-1][-1]['bbox'][2]<15:groups[-1].append(sp)
                else:groups.append([sp])
            top=max(last_bottom,min(sp['bbox'][1]for sp in ss)-self.box.y0-2);row_height=0
            for i,g in enumerate(groups):
                x=max(0,(min(sp['bbox'][0]for sp in g)-self.box.x0)/self.box.width*availWidth)
                end=(groups[i+1][0]['bbox'][0]-self.box.x0)/self.box.width*availWidth-3 if i+1<len(groups)else availWidth
                width=max(8,end-x);paragraph=Paragraph(markup(g),style());_,height=paragraph.wrap(width,10000)
                if paragraph.minWidth()>width+.1:raise ReviewRequired('Form cell cannot fit at 11pt without breaking a field.')
                self.parts.append((x,top,width,height,paragraph));row_height=max(row_height,height)
            last_bottom=top+row_height
        self.height=max(self.height,last_bottom+2);self.width=availWidth
        return self.width,self.height
    def draw(self):
        for x,top,width,height,paragraph in self.parts:paragraph.drawOn(self.canv,x,self.height-top-height)

def build_table(tab,spans,source_width,drawings,preserve_form=False):
    cells=[fitz.Rect(c) for c in tab.cells if c]
    xs=sorted(set(round(v,2) for c in cells for v in (c.x0,c.x1)))
    ys=sorted(set(round(v,2) for c in cells for v in (c.y0,c.y1)))
    # find_tables boundaries occasionally differ by tiny floating point amounts.
    def uniq(vals):
        out=[]
        for v in vals:
            if not out or v-out[-1]>.5:out.append(v)
        return out
    xs=uniq(xs);ys=uniq(ys)
    cols=len(xs)-1;rows=len(ys)-1
    widths=[(xs[i+1]-xs[i])/source_width*WIDTH for i in range(cols)]
    total=sum(widths)
    for i,w in enumerate(widths):
        if w<20:
            delta=20-w;j=max(range(cols),key=lambda k:widths[k]);widths[j]-=delta;widths[i]=20
    data=[['' for _ in range(cols)]for _ in range(rows)]
    commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,'#777777'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]
    consumed=set();texts=[];spans_list=[];minimums=[min(w,20)for w in widths]
    for cell in cells:
        ci=min(range(len(xs)),key=lambda i:abs(xs[i]-cell.x0));cj=min(range(len(xs)),key=lambda i:abs(xs[i]-cell.x1))-1
        ri=min(range(len(ys)),key=lambda i:abs(ys[i]-cell.y0));rj=min(range(len(ys)),key=lambda i:abs(ys[i]-cell.y1))-1
        for drawing in drawings:
            fill=drawing.get('fill');r=fitz.Rect(drawing['rect'])
            if fill and r.height>1 and r.width>1 and r.contains(fitz.Point((cell.x0+cell.x1)/2,(cell.y0+cell.y1)/2)):
                rgb=fill if len(fill)==3 else (fill[0],)*3
                if min(rgb)<.98:commands.append(('BACKGROUND',(ci,ri),(cj,rj),Color(*rgb)))
        selected=[]
        for k,s in enumerate(spans):
            if k in consumed:continue
            r=fitz.Rect(s['bbox']);cx=(r.x0+r.x1)/2;cy=s['origin'][1]-s['size']*.35
            if cell.x0-.2<=cx<=cell.x1+.2 and cell.y0-.2<=cy<=cell.y1+.2:
                selected.append(s);consumed.add(k)
        txt=plain(selected);texts.append(txt)
        if ci==cj:
            for sp in selected:
                if sp['text']:
                    minimums[ci]=max(minimums[ci],pdfmetrics.stringWidth(sp['text'],'Mulish-Black' if is_bold(sp)else 'Mulish-SemiBold',SIZE)+5)
        if ci==cj:
            # Superscripts attached to a word still consume horizontal space.
            wordfont='Mulish-Black' if any(is_bold(sp)for sp in selected) else 'Mulish-SemiBold'
            for word in txt.split():minimums[ci]=max(minimums[ci],pdfmetrics.stringWidth(word,wordfont,SIZE)+5)
        bold=bool(selected) and all(is_bold(s)for s in selected)
        num=bool(re.fullmatch(r'[\d,().%+\-\s]+',txt.strip()))
        cell_markup=markup(selected)
        if len(txt)>100 and not num:
            sections=[];last_y=None
            for yy,line in rows_of(selected):
                if last_y is None or yy-last_y>max(sp['size']for sp in line)*1.8:sections.append([])
                sections[-1].append(markup(line));last_y=yy
            cell_markup='<br/><br/>'.join(' '.join(section)for section in sections)
        alignment=TA_RIGHT if num and ci>0 else TA_LEFT
        # Retain source-centred short cells, especially vertically merged allowances.
        # Inspect each source line; a long paragraph merely filling its cell is not evidence.
        lines=[line for _,line in rows_of(selected)]
        centred=bool(lines) and all(
            abs((min(s['bbox'][0] for s in line)+max(s['bbox'][2] for s in line))/2-cell.x0-cell.width/2)<max(2,cell.width*.04)
            and max(s['bbox'][2] for s in line)-min(s['bbox'][0] for s in line)<cell.width*.85
            for line in lines)
        if centred and not preserve_form:
            alignment=TA_CENTER
            if rj>ri:
                top=min(s['bbox'][1] for s in selected);bottom=max(s['bbox'][3] for s in selected)
                if abs((top+bottom)/2-(cell.y0+cell.y1)/2)<max(5,cell.height*.12):
                    commands.append(('VALIGN',(ci,ri),(cj,rj),'MIDDLE'))
        data[ri][ci]=FormCell(selected,cell) if preserve_form and selected else Paragraph(cell_markup,style(bold,alignment))
        if cj>ci or rj>ri:
            commands.append(('SPAN',(ci,ri),(cj,rj)));spans_list.append((ci,ri,cj,rj))
    first_nonempty=[i for i,cell in enumerate(data[0]) if hasattr(cell,'getPlainText') and cell.getPlainText().strip()]
    if len(first_nonempty)==1:
        heading=data[0][first_nonempty[0]];data[0]=[heading]+['']*(cols-1)
        commands=[cmd for cmd in commands if not(cmd[0]=='SPAN' and cmd[1][1]==0)]
        commands.append(('SPAN',(0,0),(cols-1,0)))
    extracted=' '.join(texts)
    repeat=0 if preserve_form else 3 if 'Unaudited' in extracted[:600] else (0 if cols==2 else 1)
    # Never split a merged heading across the repeating boundary.
    while any(ri<repeat<=rj for ci,ri,cj,rj in spans_list):repeat=max(rj+1 for ci,ri,cj,rj in spans_list if ri<repeat<=rj)
    repeat=min(repeat,rows)
    for i,minimum in enumerate(minimums):
        if widths[i]<minimum:
            deficit=minimum-widths[i];j=max(range(cols),key=lambda k:widths[k]-minimums[k] if k!=i else -1)
            if widths[j]-minimums[j]<deficit:raise ReviewRequired('Table is too wide at the requested font size.')
            widths[j]-=deficit;widths[i]=minimum
    if preserve_form:
        for ri,row in enumerate(data[:-1]):
            if any(isinstance(cell,FormCell) and plain(cell.spans).startswith('Section') for cell in row):
                commands.append(('NOSPLIT',(0,ri),(-1,ri+1)))
    table=Table(data,colWidths=widths,repeatRows=repeat,hAlign='RIGHT',splitByRow=1,minRowHeights=[ys[i+1]-ys[i]for i in range(rows)] if preserve_form else None)
    table.setStyle(TableStyle(commands));table.spaceAfter=3
    return table,consumed,extracted

def numeric_rows(document):
    result=collections.Counter()
    for page in document:
        ss=spans_of(page)
        for table in page.find_tables().tables:
            for row in table.rows:
                box=fitz.Rect(row.bbox);numbers=[]
                for sp in ss:
                    x=(sp['bbox'][0]+sp['bbox'][2])/2;y=sp['origin'][1]-sp['size']*.35
                    if box.contains(fitz.Point(x,y)) and re.fullmatch(r'\d[\d,]*\.\d+%?',sp['text']):numbers.append(sp)
                values=tuple(sp['text']for sp in sorted(numbers,key=(lambda z:(round(z['origin'][1],1),z['bbox'][0])) if sum(cell is not None for cell in row.cells)<=2 else (lambda z:z['bbox'][0])))
                if values:result[values]+=1
    return result

def mark_source_page_numbers(doc):
    candidates=[]
    for page in doc:
        for row in page.get_text('dict')['blocks']:
            for line in row.get('lines',[]):
                spans=[sp for sp in line['spans'] if sp['text'].strip()]
                if len(spans)!=1:continue
                sp=spans[0];box=fitz.Rect(sp['bbox']);value=sp['text'].strip()
                edge=box.y1<page.rect.height*.09 or box.y0>page.rect.height*.85
                if value==str(page.number+1) and edge and abs((box.x0+box.x1)/2-page.rect.width/2)<page.rect.width*.08:candidates.append((page.number,box))
    matched={}
    for pn,box in candidates:
        if sum(abs(other.y0-box.y0)<2 for _,other in candidates)>=2:matched.setdefault(pn,[]).append(box)
    doc._source_page_numbers=matched

def source_page_number(sp,page):
    return any(box.contains(fitz.Rect(sp['bbox'])) for box in getattr(page.parent,'_source_page_numbers',{}).get(page.number,[]))

def legacy_header_boxes(page):
    known=json.loads((ROOT/'assets'/'known_header_logos.json').read_text())
    boxes=[]
    for info in page.get_image_info(xrefs=True):
        box=fitz.Rect(info['bbox'])
        if info.get('xref') and box.y1<page.rect.height*.28:
            pix=fitz.Pixmap(page.parent,info['xref'])
            digest=hashlib.sha256(pix.samples).hexdigest()
            from brand_cleanup import matches
            if digest in known or matches(pix,ROOT/'assets/header.jpg'):boxes.append(box)
    vector_file=ROOT/'assets/known_vector_headers.json'
    if vector_file.exists():
        drawings=[fitz.Rect(d['rect']) for d in page.get_drawings() if d['rect'].y1<page.rect.height*.12 and d['rect'].width>0]
        if drawings:
            region=drawings[0]
            for box in drawings[1:]:region=region|box
            if not any(region.intersects(fitz.Rect(sp['bbox'])) for sp in spans_of(page)):
                digest=hashlib.sha256(page.get_pixmap(clip=region,matrix=fitz.Matrix(2,2),alpha=False).samples).hexdigest()
                if digest in json.loads(vector_file.read_text()):boxes.append(region)
    return boxes

def decorative_border(drawing,page):
    r=fitz.Rect(drawing['rect'])
    if min(r.width,r.height)<=4:
        outer=(r.x1<page.rect.width*.1 or r.x0>page.rect.width*.9 or r.y1<page.rect.height*.1 or r.y0>page.rect.height*.9)
        if outer and not any((fitz.Rect(sp['bbox'])+(-3,-3,3,3)).intersects(r)for sp in spans_of(page)):
            return bool(drawing.get('fill')) and all(item[0]=='re' for item in drawing['items'])
    if r.width<page.rect.width*.7 or r.height<50:return False
    body=[fitz.Rect(sp['bbox'])for sp in spans_of(page)if not is_footer(sp,page)]
    if r.height<page.rect.height*.7 and (not body or not all((r+(-3,-3,3,3)).contains(q)for q in body)):return False
    for item in drawing['items']:
        if item[0]=='re':
            q=fitz.Rect(item[1])
            if not all(abs(a-b)<1 for a,b in zip(q,r)):return False
        elif item[0]=='l':
            a,b=item[1:3]
            if not (any(abs(a.x-edge)<1 and abs(b.x-edge)<1 for edge in (r.x0,r.x1)) or any(abs(a.y-edge)<1 and abs(b.y-edge)<1 for edge in (r.y0,r.y1))):return False
        else:return False
    return bool(drawing['items'])

def convert_legacy(source,destination):
    if Path(source).resolve()==Path(destination).resolve():raise ValueError('Output must not overwrite the original.')
    import cgas_forms
    if cgas_forms.matches(source):return cgas_forms.convert(source,destination)
    import bonus_terms
    bonus_layout=bonus_terms.matches(source)
    import annual_report
    if annual_report.matches(source):return annual_report.convert(source,destination)
    with ExitStack() as resources:
        setup_fonts();source=Path(source);destination=Path(destination)
        if source.resolve()==destination.resolve():raise ValueError('Output must not overwrite the original.')
        src=resources.enter_context(fitz.open(source))
        if src.needs_pass:raise ReviewRequired('Encrypted PDF: provide an unlocked copy.')
        if src.is_form_pdf:raise ReviewRequired('Interactive form: reflow could lose fields. Use the editable source.')
        trade_profile=ROOT/'assets'/'trade-form-profile.json'
        form_layout=trade_profile.exists() and hashlib.sha256(source.read_bytes()).hexdigest()==json.loads(trade_profile.read_text())['sha256']
        if any(p.rotation for p in src):raise ReviewRequired('Rotated pages require a separate layout profile.')
        border_pages=sum(any(decorative_border(dr,pg)for dr in pg.get_drawings())for pg in src)
        continuous=form_layout or bool(legacy_header_boxes(src[0])) or border_pages>=max(1,len(src)*.5)
        glyphs=visible_glyphs(ROOT/'assets'/'Mulish-SemiBold.ttf')
        boldglyphs=visible_glyphs(ROOT/'assets'/'Mulish-Black.ttf')
        story=[];source_content=[];structured=[];table_count=0;page_map=[];warnings=[];removed_headers=0;removed_borders=0
        for pn,page in enumerate(src):
            spans=[s for s in spans_of(page) if not is_footer(s,page)]
            if bonus_layout:spans=bonus_terms.clean_spans(spans,pn)
            if form_layout:
                # Reviewed printed form: replace its tokenized page counter;
                # retain its repeated document version once, at the end.
                spans=[s for s in spans if not (s['bbox'][1]>page.rect.height*.92 and
                    (s['text']=='Page' or s['text'].isdigit() or
                     (pn<len(src)-1 and s['bbox'][1]>page.rect.height*.935)))]
            if not spans:raise ReviewRequired(f'Page {pn+1} has no extractable text (scan/empty page).')
            for s in spans:
                missing=set(s['text'])-((boldglyphs if is_bold(s) else glyphs)|{'➢'})
                if missing:raise ReviewRequired(f'Font coverage on page {pn+1}: {repr("".join(sorted(missing)))}. Install complete Mulish font files in assets.')
            source_content.extend(s['text'] for s in spans)
            header_boxes=legacy_header_boxes(page);removed_headers+=len(header_boxes)
            tabs=bonus_terms.tables(pn) if bonus_layout else page.find_tables().tables
            if form_layout and pn==3:
                for box in [(72.024,72,536.74,129.26),(70.584,149.3,524.854,160.82)]:
                    tabs.append(SimpleNamespace(bbox=box,cells=[box]))
            if form_layout and pn==1:
                original=tabs[0];bottom=max(c[3] for c in original.cells if c)
                tail=[c for c in original.cells if c and abs(c[3]-bottom)<.5]
                split=min(c[1] for c in tail)
                tabs=[SimpleNamespace(bbox=(original.bbox[0],original.bbox[1],original.bbox[2],split),cells=[c for c in original.cells if c and c not in tail]),
                      SimpleNamespace(bbox=(original.bbox[0],split,original.bbox[2],bottom),cells=tail)]
            # Unknown vector graphics must be reviewed, rather than silently dropped.
            for dr in page.get_drawings():
                rect=fitz.Rect(dr['rect'])
                if any((box+(-2,-2,2,2)).contains(rect)for box in header_boxes):continue
                if any((fitz.Rect(t.bbox)+(-2,-2,2,2)).contains(rect) for t in tabs):continue
                if decorative_border(dr,page):removed_borders+=1;continue
                if rect.is_empty:continue
                if rect.height < 1.5 and rect.width > 1 and not any((fitz.Rect(t.bbox)+(-2,-2,2,2)).contains(rect) for t in tabs):
                    matches=[s for s in spans if abs(s['bbox'][3]-rect.y0)<4 and s['bbox'][0]<rect.x1+1 and s['bbox'][2]>rect.x0-1]
                    if matches:
                        for s in matches:s['underline']=True
                        continue
                if not any((fitz.Rect(t.bbox)+(-2,-2,2,2)).contains(rect) for t in tabs):
                    feature='checkboxes or vector symbols' if max(rect.width,rect.height)<20 else 'vector diagrams/artwork outside recognized tables'
                    raise ReviewRequired(f'Page {pn+1} contains {feature}. This layout needs custom handling to preserve its meaning during 11pt reflow.')
            x0=min(s['bbox'][0] for s in spans);x1=max(s['bbox'][2]for s in spans)
            if tabs:x0=min(x0,min(t.bbox[0]for t in tabs));x1=max(x1,max(t.bbox[2]for t in tabs))
            source_width=x1-x0;items=[];used=set()
            for tab in tabs:
                table,consumed,txt=build_table(tab,spans,source_width,page.get_drawings(),preserve_form=form_layout and pn<3)
                if used&consumed:raise ReviewRequired(f'Overlapping extracted tables on page {pn+1}.')
                if bonus_layout:table.splitByRow=0
                if form_layout and pn==1 and tab is tabs[-1]:table.keepWithNext=True
                used|=consumed;structured.append(txt);table_count+=1
                items.append((tab.bbox[1],tab.bbox[3],table))
            prose=[]
            duplicate_images=json.loads((ROOT/'assets'/'known_duplicate_text_images.json').read_text())
            text_overlay_page=any(info.get('xref') and hashlib.sha256(fitz.Pixmap(src,info['xref']).samples).hexdigest() in duplicate_images for info in page.get_image_info(xrefs=True))
            for y,ss in rows_of([s for k,s in enumerate(spans)if k not in used]):
                groups=[]
                for s in ss:
                    if groups and s['bbox'][0]-groups[-1][-1]['bbox'][2]<15:groups[-1].append(s)
                    else:groups.append([s])
                if text_overlay_page:groups=[ss]
                structured.extend(s['text']for s in ss)
                top=min(s['bbox'][1]for s in ss);bottom=max(s['bbox'][3]for s in ss)
                text=plain(ss)
                canmerge=(prose and len(groups)==1 and len(prose[-1][2])==1 and top-prose[-1][1]<1.8
                    and abs(groups[0][0]['bbox'][0]-prose[-1][2][0][0]['bbox'][0])<20
                    and not re.match(r'^(?:[0-9]+\.|\([ivx]+\)|[a-z][.)]|[•●▪])\s',text)
                    and not is_bold(ss[0]) and not is_bold(prose[-1][2][0][0])
                    and not re.fullmatch(r'\d+\.\s*(?:General Terms|Offer Details):?',plain(prose[-1][2][0]).strip())
                    and not any(t.bbox[1]>=prose[-1][1]-1 and t.bbox[3]<=top+1 for t in tabs))
                if canmerge:
                    prose[-1][1]=bottom;prose[-1][2][0].extend(ss)
                else:prose.append([top,bottom,groups])
            for top,bottom,groups in prose:
                if len(groups)==1:
                    ss=groups[0];st=style();st.keepWithNext=bool(all(is_bold(t)for t in ss) and len(plain(ss))<180);st.leftIndent=max(0,(ss[0]['bbox'][0]-x0)/source_width*WIDTH)
                    txt=markup(ss).replace('<br/>',' ')
                    title='Seniors’ Advantage GICs - Terms & Conditions'
                    if canonical(plain(ss))==canonical(title):txt='<b><u>'+escape(title)+'</u></b>'
                    if 'Rs.' in plain(ss) and len(plain(ss))<18:st.leftIndent=0;st.alignment=TA_RIGHT
                    obj=Paragraph(txt,st)
                else:obj=PositionedRow(groups,x0,source_width)
                obj.source_text=plain([s for g in groups for s in g])
                if bonus_layout and re.match(r'^(?:Canadian Dollar|US Dollar|Applicable Interest Rate|Definitions|QUALIFYING CRITERIA|Other Conditions|Who is eligible)',obj.source_text):obj.keepWithNext=True
                items.append((top,bottom,obj))
            # Keep embedded raster artwork except small top logos, replaced by the supplied banner.
            for info in page.get_image_info(xrefs=True):
                box=fitz.Rect(info['bbox'])
                if bonus_layout and bonus_terms.duplicate_image(info):continue
                duplicate_images=json.loads((ROOT/'assets'/'known_duplicate_text_images.json').read_text())
                if info.get('xref') and hashlib.sha256(fitz.Pixmap(src,info['xref']).samples).hexdigest() in duplicate_images:continue
                if any((hb+(-1,-1,1,1)).contains(box)for hb in header_boxes):continue
                if box.y1<35 and box.width<150:continue
                if not info.get('xref'):raise ReviewRequired(f'Inline image on page {pn+1} needs review.')
                # Render the visible original region, respecting clipping/masks.
                pix=page.get_pixmap(clip=box,matrix=fitz.Matrix(2,2))
                img=Image(BytesIO(pix.tobytes('png')),width=min(box.width,WIDTH),height=box.height)
                items.append((box.y0,box.y1,img))
            items.sort(key=lambda z:z[0])
            last=None;page_story=[];signature_at=None
            for top,bottom,obj in items:
                if 'For and on behalf of the Board' in getattr(obj,'source_text',''):signature_at=len(page_story)
                if last is not None and top-last>3:
                    space=Spacer(1,min((top-last)*1.15,24))
                    if bonus_layout and page_story and getattr(page_story[-1],'keepWithNext',False):space.keepWithNext=True
                    page_story.append(space)
                if bonus_layout and getattr(obj,'source_text','').strip()=='mentioned below':
                    for previous in reversed(page_story):
                        previous.keepWithNext=True
                        if not isinstance(previous,Spacer):break
                page_story.append(obj);last=bottom
            if bonus_layout and pn==3:
                table_at=next(i for i,obj in enumerate(page_story) if isinstance(obj,Table))
                page_story=[KeepTogether(page_story[:table_at+1])]+page_story[table_at+1:]
            if signature_at is not None:
                page_story=page_story[:signature_at]+[KeepTogether(page_story[signature_at:])]
            story.extend(page_story)
            if pn<len(src)-1:
                gap=Spacer(1,4) if continuous else PageBreak()
                if form_layout and getattr(story[-1],'keepWithNext',False):gap.keepWithNext=True
                story.append(gap)
        if canonical(''.join(source_content))!=canonical(''.join(structured)):
            raise ReviewRequired('Text inventory changed during extraction; no output approved.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as temp_resources:
            body=Path(tmp)/'body.pdf'
            doc=SimpleDocTemplate(str(body),pagesize=A4,leftMargin=LEFT-6,rightMargin=RIGHT-6,topMargin=TOP-6,bottomMargin=BOTTOM-6,title=source.stem+' - A4 Mulish',author='')
            doc.build(story)
            bodydoc=temp_resources.enter_context(fitz.open(body));out=temp_resources.enter_context(fitz.open())
            for pn,p in enumerate(bodydoc):
                dest=out.new_page(width=A4[0],height=A4[1])
                bs=spans_of(p);rects=[fitz.Rect(s['bbox'])for s in bs]+[fitz.Rect(d['rect'])for d in p.get_drawings()]+[fitz.Rect(i['bbox'])for i in p.get_image_info()]
                if not rects:raise ReviewRequired('An unexpected blank output page was created.')
                first=min(r.y0 for r in rects);last=max(r.y1 for r in rects)
                shift=TOP-first
                if last+shift>A4[1]-BOTTOM+.5:raise ReviewRequired('Content exceeded bottom margin.')
                dest.show_pdf_page(fitz.Rect(0,shift,A4[0],A4[1]+shift),bodydoc,pn)
                for link in p.get_links():
                    if link.get('kind')==fitz.LINK_URI:
                        box=fitz.Rect(link['from'])+(0,shift,0,shift);dest.insert_link({'kind':fitz.LINK_URI,'from':box,'uri':link['uri']})
                dest.insert_image(fitz.Rect(0,0,A4[0],HEADER),filename=str(ROOT/'assets'/'header.jpg'))
            # Footer: blue letter-spaced Page + dark page count, as in the reference.
            font=fitz.Font(fontfile=str(ROOT/'assets'/'Mulish-SemiBold.ttf'))
            for pn,p in enumerate(out):
                p.insert_font(fontname='Mulish',fontfile=str(ROOT/'assets'/'Mulish-SemiBold.ttf'))
                label='P a g e';count=f'{pn+1} | {len(out)}';pad=4
                first_width=font.text_length(label,fontsize=SIZE);last_width=font.text_length(count,fontsize=SIZE)
                x=531.315/595.32*A4[0]-first_width-pad-last_width;y=A4[1]-(841.92-786.696)
                p.insert_text((x,y),label,fontname='Mulish',fontsize=SIZE,color=(.19,.51,.85))
                p.insert_text((x+first_width+pad,y),count,fontname='Mulish',fontsize=SIZE,color=(.15,.21,.28))
            # Verify the actual rendered body text still contains every character occurrence.
            actual=''.join(p.get_text()for p in bodydoc)
            missing=canonical(''.join(source_content))-canonical(actual)
            if missing:raise ReviewRequired('Output text check failed: '+str(dict(missing)))
            original_rows=numeric_rows(src);converted_rows=numeric_rows(out)
            if original_rows!=converted_rows:
                raise ReviewRequired('Numeric table row order/count mismatch. '+repr(original_rows)+' vs '+repr(converted_rows))
            out.save(destination,garbage=4,deflate=True)
        checked=resources.enter_context(fitz.open(destination));sizes=set();gaps=[]
        for p in checked:
            ss=[s for s in spans_of(p) if s['bbox'][1]<A4[1]-BOTTOM]
            sizes.update(round(s['size'],3)for s in ss)
            if any(s['bbox'][0]<LEFT-.5 or s['bbox'][2]>A4[0]-RIGHT+.5 for s in ss):raise ReviewRequired('Body text exceeded horizontal margins.')
            rects=[fitz.Rect(s['bbox'])for s in ss]+[fitz.Rect(d['rect'])for d in p.get_drawings() if d['rect'].y0<A4[1]-BOTTOM]
            gaps.append(round((min(r.y0 for r in rects)-HEADER)/CM,5))
        report={'input':source.name,'source_pages':len(src),'output_pages':len(checked),'tables':table_count,'old_headers_removed':removed_headers,'page_borders_removed':removed_borders,'numeric_rows_verified':sum(original_rows.values()),'font':'Mulish','font_px_equivalent':round(SIZE*96/72,4),'font_pt':SIZE,'page_size':'A4','continuous_content_flow':continuous,'top_margin_cm':3.0,'header_to_content_cm':gaps,'left_margin_cm':1.88,'right_margin_cm':1.89,'bottom_margin_cm':2.55,'body_font_sizes_pt':sorted(sizes),'bonus_terms_layout':bonus_layout,'form_writing_space_preserved':form_layout,'symbol_font_exceptions':['➢ uses embedded DejaVu Sans at 11pt'] if '➢' in ''.join(source_content) else [],'character_inventory':'passed; repeated table headings permitted; discretionary soft hyphens normalized','status':'CONVERTED_REVIEW_LAYOUT','notes':['Reflow changes line wraps and pagination. Manual layout review required before publishing.','Word font size 11 interpreted as 11pt. Top margin is 3cm from the page edge, matching the screenshot.','Superscript markers retained at 11pt; original visible text checked. Hidden white page-number artifacts excluded.']}
        Path(str(destination)+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report

def _convert_selected(source,destination,strict=False):
    """Use reviewed profiles where available; otherwise use verified page-level conversion."""
    import adaptive, cgas_forms, bonus_terms, annual_report
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Output must not overwrite original')
    with fitz.open(source) as doc:
        if doc.needs_pass:raise adaptive.BlockedPDF('Password-protected PDF: supply an unlocked copy.')
        if any(link.get('kind') not in (fitz.LINK_URI,fitz.LINK_GOTO) for page in doc for link in page.get_links()):raise adaptive.BlockedPDF('Special PDF link action requires original file; conversion blocked to avoid losing navigation.')
        if doc.is_form_pdf or doc.get_sigflags()>0:raise adaptive.BlockedPDF('Interactive or signed PDF: original retained; conversion blocked.')
    trade=ROOT/'assets/trade-form-profile.json'
    known=cgas_forms.matches(source) or bonus_terms.matches(source) or annual_report.matches(source) or (trade.exists() and hashlib.sha256(source.read_bytes()).hexdigest()==json.loads(trade.read_text())['sha256'])
    if known:
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as td:
            temp=Path(td)/'converted.pdf'
            try:result=convert_legacy(source,temp)
            except Exception as exc:return adaptive.convert(source,destination,strict,initial_error=str(exc))
            from release import VERSION
            result['engine_version']=VERSION;result['font_compliance']='PROFILE_VERIFIED_REVIEW_ARTWORK';result.setdefault('preserved_source_pages',[])
            temp.replace(destination)
            Path(str(destination)+'.json').write_text(json.dumps(result,indent=2),'utf-8')
            return result
    return adaptive.convert(source,destination,strict)

def convert(source,destination,strict=False):
    """All engines pass a common, atomic, final-file compliance gate."""
    import quality_gate, adaptive, os
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Output must not overwrite original')
    with fitz.open(source) as doc:
        if doc.needs_pass:raise adaptive.BlockedPDF('Password-protected PDF: supply an unlocked original.')
        if ((doc.metadata or {}).get('producer') or '').startswith('A4 PDF Converter'):
            raise adaptive.BlockedPDF('This is already a converter output. Select the original PDF to avoid repeated headers and reflow.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as td:
        temp=Path(td)/'converted.pdf'
        result=_convert_selected(source,temp,strict)
        result['verification']=quality_gate.inspect(temp,result)
        result['review_reasons']=result['verification']['review_reasons']
        if not result['verification']['passed']:
            result['status']='PARTIAL_REVIEW_REQUIRED';result['font_compliance']='PARTIAL'
            if strict:raise ReviewRequired('; '.join(result['review_reasons']))
        elif not result.get('font_compliance','').startswith('ALL_'):
            result['font_compliance']='ALL_REBUILT_TEXT_11PT_MULISH'
        result['release_readiness']='MEASURED_FORMAT_COMPLIANT_REVIEW_LAYOUT' if result['verification']['passed'] else 'NOT_FULLY_CONVERTED_REVIEW_REQUIRED'
        sidecar=Path(td)/'converted.pdf.json';sidecar.write_text(json.dumps(result,indent=2,ensure_ascii=False),'utf-8')
        os.replace(temp,destination);os.replace(sidecar,Path(str(destination)+'.json'))
        from review_report import write
        try:write(destination,result)
        except OSError as error:
            result['review_report_warning']='Could not write HTML review report: '+str(error)
            Path(str(destination)+'.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),'utf-8')
        return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('output');ap.add_argument('--strict',action='store_true',help='Reject partial or noncompliant conversions without replacing the output.');args=ap.parse_args()
    print(json.dumps(convert(args.input,args.output,strict=args.strict),indent=2))
