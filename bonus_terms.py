"""Reviewed table boundaries and duplicate-image handling for the supplied bonus terms."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json
import fitz
ROOT=Path(__file__).resolve().parent

def matches(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()==json.loads((ROOT/'assets'/'bonus-terms-profile.json').read_text())['sha256']

def grid(xs,ys,merged_rows=()):
    cells=[]
    for ri,(y0,y1) in enumerate(zip(ys,ys[1:])):
        if ri in merged_rows:cells.append((xs[0],y0,xs[-1],y1))
        else:cells.extend((x0,y0,x1,y1)for x0,x1 in zip(xs,xs[1:]))
    return SimpleNamespace(bbox=(xs[0],ys[0],xs[-1],ys[-1]),cells=cells)

def tables(page_number):
    if page_number==2:
        return [grid([51.8645,163.51,268.54,372.30,505.7578],[119.948,173.012,212.180,236.060,274.820,313.610,337.610,406.130]),
                grid([51.45,203.016,354.578,506.652],[452.407,495.249,513.693,530.614,563.012,580.435,597.380,630.750]),
                grid([56.25,498.50],[679.448,761.198])]
    if page_number==3:
        return [grid([42.4985,140.90,197.67,267.29,343.87,413.81,481.28,551.7215],
                     [217.111,286.482,303.890,331.970,360.170,388.250,416.330,444.410,472.630,500.710,528.790,546.190,574.270],merged_rows=(10,))]
    return []

def clean_spans(spans,page_number):
    # The discarded slogan has zero opacity and no visible image counterpart.
    if page_number==0:
        spans=[s for s in spans if not (s['text'] in ('Exciting','News') and 96<s['bbox'][1]<99)]
    if page_number==2:
        for s in spans:
            if (119<s['origin'][1]<173 and 51<s['bbox'][0]<506) or (679<s['origin'][1]<762 and 56<s['bbox'][0]<499):s['color']=0xffffff
    if page_number==2:
        for s in spans:
            if 730<s['origin'][1]<748 and 100<s['bbox'][0]<450:s['underline']=True
    # Align superscript OCR fragments with their parent row while rendering
    # their markers at the requested 11pt with a small baseline rise.
    body=[s for s in spans if s['size']>=9]
    for s in spans:
        if s['size']<9:
            near=[b for b in body if abs(b['origin'][1]-s['origin'][1])<9]
            if near:
                parent=min(near,key=lambda b:abs(b['origin'][1]-s['origin'][1])*8+min(abs(b['bbox'][2]-s['bbox'][0]),abs(b['bbox'][0]-s['bbox'][2])))
                s['flags']|=1;s['origin']=(s['origin'][0],parent['origin'][1]-s['size']*.55)
    # Fragmented OCR places an artificial space inside the printed month name.
    for i in range(len(spans)-1,0,-1):
        a,b=spans[i-1],spans[i]
        if a['text']=='Oct' and b['text']=='ober' and abs(a['origin'][1]-b['origin'][1])<2:
            a['text']='October';a['bbox']=(a['bbox'][0],min(a['bbox'][1],b['bbox'][1]),b['bbox'][2],max(a['bbox'][3],b['bbox'][3]));spans.pop(i)
    return spans

def duplicate_image(info):
    # Every 2x2 colour tile in this reviewed PDF is a masked raster rendering of
    # extractable text. The corresponding text is rebuilt once at 11pt.
    return info['width']==2 and info['height']==2
