const CollegeAPI = (() => {
 const base='https://hmnoqybdcfwqbjhorwzd.supabase.co/functions/v1/';
 const fields=['school_id','school_name','school_name_cn','short_name','city','city_cn','state','state_cn','region','school_type','undergrad_enrollment','undergrad_enrollment_year','acceptance_rate','admissions_year','coa','coa_year','tuition_fees','tuition_fees_year'];
 const cache=new Map();
 async function request(endpoint,body){
  const response=await fetch(base+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000),cache:'no-store'});
  if(!response.ok)throw new Error('Data unavailable');return response.json();
 }
 return {fields,async directory(){const rows=await request('discover-schools',{});
  if(!Array.isArray(rows)||!rows.length||rows.length>10000||new Set(rows.map(r=>r.school_id)).size!==rows.length||rows.some(r=>fields.some(f=>!Object.hasOwn(r,f))||Object.keys(r).length!==fields.length||typeof r.school_id!=='string'||typeof r.school_name!=='string'))throw new Error('Invalid directory response');return rows;},
 async pair(a,b){if(a===b)throw new Error('Two distinct schools required');const key=a+'|'+b;if(cache.has(key))return cache.get(key);
 let rows;
 try {const saved=JSON.parse(sessionStorage.getItem('cc-selected-pair')||'null');if(saved?.key===key&&Date.now()-saved.time<300000)rows=saved.rows}catch{}
 if(!rows)rows=await request('compare-schools-basic-v2',{schoolA:a,schoolB:b});
 if(!Array.isArray(rows)||rows.length!==2||rows[0]?.school_id!==a||rows[1]?.school_id!==b)throw new Error('Invalid comparison response');cache.clear();cache.set(key,rows);try{sessionStorage.setItem('cc-selected-pair',JSON.stringify({key,time:Date.now(),rows}))}catch{}return rows;}};
})();
