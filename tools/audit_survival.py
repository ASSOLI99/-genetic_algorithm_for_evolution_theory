"""Bounded, preplanned extinction-accounting diagnostics; no model modifications."""
import argparse
from collections import defaultdict
from dataclasses import replace
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import time

import numpy as np

from evolution_lab_v2.artifacts import ROOT, provenance, signature, write_json
from evolution_lab_v2.eco_analysis import wilson
from evolution_lab_v2.eco_config import EcoConfig, STRATEGIES, MAX_BATCH_CENSUS_TICKS, MAX_BATCH_LOCUS_TICKS
from evolution_lab_v2.eco_io import simulate, write_csv

CASES = ('seven_default','seven_neutral','seven_neutral_pooled','pair_default',
         'isolated_clone','isolated_two_parent','seven_no_crossover')


def plan(values):
    if values['schema'] != 'survival-audit-1' or tuple(values['cases']) != CASES:
        raise ValueError('Unknown diagnostic design')
    seeds=values['seeds']
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s<0 for s in seeds):
        raise ValueError('Distinct nonnegative integer seeds required')
    configurations=[]
    for case in CASES:
        counts=(112,112,0,0,0,0,0) if case=='pair_default' else (224,0,0,0,0,0,0) if case=='isolated_clone' else (0,224,0,0,0,0,0) if case=='isolated_two_parent' else (32,)*7
        for environment in values['environments']:
            for seed in seeds:
                cfg=EcoConfig(seed=seed,steps=values['steps'],capacity=values['capacity'],initial_counts=counts,
                    environment=environment,selection_coefficient=0 if 'neutral' in case else .04,
                    compatibility_scope='all_mixing' if case=='seven_neutral_pooled' else 'within_strategy',
                    recombination_rate=0 if case=='seven_no_crossover' else .05,
                    record_parentage=False,log_every=20,checkpoint_every=400)
                configurations.append({'id':f'{case}_{environment}_{seed}','case':case,'config':cfg.to_dict()})
    work=sum(r['config']['steps']*r['config']['capacity'] for r in configurations)
    loci=sum(r['config']['steps']*r['config']['capacity']*sum(r['config']['chromosome_lengths']) for r in configurations)
    if work>MAX_BATCH_CENSUS_TICKS or loci>MAX_BATCH_LOCUS_TICKS:
        raise ValueError('Diagnostic workload exceeds aggregate guards')
    return {'input':values,'runs':configurations,'upper_individual_updates':work,'upper_locus_updates':loci}


def life_table(config, performance=1):
    """Low-density reproduction per newborn, with unlimited mates/food/space."""
    probability=1.; rows=[]
    for age in range(config.max_age):
        probability*=config.survival_probability*math.exp(-config.senescence_rate*max(0,age-config.senescence_age))
        offspring=probability*config.fecundity*performance if age>=config.maturity_age else 0.
        rows.append({'age':age,'alive_after_survival':probability,'expected_focal_offspring':offspring})
    return {'constant_performance':performance,'expected_low_density_focal_offspring':sum(r['expected_focal_offspring'] for r in rows),
            'probability_to_first_breeding':next((r['alive_after_survival'] for r in rows if r['age']>=config.maturity_age),0),
            'rows':rows}


