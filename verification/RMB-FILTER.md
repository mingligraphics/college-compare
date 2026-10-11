# Test-site RMB tuition filter

Labels: 20万元以下; 20万-35万元; 35万-50万元; 50万元以上.

Fixed approximate USD/CNY rate: 7. No live FX. Filter valid nonnegative tuition_fees (USD) × 7, without rounding, into [0,200000), [200000,350000), [350000,500000), [500000,infinity) CNY. Exact boundaries belong to the next band; 500000 is included in the last band. Missing or invalid fees are excluded when filtering, retained for all-fees. COA is not used. Existing detailed amounts, records and API/security protections remain unchanged.

Badges fit rendered text with 10px horizontal padding. Existing two-line handling and optional English short-name rendering remain; mobile grid minimum sizing prevents long badges expanding narrow cards.

Validation: 19 automated checks passed, including exact thresholds and values immediately either side. 1440px, 390px and 320px browser checks showed no horizontal overflow, different MIT/UCLA widths and two-line wrapping at 320px.
