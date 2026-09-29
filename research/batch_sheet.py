"""Decode native CellData reads; formula integrity and complete bounded scans."""
import json,re
from pathlib import Path
from batch_contract import COLUMNS,SPREADSHEET,digest
from sources import require

def value(c):return next(iter(c.get('effectiveValue',c.get('userEnteredValue',{})).values()),'')
def normalize(formula):return re.sub(r'(\$[A-Z]+)\d+',r'\1#',formula)
def decode(raw,formula_contract):
 d=raw.get('structuredContent',raw);require(d['spreadsheetId']==SPREADSHEET,'Wrong sheet')
 tabs={s['properties']['title']:s for s in d['sheets']};result={};errors=[]
 for title in ('Staging','Sources'):
  tab=tabs[title];header_data=next(x for x in tab['data'] if x.get('startRow',0)==0 and x.get('startColumn',0)==0)
  headers=[value(c) for c in header_data['rowData'][0]['values']]
  require(len(headers)==len(set(headers)),'Duplicate research header')
  data=next(x for x in tab['data'] if x.get('startRow')==145 and x.get('startColumn',0)==0)
  require(len(data['rowData'])==400,'Batch scan incomplete')
  rows=[]
  for offset,r in enumerate(data['rowData']):
   cells=r['values'];vals=[value(c) for c in cells];vals+=['']*(len(headers)-len(vals));row=dict(zip(headers,vals));rows.append(row)
   for field in ('provenance_check','promotion_gate'):
    col=headers.index(field);f=cells[col].get('userEnteredValue',{}).get('formulaValue','')
    expected=re.sub(r'(\$[A-Z]+)#',lambda m:m[1]+str(146+offset),formula_contract[title][field])
    if f!=expected:errors.append(f'{title}:{146+offset}:{field}')
  ids=[r['record_id'] for r in rows]
  record_col=headers.index('record_id')
  id_chunks=[d for d in tab['data'] if d.get('startColumn')==record_col]
  require(len(id_chunks)==2,'Full research identity scan required')
  require({d.get('startRow') for d in id_chunks}=={1,545},'Invalid research identity bounds')
  for chunk in id_chunks:
   ids += [value(r['values'][0]) for r in chunk.get('rowData',[]) if r.get('values') and value(r['values'][0])]
  require(len(ids)==len(set(ids)),'Duplicate research ID outside selected batch')
  result[title]=rows
 tab=tabs['School'];require(len(tab['data'])==1 and tab['data'][0].get('startRow',0)==0,'Whole School range required')
 grid=tab['data'][0]['rowData'];headers=[value(c) for c in grid[0]['values']]
 require(len(headers)==len(set(headers)) and set(COLUMNS)<=set(headers),'School headers invalid')
 rows=[];positions={}
 for n,r in enumerate(grid[1:],2):
  vals=[value(c) for c in r.get('values',[])];vals+=['']*(len(headers)-len(vals));require(len(vals)==len(headers),'Malformed row')
  if all(v=='' for v in vals):continue
  record={k:(None if v=='' else v) for k,v in zip(headers,vals)}
  require(isinstance(record['school_id'],str) and record['school_id'] not in positions,'Orphan/duplicate School row')
  for field in ('english_tests_accepted','famous_majors','famous_majors_cn','notable_alumni'):
   if record.get(field) is not None and isinstance(record[field],str):record[field]=json.loads(record[field])
  rows.append(record);positions[record['school_id']]=n
 # Google omits trailing empty rows. Read range receipt is required separately,
 # because CellData alone cannot prove that a caller requested the whole grid.
 result['School']={'source_tab':'School','spreadsheet_id':SPREADSHEET,'headers':headers,'rows':rows,'row_positions':positions,'allocated_row_count':tab['properties']['gridProperties']['rowCount'],'read_row_count':0}
 result['formula_errors']=errors
 return result

def read_live(service):
 meta=service.spreadsheets().get(spreadsheetId=SPREADSHEET,fields='sheets(properties)').execute()
 tabs={s['properties']['title']:s['properties'] for s in meta['sheets']}
 require(all(t in tabs for t in ('Staging','Sources','School','Basic_v1_research_rules')),'Missing sheet')
 require(tabs['Staging']['gridProperties']['rowCount']==1000 and tabs['Sources']['gridProperties']['rowCount']==1000,'Research bounds changed; re-plan')
 count=tabs['School']['gridProperties']['rowCount']
 require(tabs['School']['gridProperties']['columnCount']==53 and count<=10000,'Unreviewed School bounds/schema')
 ranges=["'School'!A1:BA"+str(count),"'Staging'!A1:AH1","'Staging'!A146:AH545","'Sources'!A1:X1","'Sources'!A146:X545","'Basic_v1_research_rules'!A1:I105","'Staging'!T2:U145","'Staging'!T546:U1000","'Sources'!J2:K145","'Sources'!J546:K1000"]
 raw=service.spreadsheets().get(spreadsheetId=SPREADSHEET,ranges=ranges,includeGridData=True).execute()
 return raw,{'ranges':ranges,'allocated_school_rows':count}
