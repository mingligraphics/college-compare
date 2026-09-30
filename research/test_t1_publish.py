import copy
import unittest
from school_publish import COLUMNS
from t1_publish import IDS, EXTRA, selected_rows, build_sql

def fixture():
    return [{**dict.fromkeys((*COLUMNS,*EXTRA)), 'school_id':sid,
             'school_name':'Synthetic school', 'signature_programs':[
                 {'program_key':'test','name_en':'Synthetic','name_cn':'测试',
                  'selection_basis':'relative_strength'}]} for sid in IDS]

class T1Test(unittest.TestCase):
    def test_nulls_and_json_cells(self):
        rows=fixture();rows[0]['signature_programs']='[{"program_key":"test","name_en":"Synthetic","name_cn":"测试","selection_basis":"renowned"}]'
        result=selected_rows(rows)
        self.assertIsNone(result[0]['coa'])
        self.assertIsNone(result[0]['gpa_unweighted_25'])
        self.assertEqual(result[0]['signature_programs'][0]['selection_basis'],'renowned')
    def test_missing_duplicate_invalid(self):
        for mutate in (lambda r:r.pop(),lambda r:r.append(copy.deepcopy(r[0])),
                       lambda r:r[0].update(gpa_unweighted_25=4.1),
                       lambda r:r[0].update(gpa_unweighted_25=4,gpa_unweighted_75=3),
                       lambda r:r[0]['signature_programs'][0].update(selection_basis='ranked')):
            rows=fixture();mutate(rows)
            with self.assertRaises(ValueError):selected_rows(rows)
    def test_refuses_replay(self):
        with self.assertRaises(ValueError):
            build_sql(fixture(),{'rows':[{'school_id':'duke'}]},'')
    def test_sql_quotes_source_text_and_guards_all_rows(self):
        rows=fixture();rows[0]['school_name']="O'Brien $guard$"
        before={'rows':[], 'triggers':[], 'columns':[{'column_name':f} for f in COLUMNS]}
        sql=build_sql(rows,before,'BEGIN; SELECT 1; COMMIT;',rollback=True)
        self.assertIn("O''Brien $guard$",sql)
        self.assertIn('ACCESS EXCLUSIVE',sql)
        self.assertIn('Full readback mismatch',sql)
        self.assertTrue(sql.endswith('ROLLBACK;'))
        self.assertNotIn('ON CONFLICT',sql)

if __name__=='__main__': unittest.main()
