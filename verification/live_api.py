import urllib.request,urllib.error,json,pathlib
R=pathlib.Path('verification');base='https://hmnoqybdcfwqbjhorwzd.supabase.co/functions/v1/'
def call(endpoint,body):
 req=urllib.request.Request(base+endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':'https://mingligraphics.github.io'})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r),r.headers.get('Access-Control-Allow-Origin')
 except urllib.error.HTTPError as e:return e.code,json.load(e),None
fields=['school_id','school_name','school_name_cn','short_name','city','city_cn','state','state_cn','region','school_type','undergrad_enrollment','undergrad_enrollment_year','acceptance_rate','admissions_year','coa','coa_year','tuition_fees','tuition_fees_year']
status,rows,cors=call('discover-schools',{});assert status==200 and len(rows)==299 and all(set(r)==set(fields) for r in rows);assert cors=='https://mingligraphics.github.io'
byid={r['school_id']:r for r in rows};tests=[]
for a,b in [('nyu','bu'),('bu','nyu'),('us_164465','us_164580')]:
 status,pair,_=call('compare-schools-basic-v2',{'schoolA':a,'schoolB':b});assert status==200 and [r['school_id'] for r in pair]==[a,b];assert all(len(r)==57 for r in pair);assert all(all(r[f]==byid[r['school_id']][f] for f in fields) for r in pair);tests.append({'pair':[a,b],'status':status,'fields':57,'directory_match':True})
for body in [{'schoolA':'nyu','schoolB':'nyu'},{'schoolA':'nyu','schoolB':'not_a_school'}]:
 status,_,_=call('compare-schools-basic-v2',body);assert status in [400,404];tests.append({'invalid_request_status':status})
assert call('discover-schools',{'fields':'all'})[0]==400
result={'directory_count':len(rows),'fields':fields,'cors':cors,'tests':tests};(R/'live-api-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
