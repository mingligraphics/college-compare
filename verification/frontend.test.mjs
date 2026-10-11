import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const html=fs.readFileSync('dist/index.html','utf8');
test('four filters use tuition rather than COA, exact boundaries and undergraduate scope',()=>{
 const values={search:'',region:'',size:'',tuition:'',international:''};
 const schools=[4999,5000,15000,15001,null].map((n,i)=>({school_id:String(i),undergrad_enrollment:n,tuition_fees:[29999,30000,50000,70000,null][i],coa:999999,international_pct:[4.99,5,10,20,null][i],international_pct_scope:'undergraduate',school_name:'University '+i,school_name_cn:'大学'+i,short_name:i===0?'ABC':null,region:i===4?null:'east_coast'}));
 schools.push({...schools[0],school_id:'all',international_pct_scope:'all_students'});
 const ctx={schools,filtered:[],page:8,present:v=>v!==null&&v!==undefined&&v!=='',$:id=>({value:values[id]}),render:()=>{}};vm.createContext(ctx);vm.runInContext(html.match(/function internationalValue.*?(?=\nfunction fitCardNames)/s)[0],ctx);
 const run=(id,value)=>{for(const k in values)values[k]='';values[id]=value;ctx.apply();return Array.from(ctx.filtered,r=>r.school_id)};
 assert.deepEqual(run('size','medium'),['1','2']);assert.deepEqual(run('size','large'),['3']);
 for(const [key,id] of [['low','0'],['mid','1'],['high','2'],['top','3']]){assert.deepEqual(run('international',key),[id]);assert(run('tuition',key).includes(id));}
 assert.equal(run('tuition','').length,6);assert(!run('tuition','top').includes('4'));assert.deepEqual(run('search','abc'),['0','all']);assert.deepEqual(run('search','大学2'),['2']);assert.equal(ctx.page,1);
 const labels=[...html.matchAll(/<label>([^<]+)<select/g)].map(m=>m[1]);assert.deepEqual(labels,['地理位置','每年学费','本科生规模','国际生比例']);assert.doesNotMatch(html,/<option[^>]*>暂无数据|new Option\('暂无数据'/);
});
test('pair transport caches only selected pair and rejects reversed or malformed responses',async()=>{
 let calls=0;const store=new Map();const ctx={fetch:async()=>{calls++;return {ok:true,json:async()=>[{school_id:'nyu'},{school_id:'bu'}]}},AbortSignal,sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},Date,Map};vm.createContext(ctx);vm.runInContext(fs.readFileSync('dist/api.js','utf8')+';this.api=CollegeAPI',ctx);await ctx.api.pair('nyu','bu');await ctx.api.pair('nyu','bu');assert.equal(calls,1);await assert.rejects(()=>ctx.api.pair('bu','nyu'));await assert.rejects(()=>ctx.api.pair('nyu','nyu'));
});
test('published frontend has no embedded profiles or credential markers',()=>{for(const p of ['dist/index.html','dist/existing-comparison.html','dist/api.js'])assert.doesNotMatch(fs.readFileSync(p,'utf8'),/const DATA=|const snapshot=|gpa_scale_definition["']\s*:|SUPABASE_SECRET_KEYS|service_role|sb_secret_|eyJhbGci/)});
test('test cards show full abbreviations, actual control, sourced category ranks and comparison hides year rows',()=>{
 assert(!html.includes('.slice(0,5)'));assert(html.includes('control-badge'));assert(!html.includes('年度总费用 · COA'));assert(!html.includes('把选择放在一起看'));
 const source=html.match(/const control=.*?(?=\nfunction)/s)[0];const ctx={present:v=>v!==null&&v!==undefined&&v!==''};vm.createContext(ctx);vm.runInContext(source+';this.c=control;this.r=ranking',ctx);
 assert.equal(ctx.c({institution_control:'public'}),'公立');assert.equal(ctx.c({institution_control:'private_nonprofit'}),'私立');assert.equal(ctx.c({institution_control:null}),'暂无数据');
 assert.equal(ctx.r({ranking_usnews:2,ranking_category:'national_liberal_arts_college'}),'U.S. News · 全美文理学院 #2');assert.equal(ctx.r({ranking_usnews:null}),'U.S. News · 暂无数据');assert.equal(ctx.r({ranking_usnews:2,ranking_category:'unknown'}),'U.S. News · 暂无数据');
 const comparison=html.match(/function showComparison.*?(?=\n\[)/s)[0];assert(!/admissions_year|coa_year|tuition_fees_year|international_pct_year|undergrad_enrollment_year/.test(comparison));assert(comparison.indexOf("['地理位置'")<comparison.indexOf("['大学排名"));
 const full=fs.readFileSync('dist/existing-comparison.html','utf8').match(/function comparisonDetail.*?(?=\nfunction fillSelectors)/s)[0];assert(!/\.years|Year|年份|学年/.test(full));assert(full.includes('大学排名（U.S. News）'));
});
