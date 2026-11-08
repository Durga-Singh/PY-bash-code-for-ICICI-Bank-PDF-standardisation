"""Reviewed portrait layouts for the supplied 2018 disclosure; exact-source gated."""
import hashlib
import re
from io import BytesIO
from types import SimpleNamespace
import fitz
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Flowable,Paragraph,Spacer,SimpleDocTemplate
from reportlab.lib.enums import TA_CENTER

SOURCE='5473d83b158faf17a910112b623fd7bd2773b8de90f065ecc8252f61f577eb72'
def matches(path):return hashlib.sha256(path.read_bytes()).hexdigest()==SOURCE

def build(page,spans,exceptions,c,a):
    if page.number==137:return chart(page,spans,exceptions,c,a)
    if 102<=page.number<=108:return capital_table(page,spans,exceptions,c,a)
    if page.number in (149,150):return split_table(page,spans,exceptions,c,a)
    return None

def document(story,c):
    from layout_core import build_document
    return build_document(story,c)

def chart(page,spans,exceptions,c,a):
    boxes=sorted([fitz.Rect(d['rect']) for d in page.get_drawings() if d['rect'].y0>200 and d['rect'].y1<350 and d['rect'].width>80],key=lambda b:(round(b.y0/30),b.x0))
    assert len(boxes)==8
    used=set();groups=[]
    for box in boxes:
        group=[]
        for i,sp in enumerate(spans):
            if box.contains(fitz.Point((sp['bbox'][0]+sp['bbox'][2])/2,sp['origin'][1]-sp['size']*.35)):group.append(sp);used.add(i)
        groups.append(group)
    class Chart(Flowable):
        def __init__(self):
            super().__init__();self.width=c.WIDTH;self.height=290
        def draw(self):
            cv=self.canv
            def text(group,x,y,w):
                p=Paragraph(a.text_markup(group,page,exceptions),a.body_style(TA_CENTER));_,h=p.wrap(w,1000);p.drawOn(cv,x,y-h)
            text([s for s in spans if 108<s['origin'][1]<125],100,290,c.WIDTH-200)
            text([s for s in spans if 150<s['origin'][1]<180],80,244,c.WIDTH-160)
            for top in [267,202]:
                x=c.WIDTH/2;cv.setLineWidth(1);cv.line(x,top,x,top-14);path=cv.beginPath();path.moveTo(x-4,top-10);path.lineTo(x,top-16);path.lineTo(x+4,top-10);path.close();cv.drawPath(path,fill=1)
            w=(c.WIDTH-24)/4
            for i,group in enumerate(groups):
                x=(i%4)*(w+8);y=180-(i//4)*100;cv.setStrokeColorRGB(.65,.65,.65);cv.rect(x,y-86,w,86);text(group,x+4,y-8,w-8)
    story=[]
    for group in [[s for s in spans if s['origin'][1]<80],[s for s in spans if 80<=s['origin'][1]<108]]:
        story.extend([Paragraph(a.text_markup(group,page,exceptions),a.body_style()),Spacer(1,12)])
    story.extend([Chart(),Spacer(1,14)])
    foot=[s for s in spans if s['origin'][1]>=350]
    # Group footnote markers and their descriptions by the five reviewed baseline bands.
    for lo,hi in [(350,382),(382,406),(406,430),(430,454),(454,484),(484,500),(500,525),(525,600)]:
        group=[s for s in foot if lo<=s['origin'][1]<hi]
        if group:story.extend([Paragraph(a.text_markup(group,page,exceptions),a.body_style()),Spacer(1,5)])
    return document(story,c),0

def capital_table(page,spans,exceptions,c,a):
    spans=[dict(sp) for sp in spans]
    # Reviewed source-page 106 has three shifted cells in its final issuance row.
    # Restore their semantic columns without changing text or numeric values.
    if page.number==105:
        for sp in spans:
            if 550<sp['origin'][1]<560:
                target={'99,898,476':180,'10.00':245,'1,002.50':295}.get(sp['text'])
                if target and sp['bbox'][0]<300:
                    b=sp['bbox'];dx=target-(b[0]+b[2])/2;sp['bbox']=(b[0]+dx,b[1],b[2]+dx,b[3])
    xs=[55,147,224,277,322,377,498,562]
    rows=c.rows_of(spans);head=next(y for y,ss in rows if 'Date of' in c.plain(ss))
    # The last three source pages position the Shares heading in the date
    # column. Keep it with Number of Equity in the reviewed reconstruction.
    if page.number in (106,107,108):
        for sp in spans:
            if sp['text']=='Shares' and sp['bbox'][0]<140 and head<sp['origin'][1]<head+25:
                b=sp['bbox'];sp['bbox']=(180,b[1],180+b[2]-b[0],b[3])
    # The # footnote on page 108 belongs to cumulative capital.
    if page.number==107:
        for sp in spans:
            if sp['text']=='#' and 250<sp['origin'][1]<265:
                b=sp['bbox'];sp['bbox']=(499,b[1],499+b[2]-b[0],b[3])
    note_y=min((y for y,ss in rows if any(sp['text'].startswith('*') and sp['bbox'][0]<80 for sp in ss)),default=10000)
    date_groups=[]
    for y,ss in rows:
        if y<=head+25 or y>=note_y:continue
        if any(sp['bbox'][0]<140 for sp in ss):
            if date_groups and y-date_groups[-1][-1]<12:date_groups[-1].append(y)
            else:date_groups.append([y])
    amounts=sorted([s for s in spans if 147<=(s['bbox'][0]+s['bbox'][2])/2<224 and head+25<s['origin'][1]<note_y and re.fullmatch(r'\**-?\d[\d,]*',s['text'])],key=lambda s:s['origin'][1])
    ys=[];last_amount=-1
    for s in amounts:
        y=s['origin'][1];group=next((g for g in date_groups if g[0]-.5<=y<=g[-1]+.5),[])
        start=group[0] if group and group[0]>last_amount else y
        last_amount=y
        if not ys or start>ys[-1]+8:ys.append(start-4)
    if not ys:raise a.PreservePage('Capital table row anchors missing')
    end=max(s['bbox'][3] for s in spans)+2
    # Keep post-table notes as prose when a row runs across several columns.
    trailing=[(y,ss) for y,ss in rows if y>amounts[-1]['origin'][1]+10 and any(s['bbox'][0]<80 and (s['text'].startswith('*') or s['text'].startswith('Note')) for s in ss)]
    if trailing:end=trailing[0][0]-5
    ys=[head-10]+ys+[end]
    for sp in spans:
        if head+25<sp['origin'][1]<end and sp['bbox'][0]>=498 and not re.fullmatch(r'[#*\d,\-]+',sp['text']):
            b=sp['bbox'];sp['bbox']=(400,b[1],400+b[2]-b[0],b[3])
    cells=[(xs[i],ys[j],xs[i+1],ys[j+1]) for j in range(len(ys)-1) for i in range(len(xs)-1)]
    tab=SimpleNamespace(cells=cells,bbox=(xs[0],ys[0],xs[-1],ys[-1]))
    data,used,texts=a.table_flow(tab,spans,page,c.WIDTH,xs[-1]-xs[0],exceptions)
    data.splitInRow=0
    before=[s for i,s in enumerate(spans) if i not in used and s['origin'][1]<head];after=[s for i,s in enumerate(spans) if i not in used and s['origin'][1]>=head]
    story=[]
    if before:story.extend([Paragraph(a.text_markup(before,page,exceptions),a.body_style()),Spacer(1,10)])
    story.append(data)
    if after:story.extend([Spacer(1,8),Paragraph(a.text_markup(after,page,exceptions),a.body_style())])
    return document(story,c),1

def split_table(page,spans,exceptions,c,a):
    from reportlab.platypus import Table,TableStyle,PageBreak
    from reportlab.lib.enums import TA_RIGHT
    tab=page.find_tables().tables[0];grid=[];used=set()
    for row in tab.rows:
        cells=[]
        for cell in row.cells:
            if not cell:raise a.PreservePage('Cannot split merged columns safely')
            box=fitz.Rect(cell);ss=[]
            for i,sp in enumerate(spans):
                if box.contains(fitz.Point((sp['bbox'][0]+sp['bbox'][2])/2,sp['origin'][1]-sp['size']*.35)):ss.append(sp);used.add(i)
            cells.append(ss)
        grid.append(cells)
    if page.number==150:
        previous=page.parent[149];ps,_=a.content_spans(previous);header=[]
        for cell in previous.find_tables().tables[0].rows[0].cells:
            box=fitz.Rect(cell);header.append([sp for sp in ps if box.contains(fitz.Point((sp['bbox'][0]+sp['bbox'][2])/2,sp['origin'][1]-sp['size']*.35))])
        grid.insert(0,header)
    # Join the source header's line-wrapped word fragments. All letters,
    # punctuation and emphasis are retained; only the internal spaces change.
    for ci,cell in enumerate(grid[0]):
        label=' '.join(c.plain(cell).split())
        fixed=label.replace('Coupo n','Coupon').replace('Redemptio n','Redemption').replace('Unsecure d','Unsecured')
        if fixed!=label:
            merged=dict(cell[0]);merged['text']=fixed;grid[0][ci]=[merged]
    before=[sp for i,sp in enumerate(spans) if i not in used];story=[]
    if before:story.extend([Paragraph(a.text_markup(before,page,exceptions),a.body_style()),Spacer(1,10)])
    for part,cols in enumerate([[0,1,2,3],[0,4,5,6,7]]):
        if part:story.append(PageBreak())
        data=[]
        for ri,row in enumerate(grid):
            data.append([Paragraph(a.text_markup(row[ci],page,exceptions),a.body_style(TA_RIGHT if ci in (1,3) and ri else 0)) for ci in cols])
        mins=[max(row[j].minWidth()+8 for row in data) for j in range(len(cols))]
        if sum(mins)>c.WIDTH:raise a.NeedWider('Split table still exceeds portrait width')
        weights=[1,1,1,1.4] if part==0 else [1,1,1,1.8,1]
        widths=[m+(c.WIDTH-sum(mins))*w/sum(weights) for m,w in zip(mins,weights)]
        t=Table(data,colWidths=widths,repeatRows=1,splitByRow=1,splitInRow=1,hAlign='LEFT');t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,'#727272'),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]));story.append(t)
    return document(story,c),1
