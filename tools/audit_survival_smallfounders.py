"""Supplemental persistence control; keeps the original diagnostic plan immutable."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from evolution_lab_v2.artifacts import ROOT, provenance, signature, write_json
from evolution_lab_v2.eco_analysis import wilson
from evolution_lab_v2.eco_config import EcoConfig, MAX_BATCH_CENSUS_TICKS, MAX_BATCH_LOCUS_TICKS
from evolution_lab_v2.eco_io import simulate
from tools.audit_survival import inspect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    primary=json.loads((args.primary/'plan.json').read_text())
    if not json.loads((args.primary/'integrity.json').read_text())['all_passed']:
        raise ValueError('Primary audit must be complete')
    if primary['input']['steps']!=800 or primary['input']['capacity']!=336:
        raise ValueError('Supplement requires the declared original design')
    configurations=[]
    for environment in primary['input']['environments']:
        for seed in primary['input']['seeds'][:6]:
            cfg=EcoConfig(seed=seed,steps=800,capacity=336,initial_counts=(0,32,0,0,0,0,0),
                          environment=environment,record_parentage=False,log_every=20,checkpoint_every=400)
            configurations.append(cfg)
    work=sum(c.steps*c.capacity for c in configurations)
    loci=sum(c.steps*c.capacity*c.loci for c in configurations)
    if work+primary['upper_individual_updates']>MAX_BATCH_CENSUS_TICKS or loci+primary['upper_locus_updates']>MAX_BATCH_LOCUS_TICKS:
        raise ValueError('Combined workload exceeds guards')
    folder=args.output;folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'plan.json',{'protocol':'SURVIVAL_SMALL_FOUNDERS_PROTOCOL.md','configs':[c.to_dict() for c in configurations],
        'primary_plan_sha256':hashlib.sha256((args.primary/'plan.json').read_bytes()).hexdigest(),
        'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'protocol_sha256':hashlib.sha256((ROOT/'SURVIVAL_SMALL_FOUNDERS_PROTOCOL.md').read_bytes()).hexdigest(),
        'source_signature':signature(),'combined_upper_individual_updates':work+primary['upper_individual_updates'],
        'combined_upper_locus_updates':loci+primary['upper_locus_updates'],'provenance':provenance()})
    rows=[];checks=[]
    for index,cfg in enumerate(configurations,1):
        directory=folder/f'{cfg.environment}_{cfg.seed}';started=time.perf_counter()
        summary=simulate(cfg,directory,quiet=True);checks.append(inspect(directory));entry=summary['strategies']['two_parent']
        rows.append({'environment':cfg.environment,'seed':cfg.seed,'extinction_tick':entry['extinction_tick'],'population':entry['population']})
        print(f'[{index}/{len(configurations)}] {directory.name} {time.perf_counter()-started:.2f}s',flush=True)
    aggregate=[]
    for environment in primary['input']['environments']:
        sample=[r for r in rows if r['environment']==environment];events=sum(r['extinction_tick'] is not None for r in sample)
        aggregate.append({'environment':environment,'replicates':len(sample),'extinctions':events,'extinction_ci95':wilson(events,len(sample)),
            'final_counts':[r['population'] for r in sample]})
    write_json(folder/'analysis.json',{'observations':rows,'aggregate':aggregate})
    write_json(folder/'integrity.json',{'all_passed':True,'runs':checks})
    print(json.dumps(aggregate,indent=2),flush=True)


if __name__=='__main__':main()
