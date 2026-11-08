"""Page-level PDF conversion with explicit preservation and verification outcomes.
No OCR guesses, font-size reduction, or silent loss of forms/annotations.
"""
from pathlib import Path
from io import BytesIO
from collections import Counter
from contextlib import contextmanager
import json,re,tempfile,hashlib,os,copy,base64
import fitz
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,Image,Flowable
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.enums import TA_LEFT,TA_CENTER,TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from xml.sax.saxutils import escape
import converter as c

from release import VERSION
class PreservePage(Exception):pass
class NeedWider(Exception):pass
class BlockedPDF(Exception):pass

@contextmanager
def dimensions(width):
    old=c.WIDTH;c.WIDTH=width
    try:yield
    finally:c.WIDTH=old

def inventory(text):
    return Counter(ch for ch in text if not ch.isspace() and ch!='\xad')

def footer(sp,page):
    text=sp['text'].strip();r=fitz.Rect(sp['bbox'])
    return bool(re.fullmatch(r'(?:Page\s*)?\d+(?:\s*(?:of|/|\|)\s*\d+)?',text,re.I)) and r.y0>page.rect.height*.90

def content_spans(page):
    spans=[];symbols=[]
    for original in c.spans_of(page):
        sp=dict(original)
        if footer(sp,page) or c.source_page_number(sp,page):continue
        if sp['font'].startswith('Symbol') and '\uf0b7' in sp['text']:
            sp['text']=sp['text'].replace('\uf0b7','•');symbols.append('Symbol list bullet mapped to Unicode bullet')
        if len(sp['text'])==1 and re.search('Wingdings|Webdings|Symbol|Zapf',sp['font'],re.I) and sp['text'] not in c.visible_glyphs(c.ROOT/'assets/Mulish-SemiBold.ttf'):
            sp['symbol_artwork']=True
        spans.append(sp)
    return spans,symbols

def text_markup(spans, page, exceptions):
    # Retain a reviewed Wingdings marker as artwork, not an invented character.
    groups=c.rows_of(spans);lines=[]
    for _,ss in groups:
        bits=[]
        for sp in ss:
            if sp.get('symbol_artwork') or sp['text']=='\uf0f1' and re.search('Wingdings',sp['font'],re.I):
                pix=page.get_pixmap(clip=fitz.Rect(sp['bbox']),matrix=fitz.Matrix(3,3),alpha=True)
                uri='data:image/png;base64,'+base64.b64encode(pix.tobytes('png')).decode()
                box=fitz.Rect(sp['bbox']);width=min(18,max(3,11*box.width/max(1,box.height)))
                bits.append(f'<img src="{uri}" width="{width}" height="11" valign="middle"/>');exceptions.add('Original symbol glyphs retained as 11pt-high artwork')
            else:
                value=c.markup([sp])
                bits.append(value)
        lines.append(' '.join(bits))
    return ' '.join(lines)

def check_glyphs(spans):
    glyphs={name:c.visible_glyphs(c.ROOT/'assets'/f'{name}.ttf') for name in ('Mulish-SemiBold','Mulish-Black','Mulish-SemiBoldItalic','Mulish-BlackItalic')}
    missing=set()
    for sp in spans:
        if sp.get('symbol_artwork'):continue
        name='Mulish-Black' if c.is_bold(sp) else 'Mulish-SemiBold'
        if sp.get('flags',0)&2 or 'italic' in sp['font'].lower() or 'oblique' in sp['font'].lower():name+='Italic'
        chars=set(sp['text'])-glyphs[name]
        if 'Wingdings' in sp['font']:chars.discard('\uf0f1')
        missing|=chars
    if missing:raise PreservePage('Mulish has no verified glyphs for '+repr(''.join(sorted(missing))))

def body_style(align=TA_LEFT,indent=0,bold=False):
    return ParagraphStyle('adaptive',fontName='Mulish-Black' if bold else 'Mulish-SemiBold',fontSize=11,leading=14,alignment=align,leftIndent=indent,splitLongWords=False,allowWidows=0,allowOrphans=0,spaceAfter=0)

def close_edges(values):
    result=[]
    for v in sorted(values):
        if not result or v-result[-1]>.6:result.append(v)
    return result

