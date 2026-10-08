"""Conservative positioned-row profile for the supplied 2000 ICICI Form 20-F.

Each source row stays together; text grows vertically within its original column.
Two organisational charts are retained as vector artwork, with original labels.
This profile is deliberately content-fingerprinted, not a generic PDF fallback.
"""
from pathlib import Path
from io import BytesIO
from collections import Counter
import hashlib,json,re,tempfile
from contextlib import ExitStack
import fitz
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT,TA_RIGHT,TA_CENTER
from xml.sax.saxutils import escape

CHARTS={27:(66,137,546,385),59:(65,552,556,708)}
PAGE_W,PAGE_H=landscape(A4)
LEFT=1.88*72/2.54;RIGHT=1.89*72/2.54;TOP=3*72/2.54;BOTTOM=2.55*72/2.54
WIDTH=PAGE_W-LEFT-RIGHT;HEIGHT=PAGE_H-TOP-BOTTOM

def matches(source):
    profile=json.loads(Path(__file__).with_name('assets').joinpath('form20f-profile.json').read_text())
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()==profile['sha256']

def canon(t):return Counter(c for c in t.replace('\uf8e7','—') if not c.isspace() and c!='\xad')
def value(t):return bool(re.fullmatch(r'(?:Rs\.?|US\$|\$)?\s*[-−—_\d,.()%]+(?:\(\d+\))?',t.replace('US $','US$')))
def currency(t):return bool(re.fullmatch(r'Rs\.?|US\$|\$',t))
def page_footer(s,p):
    return s['bbox'][1]>p.rect.height*.90 and bool(re.fullmatch(r'(?:F-)?\d+',s['text'].strip())) and p.rect.width*.3<s['bbox'][0]<p.rect.width*.7

def make_groups(ss):
    groups=[]
    for s in ss:
        gap=s['bbox'][0]-groups[-1][-1]['bbox'][2] if groups else 999
        previous=groups[-1][-1]['text'] if groups else ''
        split=(gap>8 or (value(previous) and value(s['text']) and gap>1.0)
               or (value(s['text']) and gap>4 and previous.endswith('.'))
               or (value(previous) and (currency(s['text']) or s['text']=='US') and gap>0))
        if (currency(previous) and gap<12) or (s.get('flags',0)&1 and gap<10):split=False
        if groups and not split:groups[-1].append(s)
        else:groups.append([s])
    return groups

class Row:
    def __init__(self,ss,source_left,source_width,helpers):
        c=helpers;self.ss=ss;self.sy=min(s['bbox'][1] for s in ss);self.ey=max(s['bbox'][3] for s in ss)
        self.baseline=min(s['origin'][1] for s in ss);self.parts=[];self.rules=[];self.boxes=[];self.repeat_header=[]
        self.numeric=[s['text'] for s in ss if value(s['text']) and any(ch.isdigit() for ch in s['text'])]
        self.expected=''.join(s['text'] for s in ss);self.minfont=min(s['size'] for s in ss)
        scale=WIDTH/source_width;groups=make_groups(ss);height=14
        for gi,g in enumerate(groups):
            lo=min(s['bbox'][0] for s in g);hi=max(s['bbox'][2] for s in g)
            # Use the original cell position and at most half its neighbouring gap.
            prev=max(s['bbox'][2] for s in groups[gi-1]) if gi else source_left
            nxt=min(s['bbox'][0] for s in groups[gi+1]) if gi+1<len(groups) else source_left+source_width
            x=max(0,(lo-source_left)*scale-min(3,max(0,(lo-prev)*scale/2-2)))
            right=min(WIDTH,(hi-source_left)*scale+max(0,(nxt-hi)*scale/2-2))
            text=c.plain(g).replace('\n',' ').replace('\uf8e7','—')
            num=value(text.strip())
            if num:
                # Numeric anchors preserve original right edges, including sparse columns.
                right=min(WIDTH,(hi-source_left)*scale)
            w=max(8,right-x)
            st=ParagraphStyle('row',fontName='Mulish-SemiBold',fontSize=11,leading=14,alignment=TA_RIGHT if num else TA_LEFT,splitLongWords=False,allowWidows=1,allowOrphans=1)
            markup=c.markup(g).replace('<br/>',' ').replace('\uf8e7','—')
            # A leader is decoration; allow it to wrap only as a last resort.
            p=Paragraph(markup,st)
            minw=p.minWidth()
            if minw>w+.01:
                extra=minw-w
                left_room=max(0,(lo-prev)*scale-2-min(3,max(0,(lo-prev)*scale/2-2)))
                shift=min(left_room,extra);x-=shift;w+=shift
                if p.minWidth()>w+.01:
                    right_room=max(0,min(WIDTH,(nxt-source_left)*scale-3)-(x+w))
                    w+=min(right_room,p.minWidth()-w)
                if p.minWidth()>w+.1:
                    raise c.ReviewRequired(f'Cannot fit unbroken token {text!r} at 11pt (needs {minw:.1f}, available {w:.1f}).')
            _,h=p.wrap(w,10000);height=max(height,h)
            self.parts.append((x,w,h,p,text))
        self.height=height+2
        self.numeric_cells=sum(value(c.plain(g).replace('\n',' ').strip()) and any(ch.isdigit() for sp in g for ch in sp['text']) for g in groups)
        self.source_text=c.plain(ss)
        self.all_bold=all(c.is_bold(sp) for sp in ss)
    def draw(self,canvas,top):
        for x,w,h,p,text in self.parts:p.drawOn(canvas,LEFT+x,PAGE_H-top-h)
        for x0,x1,where in self.rules:
            y=top+(0 if where=='top' else self.height-1)
            canvas.setStrokeColorRGB(.35,.35,.35);canvas.setLineWidth(.3)
            canvas.line(LEFT+x0,PAGE_H-y,LEFT+x1,PAGE_H-y)
        for x,checked in self.boxes:
            yy=PAGE_H-top-10
            canvas.setStrokeColorRGB(0,0,0);canvas.setLineWidth(.5);canvas.rect(LEFT+x,yy,8,8,stroke=1,fill=0)
            if checked:
                canvas.line(LEFT+x,yy,LEFT+x+8,yy+8);canvas.line(LEFT+x,yy+8,LEFT+x+8,yy)


