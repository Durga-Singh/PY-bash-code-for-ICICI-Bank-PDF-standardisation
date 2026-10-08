"""Windows/macOS/Linux Tk desktop uploader; processing stays on this computer."""
import os,sys,threading,queue,time,subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from batch import Runner,inputs

class App:
    def __init__(self,root):
        self.root=root;root.title('A4 PDF Converter v1.4 | Layout fix + Canada PDFs');root.geometry('940x580')
        self.jobs=queue.Queue();self.events=queue.Queue();self.pending=set();self.stop=threading.Event();self.watch_folder=None;self.observed={}
        self.output=tk.StringVar(value=str(Path.home()/'Documents'/'Converted_PDFs'))
        ttk.Label(root,text='A4 PDF Converter',font=('Segoe UI',20,'bold')).pack(anchor='w',padx=20,pady=(18,5))
        ttk.Label(root,text='Mulish 11pt (Word size 11)  •  3cm TOP page margin  •  Reference banner + Page x | y footer').pack(anchor='w',padx=20)
        ttk.Label(root,text='Text and tables reflow. Unsupported PDFs go to NEEDS_REVIEW; originals stay unchanged.').pack(anchor='w',padx=20,pady=(4,16))
        row=ttk.Frame(root);row.pack(fill='x',padx=20)
        ttk.Label(row,text='Output folder:').pack(side='left');ttk.Entry(row,textvariable=self.output).pack(side='left',expand=True,fill='x',padx=8);ttk.Button(row,text='Browse',command=self.choose_output).pack(side='left')
        buttons=ttk.Frame(root);buttons.pack(fill='x',padx=20,pady=14)
        for title,fn in [('Add PDFs & convert',self.add_files),('Add folder',self.add_folder),('Watch folder',self.watch),('Stop watching',self.unwatch),('Open output',self.open_output)]:ttk.Button(buttons,text=title,command=fn).pack(side='left',padx=(0,8))
        self.status=tk.StringVar(value='Choose PDFs to start automatically. You can add more while the queue runs.')
        ttk.Label(root,textvariable=self.status).pack(anchor='w',padx=20,pady=(0,8))
        frame=ttk.Frame(root);frame.pack(fill='both',expand=True,padx=20,pady=(0,15))
        self.log=tk.Text(frame,wrap='word',state='disabled',font=('Consolas',10));self.log.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,command=self.log.yview);scroll.pack(side='right',fill='y');self.log.configure(yscrollcommand=scroll.set)
        ttk.Label(root,text='Results: PDF + validation JSON + batch_report.csv. Check the sample before using a new document layout.').pack(anchor='w',padx=20,pady=(0,14))
        threading.Thread(target=self.worker,daemon=True).start();self.root.after(200,self.poll);self.root.protocol('WM_DELETE_WINDOW',self.close)
    def choose_output(self):
        p=filedialog.askdirectory()
        if p:self.output.set(p)
    def enqueue(self,paths):
        output=str(Path(self.output.get()).resolve());count=0
        for p in paths:
            p=str(Path(p).resolve());key=(p,output)
            if key not in self.pending:self.pending.add(key);self.jobs.put(key);count+=1
        self.status.set(f'Queued {count} PDF(s). Processing automatically...')
    def add_files(self):self.enqueue(filedialog.askopenfilenames(filetypes=[('PDF documents','*.pdf')]))
    def add_folder(self):
        p=filedialog.askdirectory()
        if p:
            if Path(p).resolve()==Path(self.output.get()).resolve():messagebox.showerror('Separate folders','Choose a different output folder.');return
            self.enqueue(inputs(p,self.output.get()))
    def watch(self):
        p=filedialog.askdirectory()
        if p:
            if Path(p).resolve()==Path(self.output.get()).resolve():messagebox.showerror('Separate folders','Choose a different output folder.');return
            self.watch_folder=p;self.observed={};self.status.set('Watching '+p+' — new stable PDFs convert automatically.')
    def unwatch(self):self.watch_folder=None;self.status.set('Watching stopped. Already queued files will finish.')
    def open_output(self):
        p=Path(self.output.get());p.mkdir(parents=True,exist_ok=True)
        if sys.platform=='win32':os.startfile(str(p))
        else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(p)])
    def worker(self):
        runners={}
        while not self.stop.is_set():
            try:key=self.jobs.get(timeout=.5)
            except queue.Empty:continue
            path,out=key;self.events.put(('start',key,None))
            try:
                if out not in runners:runners[out]=Runner(out)
                result=runners[out].process(path);self.events.put(('done',key,result))
            except Exception as e:self.events.put(('done',key,{'status':'NEEDS_REVIEW','detail':str(e)}))
            self.jobs.task_done()
        for r in runners.values():r.close()
    def poll(self):
        while True:
            try:kind,key,result=self.events.get_nowait()
            except queue.Empty:break
            if kind=='start':self.status.set('Converting '+Path(key[0]).name)
            else:
                self.pending.discard(key);self.log.configure(state='normal');self.log.insert('end',f"{Path(key[0]).name}: {result['status']}\n{result['detail']}\n\n");self.log.see('end');self.log.configure(state='disabled')
                self.status.set(f'{len(self.pending)} remaining.' if self.pending else 'Queue complete. Check batch_report.csv and review the converted layouts.')
        if self.watch_folder:
            try:
                for p in inputs(self.watch_folder,self.output.get()):
                    st=p.stat();stamp=(st.st_size,st.st_mtime_ns);old=self.observed.get(p)
                    if old and old[0]==stamp and old[1]!=True and time.monotonic()-old[1]>3:
                        self.enqueue([p]);self.observed[p]=(stamp,True)
                    elif not old or old[0]!=stamp:self.observed[p]=(stamp,time.monotonic())
            except OSError as e:self.status.set('Folder access error: '+str(e))
        self.root.after(500,self.poll)
    def close(self):
        if self.pending and not messagebox.askyesno('Conversion in progress','Exit now? Completed jobs are saved. Re-add the folder next time to resume unfinished files.'):return
        self.stop.set();self.root.destroy()
if __name__=='__main__':App(tk.Tk());tk.mainloop()
