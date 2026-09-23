"""Reviewed research interpretations; no factual school values or retrieval logic."""
import json
from collections import defaultdict
from sources import keys, require, text, verify_excerpt


def select_reviewed(record, source):
    # Local import avoids a module cycle; the core remains responsible for numeric validation.
    from staging import amount
    require(source.get('evidence_kind') == 'reviewed_findings',
            'Named reviewed rules require explicitly labeled reviewed_findings evidence')
    rule, field = record['selection_rule'], record['field']
    text(record['source_concept'], 'source_concept')
    keys(record['review'], {'flag_reason', 'review_notes'}, 'review')
    for value in record['review'].values():
        require(isinstance(value, str) and value == value.strip(), 'Review notes/flags must be strings without surrounding whitespace')
    flag = record['review']['flag_reason']
    numerator = denominator = None
    detail = {'source_concept': record['source_concept']}
    if rule == 'majority_undergraduate_schools':
        require(field in {'tuition', 'coa'}, 'Majority applies only to costs')
        denominator = record['coverage_denominator']
        require(type(denominator) is int and denominator > 0, 'Positive integer denominator required')
        observations = record['observations']
        require(isinstance(observations, list) and observations, 'Reported majority requires observations')
        totals, labels, covered = defaultdict(int), set(), 0
        for observation in observations:
            keys(observation, {'label', 'candidate_value', 'coverage_count', 'evidence'}, 'reported observation')
            text(observation['label'], 'label')
            require(observation['label'] not in labels, 'Duplicate reported coverage group')
            labels.add(observation['label'])
            count = observation['coverage_count']
            require(type(count) is int and count > 0, 'Positive integer coverage count required')
            covered += count
            amount(observation['candidate_value'], field)
            verify_excerpt(source, observation['evidence'])
            if observation['candidate_value'] is not None:
                totals[observation['candidate_value']] += count
        require(covered <= denominator, 'Reported coverage exceeds denominator')
        winners = [(v, n) for v, n in totals.items() if n * 2 > denominator]
        value = None
        if len(winners) == 1:
            value, numerator = winners[0]
        else:
            flag = ' '.join(filter(None, [flag, 'No reported value covers >50%; manual selection required.']))
        flag = ' '.join(filter(None, [flag, 'Coverage uses reviewed aggregate counts, not an independently checked unit roster.']))
        detail.update(coverage_basis='reported_undergraduate_school_program_groups',
                      coverage_denominator=denominator, observations=observations)
    else:
        value = record['candidate_value']
        amount(value, field)
        for name in ('alternatives', 'components'):
            require(isinstance(record[name], list), f'{name} must be an array')
            labels = set()
            for item in record[name]:
                keys(item, {'label', 'candidate_value', 'evidence'}, name)
                text(item['label'], 'label')
                require(item['label'] not in labels, f'Duplicate {name} label')
                labels.add(item['label'])
                amount(item['candidate_value'], field)
                verify_excerpt(source, item['evidence'])
            detail[name] = record[name]
        if rule in ('living_arrangement_ambiguous', 'unresolved_source_conflict'):
            require(value is None, 'Unresolved cases must not select a candidate_value')
            require(bool(flag) and bool(record['alternatives']), 'Unresolved cases require a flag and alternatives')
            if rule == 'living_arrangement_ambiguous':
                require(field == 'coa', 'Living-arrangement ambiguity applies to COA')
        else:
            require(value is not None, 'Reported/standard value must be known')
            if rule == 'resident_standard':
                require(field == 'coa', 'Resident standard applies to COA')
            elif rule == 'university_standard':
                require(field in {'tuition', 'coa'}, 'University standard applies to costs')
            else:
                require(field == 'first_year_enrollment', 'Reported enrollment rules require first_year_enrollment')
            if rule == 'cds_reported':
                require(source['source_type'] == 'CDS', 'cds_reported requires CDS provenance')
            elif rule in ('university_standard', 'resident_standard', 'university_reported'):
                require(source['source_type'] == 'university', 'University rule requires university provenance')
        if record['components']:
            require(field == 'first_year_enrollment' and value is not None,
                    'Components may verify a selected first-year enrollment total only')
            require(all(c['candidate_value'] is not None for c in record['components']), 'Component values must be known')
            require(sum(c['candidate_value'] for c in record['components']) == value,
                    'Components do not sum to reported enrollment')
        if record['alternatives']:
            require(bool(flag), 'Alternatives/exceptions require an explicit review flag')
        if field == 'tuition' and record['source_concept'] != 'tuition_only':
            require(bool(flag), 'Tuition semantic mismatch requires an explicit flag')
    audit = '\nReviewed interpretation: ' + json.dumps(detail, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return value, numerator, denominator, flag, audit
