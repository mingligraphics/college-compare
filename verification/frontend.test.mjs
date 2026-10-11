import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const html=fs.readFileSync('dist/index.html','utf8');
test('four filters use tuition rather than COA, exact boundaries and undergraduate scope',()=>{
 const values={search:'',region:'',size:'',tuition:'',international:''};
 const schools=[4999,5000,15000,15001,null].map((n,i)=>({school_id:String(i),undergrad_enrollment:n,tuition_fees:[200000/7-1,200000/7,50000,500000/7,null][i],coa:999999,international_pct:[4.99,5,10,20,null][i],international_pct_scope:'undergraduate',school_name:'University '+i,school_name_cn:'大学'+i,short_name:i===0?'ABC':null,region:i===4?null:'east_coast'}));
 schools.push({...schools[0],school_id:'all',international_pct_scope:'all_students'});
 const ctx={schools,filtered:[],page:8,present:v=>v!==null&&v!==undefined&&v!=='',$:id=>({value:values[id]}),render:()=>{}};vm.createContext(ctx);vm.runInContext(html.match(/const USD_CNY_RATE.*?(?=\nfunction fitCardNames)/s)[0],ctx);
 const run=(id,value)=>{for(const k in values)values[k]='';values[id]=value;ctx.apply();return Array.from(ctx.filtered,r=>r.school_id)};
 assert.deepEqual(run('size','medium'),['1','2']);assert.deepEqual(run('size','large'),['3']);
 for(const [key,id] of [['low','0'],['mid','1'],['high','2'],['top','3']]){assert.deepEqual(run('international',key),[id]);assert(run('tuition',key).includes(id));}
 assert.equal(run('tuition','').length,6);assert(!run('tuition','top').includes('4'));assert.deepEqual(run('search','abc'),['0','all']);assert.deepEqual(run('search','大学2'),['2']);assert.equal(ctx.page,1);
 const labels=[...html.matchAll(/<label>([^<]+)<select/g)].map(m=>m[1]);assert.deepEqual(labels,['地理位置','每年学杂费（人民币）','本科生规模','国际生比例']);assert.doesNotMatch(html,/<option[^>]*>暂无数据|new Option\('暂无数据'/);
});
test('pair transport caches only selected pair and rejects reversed or malformed responses',async()=>{
 let calls=0;const store=new Map();const ctx={fetch:async()=>{calls++;return {ok:true,json:async()=>[{school_id:'nyu'},{school_id:'bu'}]}},AbortSignal,sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},Date,Map};vm.createContext(ctx);vm.runInContext(fs.readFileSync('dist/api.js','utf8')+';this.api=CollegeAPI',ctx);await ctx.api.pair('nyu','bu');await ctx.api.pair('nyu','bu');assert.equal(calls,1);await assert.rejects(()=>ctx.api.pair('bu','nyu'));await assert.rejects(()=>ctx.api.pair('nyu','nyu'));
});
test('published frontend has no embedded profiles or credential markers',()=>{for(const p of ['dist/index.html','dist/existing-comparison.html','dist/api.js'])assert.doesNotMatch(fs.readFileSync(p,'utf8'),/const DATA=|const snapshot=|gpa_scale_definition["']\s*:|SUPABASE_SECRET_KEYS|service_role|sb_secret_|eyJhbGci/)});
test('test cards show full abbreviations, actual control, sourced category ranks and comparison hides year rows',()=>{
 assert(!html.includes('.slice(0,5)'));assert(html.includes('control-badge'));assert(!html.includes('年度总费用 · COA'));assert(!html.includes('把选择放在一起看'));
 const source=html.match(/const control=.*?(?=\nfunction)/s)[0];const ctx={present:v=>v!==null&&v!==undefined&&v!==''};vm.createContext(ctx);vm.runInContext(source+'\n;this.c=control;this.r=ranking',ctx);
 assert.equal(ctx.c({institution_control:'public'}),'公立');assert.equal(ctx.c({institution_control:'private_nonprofit'}),'私立');assert.equal(ctx.c({institution_control:null}),'暂无数据');
 assert.equal(ctx.r({ranking_usnews:2,ranking_category:'national_liberal_arts_college'}),'U.S. News · 全美文理学院 #2');assert.equal(ctx.r({ranking_usnews:null}),'U.S. News · 暂无数据');assert.equal(ctx.r({ranking_usnews:2,ranking_category:'unknown'}),'U.S. News · 暂无数据');
 const comparison=html.match(/function showComparison.*?(?=\n\[)/s)[0];assert(!/admissions_year|coa_year|tuition_fees_year|international_pct_year|undergrad_enrollment_year/.test(comparison));assert(comparison.indexOf("['地理位置'")<comparison.indexOf("['大学排名"));
 const full=fs.readFileSync('dist/existing-comparison.html','utf8').match(/function comparisonDetail.*?(?=\nfunction fillSelectors)/s)[0];assert(!/\.years|Year|年份|学年/.test(full));assert(full.includes('大学排名（U.S. News）'));
});
test('RMB conversion has exclusive boundaries, preserves zero and rejects missing or invalid fees',()=>{
 const ctx={present:v=>v!==null&&v!==undefined&&v!==''};vm.createContext(ctx);vm.runInContext(html.match(/const USD_CNY_RATE.*?(?=\nfunction internationalValue)/s)[0],ctx);
 for(const value of [null,undefined,'',' ',false,-1,NaN,Infinity,'invalid'])assert.equal(ctx.tuitionRmb(value),null);
 assert.equal(ctx.tuitionRmb(0),0);assert.equal(ctx.tuitionRmb('30000'),210000);
 const values={search:'',region:'',size:'',tuition:'',international:''};Object.assign(ctx,{$:id=>({value:values[id]}),render(){},schools:[],filtered:[]});vm.runInContext(html.match(/function internationalValue.*?(?=\nfunction fitCardNames)/s)[0],ctx);
 for(const [threshold,lower,upper] of [[200000,'low','mid'],[350000,'mid','high'],[500000,'high','top']])for(const delta of [-.01,0,.01]){
 ctx.schools=[{school_name:'Boundary',tuition_fees:(threshold+delta)/7}];let matches=[];for(const band of ['low','mid','high','top']){values.tuition=band;ctx.apply();if(ctx.filtered.length)matches.push(band)}assert.deepEqual(matches,[delta<0?lower:upper]);
 }
});
test('abbreviation badges preserve missing-name behavior and escape source text',()=>{
 const ctx={esc:s=>String(s).replace(/</g,'&lt;').replace(/>/g,'&gt;')};vm.createContext(ctx);vm.runInContext(html.match(/function abbreviationBadge.*?(?=\nfunction render)/s)[0],ctx);
 for(const short_name of [null,undefined,'','  ','中文全称','中文 MIT','123'])assert.equal(ctx.abbreviationBadge({short_name}),'');
 assert(ctx.abbreviationBadge({short_name:' MIT '}).includes('>MIT</span>'));assert(!ctx.abbreviationBadge({short_name:'<img src=x>'}).includes('<img'));
});
test('discovery ranks sort numerically, missing last and ties deterministically',()=>{
 const ctx={present:v=>v!==null&&v!==undefined&&v!==''};vm.createContext(ctx);vm.runInContext(html.match(/function rankingNumber.*?(?=\nfunction internationalValue)/s)[0],ctx);
 const rows=[{school_id:'x',ranking_usnews:'100'},{school_id:'z',school_name:'Alpha',ranking_category:'national_university',ranking_usnews:'2'},{school_id:'a',school_name:'Alpha',ranking_category:'national_university',ranking_usnews:2},{school_id:'c',ranking_category:'national_liberal_arts_college',ranking_usnews:2},{school_id:'t',ranking_usnews:'10'},{school_id:'u',ranking_usnews:null},{school_id:'one',ranking_usnews:1}];
 const expected=['a','z','c','one','t','x','u'];assert.deepEqual([...rows].sort(ctx.compareSchoolRank).map(s=>s.school_id),expected);assert.deepEqual([...rows].reverse().sort(ctx.compareSchoolRank).map(s=>s.school_id),expected);
 for(const v of [null,undefined,'',' ',false,0,-1,'unranked','10x',Infinity])assert.equal(ctx.rankingNumber({ranking_usnews:v}),Infinity);
 assert(html.includes('}).sort(compareSchoolRank);render()'));assert(html.includes('summaryRanking(s)'));assert(!html.includes('<h2>U.S. News 2027'));assert(html.includes('固定估算：1 USD≈7 CNY（非实时）'));
});