class CoverRow(Row):
    def __init__(self,ss,source_left,source_width,helpers):
        super().__init__(ss,source_left,source_width,helpers)
        c=helpers;self.parts=[];self.height=0;groups=[]
        for sp in ss:
            if groups and sp['bbox'][0]-groups[-1][-1]['bbox'][2]<40:groups[-1].append(sp)
            else:groups.append([sp])
        for gi,g in enumerate(groups):
            lo=min(z['bbox'][0]for z in g);hi=max(z['bbox'][2]for z in g)
            centered=len(groups)==1 and abs((lo+hi)/2-323)<30 and len(c.plain(g))<170
            x=0 if centered else max(0,(lo-source_left)/source_width*WIDTH)
            w=WIDTH-x if gi==len(groups)-1 else (groups[gi+1][0]['bbox'][0]-source_left)/source_width*WIDTH-x-8
            st=ParagraphStyle('cover',fontName='Mulish-SemiBold',fontSize=11,leading=12.5,alignment=TA_CENTER if centered else TA_LEFT,splitLongWords=False)
            text=c.markup(g).replace('<br/>',' ');para=Paragraph(text,st);_,h=para.wrap(w,1000)
            self.parts.append((x,w,h,para,c.plain(g)));self.height=max(self.height,h+1)

def add_full_header(page,c):
    # Extend only the empty gradient, keeping the logo's proportions unchanged.
    w=page.rect.width
    if abs(w-A4[0])<1:
        page.insert_image(fitz.Rect(0,0,w,c.HEADER),filename=str(c.ROOT/'assets'/'header.jpg'));return
    with fitz.open() as header:
        hp=header.new_page(width=A4[0],height=c.HEADER)
        hp.insert_image(hp.rect,filename=str(c.ROOT/'assets'/'header.jpg'))
        clip=fitz.Rect(1,0,A4[0]-1,c.HEADER)
        pad=(w-clip.width)/2
        page.show_pdf_page(fitz.Rect(0,0,w,c.HEADER),header,0,clip=fitz.Rect(20,0,100,c.HEADER),keep_proportion=False)
        page.show_pdf_page(fitz.Rect(pad,0,pad+clip.width,c.HEADER),header,0,clip=clip,keep_proportion=False)


class Chart:
    def __init__(self,pn,box):
        self.pn=pn;self.box=fitz.Rect(box);self.sy=self.box.y0;self.ey=self.box.y1
        self.height=min(HEIGHT-5,self.box.height*1.25);self.width=self.height/self.box.height*self.box.width
        self.rules=[];self.numeric=[];self.minfont=99;self.expected='';self.repeat_header=[]


