# Test-site discovery ranking order

Primary key: existing ranking_usnews converted with Number, requiring a positive finite integer. Blank, missing, invalid and unranked values sort after ranked schools. Ties (including missing ranks): raw ranking_category, then English school_name, then unique school_id, in ascending JavaScript string order (locale independent).

No category grouping: the requested global numerical order remains; a visible caveat above the list explains independent categories and every card retains its category label. Existing test endpoint supplies 2027 ranks. Filtering precedes sorting and pagination; original directory array is not mutated.

Validation: 20 automated regression tests, 43 browser assertions against 299 live records (44 missing ranks), plus 1440/390/320px layout checks. No horizontal overflow; category caveat and card labels visible. Deployment is checked with the same browser script and exact before/after directory equality, plus production main, production page hash and PR #1 state.
