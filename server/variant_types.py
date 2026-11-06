"""Describe inactive patterns without deriving school service from a weekday alone."""

# The GTFS has no variant-type field. This published school branch is identified
# by its actual termini: 706DS, Eroi di Rodi/Console -> EUR Fermi, 13:10/14:10.
# https://romaatac.altervista.org/autobus-706/
SCHOOL_BRANCHES = {('706', '82163', '82073')}


def contained_path(shorter, longer):
    return any(longer[i:i+len(shorter)] == shorter for i in range(len(longer)-len(shorter)+1))


def inactive_variants(route_id, groups, active_ids):
    primary = {}
    for group in groups:
        key = (group['direction'], group['headsign'])
        previous = primary.get(key)
        if previous is None or (len(group['trips']), len(group['stops'])) > (len(previous['trips']), len(previous['stops'])):
            primary[key] = group
    result = []
    for group in groups:
        if group['id'] in active_ids:
            continue
        stops = [s['stop_id'] for s in group['stops']]
        main = [s['stop_id'] for s in primary[(group['direction'], group['headsign'])]['stops']]
        if (route_id, stops[0], stops[-1]) in SCHOOL_BRANCHES:
            category = 'Deviata scolastica'
        elif stops == main:
            category = 'Ordinaria'
        elif contained_path(stops, main):
            category = 'Limitata'
        elif contained_path(main, stops):
            category = 'Prolungata'
        elif len(set(stops) & set(main)) >= max(2, min(len(stops), len(main)) / 2):
            category = 'Deviata'
        else:
            category = 'Altra variante'
        result.append({k: v for k, v in group.items() if k not in ('stops', 'trips')} | {'category': category})
    return result
