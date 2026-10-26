"""Intentional removal has distinct accounting, exact timing and reversible replay."""
from pathlib import Path

import numpy as np
import pytest

from evolution_lab_v2.eco_config import EcoConfig
from evolution_lab_v2.ecology import initialize, step
from evolution_lab_v2.eco_io import load_checkpoint
from evolution_lab_v2.gui_session import LabSession, SessionError, fingerprint, replay_session
from tools.audit_survival import inspect


def session(tmp_path,**kwargs):
    lab=LabSession(tmp_path/'runs')
    lab.configure({'steps':100,'duration_million_years':'20','capacity':168,'seed':42,**kwargs},True)
    return lab


def test_removal_saves_future_maintenance_without_refunding_food():
    cfg=EcoConfig(steps=2,fecundity=0,survival_probability=1,senescence_rate=0,
                  initial_resources=100,resource_capacity=200,resource_renewal=0)
    treated,control=initialize(cfg),initialize(cfg)
    treated.birth_tick[:]=-4;control.birth_tick[:]=-4
    step(treated,remove_programs=(1,));step(control)
    assert len(treated.ids)==192 and len(control.ids)==224
    assert not np.any(treated.strategy==1)
    assert treated.cumulative['experimental_removals'][1]==32
    assert sum(treated.cumulative['survival_deaths'])==0
    assert treated.resources==52 and control.resources==44  # exactly eight saved maintenance units
    assert treated.resource_ledger[0]['before']==control.resource_ledger[0]['before']==100
    assert treated.ledger[1]['start']==32 and treated.ledger[1]['end']==0
    assert treated.extinct['two_parent']==1
    assert any(e['event']=='experimental_removal' and e['removed_count']==32 for e in treated.events)


@pytest.mark.parametrize('invalid',[(1,1),(-1,),(7,),(True,),('clone',),None])
def test_bad_core_removal_is_rejected_before_state_changes(invalid):
    state=initialize(EcoConfig(steps=1));before=fingerprint(state)
    with pytest.raises(ValueError):step(state,remove_programs=invalid)
    assert fingerprint(state)==before


def test_queued_single_world_removal_does_not_touch_other_worlds(tmp_path):
    lab=session(tmp_path/'a');control=session(tmp_path/'b')
    lab.control('pause');before=fingerprint(lab.worlds['static'])
    event=lab.remove_program({'strategy':'clone','target':'static'})
    assert event['scheduled_count']==16 and event['execution_tick']==1
    assert fingerprint(lab.worlds['static'])==before and lab.tick==0
    with pytest.raises(SessionError):lab.remove_program({'strategy':'two_parent','target':'static'})
    lab.advance_ticks(1);control.advance_ticks(1)
    assert lab.pending_removal is None and not np.any(lab.worlds['static'].strategy==0)
    assert lab.worlds['static'].cumulative['experimental_removals'][0]==16
    assert lab.worlds['static'].extinct['clone']==1
    for name in ('periodic','autocorrelated'):assert fingerprint(lab.worlds[name])==fingerprint(control.worlds[name])
    with pytest.raises(SessionError) as error:lab.remove_program({'strategy':'clone','target':'static'})
    assert error.value.code=='program_absent'


def test_global_scope_removes_only_the_selected_program(tmp_path):
    lab=session(tmp_path)
    event=lab.remove_program({'strategy':'eight_parent','target':'all'})
    assert event['scheduled_count']==48 and len(event['counts_by_world'])==3
    lab.advance_ticks(1)
    for world in lab.worlds.values():
        assert not np.any(world.strategy==6)
        assert world.cumulative['experimental_removals']==[0,0,0,0,0,0,16]


def test_removal_is_separate_from_catastrophe_spacing_but_cannot_overlap(tmp_path):
    lab=session(tmp_path)
    lab.remove_program({'strategy':'clone','target':'static'})
    with pytest.raises(SessionError):lab.catastrophe({})
    lab.advance_ticks(1)
    assert lab.next_allowed_tick==0
    event=lab.catastrophe({'kind':'drought','duration_million_years':'.2'})
    with pytest.raises(SessionError):lab.remove_program({'strategy':'two_parent','target':'static'})
    lab.advance_ticks(1)
    assert lab.tick<event['next_allowed_tick']
    lab.remove_program({'strategy':'two_parent','target':'static'})
    assert lab.next_allowed_tick==event['next_allowed_tick']


@pytest.mark.parametrize('values',[{}, {'strategy':'clone'}, {'strategy':'unknown','target':'all'},
    {'strategy':'clone','target':'missing'}, {'strategy':'clone','target':'static','count':1}])
def test_bad_gui_removal_input_is_rejected(tmp_path,values):
    lab=session(tmp_path)
    with pytest.raises(SessionError):lab.remove_program(values)
    assert not lab.actions and lab.pending_removal is None


def test_removal_is_unavailable_in_isolation_and_after_stop(tmp_path):
    lab=session(tmp_path,comparison_mode='isolated',environments=['static'])
    with pytest.raises(SessionError):lab.remove_program({'strategy':'clone','target':'all'})
    lab.status='completed'
    with pytest.raises(SessionError):lab.remove_program({'strategy':'clone','target':'all'})


@pytest.mark.parametrize('pending',[False,True])
def test_mixed_intervention_replay_and_checkpoints_preserve_cause(tmp_path,pending):
    lab=session(tmp_path)
    lab.remove_program({'strategy':'two_parent','target':'static'});lab.advance_ticks(1)
    lab.catastrophe({'kind':'drought','duration_million_years':'.2'});lab.advance_ticks(1)
    lab.remove_program({'strategy':'four_parent','target':'all'})
    if not pending:lab.advance_ticks(3)
    saved=lab.export();folder=Path(saved['directory'])
    restored=replay_session(folder/'session.json')
    assert restored.actions==lab.actions and restored.pending_removal==lab.pending_removal
    for name,world in lab.worlds.items():
        assert fingerprint(world)==fingerprint(restored.worlds[name])
        checkpoint=load_checkpoint(folder/name/'checkpoint.npz',world.config)
        assert checkpoint.ledger==world.ledger and checkpoint.events==world.events
        assert inspect(folder/name)['all_balances_valid']
        if not pending:
            step(checkpoint);step(restored.worlds[name])
            assert fingerprint(checkpoint)==fingerprint(restored.worlds[name])
    metrics=lab.snapshot()['worlds'][0]['strategies'][1]
    assert metrics['extinction_cause']=='experimental_removal'
    assert 'إزالة تجريبية' in (folder/'REPORT.html').read_text(encoding='utf-8')


def test_removing_the_last_population_records_intentional_loss(tmp_path):
    lab=session(tmp_path,environments=['static'])
    world=lab.worlds['static'];world.strategy[:]=0  # explicit synthetic single-program state for this edge case
    event=lab.remove_program({'strategy':'clone','target':'all'})
    lab.advance_ticks(1)
    assert event['scheduled_count']==112 and lab.status=='extinct'
    assert not len(world.ids) and world.cumulative['experimental_removals'][0]==112
