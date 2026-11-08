import sys, json, hashlib, base64
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HOST='com.local.a4_pdf_converter'
def main():
    import winreg
    manifest=json.loads((ROOT/'extension'/'manifest.json').read_text())
    digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
    ident=''.join(chr(97+int(c,16)) for c in digest)
    launcher=ROOT/'native_host_windows.bat'
    launcher.write_text('@echo off\r\n"'+sys.executable+'" "'+str(ROOT/'native_host.py')+'" %*\r\n',encoding='utf-8')
    target=ROOT/'native_host_manifest.json'
    target.write_text(json.dumps({'name':HOST,'description':'Local PDF batch converter','path':str(launcher),'type':'stdio','allowed_origins':[f'chrome-extension://{ident}/']},indent=2))
    for browser in ('Google\\Chrome','BraveSoftware\\Brave-Browser'):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Software\\'+browser+'\\NativeMessagingHosts\\'+HOST) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(target))
    print('Installed for this Windows user. Extension ID:',ident)
    print('In Chrome/Brave extensions: enable Developer mode, Load unpacked, select:',ROOT/'extension')
if __name__=='__main__':main()
