"""Rebuild every count reported in the article from the stored reader outputs.

Usage:  python reproduce.py [OUTDIR]     (default: ./results_rebuilt)

Reads only files under ./work (relative to this script). Writes into a fresh
OUTDIR: provisions.csv, tables.json, checks.json. No model is called; this is a
deterministic re-aggregation of outputs already stored in the package.
"""
import csv, glob, json, os, re, sys, statistics, collections as C
from pathlib import Path

ROOT = Path(__file__).resolve().parent
W = ROOT / 'work'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'results_rebuilt'
if OUT.exists() and any(OUT.iterdir()):
    sys.exit(f'{OUT} is not empty; give an empty or new directory')
OUT.mkdir(parents=True, exist_ok=True)

BROKEN = {'B1', 'B2', 'B3', 'F1'}
CORE = {'B1', 'F1'}
RANK = {'not_refuted': 0, 'uncertain': 1, 'partly_refuted': 2, 'refuted': 3}


def jsonl(pattern, key):
    d = {}
    for f in sorted(glob.glob(str(W / pattern))):
        for line in open(f, encoding='utf-8'):
            if line.strip():
                o = json.loads(line)
                d[o[key]] = o
    return d


def cls(code):
    return 'broken' if code in BROKEN else ('traced' if code in ('T1', 'T2') else code)


# ---------------------------------------------------------------- 1. second-stage reading
packets = jsonl('s2c/s2_packets.jsonl', 'packet_id')
changed = set(json.load(open(W / 's2c/changed_ids.json')))
disc = set(json.load(open(W / 's2c/discordant_v2.json')))
S1, G1 = jsonl('s2b/out/sonnet_s2_chunk*.jsonl', 'packet_id'), jsonl('s2b/gpt/gpt_s2_chunk*.jsonl', 'packet_id')
S2, G2 = jsonl('s2c/out/sonnet_r_chunk*.jsonl', 'packet_id'), jsonl('s2c/gpt/gpt_r_chunk*.jsonl', 'packet_id')
O = jsonl('s2c/opus_out/opus_o_chunk*.jsonl', 'packet_id')
S = {k: (S2[k] if k in changed else v) for k, v in S1.items()}   # corrected packets re-read
G = {k: (G2[k] if k in changed else v) for k, v in G1.items()}
assert set(S) == set(G) == set(packets) and disc <= set(O)

# ---------------------------------------------------------------- 2. refutation round
tasks = C.defaultdict(list)
for f in sorted(glob.glob(str(W / 'refute/tasks*/*.jsonl'))):
    for line in open(f, encoding='utf-8'):
        if line.strip():
            o = json.loads(line)
            tasks[o['task_id']].append(o)
opus_ref = C.defaultdict(list)
for pat in ('refute/out/opus_t*.jsonl', 'refute/out2/opus_u*.jsonl'):
    for k, o in jsonl(pat, 'task_id').items():
        opus_ref[k].append(o['result'])
gpt_ref = {k: o['result'] for k, o in jsonl('gptref/gpt_refute_g*.jsonl', 'task_id').items()}
# Opus read up to two rounds (second round with the union of statutes cited anywhere in the rule);
# the stronger refutation of the two rounds is kept.
opus_final = {k: max(v, key=RANK.get) for k, v in opus_ref.items()}

# ---------------------------------------------------------------- 3. provision table
rows = []
for k in sorted(S):
    s, g = S[k]['article_status'], G[k]['article_status']
    o = O[k]['article_status'] if k in disc else ''
    if k in disc:
        votes = C.Counter([cls(s), cls(g), cls(o)])
        top, n = votes.most_common(1)[0]
        if n >= 2:
            final_cls, how = top, 'majority'
        else:                                   # three different classes
            final_cls, how = cls(o), 'adjudicator_only'
        final = [x for x in (o, s, g) if cls(x) == final_cls][0]
    else:
        final = s
        final_cls = cls(s) if cls(s) == cls(g) else 'differ_nonbroken'
        how = 'agree' if s == g else ('agree_class' if cls(s) == cls(g) else 'differ_nonbroken')
    has_law = any(len(t['law_files']) > 0 for t in tasks.get(k, []))
    r = dict(packet_id=k, rule_id=k.split('#')[0], rule_title=packets[k]['rule_title'],
             rule_type=packets[k]['rule_type'], article=packets[k]['article'],
             reader1=s, reader2=g, adjudicator=o, final=final, final_class=final_cls, resolution=how,
             conf1=S[k].get('confidence', ''), conf2=G[k].get('confidence', ''),
             addressee1=S[k]['addressee'], addressee2=G[k]['addressee'],
             refute_opus=opus_final.get(k, ''), refute_gpt=gpt_ref.get(k, ''),
             refute_statutes_supplied=int(has_law) if k in tasks else '')
    r['set_either'] = int(s in BROKEN or g in BROKEN)
    r['set_both'] = int(s in BROKEN and g in BROKEN)
    r['set_broken_incl_adjudicator'] = int(final_cls == 'broken')
    r['set_candidate'] = int(final_cls == 'broken' and how != 'adjudicator_only')
    r['set_not_refuted'] = int(r['set_candidate'] and r['refute_opus'] not in ('refuted', 'partly_refuted')
                               and r['refute_gpt'] not in ('refuted', 'partly_refuted'))
    r['set_core'] = int(r['set_candidate'] and r['refute_opus'] == 'not_refuted'
                        and r['refute_gpt'] == 'not_refuted' and has_law)
    r['set_core_B1F1'] = int(r['set_core'] and final in CORE)
    rows.append(r)

