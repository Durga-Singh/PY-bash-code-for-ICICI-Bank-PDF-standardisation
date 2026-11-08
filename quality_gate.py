"""Measure the saved PDF instead of trusting a converter's declared settings."""
from collections import Counter
import fitz
from reportlab.lib.pagesizes import A4

def inspect(path, report):
    fonts = Counter(); sizes = Counter(); bad_fonts = set(); bad_sizes = []
    pages_without_text = []; outside = set()
    with fitz.open(path) as doc:
        for page in doc:
            pn = page.number + 1
            sizes[f'{page.rect.width:.2f} x {page.rect.height:.2f} pt'] += 1
            if abs(page.rect.width-A4[0]) > .1 or abs(page.rect.height-A4[1]) > .1:
                bad_sizes.append(pn)
            spans = [s for b in page.get_text('dict')['blocks'] for line in b.get('lines', []) for s in line['spans'] if s['text'].strip()]
            body = [s for s in spans if s['bbox'][1] < page.rect.height - 72]
            if not body: pages_without_text.append(pn)
            for s in spans:
                fonts[f'{s["font"]} {s["size"]:.3f} pt'] += 1
                if 'Mulish' not in s['font'] or abs(s['size']-11) > .02:
                    bad_fonts.add(pn)
                if s['bbox'][0] < -.5 or s['bbox'][2] > page.rect.width+.5 or s['bbox'][1] < -.5 or s['bbox'][3] > page.rect.height+.5:
                    outside.add(pn)
    preserved = report.get('preserved_source_pages', [])
    artwork = [p['source_page'] for p in report.get('pages', []) if 'Embedded images retained as artwork' in p.get('exceptions', [])]
    reasons = []
    if bad_fonts: reasons.append('Non-Mulish or non-11pt text on output pages: ' + ', '.join(map(str, sorted(bad_fonts))))
    if bad_sizes: reasons.append('Non-portrait-A4 output pages: ' + ', '.join(map(str, bad_sizes)))
    if preserved: reasons.append('Original layout retained on source pages: ' + ', '.join(map(str, preserved)))
    if artwork: reasons.append('Text inside retained artwork cannot be font-verified; source pages: ' + ', '.join(map(str, artwork)))
    if outside: reasons.append('Text exceeds page boundaries: ' + ', '.join(map(str, sorted(outside))))
    return {'passed': not reasons, 'measured_page_sizes': dict(sizes), 'measured_fonts_and_sizes': dict(fonts),
            'noncompliant_font_output_pages': sorted(bad_fonts), 'noncompliant_size_output_pages': bad_sizes,
            'unverified_artwork_source_pages': artwork, 'output_pages_without_body_text': pages_without_text,
            'text_outside_page': sorted(outside), 'review_reasons': reasons}