def table_flow(tab,spans,page,available,source_width,exceptions):
    cells=[fitz.Rect(box) for box in tab.cells if box]
    xs=close_edges(v for cell in cells for v in (cell.x0,cell.x1));ys=close_edges(v for cell in cells for v in (cell.y0,cell.y1))
    n=len(xs)-1;m=len(ys)-1
    # Broken grid edges can leave a real header cell absent from find_tables().
    # Fill only uncovered grid slots containing source text; never infer values.
    for ri in range(len(ys)-1):
        for ci in range(len(xs)-1):
            box=fitz.Rect(xs[ci],ys[ri],xs[ci+1],ys[ri+1]);mid=fitz.Point((box.x0+box.x1)/2,(box.y0+box.y1)/2)
            if any(cell.contains(mid) for cell in cells):continue
            if any(box.contains(fitz.Point((sp['bbox'][0]+sp['bbox'][2])/2,sp['origin'][1]-sp['size']*.35)) for sp in spans):cells.append(box)

    if n<1 or m<1:raise PreservePage('Invalid table boundaries')
    target=min(available,max(available*.5,(xs[-1]-xs[0])/source_width*available))
    widths=[(xs[i+1]-xs[i])/(xs[-1]-xs[0])*target for i in range(n)]
    minima=[14.0]*n;data=[['']*n for _ in range(m)];commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,'#727272'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]
    used=set();cell_texts=[];merges=[];all_top_bold=[];drawings=page.get_drawings()
    for box in cells:
        ci=min(range(len(xs)),key=lambda j:abs(xs[j]-box.x0));cj=min(range(len(xs)),key=lambda j:abs(xs[j]-box.x1))-1
        ri=min(range(len(ys)),key=lambda j:abs(ys[j]-box.y0));rj=min(range(len(ys)),key=lambda j:abs(ys[j]-box.y1))-1
        for drawing in drawings:
            fill=drawing.get('fill')
            # A single PDF drawing can contain four filled border strips; its
            # union bounding box is NOT a filled cell background.
            areas=[fitz.Rect(item[1]) for item in drawing['items'] if item[0]=='re']
            if fill and min(fill)<.98 and any(area.width>2 and area.height>2 and area.contains(fitz.Point((box.x0+box.x1)/2,(box.y0+box.y1)/2)) for area in areas):
                from reportlab.lib.colors import Color
                rgb=fill if len(fill)==3 else (fill[0],)*3
                commands.append(('BACKGROUND',(ci,ri),(cj,rj),Color(*rgb)))
        selected=[]
        for k,sp in enumerate(spans):
            x=(sp['bbox'][0]+sp['bbox'][2])/2;y=sp['origin'][1]-sp['size']*.35
            if k not in used and box.x0-.15<=x<=box.x1+.15 and box.y0-.15<=y<=box.y1+.15:selected.append(sp);used.add(k)
        txt=c.plain(selected);cell_texts.append(txt)
        if selected and ri==0:all_top_bold.append(all(c.is_bold(sp) for sp in selected))
        align=TA_RIGHT if re.fullmatch(r'[\d,.()%+\-\s]+',txt.strip()) and ci else TA_LEFT
        lines=c.rows_of(selected)
        centered=bool(lines) and all(abs((min(sp['bbox'][0] for sp in ss)+max(sp['bbox'][2] for sp in ss))/2-(box.x0+box.x1)/2)<max(2,box.width*.035) and max(sp['bbox'][2] for sp in ss)-min(sp['bbox'][0] for sp in ss)<box.width*.85 for _,ss in lines)
        if centered:align=TA_CENTER
        if centered and rj>ri and selected:
            mid=(min(sp['bbox'][1] for sp in selected)+max(sp['bbox'][3] for sp in selected))/2
            if abs(mid-(box.y0+box.y1)/2)<max(5,box.height*.12):commands.append(('VALIGN',(ci,ri),(cj,rj),'MIDDLE'))
        from layout_core import cell_paragraph
        # Keep run boundaries: 0.0 followed by a raised footnote 1 is not 0.01.
        proof_text=' '.join(sp['text'] for _,row in c.rows_of(selected) for sp in row if not sp.get('symbol_artwork'))
        para=cell_paragraph(text_markup(selected,page,exceptions),body_style(align),f'{page.number}:{tab.bbox}:{ri}:{ci}',proof_text);data[ri][ci]=para
        if ci==cj:minima[ci]=max(minima[ci],para.minWidth()+6.2)
        if ci<cj or ri<rj:commands.append(('SPAN',(ci,ri),(cj,rj)));merges.append((ci,ri,cj,rj))
    if sum(minima)>available:raise NeedWider('Table needs wider columns at 11pt')
    target=max(target,sum(minima));widths=[w*target/sum(widths) for w in widths] if sum(widths)>0 else widths
    # Water-fill all columns, retaining spare width in proportion to source widths.
    fixed=set()
    while True:
        deficit=[i for i in range(n) if i not in fixed and widths[i]<minima[i]]
        if not deficit:break
        for i in deficit:widths[i]=minima[i];fixed.add(i)
        spare=target-sum(widths[i] for i in fixed);weight=sum(xs[i+1]-xs[i] for i in range(n) if i not in fixed)
        for i in range(n):
            if i not in fixed:widths[i]=spare*(xs[i+1]-xs[i])/weight
    repeat=1 if all_top_bold and sum(all_top_bold)>=len(all_top_bold)*.6 else 0
    if repeat and any(ri<repeat<=rj for ci,ri,cj,rj in merges):repeat=0
    table=Table(data,colWidths=widths,repeatRows=repeat,splitByRow=1,splitInRow=1,hAlign='LEFT')
    table.setStyle(TableStyle(commands));table.spaceAfter=6
    return table,used,cell_texts

