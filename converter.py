"""Local PDF reflow tool. Originals are never modified. See README before batch use."""
from pathlib import Path
from contextlib import ExitStack
from io import BytesIO
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
    for name in ('Mulish-SemiBold','Mulish-Black'):
        pdfmetrics.registerFont(TTFont(name,str(ROOT/'assets'/f'{name}.ttf')))
    pdfmetrics.registerFontFamily('Mulish-SemiBold',normal='Mulish-SemiBold',bold='Mulish-Black',italic='Mulish-SemiBold',boldItalic='Mulish-Black')

def style(bold=False,align=TA_LEFT):
    return ParagraphStyle('body',fontName='Mulish-Black' if bold else 'Mulish-SemiBold',fontSize=SIZE,leading=SIZE*1.25,alignment=align,spaceAfter=0,spaceBefore=0,splitLongWords=False,allowWidows=0,allowOrphans=0)

def para(text,bold=False,align=TA_LEFT):
    return Paragraph(escape(text).replace('\n','<br/>'),style(bold,align))

def canonical(text):
    # A multiset, insensitive to wrapping and PDF extraction order; includes punctuation/digits.
    return collections.Counter(c for c in text if not c.isspace() and c!='\xad')

def visible_glyphs(path):
    f=FontInspector(path);c=f.getBestCmap();g=f['glyf']
    return {chr(k) for k,v in c.items() if g[v].numberOfContours!=0}|set(' \n\r\t')

def is_bold(s):
    name=s['font']
    return 'Black' in name or ('Bold' in name and 'SemiBold' not in name)

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
    return out

def is_footer(s,page):
    # Only remove a bare page number in the bottom 4%; retain other footer/legal text.
    return re.fullmatch(r'\s*\d+\s*',s['text']) is not None and (s['bbox'][1]>page.rect.height*.96 or (s['color']==0xffffff and s['size']<5))

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
            v=escape(s['text'].strip())
            if s.get('flags',0)&1 or s['size']<5.4:v=f'<super size="{SIZE}" rise="2.5">{v}</super>'
            if is_bold(s):v='<b>'+v+'</b>'
            if s.get('underline'):v='<u>'+v+'</u>'
            if s.get('color',0):v=f'<font color="#{s["color"]:06x}">{v}</font>'
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

def build_table(tab,spans,source_width,drawings):
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
        data[ri][ci]=Paragraph(cell_markup,style(bold,TA_RIGHT if num and ci>0 else TA_LEFT))
        if cj>ci or rj>ri:
            commands.append(('SPAN',(ci,ri),(cj,rj)));spans_list.append((ci,ri,cj,rj))
    first_nonempty=[i for i,cell in enumerate(data[0]) if hasattr(cell,'getPlainText') and cell.getPlainText().strip()]
    if len(first_nonempty)==1:
        heading=data[0][first_nonempty[0]];data[0]=[heading]+['']*(cols-1)
        commands=[cmd for cmd in commands if not(cmd[0]=='SPAN' and cmd[1][1]==0)]
        commands.append(('SPAN',(0,0),(cols-1,0)))
    extracted=' '.join(texts)
    repeat=3 if 'Unaudited' in extracted[:600] else (0 if cols==2 else 1)
    # Never split a merged heading across the repeating boundary.
    while any(ri<repeat<=rj for ci,ri,cj,rj in spans_list):repeat=max(rj+1 for ci,ri,cj,rj in spans_list if ri<repeat<=rj)
    repeat=min(repeat,rows)
    for i,minimum in enumerate(minimums):
        if widths[i]<minimum:
            deficit=minimum-widths[i];j=max(range(cols),key=lambda k:widths[k]-minimums[k] if k!=i else -1)
            if widths[j]-minimums[j]<deficit:raise ReviewRequired('Table is too wide at the requested font size.')
            widths[j]-=deficit;widths[i]=minimum
    table=Table(data,colWidths=widths,repeatRows=repeat,hAlign='RIGHT',splitByRow=1)
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

def legacy_header_boxes(page):
    known=json.loads((ROOT/'assets'/'known_header_logos.json').read_text())
    boxes=[]
    for info in page.get_image_info(xrefs=True):
        box=fitz.Rect(info['bbox'])
        if info.get('xref') and box.y1<page.rect.height*.2:
            digest=hashlib.sha256(fitz.Pixmap(page.parent,info['xref']).samples).hexdigest()
            if digest in known:boxes.append(box)
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

