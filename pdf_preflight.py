"""Document-scoped font inspection; no filename or document fingerprint rules."""
from io import BytesIO
import re
from fontTools.ttLib import TTFont

OPAQUE = re.compile(r'^(?:[A-Z]{6}\+)?(?:CIDFont\+.*|F\d+|Font\d+|C\d+_\d+|Unknown.*)$', re.I)

def _name(font, ids):
    for ident in ids:
        value = font['name'].getDebugName(ident) if 'name' in font else None
        if value:
            return value
    return ''

def font_metadata(doc, xref):
    cache = getattr(doc, '_resolved_font_programs', None)
    if cache is None:
        cache = doc._resolved_font_programs = {}
    if xref not in cache:
        result = None
        try:
            _, _, _, data = doc.extract_font(xref)
            if data:
                with TTFont(BytesIO(data), lazy=False) as font:
                    name = _name(font, (6, 4, 1))
                    family = _name(font, (16, 1))
                    style = _name(font, (17, 2))
                    os2 = font.get('OS/2'); post = font.get('post')
                    weight = getattr(os2, 'usWeightClass', 400)
                    selection = getattr(os2, 'fsSelection', 0)
                    italic = bool(selection & 1 or getattr(post, 'italicAngle', 0) or re.search('italic|oblique', style, re.I))
                    if name and not OPAQUE.fullmatch(name):
                        result = {'font': name, 'family': family, 'bold': weight >= 700, 'italic': italic, 'weight': weight, 'xref': xref}
        except Exception as error:
            # Do not invent a family/weight when a font program cannot be read.
            issues = getattr(doc, '_font_resolution_issues', None)
            if issues is None: issues = doc._font_resolution_issues = []
            issues.append({'xref': xref, 'reason': str(error)[:240]})
        cache[xref] = result
    return cache[xref]

def resolve_spans(page, spans):
    opaque = {s['font'] for s in spans if OPAQUE.fullmatch(s['font'])}
    if not opaque:
        return spans
    mappings = {}
    for xref, _, _, base, resource, *_ in page.get_fonts(full=True):
        aliases = {base, re.sub(r'^[A-Z]{6}\+', '', base), resource}
        for alias in aliases & opaque:
            meta = font_metadata(page.parent, xref)
            if meta: mappings.setdefault(alias, []).append(meta)
    for span in spans:
        choices = mappings.get(span['font'], [])
        identities = {(m['font'], m['bold'], m['italic']) for m in choices}
        if len(identities) != 1:
            continue
        meta = choices[0]
        span['source_font'] = span['font']
        span['font'] = meta['font']
        span['font_weight'] = meta['weight']
        span['flags'] = (span.get('flags', 0) & ~(16 | 2)) | (16 if meta['bold'] else 0) | (2 if meta['italic'] else 0)
    return spans

def diagnostics(doc):
    return {'resolved_embedded_fonts': [m for m in getattr(doc, '_resolved_font_programs', {}).values() if m],
            'font_resolution_issues': getattr(doc, '_font_resolution_issues', [])}