def hidden_background(dr,page):
    fill=dr.get('fill');box=fitz.Rect(dr['rect'])
    return bool(fill and min(fill)>.98) or box.is_empty

def find_visible_tables(page):
    # White fill-only rectangles are text background/erasure patches, not
    # visible cell boundaries. Keep stroked white cells and thin filled rules.
    paths=[dr for dr in page.get_drawings() if not
           (dr['type']=='f' and dr.get('fill') and min(dr['fill'])>.98)]
    return page.find_tables(paths=paths)

def page_features(page,spans,tabs,header_boxes):
    if any(link.get('kind')!=fitz.LINK_URI for link in page.get_links()):raise PreservePage('Original internal or special link layout retained')
    if any(page.annots() or []):raise PreservePage('Annotation appearance flattened; original retains editable comments')
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines',[]):
            if tuple(round(v,2) for v in line.get('dir',(1,0)))!=(1.0,0.0):raise PreservePage('Rotated or vertical text needs original layout')
    for dr in page.get_drawings():
        box=fitz.Rect(dr['rect'])
        if hidden_background(dr,page):continue
        if any((fitz.Rect(t.bbox)+(-2,-2,2,2)).contains(box) for t in tabs):continue
        if any((b+(-2,-2,2,2)).contains(box) for b in header_boxes):continue
        if c.decorative_border(dr,page):continue
        if min(box.width,box.height)<2:continue # rules and rectangular text borders
        if all(item[0]=='re' for item in dr['items']) and not dr.get('fill'):continue
        raise PreservePage('Vector diagram or symbol retained in original layout')

def prose_items(spans,page,available,x0,x1,exceptions):
    rows=c.rows_of(spans);items=[];groups=[]
    for y,ss in rows:
        top=min(sp['bbox'][1] for sp in ss);bottom=max(sp['bbox'][3] for sp in ss)
        starts=bool(re.match(r'^(?:[•\uf0f1]|\(?[0-9a-z]+[.)])\s',c.plain(ss)))
        bold=all(c.is_bold(sp) for sp in ss)
        if groups and top-groups[-1][1]<5 and bold==groups[-1][3] and not starts and abs(ss[0]['bbox'][0]-groups[-1][2][0]['bbox'][0])<100:
            groups[-1][1]=bottom;groups[-1][2].extend(ss)
        else:groups.append([top,bottom,list(ss),bold])
    for top,bottom,ss,bold in groups:
        indent=min(available*.16,max(0,(min(sp['bbox'][0] for sp in ss)-x0)/(x1-x0)*available))
        centered=bold and len(c.plain(ss))<120 and abs((min(sp['bbox'][0] for sp in ss)+max(sp['bbox'][2] for sp in ss))/2-(x0+x1)/2)<10
        st=body_style(TA_CENTER if centered else TA_LEFT,0 if centered else indent)
        # Lists retain their hanging indent when text wraps at the new size.
        first=c.rows_of(ss)[0][1]
        value=text_markup(ss,page,exceptions)
        if len(first)>1 and re.fullmatch(r'(?:[•\uf0f1]|\(?[0-9a-zA-Z]+[.)])',first[0]['text']):
            hang=min(32,max(12,first[1]['bbox'][0]-first[0]['bbox'][0]))
            st.leftIndent=indent+hang;st.firstLineIndent=0;st.bulletIndent=indent
            st.bulletFontName='Mulish-Black' if c.is_bold(first[0]) else 'Mulish-SemiBold';st.bulletFontSize=11
            value='<bullet>'+text_markup([first[0]],page,exceptions)+'</bullet>'+text_markup([s for s in ss if s is not first[0]],page,exceptions)
        p=Paragraph(value,st)
        if p.minWidth()>available-indent:raise NeedWider('Long unbroken text cannot fit at 11pt')
        # Heading is kept with the next item unless it is the final source-page item.
        p.keepWithNext=bool(bold and len(c.plain(ss))<200);items.append((top,bottom,p))
    return items

