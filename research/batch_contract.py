"""Explicit batch contract. The original pilot entry points keep their defaults."""
import hashlib,json
from pathlib import Path
from school_publish import COLUMNS,validate_rows,records
from sources import require
IDS=('harvard','stanford','mit','princeton','yale','columbia','penn','uchicago','ucla','usc')
RESEARCH_IDS=('US-166027','US-243744','US-166683','US-186131','US-130794','US-190150','US-215062','US-144050','US-110662','US-123961')
NAMES=('Harvard University','Stanford University','Massachusetts Institute of Technology','Princeton University','Yale University','Columbia University','University of Pennsylvania','University of Chicago','University of California, Los Angeles','University of Southern California')
SPREADSHEET='1gMcmRGVxWgw4olbax2Vwxf4ZDJroBaHShH8A1qAjkrw'
PROJECT='hmnoqybdcfwqbjhorwzd'
RULE='BATCH_PROMOTION_V2_20260929'
PAIR_KEYS={'school_id':'school_id','field':'field','candidate_value':'value','academic_year':'academic_year','source_name':'source_name','source_url':'source_url','checked_date':'checked_date','evidence':'notes','basic_field':'basic_field','definition_version':'definition_version','applicable_cycle':'applicable_cycle','scope':'scope','method':'method','calculation_details':'calculation_details','alternatives_json':'alternatives_json','selection_evidence':'selection_evidence'}
CODES=frozenset(('BLANK_SCORE_NOT_REPORTED','BLANK_POLICY_CYCLE_UNPUBLISHED','BLANK_TEST_LIST_NOT_ENUMERATED','CURRENT_POLICY_CYCLE_UNPUBLISHED','RANKING_PUBLISHER_CAPTURE','GRADUATION_COHORT_UNSPECIFIED','SOURCE_HEADER_PERIOD_CONFLICT_ACCEPTED','REPRESENTATIVE_COST_SCOPE_ACCEPTED','COHORT_OR_SCOPE_SELECTION_ACCEPTED','POLICY_CLASSIFICATION_LIMITATION_ACCEPTED'))

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def validate_batch(rows,complete=True):
 require(isinstance(rows,list),'Invalid batch rows')
 if not rows:
  require(not complete,'Missing schools');return []
 result=records(validate_rows(rows,master=True,allowed_ids=IDS))
 require(not complete or tuple(r['school_id'] for r in result)==IDS,'Exact ten-school manifest required')
 for r in result:
  require(r['school_name']==NAMES[IDS.index(r['school_id'])],'Institution identity mismatch')
 if complete:
  stanford=result[1];require((stanford['ranking_usnews'],stanford['ranking_category'],stanford['ranking_year'])==(5,'national_university',2027),'Stanford ranking regression')
  require(result[2]['school_id']=='mit','MIT identity regression')
 return result

def candidate_digest(s,sid):
 p={k:s[k] for k in PAIR_KEYS};p.update(record_id=s['record_id'],related_record_id=s['related_record_id'],production_id=sid)
 return digest(p)

def verified_attachment(e):
 require(isinstance(e,dict) and e.get('path') and e.get('sha256'),'Missing durable evidence')
 p=Path(e['path']);require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],'Attachment missing or changed')


