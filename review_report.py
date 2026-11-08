"""A local, readable report next to each generated PDF; no external resources."""
from html import escape
from pathlib import Path
from urllib.parse import quote

def write(pdf_path, result):
    pdf_path=Path(pdf_path);path=pdf_path.with_suffix('.review.html')
    e=lambda value:escape(str(value))
    verified=result.get('verification',{});passed=verified.get('passed',False)
    title='Format checks passed' if passed else 'Incomplete conversion - review required'
    issues=''.join('<li>'+e(reason)+'</li>' for reason in result.get('review_reasons',[]))
    rows=''.join('<tr>'+''.join('<td>'+e(value)+'</td>' for value in [r['source_page'],f"{r['output_start']}-{r['output_end']}",r['mode'],r.get('reason') or '; '.join(r.get('exceptions',[]))])+'</tr>' for r in result.get('pages',[]))
    font_rows=''.join('<tr><td>'+e(name)+'</td><td>'+str(count)+'</td></tr>' for name,count in verified.get('measured_fonts_and_sizes',{}).items())
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{e(title)}</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 22px;color:#233044}}h1{{color:{'#176145' if passed else '#9c4812'}}}table{{border-collapse:collapse;width:100%;margin:20px 0}}th,td{{border:1px solid #d7dde4;text-align:left;padding:9px;vertical-align:top}}th{{background:#f0f4f7}}code{{overflow-wrap:anywhere}}a{{color:#1759a2}}</style>
<h1>{e(title)}</h1><p>{e(result['input'])} · Converter {e(result['engine_version'])}</p>
<p>{e(result['source_pages'])} source pages → {e(result['output_pages'])} output pages.</p>
<p><a href="{e(quote(pdf_path.name))}">Open the PDF</a> · <a href="{e(quote(pdf_path.name+'.json'))}">Detailed verification data</a></p>
<p>Target: A4 portrait, Mulish 11pt text, the reference banner/footer, and page margins of top 3cm, bottom 2.55cm, left 1.88cm and right 1.89cm.</p>
<ul>{issues}</ul><p>Measured font/page checks do not certify semantic or visual equivalence for every PDF. Review reflowed tables, diagrams and pagination before publication. Original page references remain as written; source-page bookmarks locate the corresponding output.</p>
<h2>Actual text fonts and sizes</h2><table><tr><th>Font and size</th><th>Text spans</th></tr>{font_rows}</table>
<h2>Page outcomes</h2><table><tr><th>Source page</th><th>Output pages</th><th>Outcome</th><th>Details</th></tr>{rows}</table></html>'''
    temporary=path.with_suffix('.html.tmp');temporary.write_text(body,'utf-8');temporary.replace(path);return path