def rule_page(page,spans,tabs,size,exceptions):
    available=size[0]-c.LEFT-c.RIGHT
    x0=min([sp['bbox'][0] for sp in spans]+[t.bbox[0] for t in tabs]);x1=max([sp['bbox'][2] for sp in spans]+[t.bbox[2] for t in tabs]);source_width=max(1,x1-x0)
    items=[];used=set();cell_texts=[]
    for tab in tabs:
        table,consumed,texts=table_flow(tab,spans,page,available,source_width,exceptions)
        if used&consumed:raise PreservePage('Overlapping table detections')
        used|=consumed;cell_texts.extend(texts);items.append((tab.bbox[1],tab.bbox[3],table))
    free=[sp for k,sp in enumerate(spans) if k not in used]
    # Do not merge prose through a table or figure boundary.
    buckets={}
    for sp in free:
        y=sp['origin'][1]-sp['size']*.35
        bucket=sum(t.bbox[3]<y for t in tabs)
        buckets.setdefault(bucket,[]).append(sp)
    for part in buckets.values():items.extend(prose_items(part,page,available,x0,x1,exceptions))
    if inventory(''.join(c.plain([sp]) for sp in free)+''.join(cell_texts))!=inventory(''.join(sp['text'] for sp in spans)):raise PreservePage('Table extraction changed text inventory')
    headers=c.legacy_header_boxes(page)
    for info in page.get_image_info(xrefs=True):
        box=fitz.Rect(info['bbox'])
        if any((hb+(-1,-1,1,1)).contains(box) for hb in headers):continue
        if any(box.intersects(fitz.Rect(sp['bbox'])) for sp in spans):raise PreservePage('Text overlaps an image or scan')
        pix=page.get_pixmap(clip=box,matrix=fitz.Matrix(2,2),alpha=False);scale=min(1,available/box.width,(size[1]-c.TOP-c.BOTTOM)/box.height)
        img=Image(BytesIO(pix.tobytes('png')),width=box.width*scale,height=box.height*scale);items.append((box.y0,box.y1,img));exceptions.add('Embedded images retained as artwork')
    items.sort(key=lambda item:item[0]);story=[];last=None
    for top,bottom,obj in items:
        if last is not None and top-last>3:
            gap=Spacer(1,min(12,top-last));gap.keepWithNext=bool(story and getattr(story[-1],'keepWithNext',False));story.append(gap)
        story.append(obj);last=bottom
    if story:story[-1].keepWithNext=False
    if not story:raise PreservePage('No safely reflowable page content')
    from layout_core import build_document
    return build_document(story,c,size),len(tabs)

def has_positioned_columns(spans):
    # A paragraph containing dates/amounts is not a table. Require actual gutters.
    return sum(sum(b['bbox'][0]-a['bbox'][2]>14 for a,b in zip(ss,ss[1:]))>=2 for _,ss in c.rows_of(spans))>=3

