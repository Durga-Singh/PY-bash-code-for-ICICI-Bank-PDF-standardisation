"""Portable XLSX output for the installed application (stdlib only)."""
import zipfile
from xml.sax.saxutils import escape, quoteattr
from pathlib import Path

COLUMNS=[('index','No.'),('url','Requested URL'),('final_url','Downloaded URL'),('download','Download status'),('status','Conversion status'),('original','Original PDF'),('converted','Converted PDF'),('source_pages','Source pages'),('output_pages','Converted pages'),('error','Details'),('font_compliance','Font compliance'),('preserved_pages','Original-font source pages'),('validation_report','Verification report'),('issue_count','Review issues')]
def report(batch, path):
    def col(n):
        s=''
        while n:n,r=divmod(n-1,26);s=chr(65+r)+s
        return s
    rows=[];links=[];rels=[]
    for ri,job in enumerate([dict(COLUMNS)]+batch['jobs'],1):
        cells=[]
        for ci,(key,label) in enumerate(COLUMNS,1):
            ref=f'{col(ci)}{ri}';v=str(job.get(key,''));v=''.join(c for c in v if ord(c)>=32 or c in '\n\t')[:32767]
            st=1 if ri==1 else 2 if key in ('original','converted','validation_report') and v else 0
            cells.append(f'<c r="{ref}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>')
            if ri>1 and key in ('original','converted','validation_report') and v:
                rid=f'rId{len(rels)+1}'
                links.append(f'<hyperlink ref="{ref}" r:id="{rid}"/>')
                rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target={quoteattr(v)} TargetMode="External"/>')
        rows.append(f'<row r="{ri}">'+''.join(cells)+'</row>')
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rn='http://schemas.openxmlformats.org/package/2006/relationships'
    files={
    '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
    '_rels/.rels':f'<Relationships xmlns="{rn}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Conversions" sheetId="1" r:id="rId1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{rn}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
    'xl/styles.xml':f'<styleSheet xmlns="{ns}"><fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><sz val="11"/><u/><color rgb="FF0563C1"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF173C54"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
    'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="8" customWidth="1"/><col min="2" max="3" width="55" customWidth="1"/><col min="4" max="5" width="30" customWidth="1"/><col min="6" max="7" width="48" customWidth="1"/><col min="8" max="9" width="18" customWidth="1"/><col min="10" max="10" width="75" customWidth="1"/></cols><sheetData>'+''.join(rows)+f'</sheetData><autoFilter ref="A1:N{len(rows)}"/>'+('<hyperlinks>'+''.join(links)+'</hyperlinks>' if links else '')+'</worksheet>',
    'xl/worksheets/_rels/sheet1.xml.rels':f'<Relationships xmlns="{rn}">'+''.join(rels)+'</Relationships>'}
    path=Path(path);temp=path.with_suffix('.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for name,body in files.items():z.writestr(name,'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+body)
    temp.replace(path)
