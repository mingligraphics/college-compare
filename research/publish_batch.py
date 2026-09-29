"""Build a non-executable ten-school review package from native Sheet reads.

Never promotes School or connects to Supabase. Apply support lives in
batch_publish and requires live read callbacks and separately reviewed digests.
"""
import argparse,json
from pathlib import Path
from batch_sheet import decode
from batch_contract import evaluate,digest
from batch_publish import promotion_plan,database_plan

def build(raw,receipt,formulas,ledger,database):
 x=decode(raw,formulas)
 required="'School'!A1:BA"+str(x['School']['allocated_row_count'])
 if required not in receipt['ranges']:raise ValueError('Complete bounded School read receipt required')
 x['School']['read_row_count']=x['School']['allocated_row_count']
 candidates=evaluate(x['Staging'],x['Sources'],ledger,x['formula_errors'])
 d=raw.get('structuredContent',raw)
 rules=next(s for s in d['sheets'] if s['properties']['title']=='Basic_v1_research_rules')
 binding=digest({'staging':x['Staging'],'sources':x['Sources'],'ledger':ledger,'formula_contract':formulas,'rules':rules})
 plan=promotion_plan(candidates,x['School'],binding)
 return {'promotion':plan,'downstream':database_plan(None,database,preview=True,candidates=candidates,promotion_digest=plan['approval_digest'])}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('cells','receipt','formulas','ledger','database','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--dry-run',action='store_true',required=True);args=p.parse_args()
 load=lambda f:json.loads(f.read_text())
 result=build(load(args.cells),load(args.receipt),load(args.formulas),load(args.ledger),load(args.database))
 if args.output.exists():raise ValueError('Refusing to overwrite a reviewed package')
 args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('Dry-run only: '+str(args.output))
if __name__=='__main__':main()