def positioned_page(page,spans,size,exceptions):
    import annual_report as ar
    available=size[0]-c.LEFT-c.RIGHT;height=size[1]-c.TOP-c.BOTTOM
    old=(ar.PAGE_W,ar.PAGE_H,ar.WIDTH,ar.HEIGHT)
    ar.PAGE_W,ar.PAGE_H=size;ar.WIDTH=available;ar.HEIGHT=height
    try:
        x0=min(sp['bbox'][0] for sp in spans);x1=max(sp['bbox'][2] for sp in spans)
        rows=[ar.Row(ss,x0,x1-x0,c) for _,ss in c.rows_of(spans)]
        groups=[]
        for row in rows:
            prev=groups[-1][-1] if groups else None
            eligible=lambda r:len(ar.make_groups(r.ss))==1 and r.numeric_cells==0
            if prev and eligible(prev) and eligible(row) and prev.all_bold==row.all_bold and row.sy-prev.ey<4 and len(prev.source_text)>70:groups[-1].append(row)
            else:groups.append([row])
        rows=[ar.ProseRow(group,x0,x1-x0,c) if len(group)>1 else group[0] for group in groups]
        for dr in page.get_drawings():
            box=fitz.Rect(dr['rect'])
            if box.height<2 and box.width>4:
                row=min(rows,key=lambda r:min(abs(r.sy-box.y0),abs(r.ey-box.y0)));a=max(0,(box.x0-x0)/(x1-x0)*available);b=min(available,(box.x1-x0)/(x1-x0)*available)
                row.rules.append((a,b,'top' if abs(row.sy-box.y0)<abs(row.ey-box.y0) else 'bottom'))
        header_rows=[]
        for row in rows:
            if not row.all_bold:break
            header_rows.append(row)
        if not any(len(row.parts)>1 for row in header_rows) or sum(row.height for row in header_rows)>height*.25:header_rows=[]
        out=BytesIO();cv=Canvas(out,pagesize=size);y=c.TOP;last=None;records=[];pno=0
        for row in rows:
            gap=0 if last is None else max(0,min(10,row.sy-last))
            if y+gap+row.height>size[1]-c.BOTTOM:
                cv.showPage();pno+=1;y=c.TOP;gap=0
                if row not in header_rows:
                    for head in header_rows:head.draw(cv,y);y+=head.height
                if y+row.height>size[1]-c.BOTTOM:raise PreservePage('Positioned row cannot fit with its repeated column headings')
            if row.height>height:raise PreservePage('A positioned table row exceeds one page at 11pt')
            y+=gap;row.draw(cv,y);records.append((pno,y,y+row.height,row.expected,re.findall(r'\d+',row.source_text)));y+=row.height;last=row.ey
        cv.save()
        data=out.getvalue()
        with fitz.open(stream=data,filetype='pdf') as d:
            words={p.number:c.spans_of(p) for p in d}
            for pn,top,bottom,expected,numbers in records:
                text=' '.join(sp['text'] for sp in words[pn] if top<=(sp['bbox'][1]+sp['bbox'][3])/2<bottom)
                if inventory(expected)!=inventory(text) or re.findall(r'\d+',text)!=numbers:raise PreservePage('Positioned row validation failed')
        return data,1
    finally:ar.PAGE_W,ar.PAGE_H,ar.WIDTH,ar.HEIGHT=old

def validate_fragment(data,spans):
    expected=inventory(''.join(sp['text'] for sp in spans if sp['text']!='\uf0f1' and not sp.get('symbol_artwork')))
    with fitz.open(stream=data,filetype='pdf') as doc:
        actual=inventory(''.join(p.get_text() for p in doc))
        # Repeated table headings may add characters; none of the source may disappear.
        if expected-actual:raise PreservePage('Rendered output lost source text: '+str(dict(expected-actual)))
        def styled_inventory(items):
            counts=Counter()
            for sp in items:
                if sp.get('symbol_artwork') or sp['text']=='\uf0f1':continue
                key=(c.is_bold(sp),bool(sp.get('flags',0)&2) or bool(re.search('italic|oblique',sp['font'],re.I)),bool(sp.get('underline')),bool(sp.get('strike')),sp.get('color',0))
                counts.update((char,key) for char in sp['text'] if not char.isspace() and char!='\xad')
            return counts
        rendered=[sp for page in doc for sp in c.spans_of(page)]
        if styled_inventory(spans)-styled_inventory(rendered):raise PreservePage('Rendered output changed source emphasis, decoration or colour')
        for p in doc:
            words=c.spans_of(p)
            for sp in words:
                if 'Mulish' not in sp['font'] or abs(sp['size']-11)>.02:raise PreservePage('Font verification failed')
                box=fitz.Rect(sp['bbox'])
                if box.x0<c.LEFT-.5 or box.x1>p.rect.width-c.RIGHT+.5 or box.y1>p.rect.height-c.BOTTOM+2:raise PreservePage('Reflow exceeded margins')
            for _,line in c.rows_of(words):
                for left,right in zip(line,line[1:]):
                    if left['bbox'][2]>right['bbox'][0]+.6:raise PreservePage('Rendered text overlaps')
    return True