with open(OUT / 'provisions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)

R = {r['packet_id']: r for r in rows}
rules_of = lambda rs: {r['rule_id'] for r in rs}
T = {}


def count(pred):
    rs = [r for r in rows if pred(r)]
    return {'provisions': len(rs), 'rules': len(rules_of(rs)),
            'B1F1_provisions': sum(r['final'] in CORE for r in rs),
            'B1F1_rules': len(rules_of([r for r in rs if r['final'] in CORE])),
            'codes': dict(C.Counter(r['final'] for r in rs))}


core = lambda r: r['set_core'] == 1
T['table1'] = {
    'either_initial_reader': count(lambda r: r['set_either']),
    'both_initial_readers': count(lambda r: r['set_both']),
    'broken_incl_adjudicator_only': count(lambda r: r['set_broken_incl_adjudicator']),
    'candidates_agreement_or_majority': count(lambda r: r['set_candidate']),
    'candidates_not_refuted_in_whole_or_part': count(lambda r: r['set_not_refuted']),
    'core_set': count(core),
}
T['table2_final_labels'] = dict(C.Counter(
    ('broken_candidate' if r['set_candidate'] else 'broken_adjudicator_only') if r['final_class'] == 'broken'
    else r['final_class'] for r in rows))
T['resolution'] = dict(C.Counter(r['resolution'] for r in rows))

# refutation outcomes among candidates
cand = [r for r in rows if r['set_candidate']]
T['refutation'] = {
    'opus': dict(C.Counter(r['refute_opus'] for r in cand)),
    'gpt': dict(C.Counter(r['refute_gpt'] for r in cand)),
    'both_refuted': sum(r['refute_opus'] == r['refute_gpt'] == 'refuted' for r in cand),
    'either_refuted_or_partly': sum(r['refute_opus'] in ('refuted', 'partly_refuted') or r['refute_gpt'] in ('refuted', 'partly_refuted') for r in cand),
    'no_statute_supplied': sum(r['refute_statutes_supplied'] == 0 for r in cand),
    'no_statute_supplied_rules': sorted({r['rule_title'] for r in cand if r['refute_statutes_supplied'] == 0}),
}
# all provisions that went to refutation (incl. adjudicator-only), as reported in the methods
allb = [r for r in rows if r['set_broken_incl_adjudicator']]
T['refutation_all_204'] = {'n': len(allb),
    'both_refuted': sum(r['refute_opus'] == r['refute_gpt'] == 'refuted' for r in allb),
    'either_refuted': sum('refuted' in (r['refute_opus'], r['refute_gpt']) for r in allb)}

# sensitivity within the core set
sens = {
    'core': core,
    'core_excl_B3': lambda r: core(r) and r['final'] != 'B3',
    'core_both_initial_broken': lambda r: core(r) and r['set_both'],
    'core_excl_B3_and_both_initial_broken': lambda r: core(r) and r['final'] != 'B3' and r['set_both'],
    'core_both_initial_conf_ge2': lambda r: core(r) and str(r['conf1']) in ('2', '3') and str(r['conf2']) in ('2', '3'),
    'core_both_initial_B1F1': lambda r: core(r) and r['reader1'] in CORE and r['reader2'] in CORE,
    'core_partly_refuted_kept': lambda r: r['set_candidate'] and r['refute_opus'] in ('not_refuted', 'partly_refuted') and r['refute_gpt'] in ('not_refuted', 'partly_refuted') and r['refute_statutes_supplied'] == 1,
}
T['sensitivity'] = {k: count(f) for k, f in sens.items()}
T['rule_types_read_in_second_stage'] = dict(C.Counter(t for _, t in {(r['rule_id'], r['rule_type']) for r in rows}))
T['initial_conf1_eq1_in_core'] = sum(core(r) and str(r['conf1']) == '1' for r in rows)

# addressee (first reader; second reader shown alongside)
T['table4_addressee_reader1'] = dict(C.Counter(r['addressee1'] for r in rows if core(r)))
T['table4_addressee_pairs'] = {f'{a}|{b}': n for (a, b), n in C.Counter((r['addressee1'], r['addressee2']) for r in rows if core(r)).items()}

# agreement statistics (initial readers, final packets)
def kappa(a, b):
    n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = C.Counter(a), C.Counter(b)
    pe = sum(ca[c] * cb[c] for c in set(a) | set(b)) / n / n
    return (po - pe) / (1 - pe), po
ks = sorted(S)
k9, _ = kappa([S[k]['article_status'] for k in ks], [G[k]['article_status'] for k in ks])
kb, pb = kappa([S[k]['article_status'] in BROKEN for k in ks], [G[k]['article_status'] in BROKEN for k in ks])
T['agreement'] = {'kappa_9way': round(k9, 3), 'kappa_broken': round(kb, 3), 'raw_broken': round(pb, 4)}
T['undecidable_reader1_first_vs_corrected'] = {
    'before': sum(S1[k]['article_status'] == 'U' for k in S1), 'after': sum(S[k]['article_status'] == 'U' for k in S)}

# ---------------------------------------------------------------- 4. kind of rule (origin)
meta = jsonl('origin/r*.jsonl', 'rule_id')
o1, o2 = jsonl('origin/out/sonnet_r*.jsonl', 'rule_id'), jsonl('origin/out/opus_r*.jsonl', 'rule_id')
kind = {}
for rid in meta:
    a, b = o1[rid]['origin'], o2[rid]['origin']
    if a == b and a in ('event_response', 'temporary'):
        kind[rid] = 'event_or_temporary'
    elif a == b and a == 'program':
        kind[rid] = 'funding_programme'
    else:
        kind[rid] = 'standing'
T['origin_kappa'] = round(kappa([o1[r]['origin'] for r in sorted(meta)], [o2[r]['origin'] for r in sorted(meta)])[0], 3)
cand_rules = rules_of(cand)
tab3 = {}
for kd in ('event_or_temporary', 'funding_programme', 'standing'):
    rs = [r for r in meta if kind[r] == kd]
    tab3[kd] = {'rules': len(rs), 'with_candidate': len([r for r in rs if r in cand_rules])}
tab3['all'] = {'rules': len(meta), 'with_candidate': len(cand_rules)}
T['table3_kind'] = tab3
T['event_response_rules'] = [meta[r]['title'] for r in meta if o1[r]['origin'] == o2[r]['origin'] == 'event_response']


def fisher_two_sided(a, b, c, d):
    from math import comb
    n1, n2, k = a + b, c + d, a + c
    p = lambda x: comb(n1, x) * comb(n2, k - x) / comb(n1 + n2, k)
    obs = p(a)
    return sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= obs * (1 + 1e-9))
