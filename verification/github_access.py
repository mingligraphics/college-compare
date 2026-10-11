import subprocess,urllib.request,json,pathlib
p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True)
v=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
if not v.get('password'):print('GitHub authenticated access unavailable');raise SystemExit(1)
def request(path):
 r=urllib.request.Request('https://api.github.com'+path,headers={'Authorization':'Bearer '+v['password'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(r) as resp:return json.load(resp)
try:
 repo=request('/repos/mingligraphics/college-compare');pages=request('/repos/mingligraphics/college-compare/pages')
 out={'permissions':repo.get('permissions'),'default_branch':repo['default_branch'],'pages':pages}
 pathlib.Path('verification/production-settings.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
except Exception as e:print('GitHub permission check failed:',type(e).__name__);raise SystemExit(1)
