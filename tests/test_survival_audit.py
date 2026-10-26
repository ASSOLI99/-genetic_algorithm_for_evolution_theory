"""Independent stochastic life-cycle checks and persisted accounting audit controls."""
import csv
import hashlib
import json
import math

import numpy as np
import pytest

from evolution_lab_v2.artifacts import ROOT
from evolution_lab_v2.eco_config import EcoConfig
from evolution_lab_v2.eco_io import simulate
from evolution_lab_v2.ecology import advance, initialize, performance, state_digest, step
from tools.audit_survival import inspect, life_table, plan


def test_diagnostic_plan_stays_inside_declared_workload():
    values=json.loads((ROOT/'configs/survival_audit.json').read_text())
    frozen=plan(values)
    assert len(frozen['runs'])==168
    assert frozen['upper_individual_updates']==45_158_400
    assert frozen['upper_locus_updates']==722_534_400
    assert len({r['id'] for r in frozen['runs']})==168
    assert all(sum(r['config']['initial_counts'])==224 for r in frozen['runs'])
    assert all(r['config']['mating_cost']==r['config']['extra_parent_cost']==0 for r in frozen['runs'])


def test_newborn_life_table_matches_closed_form_and_birth_timing():
    cfg=EcoConfig(survival_probability=.5,maturity_age=1,senescence_age=1,senescence_rate=0,max_age=3,fecundity=.8)
    result=life_table(cfg)
    assert result['probability_to_first_breeding']==.5**2
    assert math.isclose(result['expected_low_density_focal_offspring'],.8*(.5**2+.5**3))
    assert result['rows'][0]['expected_focal_offspring']==0


def test_age_hazard_matches_binomial_expectations_and_forced_maximum_age():
    cfg=EcoConfig(seed=19011,steps=1,capacity=4000,initial_counts=(4000,0,0,0,0,0,0),
        fecundity=0,resource_capacity=100000,initial_resources=100000,record_parentage=False)
    state=initialize(cfg)
    ages=(0,8,12,16)
    state.birth_tick[:]=-np.repeat(ages,1000)
    step(state)
    for age in ages:
        observed=int(np.count_nonzero(state.birth_tick==-age))
        if age==16:
            assert observed==0
        else:
            p=.85*math.exp(-.06*max(0,age-8))
            assert abs(observed-1000*p)<4.5*math.sqrt(1000*p*(1-p))


def test_neutral_fecundity_has_no_hidden_two_parent_or_multiparent_divisor():
    output=np.zeros(7)
    for seed in range(128):
        state=initialize(EcoConfig(seed=52000+seed,steps=1,capacity=1000,initial_counts=(20,)*7,
            survival_probability=1,senescence_rate=0,selection_coefficient=0,
            resource_capacity=10000,initial_resources=10000,record_parentage=False))
        state.birth_tick[:]=-4
        step(state)
        np.testing.assert_array_equal(state.cumulative['realized_newborns'],state.cumulative['attempts'])
        output+=state.cumulative['realized_newborns']
    expected=128*20*.65
    assert (np.abs(output-expected)<4.5*math.sqrt(expected)).all()


def test_census_adult_retention_matches_conditional_hypergeometric_lottery():
    observed=expected=variance=0.
    for seed in range(80):
        state=initialize(EcoConfig(seed=58000+seed,steps=1,capacity=100,initial_counts=(14,)*7,
            survival_probability=1,senescence_rate=0,selection_coefficient=0,fecundity=4,
            resource_capacity=10000,initial_resources=10000,record_parentage=False))
        state.birth_tick[:]=-4
        step(state)
        newborns=sum(state.cumulative['funded_newborns']); total=98+newborns; p=98/total
        observed+=98-sum(state.cumulative['capacity_adult_deaths'])
        expected+=100*p
        variance+=100*p*(1-p)*(total-100)/(total-1)
        assert sum(state.cumulative['maintenance_deaths'])==0
        assert len(state.ids)==100
    assert abs(observed-expected)<4.5*math.sqrt(variance)


@pytest.mark.parametrize('parasite',['none','fixed','tracking'])
def test_performance_matches_independent_scalar_genome_formula(parasite):
    cfg=EcoConfig(parasite=parasite)
    state=initialize(cfg);target=state.environment[0]
    state.genomes[0]=target
    state.genomes[1]=1-target
    state.genomes[2,0]=target;state.genomes[2,1]=1-target
    expected=[]
    for genome in state.genomes:
        value=1.
        for locus in range(cfg.loci):
            differences=int(genome[0,locus]!=target[locus])+int(genome[1,locus]!=target[locus])
            value*=1-cfg.selection_coefficient*(1 if differences==2 else cfg.dominance if differences==1 else 0)
        if parasite!='none':
            matching=sum(int(genome[copy,locus]==state.parasite[locus-(cfg.loci-4)]) for copy in (0,1) for locus in range(cfg.loci-4,cfg.loci))/8
            value*=math.exp(-cfg.parasite_strength*matching)
        expected.append(value)
    np.testing.assert_allclose(performance(state),expected,rtol=1e-14,atol=1e-15)


def test_neutral_periodic_and_autocorrelated_targets_do_not_affect_demography():
    # These regimes have identical resource seasons. At s=0 their different
    # genetic targets must be inactive; they are not extra independent replicates.
    states=[advance(initialize(EcoConfig(environment=e,selection_coefficient=0,steps=30,record_parentage=False)))
            for e in ('periodic','autocorrelated')]
    assert not np.array_equal(states[0].environment,states[1].environment)
    assert state_digest(states[0])==state_digest(states[1])
    assert states[0].ledger==states[1].ledger


@pytest.mark.parametrize('damage',[None,'population','resources'])
def test_independent_saved_ledger_checker_detects_accounting_errors(tmp_path,damage):
    simulate(EcoConfig(steps=3,record_parentage=False),tmp_path/'run',quiet=True)
    folder=tmp_path/'run'
    if damage:
        name='ledger.csv' if damage=='population' else 'resources.csv'
        with (folder/name).open(newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        key='survival_deaths' if damage=='population' else 'maintenance'
        rows[0][key]=str(float(rows[0][key])+1)
        with (folder/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        # Repair its digest so the numerical checker, rather than a file hash,
        # must reject the inconsistent accounts.
        manifest=json.loads((folder/'manifest.json').read_text())
        manifest['artifact_sha256'][name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with pytest.raises(ValueError,match='balance'):inspect(folder)
    else:
        result=inspect(folder)
        assert result['all_balances_valid'] and result['all_artifact_hashes_valid']
