# Test-site discovery ranking order

Ranked schools first, grouped: national universities, national liberal arts colleges, regional universities North, Midwest, South, West, then unspecified categories. Within each group, positive integer ranking_usnews sorts numerically ascending. Missing/invalid ranks are globally last, ordered by the same category groups. Ties: raw ranking_category, English school_name, school_id in ascending locale-independent JavaScript string order.

Visible category labels and independent-category caveat remain. Filter before sort before pagination; no school records or APIs changed.

Validation: 20 regression tests; browser checks for category priority, numeric ranking, missing values, search, all four filters, combinations, reset and pagination; 1440/390/320px layouts.
