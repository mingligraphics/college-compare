import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const csv=readFileSync(new URL('../school.csv',import.meta.url),'utf8');
class El {
 constructor(){this.value='';this.textContent='开始比较';this.style={};this.handlers={};this.children=[];this.classList={add(){},remove(){}};}
 set innerHTML(v){this.html=v;this.children=[];} get innerHTML(){return this.html;}
 addEventListener(k,f){this.handlers[k]=f;} append(...v){this.children.push(...v);} appendChild(v){this.children.push(v);} focus(){} scrollIntoView(){}
}
async function setup(){
 const els={},timers=new Map();let tid=0,calls=0,reply=async()=>({ok:true,json:async()=>[]});
 const context=vm.createContext({document:{getElementById:id=>els[id]??=new El(),createElement:()=>new El(),body:new El(),addEventListener(){}},console,AbortController,
 setTimeout:(f,t)=>{if(t===50){f();return 0;}timers.set(++tid,f);return tid;},clearTimeout:id=>timers.delete(id),fetch:async(url,options)=>{
 if(url.startsWith('./school.csv'))return {ok:true,text:async()=>csv};
 assert.match(url,/\/compare-schools-basic-v1$/);calls++;return reply(options);
 }});
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);await new Promise(setImmediate);
 const run=s=>vm.runInContext(s,context);
 return {els,timers,run,setReply:f=>reply=f,calls:()=>calls,choose:(a,b)=>run(`openPicker('a');selectSchoolFromPicker('${a}');openPicker('b');selectSchoolFromPicker('${b}')`)};
}
const rows=[{school_id:'nyu',school_name_cn:'纽约大学',institution_control:'private_nonprofit',school_type:'research_university',region:'east_coast',city_cn:'纽约',tuition_fees:68576,tuition_fees_year:'2026-27',coa:100998,coa_year:'2026-27',undergrad_enrollment:29471,first_year_enrollment:5662,international_pct:25.55},
 {school_id:'ucb',school_name_cn:'加州大学伯克利分校',institution_control:'public',school_type:'research_university',region:'west_coast',city_cn:'伯克利',tuition_fees:58484,tuition_fees_year:'2026-27',coa:93944,coa_year:'2026-27',undergrad_enrollment:33122,first_year_enrollment:6687,international_pct:9.82}];
