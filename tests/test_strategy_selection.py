"""Starting membership is a model input, not a hidden filter or removal event."""
import json
from pathlib import Path

import pytest

from evolution_lab_v2.eco_config import STRATEGIES
from evolution_lab_v2.gui_session import LabSession, SessionError, Settings, fingerprint, replay_session


def test_missing_and_explicit_all_selection_preserve_existing_defaults():
    previous=Settings.parse({'steps':100,'capacity':168})
    explicit=Settings.parse({'steps':100,'capacity':168,'competition_strategies':list(STRATEGIES)})
    assert previous==explicit
    for config in previous.configs().values():
        assert config.initial_counts==(16,)*7
    assert previous.estimate()['total_initial_population']==336


@pytest.mark.parametrize('selected',[[],None,'clone',['clone','clone'],['unknown'],[True],[0],[{}]])
def test_invalid_or_empty_selection_is_rejected_before_initialization(tmp_path,selected):
    lab=LabSession(tmp_path)
    with pytest.raises(SessionError) as error:
        lab.configure({'competition_strategies':selected},True)
    assert error.value.code=='invalid_strategies'
    assert not lab.worlds and lab.status=='idle'


def test_selection_is_canonical_and_serialized_for_reproducibility(tmp_path):
    first=LabSession(tmp_path/'a');second=LabSession(tmp_path/'b')
    common={'steps':100,'capacity':168,'seed':42}
    first.configure({**common,'competition_strategies':['stress','two_parent']},True)
    second.configure({**common,'competition_strategies':['two_parent','stress']},True)
    assert first.settings.to_dict()['competition_strategies']==['two_parent','stress']
    first.advance_ticks(30);second.advance_ticks(30)
    for name in first.worlds:assert fingerprint(first.worlds[name])==fingerprint(second.worlds[name])


def test_excluded_programs_have_no_founders_births_or_extinction_events(tmp_path):
    lab=LabSession(tmp_path)
    estimate=lab.configure({'steps':100,'capacity':168,'seed':42,
        'competition_strategies':['clone','two_parent'],'initial_population':20,
        'initial_resources':210,'resource_capacity':300,'resource_renewal':40},True)
    assert estimate['participating_strategy_count']==2
    assert estimate['active_strategies']==['clone','two_parent']
    assert estimate['total_initial_population']==120
    assert estimate['total_initial_resources']==630
    for world in lab.worlds.values():
        assert world.config.initial_counts==(20,20,0,0,0,0,0)
        assert len(world.founders)==40 and len(world.ids)==40
        assert set(row['strategy'] for row in world.founders)=={'clone','two_parent'}
        assert (world.resources,world.config.resource_capacity,world.config.resource_renewal)==(210,300,40)
    lab.advance_ticks(100)
    for world in lab.worlds.values():
        assert set(world.strategy)<=set((0,1))
        assert not set(world.extinct)&set(STRATEGIES[2:])
        assert not any(e.get('strategy') in STRATEGIES[2:] for e in world.events)
        assert sum(world.cumulative['experimental_removals'])==0
        assert all(sum(world.cumulative[key][2:])==0 for key in world.cumulative)


@pytest.mark.parametrize('selection,count', [(['two_parent'],168),(['clone','stress'],84),(list(STRATEGIES),24)])
def test_founder_limit_uses_selected_program_count(selection,count):
    cfg=Settings.parse({'capacity':168,'steps':100,'competition_strategies':selection,'initial_population':count})
    assert all(sum(c.initial_counts)==168 for c in cfg.configs().values())
    with pytest.raises(SessionError):Settings.parse({**cfg.to_dict(),'initial_population':count+1})


def test_isolation_keeps_all_seven_separate_worlds_and_its_original_budgets():
    cfg=Settings.parse({'comparison_mode':'isolated','competition_strategies':['clone'],
        'steps':100,'capacity':168,'initial_population':40})
    assert cfg.active_strategies==STRATEGIES and len(cfg.configs())==21
    assert cfg.estimate()['total_initial_population']==840
    assert all(sum(c.initial_counts)==40 for c in cfg.configs().values())


def test_subset_export_replay_and_pending_removal_preserve_selection(tmp_path):
    lab=LabSession(tmp_path)
    lab.configure({'steps':100,'capacity':168,'seed':42,'competition_strategies':['clone','two_parent']},True)
    lab.advance_ticks(3)
    lab.remove_program({'strategy':'two_parent','target':'static'})
    saved=lab.export();folder=Path(saved['directory'])
    restored=replay_session(folder/'session.json')
    assert restored.settings.competition_strategies==('clone','two_parent')
    assert restored.pending_removal==lab.pending_removal
    lab.advance_ticks(10);restored.advance_ticks(10)
    for name in lab.worlds:assert fingerprint(lab.worlds[name])==fingerprint(restored.worlds[name])
    report=(folder/'REPORT.html').read_text(encoding='utf-8')
    assert report.count('<tr>')==13  # three worlds, six at-risk program rows, one action, three headers
    manifest=json.loads((folder/'session.json').read_text())
    manifest['settings']['competition_strategies']=['clone','stress']
    invalid=folder/'tampered.json';invalid.write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='layout'):replay_session(invalid)
