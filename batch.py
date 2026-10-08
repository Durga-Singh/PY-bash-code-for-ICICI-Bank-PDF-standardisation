"""Resumable local folder processing and optional watch mode."""
import argparse,csv,hashlib,json,sqlite3,time
from pathlib import Path
from converter import convert

class Runner:
    def __init__(self,output):
        self.output=Path(output).resolve();self.output.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.output/'conversion_history.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source TEXT, status TEXT, output TEXT, detail TEXT, updated TEXT)')
    def process(self,path,retry=False):
        path=Path(path).resolve()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        key=hashlib.sha256((str(path)+digest+'profile-v6-word-11pt-canada-layout-fix').encode()).hexdigest()
        old=self.db.execute('SELECT status,output,detail FROM jobs WHERE id=?',(key,)).fetchone()
        if old and not retry and old[0]=='CONVERTED_REVIEW_LAYOUT' and Path(old[1]).is_file():
            return {'source':str(path),'status':'ALREADY_PROCESSED','detail':old[2],'output':old[1]}
        dest=self.output/(path.stem+'_'+key[:8]+'_A4.pdf')
        try:
            report=convert(path,dest);status=report['status'];detail=f"{report['source_pages']} to {report['output_pages']} pages; {report['tables']} tables; checks passed. Review layout."
            if report.get('exceptions'):detail+=' Original chart lettering retained on source pages 27 and 59.'
        except Exception as e:
            status='NEEDS_REVIEW';detail=f'{type(e).__name__}: {e}'
            for artifact in (dest,Path(str(dest)+'.json')):
                try:artifact.unlink(missing_ok=True)
                except OSError as cleanup_error:detail+=f' | Could not remove incomplete output: {cleanup_error}'
        result={'source':str(path),'status':status,'output':str(dest)if status!='NEEDS_REVIEW' else '', 'detail':detail}
        self.db.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?,?)',(key,str(path),status,result['output'],detail,time.strftime('%Y-%m-%d %H:%M:%S')));self.db.commit()
        self.export();return result
    def export(self):
        try:
            with (self.output/'batch_report.csv').open('w',newline='',encoding='utf-8-sig')as f:
                w=csv.writer(f);w.writerow(['Source','Status','Output','Detail','Updated']);w.writerows(self.db.execute('SELECT source,status,output,detail,updated FROM jobs ORDER BY updated'))
        except PermissionError:pass # Excel may hold the CSV open; history remains in SQLite.
    def close(self):self.db.close()

def inputs(folder,output):
    folder=Path(folder).resolve();output=Path(output).resolve()
    return [p for p in folder.rglob('*')if p.suffix.lower()=='.pdf' and output not in p.resolve().parents]

def main():
    p=argparse.ArgumentParser();p.add_argument('input_folder');p.add_argument('output_folder');p.add_argument('--watch',action='store_true');p.add_argument('--retry',action='store_true');a=p.parse_args()
    if Path(a.input_folder).resolve()==Path(a.output_folder).resolve():p.error('Use a separate output folder.')
    runner=Runner(a.output_folder);observed={};processed={}
    try:
        while True:
            for path in inputs(a.input_folder,a.output_folder):
                stat=path.stat();stamp=(stat.st_size,stat.st_mtime_ns)
                if a.watch and processed.get(path)==stamp:continue
                if a.watch and observed.get(path)!=stamp:observed[path]=stamp;continue
                result=runner.process(path,retry=a.retry and not a.watch);processed[path]=stamp
                if result['status']!='ALREADY_PROCESSED':print(json.dumps(result),flush=True)
            if not a.watch:break
            time.sleep(3)
    except KeyboardInterrupt:pass
    finally:runner.close()
if __name__=='__main__':main()