def convert(source,destination):
    global PAGE_W,PAGE_H,WIDTH,HEIGHT
    import converter as c
    c.setup_fonts();source=Path(source);destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    overlays=[];mapping=[];expected=[];row_checks=[];source_page_for_output=[];repeat_count=0;row_count=0
    with ExitStack() as resources:
        src=resources.enter_context(fitz.open(source))
        with tempfile.TemporaryDirectory() as temporary,ExitStack() as temp:
            body=Path(temporary)/'annual-body.pdf';canvas=Canvas(str(body),pagesize=(PAGE_W,PAGE_H),pageCompression=1)
            output_index=0
            for pn,page in enumerate(src,1):
                PAGE_W,PAGE_H=A4 if pn==1 else landscape(A4)
                WIDTH=PAGE_W-LEFT-RIGHT;HEIGHT=PAGE_H-TOP-BOTTOM
                canvas.setPageSize((PAGE_W,PAGE_H))
                spans=[dict(s) for s in c.spans_of(page) if not page_footer(s,page)]
                expected.extend(s['text'] for s in spans)
                chart=Chart(pn-1,CHARTS[pn]) if pn in CHARTS else None
                if chart:
                    spans=[s for s in spans if not chart.box.contains(fitz.Point((s['bbox'][0]+s['bbox'][2])/2,(s['bbox'][1]+s['bbox'][3])/2))]
                x0=min(s['bbox'][0] for s in spans);x1=max(s['bbox'][2] for s in spans)
                x0=min(x0,72);x1=max(x1,540)
                rows=[]
                for y,ss in c.rows_of(spans):
                    try:rows.append((CoverRow if pn==1 else Row)(ss,x0,x1-x0,c))
                    except c.ReviewRequired as e:raise c.ReviewRequired(f'Source page {pn}: {e}') from e
                row_count+=len(rows)
                # Keep thin table rules in their original horizontal positions.
                scale=WIDTH/(x1-x0)
                for drawing in page.get_drawings():
                    rect=drawing['rect']
                    if chart and chart.box.intersects(rect):continue
                    if rect.height<1.5 and rect.width>4:
                        target=min(rows,key=lambda r:min(abs(r.sy-rect.y0),abs(r.ey-rect.y0)))
                        where='top' if abs(target.sy-rect.y0)<abs(target.ey-rect.y0) else 'bottom'
                        a=max(0,(rect.x0-x0)*scale);b=min(WIDTH,(rect.x1-x0)*scale)
                        if b>a:target.rules.append((a,b,where))
                    elif pn==1 and 5<rect.width<12 and 5<rect.height<12:
                        target=min(rows,key=lambda r:abs(r.sy-rect.y0))
                        target.boxes.append(((rect.x0-x0)*scale,195<rect.y0<215))
                # Identify column-heading bands from repeated year labels. These are
                # repeated on continuation pages without duplicating any data row.
                heading_indices=[]
                for index,row in enumerate(rows):
                    years=re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)',row.source_text)
                    if len(years)>=2 and row.numeric_cells>=2:
                        groups=make_groups(row.ss)
                        if sum(bool(re.fullmatch(r'(?:19|20)\d{2}(?:\(\d+\))?',c.plain(g).strip())) for g in groups)>=2:
                            heading_indices.append(index)
                for hi,idx in enumerate(heading_indices):
                    first=idx;last=idx
                    for j in range(idx-1,max(-1,idx-4),-1):
                        r=rows[j]
                        if rows[first].sy-r.ey>10 or min(sp['bbox'][0]for sp in r.ss)<x0+90 or r.numeric_cells:break
                        first=j
                    for j in range(idx+1,min(len(rows),idx+4)):
                        r=rows[j]
                        if r.sy-rows[last].ey>9 or min(sp['bbox'][0]for sp in r.ss)<x0+90 or r.numeric_cells:break
                        last=j
                    stop=heading_indices[hi+1] if hi+1<len(heading_indices) else len(rows)
                    data=[j for j in range(last+1,stop) if rows[j].numeric_cells>=2]
                    if data:
                        band=rows[first:last+1]
                        for j in range(last+1,data[-1]+1):rows[j].repeat_header=band
                events=sorted(rows+([chart]if chart else []),key=lambda r:r.sy)
                # A blank source line separates a paragraph/table block. Keep any block
                # fitting one page intact. Larger blocks split only between source rows.
                blocks=[]
                for event in events:
                    if blocks and not isinstance(event,Chart) and not isinstance(blocks[-1][-1],Chart) and event.sy-blocks[-1][-1].ey<7:
                        blocks[-1].append(event)
                    else:blocks.append([event])
                y=TOP;last_ey=None;page_start=output_index+1
                def next_page():
                    nonlocal output_index,y,last_ey
                    canvas.showPage();output_index+=1;source_page_for_output.append(pn);y=TOP;last_ey=None
                for block in blocks:
                    gap=0 if last_ey is None else (max(1,min(5,(block[0].sy-last_ey)*.35)) if pn==1 else max(2,min(14,block[0].sy-last_ey)))
                    block_h=sum(r.height for r in block)+gap
                    continued=False
                    if y>TOP and block_h<=HEIGHT and y+block_h>PAGE_H-BOTTOM:next_page();gap=0;continued=True
                    y+=gap
                    units=[]
                    for event in block:
                        previous=units[-1][-1] if units else None
                        join=False
                        if previous and isinstance(previous,Row) and isinstance(event,Row):
                            short_label=lambda r:len(r.source_text)<110 and min(sp['bbox'][0]for sp in r.ss)<x0+110
                            continuation=(event.sy-previous.ey<4 and event.minfont<10.5 and previous.minfont<10.5
                                and ((previous.numeric_cells>=2 and event.numeric_cells==0 and short_label(event) and not event.all_bold)
                                     or (event.numeric_cells>=2 and previous.numeric_cells==0 and short_label(previous))))
                            join=continuation or (previous.all_bold and previous.numeric_cells==0 and len(previous.source_text)<140)
                        if join:units[-1].append(event)
                        else:units.append([event])
                    for unit in units:
                        unit_height=sum(event.height for event in unit)
                        if y+unit_height>PAGE_H-BOTTOM+.01:next_page();continued=True
                        if continued and unit[0].repeat_header:
                            for heading in unit[0].repeat_header:
                                heading.draw(canvas,y);expected.append(heading.expected);repeat_count+=1;y+=heading.height
                            y+=4
                        continued=False
                        if y+unit_height>PAGE_H-BOTTOM+.01:raise c.ReviewRequired(f'A complete table row cannot fit on A4 at 11pt, source page {pn}.')
                        for event in unit:
                            if isinstance(event,Chart):
                                overlays.append((output_index,event.pn,event.box,fitz.Rect(LEFT,y,LEFT+event.width,y+event.height)))
                            else:
                                event.draw(canvas,y)
                                row_checks.append({'source_page':pn,'output_page':output_index+1,'top':y,'bottom':y+event.height,'numbers':event.numeric,'expected':event.expected,'numeric_order':re.findall(r'\d+(?:[,.]\d+)*',event.source_text)})
                            y+=event.height;last_ey=event.ey
                mapping.append({'source_page':pn,'output_start':page_start,'output_end':output_index+1})
                next_page()
                if pn%25==0:print(f'Form 20-F: laid out {pn}/{len(src)} source pages',flush=True)
            canvas.save()
            bodydoc=temp.enter_context(fitz.open(body));out=temp.enter_context(fitz.open())
            for i,bodypage in enumerate(bodydoc):
                p=out.new_page(width=bodypage.rect.width,height=bodypage.rect.height);p.show_pdf_page(p.rect,bodydoc,i)
            for i,pn,box,target in overlays:out[i].show_pdf_page(target,src,pn,clip=box)
            # Validate source row membership using only the physical output row area.
            output_spans={p.number:c.spans_of(p) for p in out}
            for record in row_checks:
                p=out[record['output_page']-1]
                txt=' '.join(sp['text'] for sp in output_spans[p.number] if record['top']<=(sp['bbox'][1]+sp['bbox'][3])/2<record['bottom'])
                if canon(record['expected'])-canon(txt):
                    raise c.ReviewRequired(f'Output row inventory failed, source page {record["source_page"]}, output page {record["output_page"]}: {canon(record["expected"])-canon(txt)}')
                # Independently compare the ordered numeric values in each row.
                numbers=lambda t:re.findall(r'\d+(?:[,.]\d+)*',t)
                if record['numeric_order']!=numbers(txt):
                    raise c.ReviewRequired(f'Numeric column order changed on output page {record["output_page"]}: {record["numeric_order"]} versus {numbers(txt)}, source {record["source_page"]}, {record["top"]}, expected {record["expected"]!r}, actual {txt!r}')
            # No two rebuilt word boxes may collide on the same baseline.
            for page_number,spans in output_spans.items():
                for _,line in c.rows_of([sp for sp in spans if 'Mulish' in sp['font']]):
                    for left,right in zip(line,line[1:]):
                        if left['bbox'][2]-right['bbox'][0]>.5:
                            raise c.ReviewRequired(f'Overlapping output text on page {page_number+1}: {left["text"]!r}, {right["text"]!r}')
            actual=''.join(p.get_text() for p in out)
            if canon(''.join(expected))!=canon(actual):
                raise c.ReviewRequired(f'Whole-document inventory failed: missing {canon("".join(expected))-canon(actual)}, extra {canon(actual)-canon("".join(expected))}')
            fontpath=c.ROOT/'assets'/'Mulish-SemiBold.ttf';font=fitz.Font(fontfile=str(fontpath))
            for i,p in enumerate(out):
                # Banner stays at its reference aspect ratio instead of stretching.
                add_full_header(p,c)
                p.insert_font(fontname='Mulish',fontfile=str(fontpath))
                baseline=p.rect.height-(841.92-786.696)
                p.insert_text((LEFT,baseline),f'Source page {source_page_for_output[i]}',fontname='Mulish',fontsize=11,color=(.15,.21,.28))
                label='P a g e';count=f'{i+1} | {len(out)}';a=font.text_length(label,fontsize=11);b=font.text_length(count,fontsize=11)
                x=p.rect.width-RIGHT-a-4-b
                p.insert_text((x,baseline),label,fontname='Mulish',fontsize=11,color=(.19,.51,.85))
                p.insert_text((x+a+4,baseline),count,fontname='Mulish',fontsize=11,color=(.15,.21,.28))
            out.set_toc([[1,f'Source page {r["source_page"]}',r['output_start']]for r in mapping])
            out.set_metadata({'title':'ICICI Form 20-F — Mulish 11 pt','subject':'A4 landscape; charts retained as source artwork','producer':'A4 PDF Converter v1.4'})
            out.save(destination,garbage=4,deflate=True)
        checked=resources.enter_context(fitz.open(destination));font_counts=Counter();bounds_errors=[]
        for p in checked:
            for sp in c.spans_of(p):
                font_counts[(sp['font'],round(sp['size'],2))]+=1
                if 'Mulish' in sp['font'] and (sp['bbox'][0]<LEFT-1 or sp['bbox'][2]>p.rect.width-RIGHT+1):bounds_errors.append(p.number+1)
        if bounds_errors:raise c.ReviewRequired(f'Horizontal overflow on output pages {sorted(set(bounds_errors))}')
        report={'input':source.name,'source_pages':len(src),'output_pages':len(checked),'tables':'positioned rows preserved','font':'Mulish','font_pt':11,'page_size':'A4; portrait cover and landscape report pages','status':'CONVERTED_REVIEW_LAYOUT','profile':'ICICI Form 20-F 2000','original_rows_verified':row_count,'repeated_heading_rows':repeat_count,'text_overlap_check':'passed','numeric_rows_verified':sum(bool(r['numbers'])for r in row_checks),'old_headers_removed':0,'page_borders_removed':0,'top_margin_cm':3,'bottom_margin_cm':2.55,'left_margin_cm':1.88,'right_margin_cm':1.89,'character_inventory':'exact, allowing repeated column headings and excluding original page footers; Symbol private dash mapped to em dash','font_spans':[{'font':f,'size_pt':size,'count':count}for (f,size),count in sorted(font_counts.items())],'exceptions':[{'source_page':pn,'feature':'Organisational chart','action':'Original vector artwork and chart label fonts retained'}for pn in CHARTS],'notes':['All rebuilt body, tables and footer text uses embedded Mulish 11 pt.','Original rows stay together. Long tables/sections may continue on another page.','Original page references remain unchanged; Source page footer and bookmarks map them to the new pagination.','Two organisational charts retain their original label fonts.','This exact-file profile does not automatically enable untested complex PDFs.'],'page_map':mapping}
        Path(str(destination)+'.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        return report

if __name__=='__main__':
    import sys
    r=convert(sys.argv[1],sys.argv[2]);print(json.dumps({k:v for k,v in r.items()if k not in ['page_map','font_spans']},indent=2))