def inspect(directory):
    """Recompute accounting from persisted records, independently of step()."""
    directory=Path(directory)
    summary=json.loads((directory/'summary.json').read_text())
    cfg=EcoConfig.from_dict(summary['config'])
    manifest=json.loads((directory/'manifest.json').read_text())
    for name,digest in manifest['artifact_sha256'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Artifact digest mismatch: {directory/name}')
    with np.load(directory/'checkpoint.npz',allow_pickle=False) as data:
        meta=json.loads(str(data['metadata'].item()))
        counts=np.bincount(data['strategy'],minlength=7)
        if data['genomes'].shape!=(int(counts.sum()),2,cfg.loci):raise ValueError('Genome/census shape')
        if len(np.unique(data['ids']))!=len(data['ids']):raise ValueError('Duplicate identities')
    previous=dict(zip(STRATEGIES,cfg.initial_counts)); first_zero={}; totals={s:defaultdict(float) for s in STRATEGIES}
    with (directory/'ledger.csv').open(newline='') as stream:ledger=list(csv.DictReader(stream))
    if len(ledger)!=summary['tick']*7:raise ValueError('Incomplete population ledger')
    for index,row in enumerate(ledger):
        s=row['strategy']; tick=int(row['tick']); x={k:float(v) for k,v in row.items() if k!='strategy'}
        if tick!=index//7+1 or s!=STRATEGIES[index%7]:raise ValueError('Ledger order')
        if int(x['start'])!=previous[s]:raise ValueError('Population continuity')
        expected=x['start']+x['realized_newborns']-sum(x[k] for k in ('survival_deaths','catastrophe_deaths','maintenance_deaths','capacity_adult_deaths'))-x.get('experimental_removals',0)
        if expected!=x['end']:raise ValueError('Population balance')
        if x['raw_newborns']!=x['funded_newborns']+x['resource_rejected']:raise ValueError('Funding balance')
        if x['funded_newborns']!=x['realized_newborns']+x['capacity_newborn_deaths']:raise ValueError('Recruitment balance')
        if cfg.initial_counts[STRATEGIES.index(s)] and x['end']==0:first_zero.setdefault(s,tick)
        previous[s]=int(x['end'])
        for key in meta['cumulative']:totals[s][key]+=x[key]
    max_residual=0.; stock=cfg.initial_resources
    with (directory/'resources.csv').open(newline='') as stream:resources=list(csv.DictReader(stream))
    if len(resources)!=summary['tick']:raise ValueError('Incomplete resource ledger')
    for row in resources:
        r={k:float(v) for k,v in row.items()}
        residual=r['before']+r['renewal']-r['catastrophe_loss']-r['overflow']-r['maintenance']-r['offspring']-r['after']
        max_residual=max(max_residual,abs(residual),abs(stock-r['before']))
        if not 0<=r['after']<=cfg.resource_capacity:raise ValueError('Resource bounds')
        stock=r['after']
    if max_residual>1e-7 or abs(stock-meta['resources'])>1e-7:raise ValueError('Resource balance/continuity')
    for i,s in enumerate(STRATEGIES):
        final=summary['strategies'][s]
        if previous[s]!=counts[i] or previous[s]!=final['population']:raise ValueError('Final census mismatch')
        if final['extinction_tick']!=first_zero.get(s):raise ValueError('First-zero extinction mismatch')
        for key,total in totals[s].items():
            if not math.isclose(total,final['cumulative'][key],rel_tol=1e-10,abs_tol=1e-7):raise ValueError('Cumulative mismatch')
    return {'directory':str(directory),'tick':summary['tick'],'population_rows':len(ledger),'resource_rows':len(resources),
            'max_resource_residual':max_residual,'all_artifact_hashes_valid':True,'all_balances_valid':True}


def analyze(folder, design):
    results=[]; checks=[]; groups=defaultdict(list)
    for planned in design['runs']:
        directory=folder/'runs'/planned['id']; check=inspect(directory);checks.append(check)
        summary=json.loads((directory/'summary.json').read_text())
        if summary['config']!=planned['config'] or not summary['complete']:raise ValueError('Incomplete/mismatched run')
        for s,entry in summary['strategies'].items():
            if not entry['initial_count']:continue
            event=entry['extinction_tick'] is not None
            result={'case':planned['case'],'environment':summary['config']['environment'],'seed':summary['config']['seed'],
                'strategy':s,'population':entry['population'],'extinct':event,'extinction_tick':entry['extinction_tick'],
                'observed_persistence':entry['extinction_tick'] if event else summary['tick'],
                'population_extinct':summary['total_population']==0,**entry['cumulative']}
            results.append(result);groups[(result['case'],result['environment'],s)].append(result)
    aggregate=[]
    for (case,environment,strategy),rows in groups.items():
        n=len(rows); events=sum(r['extinct'] for r in rows)
        aggregate.append({'case':case,'environment':environment,'strategy':strategy,'replicates':n,'extinctions':events,
            'extinction_probability':events/n,'extinction_ci95':wilson(events,n),
            'mean_final_population':float(np.mean([r['population'] for r in rows])),
            'mean_restricted_observed_persistence':float(np.mean([r['observed_persistence'] for r in rows])),
            'population_extinctions':sum(r['population_extinct'] for r in rows),
            'total_attempts':sum(r['attempts'] for r in rows),'total_mate_failures':sum(r['mate_failures'] for r in rows),
            'total_starvation_deaths':sum(r['maintenance_deaths'] for r in rows)})
    rng=np.random.default_rng(design['input']['analysis_seed']); contrasts=[]
    for environment in design['input']['environments']:
        for strategy in ('clone','two_parent'):
            for control in ('seven_neutral','seven_no_crossover'):
                a={r['seed']:r for r in groups[('seven_default',environment,strategy)]}
                b={r['seed']:r for r in groups[(control,environment,strategy)]}
                differences=np.array([b[s]['population']-a[s]['population'] for s in design['input']['seeds']])
                means=rng.choice(differences,(5000,len(differences))).mean(axis=1)
                contrasts.append({'environment':environment,'strategy':strategy,'contrast':control+' minus seven_default',
                    'mean_paired_final_count_difference':float(differences.mean()),'bootstrap_ci95':np.quantile(means,[.025,.975]).tolist()})
    write_csv(folder/'observations.csv',results);write_json(folder/'analysis.json',{'aggregate':aggregate,'paired_contrasts':contrasts})
    write_json(folder/'integrity.json',{'runs':checks,'all_passed':True})
    cells=[]
    for row in aggregate:
        if row['strategy'] not in ('clone','two_parent'):continue
        interval=row['extinction_ci95']
        values=(row['case'],row['environment'],row['strategy'],f"{row['extinctions']}/{row['replicates']}",
                f"{interval[0]:.3f}–{interval[1]:.3f}",f"{row['mean_final_population']:.2f}",f"{row['mean_restricted_observed_persistence']:.1f}")
        cells.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')
    document=('<!doctype html><meta charset="utf-8"><title>Survival calculation audit</title><style>body{font:15px Arial;max-width:1200px;margin:35px auto;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:8px}th{background:#edf3f6}</style>'
        '<h1>Survival calculation audit</h1><p>168 planned runs; 8 independent seeds per cell; 800 actual census updates. Synthetic, uncalibrated model; all added mating costs zero. All programs/results, including adverse cases, are in observations.csv and analysis.json.</p>'
        '<p>Alive groups are right-censored. Restricted persistence is min(extinction time,800), not the mean time among only extinct groups. Intervals are descriptive 95% Wilson bounds; eight seeds give wide uncertainty. These are not simultaneous confidence statements.</p>'
        '<table><tr><th>Case</th><th>Environment</th><th>Program</th><th>Extinctions</th><th>95% interval</th><th>Mean final count</th><th>Restricted persistence</th></tr>'+''.join(cells)+'</table>'
        '<p>See SURVIVAL_AUDIT_PROTOCOL.md for limits, including uniform repeated donors, focal-only fecundity selection, irreversible program loss, hard census culling, synthetic ages, and uncalibrated calendar time.</p>')
    (folder/'REPORT.html').write_text(document,encoding='utf-8')
    return aggregate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/survival_audit.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args(argv)
    values=json.loads(args.config.read_text()); design=plan(values)
    frozen={**design,'signature':signature(),'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'protocol_sha256':hashlib.sha256((ROOT/'SURVIVAL_AUDIT_PROTOCOL.md').read_bytes()).hexdigest()}
    folder=args.output
    if args.resume:
        if json.loads((folder/'plan.json').read_text())!=frozen:raise ValueError('Audit plan/source mismatch')
    else:
        folder.mkdir(parents=True,exist_ok=False);(folder/'runs').mkdir()
        write_json(folder/'plan.json',frozen);write_json(folder/'provenance.json',provenance())
        write_json(folder/'life_table.json',[life_table(EcoConfig(),score) for score in (1.,.7,.5)])
    if args.plan_only:
        print(json.dumps({'runs':len(design['runs']),'upper_individual_updates':design['upper_individual_updates'],'upper_locus_updates':design['upper_locus_updates']},indent=2));return
    elapsed=[]
    for i,planned in enumerate(design['runs'],1):
        directory=folder/'runs'/planned['id']; started=time.perf_counter()
        if directory.exists():
            inspect(directory)
            if not json.loads((directory/'summary.json').read_text())['complete']:raise ValueError('Incomplete run; inspect preserved directory before retry')
        else:simulate(EcoConfig.from_dict(planned['config']),directory,quiet=True)
        seconds=time.perf_counter()-started;elapsed.append(seconds)
        write_json(folder/'progress.json',{'completed':i,'planned':len(design['runs']),'last_seconds':seconds,'measured_seconds_this_invocation':sum(elapsed)})
        print(f"[{i}/{len(design['runs'])}] {planned['id']} {seconds:.2f}s",flush=True)
    aggregate=analyze(folder,design)
    print(f'PASS {len(design["runs"])} runs; all accounting/artifact checks. Report: {folder/"REPORT.html"}',flush=True)
    for row in aggregate:
        if row['strategy']=='two_parent':print(json.dumps(row),flush=True)


if __name__=='__main__':main()
