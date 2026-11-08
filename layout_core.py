"""Reflow primitives with independent checks of text drawn inside each cell."""
from collections import defaultdict, Counter
from io import BytesIO
import re
import fitz
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_RIGHT

class CellParagraph(Paragraph):
    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        for part in parts:
            part.cell_proof = getattr(self, 'cell_proof', None)
        return parts

    def draw(self):
        super().draw()
        proof = getattr(self, 'cell_proof', None)
        if not proof:
            return
        records = getattr(self.canv, '_cell_proof_records', None)
        if records is None: records = self.canv._cell_proof_records = []
        x, y = self.canv.absolutePosition(0, 0)
        ph = self.canv._pagesize[1]
        records.append((proof, self.canv.getPageNumber()-1, (x, ph-y-self.height, x+self.width, ph-y)))

def cell_paragraph(markup, style, identity, expected):
    para = CellParagraph(markup, style)
    para.cell_proof = (identity, expected)
    return para

def verify_cells(data, records, c):
    if not records:
        return
    expected = {}; actual = defaultdict(list)
    with fitz.open(stream=data, filetype='pdf') as doc:
        spans = {p.number: c.spans_of(p) for p in doc}
        for (identity, text), pn, coords in records:
            expected[identity] = text
            box = fitz.Rect(coords) + (-.1, -.5, .1, .5)
            selected = [s for s in spans[pn] if box.contains(fitz.Point((s['bbox'][0]+s['bbox'][2])/2, s['origin'][1]-s['size']*.35))]
            actual[identity].append(c.plain(selected))
    for identity, text in expected.items():
        rendered = ' '.join(actual[identity])
        canonical = lambda value: Counter(ch for ch in value if not ch.isspace() and ch != '\xad')
        if canonical(text) - canonical(rendered):
            raise ValueError(f'Table cell {identity} lost text during layout')
        before = re.findall(r'\d+', text); after = re.findall(r'\d+', rendered)
        # Repeated headings repeat complete sequences. A split row must retain
        # its sequence across all fragments; a document-wide character count
        # cannot detect these column/row errors.
        if before and (len(after) % len(before) or any(after[i:i+len(before)] != before for i in range(0, len(after), len(before)))):
            raise ValueError(f'Table cell {identity} changed its number sequence')

def build_document(story, c, size=A4):
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=size, leftMargin=c.LEFT-6, rightMargin=c.RIGHT-6, topMargin=c.TOP-6, bottomMargin=c.BOTTOM-6)
    doc.build(story)
    data = stream.getvalue()
    verify_cells(data, getattr(doc.canv, '_cell_proof_records', []), c)
    return data

def contents_page(page, spans, c, a, exceptions):
    """Recognise an enumerated contents list with a separate right page column.

    Requires at least five numbered entries and aligned page references; no
    source fingerprint, wording replacement, or inferred page numbers.
    """
    rows = c.rows_of(spans)
    if not rows:
        return None
    first_text = c.plain([s for _, row in rows[:2] for s in row]).lower()
    if not ('page' in first_text and ('topic' in first_text or 'content' in first_text)):
        return None
    starts = [(i, row[0]) for i, (_, row) in enumerate(rows) if re.fullmatch(r'\d+[.)]', row[0]['text'])]
    if len(starts) < 5 or max(s['bbox'][0] for _, s in starts)-min(s['bbox'][0] for _, s in starts) > 5:
        return None
    right = max(s['bbox'][2] for s in spans)
    entries = []
    for j, (start, marker) in enumerate(starts):
        end = starts[j+1][0] if j+1 < len(starts) else len(rows)
        group = [s for _, row in rows[start:end] for s in row]
        numbers = [s for s in group if s is not marker and re.fullmatch(r'\d+', s['text']) and abs(s['bbox'][2]-right) < 6]
        if len(numbers) != 1:
            return None
        number = numbers[0]; topic = [s for s in group if s is not marker and s is not number]
        if not topic:
            return None
        entries.append(([marker], topic, [number]))
    head = [s for _, row in rows[:starts[0][0]] for s in row]
    split = right - 75
    header = ([], [s for s in head if s['bbox'][0] < split], [s for s in head if s['bbox'][0] >= split])
    if not header[1] or not header[2]:
        return None
    data = []
    for ri, group in enumerate([header] + entries):
        data.append([cell_paragraph(a.text_markup(ss, page, exceptions), a.body_style(TA_RIGHT if ci == 2 else 0), f'toc:{page.number}:{ri}:{ci}', c.plain(ss)) for ci, ss in enumerate(group)])
    table = Table(data, colWidths=[30, c.WIDTH-90, 60], repeatRows=1, splitByRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),4), ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5), ('LINEBELOW',(1,0),(-1,0),.5,'#555555')]))
    return build_document([table], c), 1
