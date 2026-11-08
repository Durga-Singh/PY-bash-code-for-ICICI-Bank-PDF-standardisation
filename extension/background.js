let port, sequence=0; const pending=new Map();
chrome.action.onClicked.addListener(()=>chrome.tabs.create({url:chrome.runtime.getURL('index.html')}));
function connect(){
 if(port)return;
 port=chrome.runtime.connectNative('com.local.a4_pdf_converter');
 port.onMessage.addListener(m=>{
  if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
  if(m.event)chrome.runtime.sendMessage({nativeEvent:m}).catch(()=>{});
 });
 port.onDisconnect.addListener(()=>{
  const error=chrome.runtime.lastError?.message||'Local converter disconnected. Reconnect and resume your batch.';
  port=null;for(const resolve of pending.values())resolve({ok:false,error});pending.clear();
  chrome.runtime.sendMessage({nativeEvent:{event:'error',error}}).catch(()=>{});
 });
}
chrome.runtime.onMessage.addListener((m,sender,reply)=>{
 if(!m.command||sender.id!==chrome.runtime.id||!sender.url?.startsWith(chrome.runtime.getURL('')))return;
 try{connect();const id=++sequence;pending.set(id,reply);port.postMessage({...m.command,id});}
 catch(e){reply({ok:false,error:e.message});}
 return true;
});