test('Basic v1 uses fees, correct control labels, derived regions, undergraduate counts and NULLs',async()=>{
 const t=await setup();t.choose('nyu','ucb');t.setReply(async()=>({ok:true,json:async()=>rows}));await t.els.go.handlers.click();
 for(const value of ['40.9万元','29471','33122','25.6%','美国西海岸','学费及必缴费用','暂无数据'])assert(t.els.cards.innerHTML.includes(value),value);
 assert(!t.els.cards.innerHTML.includes('research_university'));
 assert(!t.els.cards.innerHTML.includes('east_coast'));
 assert.equal(t.els.result.style.display,'block');
 const unknown=t.run('normalize({tuition_fees:null,coa:null,international_pct:null})');assert.equal(unknown.tuition,null);assert.equal(unknown.coa,null);assert.equal(unknown.internationalPct,'');
 assert.equal(t.run('normalize({tuition_fees:0,international_pct:0}).tuition'),0);
 assert.equal(t.run('normalize({international_pct:0}).internationalPct'),'0.0%');
});
test('search, duplicate selection and empty selection do not send requests',async()=>{
 const t=await setup();for(const [query,n] of [['NYU',1],['纽约',1],['Berkeley',1],['MIT',1],['斯坦福',1],['UCLA',1],['USC',1],['zzzzz',0],['',10]]){t.els.schoolSearch.value=query;t.run('drawSchoolList()');assert.equal(t.els.schoolList.children.length,n);}
 assert.equal(t.run('Object.keys(schools).length'),13);
 await t.els.go.handlers.click();t.choose('nyu','nyu');await t.els.go.handlers.click();assert.equal(t.calls(),0);
});
test('loading restores on success, HTTP/network/JSON errors and malformed pairs',async()=>{
 const t=await setup();t.choose('nyu','ucb');
 for(const [name,f] of [['ok',async()=>({ok:true,json:async()=>rows})],['http',async()=>({ok:false})],['network',async()=>{throw Error();}],['json',async()=>({ok:true,json:async()=>{throw Error();}})],['partial',async()=>({ok:true,json:async()=>[rows[0]]})],['order',async()=>({ok:true,json:async()=>[...rows].reverse()})]]){
 t.setReply(f);const request=t.els.go.handlers.click();assert.equal(t.els.go.textContent,'正在比较…');assert.equal(t.els.go.disabled,true);await request;assert.equal(t.els.go.textContent,'开始比较');assert.equal(t.els.go.disabled,false);assert.equal(t.els.result.style.display,name==='ok'?'block':'none');}
});
test('timeout, repeated clicks and changed selections cannot leave stale results',async()=>{
 const t=await setup();t.choose('nyu','ucb');let release;t.setReply(()=>new Promise(r=>release=r));const request=t.els.go.handlers.click();await t.els.go.handlers.click();assert.equal(t.calls(),1);t.choose('bu','ucb');release({ok:true,json:async()=>rows});await request;assert.equal(t.els.result.style.display,'none');assert.equal(t.els.go.textContent,'开始比较');
 t.setReply(o=>new Promise((resolve,reject)=>o.signal.addEventListener('abort',()=>reject(Error()))));const timeout=t.els.go.handlers.click();for(const f of t.timers.values())f();await timeout;assert.equal(t.els.go.disabled,false);assert.equal(t.els.go.textContent,'开始比较');
});
const published=JSON.parse(readFileSync(new URL('./fixtures/comparison-basic-v1.json',import.meta.url),'utf8'));
for(const [a,b] of [['mit','stanford'],['usc','ucla'],['harvard','princeton']]){
 test(`Comparison v1 published pair ${a}/${b}`,async()=>{
  const t=await setup(), pair=[a,b].map(id=>published.find(r=>r.school_id===id));
  const before=JSON.stringify(pair);
  t.choose(a,b);t.setReply(async()=>({ok:true,json:async()=>pair}));await t.els.go.handlers.click();
  const detail=t.els.cards.innerHTML,summary=t.els.summaryText.innerHTML;
  assert.equal(JSON.stringify(pair),before);
  assert.equal(t.els.schoolCount.textContent,'13所美国高校官方数据');
  assert(!detail.includes('detail-section-title'));
  assert(!detail.includes('学校性质'));
  assert(!/COA|Need-based|Merit Aid|择优|按需|万元人民币|有限提供/.test(detail));
  assert(detail.includes('metric-title">排名</h3>'));
  assert(!summary.includes('本科生'));
  assert(!html.includes('一眼看懂学校'));
  assert(!/美元|\$|排名|万元|COA/.test(summary));
  assert(!/校园特点|职业特色|知名校友|明星专业|优势专业|national_university|test_optional|test_free|>0万元/.test(detail));
  for(const r of pair){
   assert(summary.includes(`${(Math.round(r.acceptance_rate*10)/10).toFixed(1)}%`));
   assert(summary.includes(`${(Math.round(r.international_pct*10)/10).toFixed(1)}%`));
   assert(![...summary.matchAll(/class="profile-meta">([^<]+)/g)].some(m=>m[1].includes(r.city_cn)));
   assert(summary.includes(t.run(`normalize(${JSON.stringify(r)}).region`)));
   assert(detail.includes(`全美综合大学 #${r.ranking_usnews}`));
   assert(detail.includes(`${r.ranking_year} 版`));
   assert(detail.includes(`${r.graduation_rate_4yr}%`));
   assert(detail.includes((r.tuition_fees*7/10000).toFixed(1)+'万元'));
  }
  const coa=detail.match(/<section class="metric"><h3 class="metric-title">总就读成本[\s\S]*?<\/section>/)[0];
  assert(!/metric-sub|学年|高约|美元|\$|20\d\d/.test(coa));
 });
}
test('Display preserves blanks, zeroes, partial ranges and escapes source text',async()=>{
 const t=await setup();
 assert.equal(t.run('moneyRmbWan(510)'),'3,570元');
 assert.equal(t.run('aidText("limited")'),'资助机会有限');
 assert.equal(t.run('normalize({institution_control:"private_nonprofit"}).schoolType'),'私立大学');
 assert.equal(t.run('locationText(normalize({state_cn:"加州",city_cn:"伯克利"}))'),'加州伯克利');
 assert.equal(t.run('percent(0)'),'0%');
 assert.equal(t.run('scoreRange(null,1500)'),'');
 assert.equal(t.run('enrollmentText(normalize({undergrad_enrollment:null,first_year_enrollment:500}))'),'');
 const detail=t.run('comparisonDetail(normalize({}),normalize({}))');
 assert(!detail.includes('#0'));assert(detail.includes('暂无数据'));
 const s=t.run('summary(normalize({school_name_cn:"<img src=x>"}),normalize({}))');
 assert(!s.includes('<img'));assert(s.includes('&lt;img'));
});
