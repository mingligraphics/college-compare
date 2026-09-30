import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler, BASIC_V2_FIELDS } from './handler.mjs';
test('v2 exposes approved program metadata and GPA, preserves nulls, hides other columns', async()=>{
 const rows=['duke','uci'].map(school_id=>({...Object.fromEntries(BASIC_V2_FIELDS.map(f=>[f,null])),school_id,private_evidence:'hidden'}));
 rows[0].signature_programs=[{program_key:'synthetic',name_en:'Synthetic',name_cn:'测试',selection_basis:'relative_strength'}];
 rows[1].gpa_unweighted_25=3.8;rows[1].gpa_population='admitted_first_year';
 const env={SUPABASE_URL:'https://example.invalid',SUPABASE_SECRET_KEYS:'{"default":"test"}'};
 const handler=createHandler({getEnv:n=>env[n],fetchImpl:async(url)=>{
  assert(url.endsWith('/get_school_comparison_basic_v2'));return Response.json(rows);
 }});
 const res=await handler(new Request('http://localhost',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({schoolA:'duke',schoolB:'uci'})}));
 assert.equal(res.status,200);const data=await res.json();
 assert.equal(data[0].gpa_unweighted_25,null);assert.equal(data[1].gpa_unweighted_25,3.8);
 assert.deepEqual(data[0].signature_programs,rows[0].signature_programs);
 assert(!Object.hasOwn(data[0],'private_evidence'));
});
