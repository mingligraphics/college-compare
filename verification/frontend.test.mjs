import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const html=fs.readFileSync('dist/index.html','utf8');
test('actual filter logic handles inclusive boundaries, missing values and name search',()=>{
 const values={search:'',region:'',size:'',budget:'',type:''};
 const schools=[4999,5000,15000,15001,null].map((n,i)=>({school_id:String(i),undergrad_enrollment:n,coa:[49999,50000,80000,80001,null][i],school_name:'University '+i,school_name_cn:'大学'+i,short_name:i===0?'ABC':null,region:i===4?null:'east_coast',school_type:i===4?null:'research_university'}));
 const ctx={schools,filtered:[],page:8,present:v=>v!==null&&v!==undefined&&v!=='',type:s=>s.school_type?'综合大学':null,$:id=>({value:values[id]}),render:()=>{}};vm.createContext(ctx);vm.runInContext(html.match(/function apply\(\).*?(?=\nfunction render)/s)[0],ctx);
 const run=(id,value)=>{for(const k in values)values[k]='';values[id]=value;ctx.apply();return Array.from(ctx.filtered,r=>r.school_id)};
 assert.deepEqual(run('size','small'),['0']);assert.deepEqual(run('size','medium'),['1','2']);assert.deepEqual(run('size','large'),['3']);assert.deepEqual(run('size','unknown'),['4']);
 assert.deepEqual(run('budget','low'),['0']);assert.deepEqual(run('budget','mid'),['1','2']);assert.deepEqual(run('budget','high'),['3']);assert.deepEqual(run('budget','unknown'),['4']);assert.deepEqual(run('region','unknown'),['4']);assert.deepEqual(run('type','unknown'),['4']);assert.deepEqual(run('search','abc'),['0']);assert.deepEqual(run('search','大学2'),['2']);assert.equal(ctx.page,1);
});
test('pair transport caches only selected pair and rejects reversed or malformed responses',async()=>{
 let calls=0;const store=new Map();const ctx={fetch:async()=>{calls++;return {ok:true,json:async()=>[{school_id:'nyu'},{school_id:'bu'}]}},AbortSignal,sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},Date,Map};vm.createContext(ctx);vm.runInContext(fs.readFileSync('dist/api.js','utf8')+';this.api=CollegeAPI',ctx);await ctx.api.pair('nyu','bu');await ctx.api.pair('nyu','bu');assert.equal(calls,1);await assert.rejects(()=>ctx.api.pair('bu','nyu'));await assert.rejects(()=>ctx.api.pair('nyu','nyu'));
});
test('published frontend has no embedded profiles or credential markers',()=>{for(const p of ['dist/index.html','dist/existing-comparison.html','dist/api.js'])assert.doesNotMatch(fs.readFileSync(p,'utf8'),/const DATA=|const snapshot=|gpa_scale_definition["']\s*:|SUPABASE_SECRET_KEYS|service_role|sb_secret_|eyJhbGci/)});