def convert(source,destination):
    if Path(source).resolve()==Path(destination).resolve():raise ValueError('Output must not overwrite the original.')
    import annual_report
    if annual_report.matches(source):return annual_report.convert(source,destination)
    with ExitStack() as resources:
        setup_fonts();source=Path(source);destination=Path(destination)
        if source.resolve()==destination.resolve():raise ValueError('Output must not overwrite the original.')
        src=resources.enter_context(fitz.open(source))
        if src.needs_pass:raise ReviewRequired('Encrypted PDF: provide an unlocked copy.')
        if src.is_form_pdf:raise ReviewRequired('Interactive form: reflow could lose fields. Use the editable source.')
        if any(p.rotation for p in src):raise ReviewRequired('Rotated pages require a separate layout profile.')
        border_pages=sum(any(decorative_border(dr,pg)for dr in pg.get_drawings())for pg in src)
        continuous=bool(legacy_header_boxes(src[0])) or border_pages>=max(1,len(src)*.5)
        glyphs=visible_glyphs(ROOT/'assets'/'Mulish-SemiBold.ttf')
        boldglyphs=visible_glyphs(ROOT/'assets'/'Mulish-Black.ttf')
        story=[];source_content=[];structured=[];table_count=0;page_map=[];warnings=[];removed_headers=0;removed_borders=0
        for pn,page in enumerate(src):
            spans=[s for s in spans_of(page) if not is_footer(s,page)]
            if not spans:raise ReviewRequired(f'Page {pn+1} has no extractable text (scan/empty page).')
            for s in spans:
                missing=set(s['text'])-(boldglyphs if is_bold(s) else glyphs)
                if missing:raise ReviewRequired(f'Font coverage on page {pn+1}: {repr("".join(sorted(missing)))}. Install complete Mulish font files in assets.')
            source_content.extend(s['text'] for s in spans)
            header_boxes=legacy_header_boxes(page);removed_headers+=len(header_boxes)
            tabs=page.find_tables().tables
            # Unknown vector graphics must be reviewed, rather than silently dropped.
            for dr in page.get_drawings():
                rect=fitz.Rect(dr['rect'])
                if any((box+(-2,-2,2,2)).contains(rect)for box in header_boxes):continue
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
                table,consumed,txt=build_table(tab,spans,source_width,page.get_drawings())
                if used&consumed:raise ReviewRequired(f'Overlapping extracted tables on page {pn+1}.')
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
                items.append((top,bottom,obj))
            # Keep embedded raster artwork except small top logos, replaced by the supplied banner.
            for info in page.get_image_info(xrefs=True):
                box=fitz.Rect(info['bbox'])
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
                if last is not None and top-last>3:page_story.append(Spacer(1,min((top-last)*1.15,24)))
                page_story.append(obj);last=bottom
            if signature_at is not None:
                page_story=page_story[:signature_at]+[KeepTogether(page_story[signature_at:])]
            story.extend(page_story)
            if pn<len(src)-1:
                story.append(Spacer(1,4) if continuous else PageBreak())
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
        report={'input':source.name,'source_pages':len(src),'output_pages':len(checked),'tables':table_count,'old_headers_removed':removed_headers,'page_borders_removed':removed_borders,'numeric_rows_verified':sum(original_rows.values()),'font':'Mulish','font_px_equivalent':round(SIZE*96/72,4),'font_pt':SIZE,'page_size':'A4','continuous_content_flow':continuous,'top_margin_cm':3.0,'header_to_content_cm':gaps,'left_margin_cm':1.88,'right_margin_cm':1.89,'bottom_margin_cm':2.55,'body_font_sizes_pt':sorted(sizes),'character_inventory':'passed; repeated table headings permitted; discretionary soft hyphens normalized','status':'CONVERTED_REVIEW_LAYOUT','notes':['Reflow changes line wraps and pagination. Manual layout review required before publishing.','Word font size 11 interpreted as 11pt. Top margin is 3cm from the page edge, matching the screenshot.','Superscript markers retained at 11pt; original visible text checked. Hidden white page-number artifacts excluded.']}
        Path(str(destination)+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('output');args=ap.parse_args()
    print(json.dumps(convert(args.input,args.output),indent=2))
