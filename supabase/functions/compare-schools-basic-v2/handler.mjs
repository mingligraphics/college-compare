import { createHandler as base } from '../compare-schools/handler.mjs';
import { BASIC_V1_FIELDS } from '../compare-schools-basic-v1/handler.mjs';
export const BASIC_V2_FIELDS = [...BASIC_V1_FIELDS, 'gpa_unweighted_25', 'gpa_unweighted_75', 'gpa_scale_definition', 'gpa_population', 'gpa_year', 'signature_programs'];
export const createHandler = options => base({ ...options, rpcName: 'get_school_comparison_basic_v2', responseFields: BASIC_V2_FIELDS });
