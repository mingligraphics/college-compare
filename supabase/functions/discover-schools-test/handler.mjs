export const FIELDS=['school_id','school_name','school_name_cn','short_name','city','city_cn','state','state_cn','region','school_type','undergrad_enrollment','undergrad_enrollment_year','acceptance_rate','admissions_year','coa','coa_year','tuition_fees','tuition_fees_year','international_pct','international_pct_year','international_pct_scope'];
export function createHandler({getEnv,fetchImpl=fetch}){return async request=>{
 const headers={'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin'};
 if(request.headers.get('origin')===(getEnv('ALLOWED_ORIGIN')||'https://mingligraphics.github.io'))Object.assign(headers,{'Access-Control-Allow-Origin':request.headers.get('origin'),'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'content-type'});
 const json=(status,body)=>new Response(JSON.stringify(body),{status,headers});
 if(request.method==='OPTIONS')return new Response(null,{status:204,headers});
 if(request.method!=='POST')return json(405,{error:'Use POST'});
 if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/json')return json(400,{error:'Use application/json'});
 try {const reader=request.body?.getReader();if(!reader)throw Error();let size=0,text='';const decoder=new TextDecoder();
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>1024){await reader.cancel();throw Error()}text+=decoder.decode(value,{stream:true})}}finally{reader.releaseLock()}
 text+=decoder.decode();const body=JSON.parse(text);if(!body||Array.isArray(body)||typeof body!=='object'||Object.keys(body).length)throw Error();
 }catch{return json(400,{error:'Provide an empty JSON object; maximum 1024 bytes'})}
 try {const url=getEnv('SUPABASE_URL'),key=JSON.parse(getEnv('SUPABASE_SECRET_KEYS')||'null')?.default;
 if(!url||typeof key!=='string'||!key.trim())throw Error();
 const response=await fetchImpl(url.replace(/\/$/,'')+'/rest/v1/rpc/get_school_discovery_test_v2',{method:'POST',headers:{'Content-Type':'application/json','Content-Profile':'public',apikey:key},body:'{}',signal:AbortSignal.timeout(10000),redirect:'error'});
 if(!response.ok)throw Error();const rows=await response.json();
 if(!Array.isArray(rows)||!rows.length||rows.length>10000||new Set(rows.map(r=>r.school_id)).size!==rows.length||rows.some(r=>FIELDS.some(f=>!Object.hasOwn(r,f))))throw Error();
 return json(200,rows.map(r=>Object.fromEntries(FIELDS.map(f=>[f,r[f]]))));
 }catch{return json(500,{error:'Directory unavailable'})}
}}
