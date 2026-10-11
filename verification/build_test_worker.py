from pathlib import Path
import json,base64
R=Path(__file__).resolve().parents[1];p=R/'separate-test-site/worker/index.js';old=p.read_text();suffix=old[old.index('export default'):];assets={}
for a in (R/'dist').iterdir():
 if a.suffix in ['.html','.js']:assets['/'+a.name]=[a.read_text().replace("const base='https://hmnoqybdcfwqbjhorwzd.supabase.co/functions/v1/';","const base='/api/';"),'text/html; charset=utf-8' if a.suffix=='.html' else 'application/javascript; charset=utf-8']
assets['/wechat-qr.jpeg']=[base64.b64encode((R/'dist/wechat-qr.jpeg').read_bytes()).decode(),'image/jpeg'];p.write_text('const assets='+json.dumps(assets,ensure_ascii=False)+';\n'+suffix)