def fisher_vs_rest(kd):
    inn = [r for r in meta if kind[r] == kd]; out = [r for r in meta if kind[r] != kd]
    a = sum(r in cand_rules for r in inn); c = sum(r in cand_rules for r in out)
    return {'in': [a, len(inn)], 'rest': [c, len(out)], 'p': round(fisher_two_sided(a, len(inn) - a, c, len(out) - c), 3)}
T['fisher'] = {k: fisher_vs_rest(k) for k in ('event_or_temporary', 'funding_programme')}

# last issued year and purpose-clause citation
T['all_rule_types_212'] = dict(C.Counter(meta[r]['type'] for r in meta))
T['core_rule_types'] = dict(C.Counter(meta[r]['type'] for r in rules_of([r for r in rows if core(r)])))
# first-stage screen
H1, G0 = jsonl('s1/out/haiku_s1*.jsonl', 'packet_id'), jsonl('s1/out/gpt_s1*.jsonl', 'packet_id')
ks1 = sorted(set(H1) & set(G0))
sel1 = {k for k in ks1 if H1[k]['new_rule'] in ('yes', 'unclear') or G0[k]['new_rule'] in ('yes', 'unclear')}
T['screen'] = {'provisions': len(ks1), 'selected': len(sel1),
               'kappa_addressee': round(kappa([H1[k]['addressee'] for k in ks1], [G0[k]['addressee'] for k in ks1])[0], 3),
               'added_reference_provisions': sorted(set(packets) - sel1)}
