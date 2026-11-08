"""Durable URL batches for the browser extension. No browser cookies are read."""
import json, os, re, time, uuid, threading, urllib.request, urllib.parse, contextlib
from pathlib import Path
from converter import convert
from excel_report import report

ROOT=Path.home()/'Documents'/'PDF_URL_Conversions'
SUCCESS='CONVERTED_REVIEW_LAYOUT'
from release import VERSION as CONVERSION_VERSION
def valid_url(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('Use a direct HTTP(S) PDF URL without embedded login credentials.')
    return url
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        valid_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
@contextlib.contextmanager
def lock(path):
    with open(path,'a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)
class Engine:
    def __init__(self,root=ROOT):self.root=Path(root);self.stop=threading.Event()
    def folder(self,ident):
        if not re.fullmatch(r'Batch_[A-Za-z0-9_]+',ident):raise ValueError('Invalid batch identifier')
        return self.root/ident
    def load(self,ident):return json.loads((self.folder(ident)/'batch.json').read_text('utf-8'))
    def save(self,b):
        folder=self.folder(b['id']);tmp=folder/'batch.tmp';tmp.write_text(json.dumps(b,ensure_ascii=False,indent=2),'utf-8');tmp.replace(folder/'batch.json')
    def create(self,urls):
        if not isinstance(urls,list) or not 1<=len(urls)<=20000:raise ValueError('Enter between 1 and 20,000 PDF URLs.')
        ident='Batch_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6];folder=self.folder(ident)
        (folder/'originals').mkdir(parents=True);(folder/'converted').mkdir();(folder/'review').mkdir()
        b={'id':ident,'created':time.strftime('%Y-%m-%d %H:%M:%S'),'jobs':[],'state':'Paused','report_warning':''}
        for i,url in enumerate(urls,1):
            if not isinstance(url,str) or len(url)>2048:raise ValueError('Invalid URL length')
            b['jobs'].append({'index':i,'url':url.strip(),'download':'Pending','status':'Pending','original':'','converted':'','error':''})
        self.save(b);self.write_report(b);return b
    def write_report(self,b):
        try:report(b,self.folder(b['id'])/'conversion_status.xlsx');b['report_warning']=''
        except PermissionError:b['report_warning']='Close conversion_status.xlsx in Excel, then click Refresh Excel.'
        self.save(b)
    def listing(self):
        out=[]
        for p in sorted(self.root.glob('Batch_*/batch.json'),reverse=True):
            try:
                b=json.loads(p.read_text('utf-8'));out.append({'id':b['id'],'state':b['state'],'count':len(b['jobs'])})
            except (OSError,ValueError):continue
        return out[:200]
    def snapshot(self,b,offset=0):
        return {**{k:v for k,v in b.items() if k!='jobs'},'folder':str(self.folder(b['id'])),'total':len(b['jobs']),'finished':sum(j['status'] not in ('Pending','Downloading','Converting') for j in b['jobs']),'converted_count':sum(j['status']==SUCCESS for j in b['jobs']),'partial_count':sum(j['status']=='PARTIAL_REVIEW_REQUIRED' for j in b['jobs']),'offset':offset,'jobs':[{k:v for k,v in j.items() if k!='final_url'} for j in b['jobs'][offset:offset+100]]}
    def run(self,ident,notify=lambda b:None,retry=False):
        folder=self.folder(ident)
        with lock(folder/'batch.lock'):
            b=self.load(ident);b['state']='Running';self.save(b);notify(b)
            try:
                for j in b['jobs']:
                    if self.stop.is_set():break
                    if j['status'] in (SUCCESS,'PARTIAL_REVIEW_REQUIRED') and j.get('conversion_version')==CONVERSION_VERSION and j['converted'] and (folder/j['converted']).exists() and not (retry and j['status']=='PARTIAL_REVIEW_REQUIRED'):continue
                    if j['status']=='Failed' and not retry:continue
                    j['error']=''
                    try:
                        if not j['original'] or not (folder/j['original']).exists():
                            j.update(status='Downloading',download='Downloading');self.save(b);notify(b)
                            valid_url(j['url']);name=urllib.parse.unquote(urllib.parse.urlsplit(j['url']).path.rsplit('/',1)[-1]);name=re.sub(r'[^A-Za-z0-9_.-]+','_',name)[:90].strip('.') or 'document.pdf'
                            if not name.lower().endswith('.pdf'):name+='.pdf'
                            rel=f"originals/{j['index']:05d}_{name}";dest=folder/rel;part=dest.with_suffix('.partial')
                            req=urllib.request.Request(j['url'],headers={'User-Agent':'A4PDFConverter/2.0','Accept':'application/pdf'})
                            try:
                                with urllib.request.build_opener(SafeRedirect()).open(req,timeout=45) as r,open(part,'wb') as f:
                                    j['final_url']=r.url;total=0
                                    while True:
                                        chunk=r.read(1024*1024)
                                        if not chunk:break
                                        total+=len(chunk)
                                        if total>300*1024*1024:raise ValueError('PDF exceeds the 300 MB per-file limit.')
                                        f.write(chunk)
                                with open(part,'rb') as f:
                                    if b'%PDF-' not in f.read(1024):raise ValueError('URL did not return a PDF (possibly a login or HTML page).')
                                part.replace(dest);j.update(original=rel,download='Downloaded')
                            finally:part.unlink(missing_ok=True)
                        j['status']='Converting';self.save(b);notify(b)
                        target='converted/'+Path(j['original']).name;output=folder/target
                        try:
                            result=convert(folder/j['original'],output)
                        except Exception:
                            raise
                        preserved=result.get('preserved_source_pages',[])
                        if result['status']=='PARTIAL_REVIEW_REQUIRED':
                            (folder/'review').mkdir(exist_ok=True)
                            review=folder/'review'/output.name
                            for old,new in ((output,review),(Path(str(output)+'.json'),Path(str(review)+'.json')),(output.with_suffix('.review.html'),review.with_suffix('.review.html'))):
                                if old.exists():old.replace(new)
                            output=review;target=output.relative_to(folder).as_posix()
                        details='; '.join(result.get('review_reasons',[])) or 'A4 portrait and Mulish 11pt measured in saved PDF. Review layout before publication.'
                        if result.get('review_report_warning'):details+=' '+result['review_report_warning']
                        j.update(status=result['status'],conversion_version=CONVERSION_VERSION,converted=target,source_pages=result.get('source_pages',''),output_pages=result.get('output_pages',''),font_compliance=result.get('font_compliance','Review artwork'),preserved_pages=', '.join(map(str,preserved)),validation_report=output.with_suffix('.review.html').relative_to(folder).as_posix() if output.with_suffix('.review.html').exists() else '',issue_count=len(result.get('review_reasons',[])),error=details)
                    except Exception as e:
                        j.update(status='Failed',converted='',error=str(e)[:3000])
                        if j['download']!='Downloaded':j['download']='Failed'
                    self.save(b);notify(b)
                    # Avoid quadratic Excel rewrites for thousands of URLs. JSON is durable per step.
                    if j['index']%10==0:self.write_report(b)
                b['state']='Paused' if self.stop.is_set() else 'Finished'
            finally:
                self.write_report(b);notify(b)
        return b
    def open_item(self,ident,kind,index=None):
        b=self.load(ident);folder=self.folder(ident)
        if kind=='folder':path=folder
        elif kind=='report':path=folder/'conversion_status.xlsx'
        elif kind in ('original','converted','validation_report'):
            job=next(j for j in b['jobs'] if j['index']==index)
            if not job.get(kind):raise ValueError('File is not available')
            path=folder/job[kind]
        else:raise ValueError('Invalid file type')
        if not path.resolve().is_relative_to(folder.resolve()) or not path.exists():raise ValueError('File is not available')
        if os.name!='nt':raise ValueError('Open folder/file is available on Windows.')
        os.startfile(str(path.resolve()))
