"""Describe exact paths; school labels require a matching published timetable."""
import json
from pathlib import Path
import re
import unicodedata


# Rome's GTFS has no DS/PS/LS field. Keep the reference data separate from the
# classifier. Match a documented ordered path, or every departure time against
# a published profile. Weekdays, rarity or a route number alone prove nothing.
SCHOOL_SERVICES = json.loads(Path(__file__).with_name('school_services.json').read_text())['rules']
SCHOOL_LABELS = {'DS': 'Deviata scolastica', 'PS': 'Prolungata scolastica',
                 'LS': 'Limitata scolastica', 'DLS': 'Deviata limitata scolastica',
                 'PDS': 'Deviata prolungata scolastica', 'DPS': 'Deviata prolungata scolastica'}


def normalized_name(name):
    plain = unicodedata.normalize('NFKD', name.upper())
    return ''.join(re.findall(r'[A-Z0-9]+', plain))


def school_code(route_name, group, sequences):
    rules = SCHOOL_SERVICES.get(route_name.strip().upper(), ())
    if not rules:
        return None
    complete = sequences and all(sequences.get(trip) for trip in group['trips'])
    times = {f"{first['departure'] // 3600 % 24:02}:{first['departure'] // 60 % 60:02}"
             for trip in group['trips'] for first in sequences[trip][:1]} if complete else set()
    stops = [s['stop_id'] for s in group['stops']]
    matches = set()
    for rule in rules:
        if rule.get('stops'):
            if stops != rule['stops']:
                continue
        elif not times or not times <= set(rule['times']):
            continue
        if any(normalized_name(rule[key]) not in normalized_name(group[field])
               for key, field in (('origin', 'fromName'), ('destination', 'toName')) if key in rule):
            continue
        matches.add(rule['code'])
    return matches.pop() if len(matches) == 1 else None


def contained_path(shorter, longer):
    return any(longer[i:i+len(shorter)] == shorter for i in range(len(longer)-len(shorter)+1))


def variant_summaries(route_name, groups, sequences=None):
    school_codes = {g['id']: school_code(route_name, g, sequences) for g in groups}
    rank = lambda g: (school_codes[g['id']] is None, len(g['trips']), len(g['stops']))
    primary = {}
    for group in groups:
        key = (group['direction'], group['headsign'])
        previous = primary.get(key)
        if previous is None or rank(group) > rank(previous):
            primary[key] = group
    result = []
    for group in groups:
        stops = [s['stop_id'] for s in group['stops']]
        main_group = primary[(group['direction'], group['headsign'])]
        main = [s['stop_id'] for s in main_group['stops']]
        if stops == main:
            category = 'Ordinaria'
        elif contained_path(stops, main):
            category = 'Limitata'
        elif contained_path(main, stops):
            category = 'Prolungata'
        elif len(set(stops) & set(main)) >= max(2, min(len(stops), len(main)) / 2):
            category = 'Deviata'
        else:
            category = 'Altra variante'
        item = {k: v for k, v in group.items() if k not in ('stops', 'trips')} | {'category': category}
        code = school_codes[group['id']]
        if code:
            item.update(category=SCHOOL_LABELS[code], schoolCode=code)
        if category == 'Deviata':
            main_ids, stop_ids = set(main), set(stops)
            extra = next((s for s in group['stops'][1:-1] if s['stop_id'] not in main_ids), None)
            skipped = next((s for s in main_group['stops'][1:-1] if s['stop_id'] not in stop_ids), None)
            if extra and extra.get('name'):
                item['pathNote'] = f"Via {extra['name']}"
            elif skipped and skipped.get('name'):
                item['pathNote'] = f"Non transita da {skipped['name']}"
        result.append(item)
    return result


def inactive_variants(route_name, groups, active_ids, sequences=None):
    return [v for v in variant_summaries(route_name, groups, sequences) if v['id'] not in active_ids]