def add_header_footer(doc):
    import annual_report as ar
    fontfile=str(c.ROOT/'assets/Mulish-SemiBold.ttf');font=fitz.Font(fontfile=fontfile)
    for i,page in enumerate(doc):
        ar.add_full_header(page,c);page.insert_font(fontname='Mulish',fontfile=fontfile)
        label='P a g e';count=f'{i+1} | {len(doc)}';w=font.text_length(label,fontsize=11);cw=font.text_length(count,fontsize=11);x=page.rect.width-c.RIGHT-w-4-cw;y=page.rect.height-(841.92-786.696)
        page.insert_text((x,y),label,fontname='Mulish',fontsize=11,color=(.19,.51,.85));page.insert_text((x+w+4,y),count,fontname='Mulish',fontsize=11,color=(.15,.21,.28))

def preserve_page(out,src,index):
    page=src[index]
    remove=c.legacy_header_boxes(page)+getattr(src,'_source_page_numbers',{}).get(index,[])
    remove += [fitz.Rect(sp['bbox']) for sp in c.spans_of(page) if footer(sp,page)]
    for box in remove:page.add_redact_annot(box,fill=(1,1,1))
    if remove:page.apply_redactions(images=0,graphics=2,text=0)
    size=A4
    dest=out.new_page(width=size[0],height=size[1]);rect=fitz.Rect(c.LEFT,c.TOP,size[0]-c.RIGHT,size[1]-c.BOTTOM)
    if page.get_contents():dest.show_pdf_page(rect,src,index,keep_proportion=True)
    # Preserve visible annotations as a rendered overlay; forms are handled before this path.
    if list(page.annots() or []):
        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),annots=True);dest.insert_image(rect,stream=pix.tobytes('png'),keep_proportion=True)
    scale=min(rect.width/page.rect.width,rect.height/page.rect.height);dx=rect.x0+(rect.width-page.rect.width*scale)/2;dy=rect.y0+(rect.height-page.rect.height*scale)/2
    for link in page.get_links():
        if link.get('kind')==fitz.LINK_URI:
            box=fitz.Rect(link['from']);box=fitz.Rect(dx+box.x0*scale,dy+box.y0*scale,dx+box.x1*scale,dy+box.y1*scale)
            dest.insert_link({'kind':fitz.LINK_URI,'from':box,'uri':link['uri']})