year = {r: int(meta[r]['last_issued'][:4]) for r in meta}
T['median_last_issued'] = {'with_candidate': statistics.median(year[r] for r in cand_rules),
                           'others': statistics.median(year[r] for r in meta if r not in cand_rules)}
def cites_article(p):
    p = re.sub(r'^\s*제\s*1\s*조\s*\([^)]*\)', '', p or '')
    return bool(re.search(r'제\s*\d+\s*조', p))
core_rules = rules_of([r for r in rows if core(r)])
pc = {r: cites_article(meta[r]['purpose']) for r in meta}
T['purpose_clause'] = {
    'cites_article': [sum(r in core_rules for r in meta if pc[r]), sum(pc.values())],
    'no_article': [sum(r in core_rules for r in meta if not pc[r]), sum(not v for v in pc.values())]}
_a, _n1 = T['purpose_clause']['no_article']; _c, _n2 = T['purpose_clause']['cites_article']
T['purpose_clause']['fisher_p'] = round(fisher_two_sided(_a, _n1 - _a, _c, _n2 - _c), 3)

# ---------------------------------------------------------------- 5. decisions
d1, d2 = jsonl('dec/out/sonnet_d*.jsonl', 'pair_id'), jsonl('dec/out/opus_d*.jsonl', 'pair_id')
pairs = json.load(open(W / 'dec/exact_pairs.json'))
T['decisions'] = {'documents_naming_a_rule': len({d for v in pairs.values() for d in v}), 'rules_named': len(pairs),
                  'both_readers_assessed_binding': sorted(k for k in d1 if d1[k]['role'] == d2[k]['role'] == 'assessed_binding')}
for name, pred in (('candidate', lambda r: r['set_candidate']), ('core', core)):
    flag = C.defaultdict(set)
    for r in rows:
        if pred(r): flag[r['rule_id']].add(r['article'])
    hits = []
    for k in d1:
        rid = k.split('|')[0]
        arts = (set(d1[k]['articles_addressed']) | set(d2[k]['articles_addressed'])) & flag.get(rid, set())
        if arts and 'applied' in (d1[k]['role'], d2[k]['role']):
            hits.append({'pair': k, 'articles': sorted(arts), 'roles': [d1[k]['role'], d2[k]['role']]})
    T['decisions'][f'applied_same_article_number_{name}'] = hits
    T['decisions'][f'rules_named_{name}'] = len(set(pairs) & set(flag))
    T['decisions'][f'rules_total_{name}'] = len(flag)
    T['decisions'][f'rules_named_{name}_B1F1'] = len(set(pairs) & {r['rule_id'] for r in rows if pred(r) and r['final'] in CORE})

# ---------------------------------------------------------------- 6. controls and case provisions
ctrl = json.load(open(W / 's2c/s2_controls.json'))
keep = ('reader1', 'reader2', 'adjudicator', 'final', 'resolution', 'refute_opus', 'refute_gpt', 'set_candidate', 'set_core')
T['controls'] = {'positive_leave_directive_art24': {k: R['2100000250466#24'][k] for k in keep},
                 'negative': {p: {k: R[p][k] for k in keep} for p in ctrl['neg_controls']}}
cases = [json.loads(l)['case_id'] for l in open(W / 'cases/cases.jsonl', encoding='utf-8') if l.strip()]
T['case_provisions'] = {c: {k: R[c][k] for k in keep} for c in cases}
T['scholarship_rules_core_B1F1'] = sum(r['set_core_B1F1'] for r in rows if '장학' in r['rule_title'])

json.dump(T, open(OUT / 'tables.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 7. checks against the manuscript
EXPECT = json.load(open(ROOT / 'expected_numbers.json', encoding='utf-8')) if (ROOT / 'expected_numbers.json').exists() else {}
def get(path):
    x = T
    for p in path.split('.'):
        x = x[int(p)] if isinstance(x, list) else x[p]
    return x
checks = {p: {'expected': v, 'rebuilt': get(p), 'ok': get(p) == v} for p, v in EXPECT.items()}
json.dump(checks, open(OUT / 'checks.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
bad = [p for p, c in checks.items() if not c['ok']]
print(f'{len(rows)} provisions; core set {T["table1"]["core_set"]["provisions"]} provisions in {T["table1"]["core_set"]["rules"]} rules')
print(f'checks: {len(checks) - len(bad)}/{len(checks)} match' + (f'; MISMATCH: {bad}' if bad else ''))
