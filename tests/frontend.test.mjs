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
 for(const value of ['$58,484','29,471','33,122','25.55%','公立大学','私立非营利大学','美国西海岸','学费及必缴费用','暂无数据'])assert(t.els.cards.innerHTML.includes(value),value);
 assert(!t.els.cards.innerHTML.includes('research_university'));
 assert(!t.els.cards.innerHTML.includes('east_coast'));
 assert.equal(t.els.result.style.display,'block');
 const unknown=t.run('normalize({tuition_fees:null,coa:null,international_pct:null})');assert.equal(unknown.tuition,null);assert.equal(unknown.coa,null);assert.equal(unknown.internationalPct,'');
 assert.equal(t.run('normalize({tuition_fees:0,international_pct:0}).tuition'),0);
 assert.equal(t.run('normalize({international_pct:0}).internationalPct'),'0%');
});
test('search, duplicate selection and empty selection do not send requests',async()=>{
 const t=await setup();for(const [query,n] of [['NYU',1],['纽约',1],['Berkeley',1],['zzzzz',0],['',3]]){t.els.schoolSearch.value=query;t.run('drawSchoolList()');assert.equal(t.els.schoolList.children.length,n);}
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