def convert(source,destination,strict=False,initial_error=None):
    source=Path(source);destination=Path(destination);c.setup_fonts()
    if source.resolve()==destination.resolve():raise ValueError('Output must not overwrite original')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with fitz.open(source) as src:
        if src.needs_pass:raise BlockedPDF('Password-protected PDF: supply an unlocked copy. No output written.')
        if len(src)==0:raise BlockedPDF('PDF has no pages')
        if src.is_form_pdf or src.get_sigflags()>0:
            raise BlockedPDF('Interactive or signed PDF: use the editable/unlocked source. No fields or signatures were flattened.')
        import reviewed_disclosure
        reviewed=reviewed_disclosure.matches(source)
        c.mark_source_page_numbers(src)
        report={'input':source.name,'source_pages':len(src),'engine_version':VERSION,'font':'Mulish','font_pt':11,'page_size':'A4','top_margin_cm':3,'bottom_margin_cm':2.55,'left_margin_cm':1.88,'right_margin_cm':1.89,'pages':[],'notes':['Body and table text on rebuilt pages is Mulish 11pt. Preserved pages keep original fonts and layout.','Original page references remain in the text; Source page bookmarks map to the new pagination.','Review the visual layout before publication.']}
        if initial_error:report['previous_engine_error']=initial_error
        with fitz.open() as out,tempfile.TemporaryDirectory() as td:
            for index in range(len(src)):
                page=src[index]
                if page.rotation:page.remove_rotation()
                start=len(out)+1;exceptions=set();tables=0;reason='';mode='REFLOWED';attempts=[]
                try:
                    spans,symbols=content_spans(page);exceptions.update(symbols)

                    if not spans:raise PreservePage('Scan, image-only or blank page: original appearance retained; no OCR text invented')
                    check_glyphs(spans)
                    finder=find_visible_tables(page);tabs=list(finder.tables)
                    custom=reviewed_disclosure.build(page,spans,exceptions,c,__import__(__name__)) if reviewed else None
                    if custom is None:
                        from layout_core import contents_page
                        custom=contents_page(page,spans,c,__import__(__name__),exceptions)
                    if custom is None:page_features(page,spans,tabs,c.legacy_header_boxes(page))
                    positioned=not tabs and has_positioned_columns(spans)
                    data=None
                    sizes=[A4]
                    for size in sizes:
                        try:
                            with dimensions(size[0]-c.LEFT-c.RIGHT):
                                data,tables=custom if custom is not None else (positioned_page(page,spans,size,exceptions) if positioned else rule_page(page,spans,tabs,size,exceptions))
                            validate_fragment(data,spans)
                            with fitz.open(stream=data,filetype='pdf') as linked:
                                targets={link.get('uri') for p in linked for link in p.get_links()}
                                if {sp['uri'] for sp in spans if sp.get('uri')}-targets:raise PreservePage('Hyperlink target validation failed')
                            break
                        except Exception as error:
                            attempts.append(str(error));data=None
                    if data is None:raise PreservePage('; '.join(dict.fromkeys(attempts))[:1600])
                    with fitz.open(stream=data,filetype='pdf') as fragment:out.insert_pdf(fragment)
                except Exception as error:
                    reason=str(error);mode='PRESERVED'
                    if strict:raise c.ReviewRequired(f'Page {index+1}: {reason}') from error
                    preserve_page(out,src,index)
                report['pages'].append({'source_page':index+1,'output_start':start,'output_end':len(out),'mode':mode,'reason':reason,'tables':tables,'exceptions':sorted(exceptions),'orientation':'landscape' if out[-1].rect.width>out[-1].rect.height else 'portrait'})
                if (index+1)%10==0 or index+1==len(src):print(f'PDF: processed {index+1}/{len(src)} source pages',flush=True)
            for rec in report['pages']:
                if rec['mode']!='PRESERVED':continue
                original=src[rec['source_page']-1];dest=out[rec['output_start']-1]
                area=fitz.Rect(c.LEFT,c.TOP,dest.rect.width-c.RIGHT,dest.rect.height-c.BOTTOM)
                scale=min(area.width/original.rect.width,area.height/original.rect.height);dx=area.x0+(area.width-original.rect.width*scale)/2;dy=area.y0+(area.height-original.rect.height*scale)/2
                for link in original.get_links():
                    if link.get('kind')!=fitz.LINK_GOTO or not 0<=link.get('page',-1)<len(src):continue
                    b=fitz.Rect(link['from']);target=report['pages'][link['page']]['output_start']-1
                    dest.insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(dx+b.x0*scale,dy+b.y0*scale,dx+b.x1*scale,dy+b.y1*scale),'page':target,'to':fitz.Point(c.LEFT,c.TOP)})
            add_header_footer(out);out.set_toc([[1,f'Source page {r["source_page"]}',r['output_start']] for r in report['pages']])
            out.set_metadata({'title':source.stem+' - A4 conversion review','producer':'A4 PDF Converter '+VERSION})
            report['output_pages']=len(out);report['reflowed_source_pages']=sum(p['mode']=='REFLOWED' for p in report['pages']);report['preserved_source_pages']=[p['source_page'] for p in report['pages'] if p['mode']=='PRESERVED'];report['tables']=sum(p['tables'] for p in report['pages']);report['status']='PARTIAL_REVIEW_REQUIRED' if report['preserved_source_pages'] else 'CONVERTED_REVIEW_LAYOUT'
            symbol_artwork=any(any('artwork' in note for note in p['exceptions']) for p in report['pages'])
            report['font_compliance']='PARTIAL' if report['preserved_source_pages'] else ('ALL_TEXT_11PT_MULISH_WITH_SYMBOL_ARTWORK' if symbol_artwork else 'ALL_REBUILT_TEXT_11PT_MULISH')
            from pdf_preflight import diagnostics
            report['preflight']=diagnostics(src)
            temp=Path(td)/'complete.pdf';out.save(temp,garbage=4,deflate=True)
            with fitz.open(temp) as check:
                if len(check)!=report['output_pages']:raise RuntimeError('Saved page count mismatch')
            # Atomic replacement on the destination filesystem; the source is never mutated.
            staging=destination.with_name(destination.name+'.partial');staging.write_bytes(temp.read_bytes());os.replace(staging,destination)
            Path(str(destination)+'.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),'utf-8')
            return report