def evaluate(staging,sources,ledger,formula_errors=None):
 """Read-only factual gate; execution permission is intentionally separate."""
 require(formula_errors is not None and not formula_errors,'FORMULA_TAMPERED')
 require(len(staging)==len(sources)==len(ledger)==400,'Exactly 400 selected paired fields required')
 source_map={r['record_id']:r for r in sources};decisions={e['record_id']:e for e in ledger}
 require(len(source_map)==len(decisions)==len({s['record_id'] for s in staging})==400,'Duplicate record ID')
 output={sid:{} for sid in IDS};research=dict(zip(RESEARCH_IDS,IDS))
 for s in staging:
  require(s['school_id'] in research,'INVALID_OR_DUPLICATE_ID');sid=research[s['school_id']];f=s['basic_field']
  require(f in COLUMNS and f not in output[sid],'Duplicate/missing field or out-of-scope GPA')
  r=source_map.get(s['related_record_id']);require(r is not None and r['related_record_id']==s['record_id'],'PAIR_MISMATCH')
  require(all(s[k]==r[v] for k,v in PAIR_KEYS.items()),'PAIR_MISMATCH')
  require(s['definition_version']=='basic_v1' and s['status']=='approved','Unreviewed candidate')
  e=decisions.get(s['record_id']);require(e is not None,'MANUAL_AUTHORIZATION_MISSING')
  require(e['candidate_digest']==candidate_digest(s,sid),'APPROVAL_DIGEST_STALE')
  require(e['related_record_id']==r['record_id'] and e['production_id']==sid and e['rule_version']==RULE,'Wrong decision scope')
  require(e['authorization']['scope']=='reconcile_and_prepare_dry_run' and e['authorization']['actor']=='Ming Li' and not e['authorization']['execution_authorized'],'Invalid dry-run authorization')
  require(e['outcome'] in ('approved_value','accepted_intentional_blank','approved_with_limitation'),'UNSUPPORTED_NONBLANK_VALUE')
  codes=set(e['reason_codes']);require(codes<=CODES,'Unknown exception code')
  require(set(e['group_ids'])<=set(decisions),'Invalid related decision group')
  if 'GRADUATION_COHORT_UNSPECIFIED' in codes:require(sid=='ucla' and f in ('graduation_rate_4yr','graduation_rate_4yr_year'),'Invalid cohort exception')
  if 'SOURCE_HEADER_PERIOD_CONFLICT_ACCEPTED' in codes:require(sid in ('uchicago','usc') and s['source_type']=='CDS','Invalid period exception')
  if 'REPRESENTATIVE_COST_SCOPE_ACCEPTED' in codes:require(f in ('tuition_fees','coa') and s['alternatives_json'] and s['selection_evidence'],'Missing cost alternatives')
  if 'POLICY_CLASSIFICATION_LIMITATION_ACCEPTED' in codes:require(f in ('international_need_aid','international_merit_aid','english_proficiency_policy','english_tests_accepted'),'Invalid policy classification exception')
  if 'COHORT_OR_SCOPE_SELECTION_ACCEPTED' in codes:require(f in ('first_year_enrollment','applicants','admitted','acceptance_rate','graduation_rate_4yr'),'Invalid cohort selection exception')
  value=None if s['candidate_value']=='' else s['candidate_value']
  require(value==e['value'] and (value is None)==(e['outcome']=='accepted_intentional_blank'),'Intentional blank changed')
  flags=set() if s['provenance_check']=='complete' else set(s['provenance_check'].split('; '))
  require(flags==set(e['covered_flags']),'Uncovered provenance flag')
  allowed=set()
  if 'BLANK_SCORE_NOT_REPORTED' in codes:
   require(value is None and f in ('sat_25','sat_75','act_25','act_75'),'Invalid score exception');allowed|={'missing_value','invalid_value'}
  if 'BLANK_POLICY_CYCLE_UNPUBLISHED' in codes:
   require(value is None and f in ('test_policy_cycle','english_policy_cycle'),'Invalid cycle exception');allowed|={'missing_value','invalid_value','missing_applicable_cycle'}
  if 'BLANK_TEST_LIST_NOT_ENUMERATED' in codes:
   require(value is None and f=='english_tests_accepted' and sid in ('stanford','uchicago'),'Invalid list exception');allowed|={'missing_value','invalid_value'}
  if 'CURRENT_POLICY_CYCLE_UNPUBLISHED' in codes:
   require(not s['applicable_cycle'] and (value is not None or 'BLANK_TEST_LIST_NOT_ENUMERATED' in codes) and f in ('test_policy','international_need_aid','international_merit_aid','english_proficiency_policy','english_tests_accepted'),'Invalid current policy exception')
   require(s['source_type'] in ('university','CDS') and s['source_url'].startswith('https://') and s['evidence'],'Unsupported current policy')
   allowed.add('missing_applicable_cycle')
  if 'RANKING_PUBLISHER_CAPTURE' in codes:
   a=e.get('attachment');verified_attachment(a)
   require(f in ('ranking_usnews','ranking_category','ranking_year') and a.get('institution_confirmation') and a['edition']==2027,'Invalid capture')
   require(value==a[{'ranking_usnews':'rank','ranking_category':'category','ranking_year':'edition'}[f]],'Capture does not support value')
   allowed.add('missing_source_url')
  require(flags<=allowed,'Non-waivable or uncovered provenance defect')
  from datetime import date
  try:d=date.fromisoformat(s['checked_date'])
  except (ValueError,TypeError):raise ValueError('INVALID_CHECKED_DATE')
  require(date(2000,1,1)<=d<=date.today(),'INVALID_CHECKED_DATE')
  if sid=='yale' and f.startswith('graduation_rate_4yr'):
   a=e.get('attachment');verified_attachment(a)
   require(a['row_D_total']==818 and a['row_C_total']==1550 and round(818/1550*100,2)==52.77,'Unresolved Yale hold')
  if s['method']=='calculated':
   details=json.loads(s['calculation_details'])
   if 'numerator' in details:
    require(type(details['denominator']) in (int,float) and details['denominator']>0,'Invalid denominator')
    result=round(details['numerator']/details['denominator']*100,2)
   elif 'admitted' in details:
    require(details['applicants']>0,'Invalid admissions denominator')
    result=round(details['admitted']/details['applicants']*100,2)
    group={v['basic_field']:v for v in staging if v['school_id']==s['school_id']}
    require(details['admitted']==group['admitted']['candidate_value'] and details['applicants']==group['applicants']['candidate_value'],'Mixed admissions inputs')
    require(s['academic_year']==group['applicants']['academic_year']==group['admitted']['academic_year'],'Mixed admissions cohorts')
   elif 'tuition' in details:result=details['tuition']+details['fees']
   elif 'inputs' in details:result=sum(details['inputs'])
   else:raise ValueError('Unsupported calculation')
   require(result==details['result']==value,'Calculation result mismatch')
   require(not details.get('source_url') or details['source_url']==s['source_url'],'Calculation source mismatch')
  if f=='school_id':require(value==sid,'Invalid production/research ID mapping')
  if f=='ranking_year' and isinstance(value,str):
   require(len(value)==4 and value.isascii() and value.isdecimal(),'Invalid text ranking year')
   value=int(value) # Explicit Sheet representation normalization; evidence retains original.
  if f=='english_tests_accepted' and value is not None:
   value=json.loads(value) if isinstance(value,str) else value
  output[sid][f]=value
 require(sum(v is None for r in output.values() for v in r.values())==21,'Intentional missingness regression')
 require(output['ucla']['graduation_rate_4yr']==87.2 and output['ucla']['graduation_rate_4yr_year']=='2025-26 catalog; entering cohort not specified','UCLA cohort limitation lost')
 return validate_batch(list(output.values()))
