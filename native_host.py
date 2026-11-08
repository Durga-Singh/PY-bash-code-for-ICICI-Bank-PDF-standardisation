"""Chrome native messaging endpoint. stdout is reserved for binary frames."""
import sys, os, json, struct, threading, contextlib
from url_batch import Engine
from release import VERSION

def validate_client_version(message):
    if message.get('action') in ('start','resume','retry') and message.get('client_version')!=VERSION:
        raise ValueError(f'Extension/converter version mismatch. Converter is {VERSION}. Close the browser, run the installer from the new package and load its extension folder.')

def read_message(stream):
    header=stream.read(4)
    if not header:return None
    if len(header)!=4:raise ValueError('Incomplete message header')
    size=struct.unpack('<I',header)[0]
    if size>16*1024*1024:raise ValueError('Message too large')
    data=bytearray()
    while len(data)<size:
        block=stream.read(size-len(data))
        if not block:raise ValueError('Incomplete message')
        data.extend(block)
    return json.loads(data)
def main():
    if os.name=='nt':
        import msvcrt
        for fd in (sys.stdin.fileno(),sys.stdout.fileno()):msvcrt.setmode(fd,os.O_BINARY)
    incoming=sys.stdin.buffer;outgoing=sys.stdout.buffer;mutex=threading.Lock();engine=Engine();worker=None
    def send(msg):
        data=json.dumps(msg,ensure_ascii=False).encode('utf-8')
        with mutex:outgoing.write(struct.pack('<I',len(data))+data);outgoing.flush()
    def work(ident,retry):
        try:
            with contextlib.redirect_stdout(sys.stderr):engine.run(ident,lambda b:send({'event':'progress','batch':engine.snapshot(b)}),retry)
        except Exception as e:send({'event':'error','error':str(e)})
    while True:
        try:msg=read_message(incoming)
        except Exception:break
        if msg is None:break
        try:
            action=msg.get('action');payload={}
            validate_client_version(msg)
            if action=='list':payload={'batches':engine.listing(),'version':VERSION}
            elif action=='status':payload={'batch':engine.snapshot(engine.load(msg['batch']),max(0,int(msg.get('offset',0))))}
            elif action in ('start','resume','retry'):
                if worker and worker.is_alive():raise ValueError('A batch is already running. Pause it before starting another.')
                b=engine.create(msg['urls']) if action=='start' else engine.load(msg['batch'])
                engine.stop.clear();worker=threading.Thread(target=work,args=(b['id'],action=='retry'),daemon=True);worker.start();payload={'batch':engine.snapshot(b)}
            elif action=='stop':engine.stop.set();payload={'message':'Pausing after the current PDF finishes.'}
            elif action=='report':
                if worker and worker.is_alive():raise ValueError('Pause the batch before refreshing Excel.')
                b=engine.load(msg['batch']);engine.write_report(b);payload={'batch':engine.snapshot(b)}
            elif action=='open':engine.open_item(msg['batch'],msg['kind'],msg.get('index'))
            else:raise ValueError('Unknown command')
            send({'id':msg.get('id'),'ok':True,**payload})
        except Exception as e:send({'id':msg.get('id'),'ok':False,'error':str(e)})
    engine.stop.set()
if __name__=='__main__':main()
