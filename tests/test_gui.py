"""Live interface policy, reproducible intervention journal and loopback HTTP boundaries."""
import http.client
import json
from pathlib import Path
import re
import threading
import time

import numpy as np
import pytest

from evolution_lab_v2.gui_session import LabSession, SessionError, Settings, fingerprint, replay_session
from evolution_lab_v2.gui_server import LabServer
from dataclasses import replace
from evolution_lab_v2 import ecology
from evolution_lab_v2.eco_config import EcoConfig, STRATEGIES


def make_session(tmp_path, **kwargs):
    lab = LabSession(tmp_path/'runs')
    values = {'steps':100,'duration_million_years':'20','capacity':168,'seed':42}
    values.update(kwargs)
    lab.configure(values, acknowledge_resources=True)
    return lab


def test_resource_acknowledgement_and_calendar_resolution(tmp_path):
    lab = LabSession(tmp_path)
    with pytest.raises(SessionError, match='الموارد'):
        lab.configure({})
    assert not lab.worlds
    first = Settings.parse({'duration_million_years':'1','steps':100})
    second = Settings.parse({'duration_million_years':'1000000000000','steps':100})
    assert first.estimate()['upper_locus_updates']==second.estimate()['upper_locus_updates']
    assert second.estimate()['actual_steps']==100
    assert 'افتراضي' in second.estimate()['calendar_mapping']


@pytest.mark.parametrize('data', [{'steps':100000000}, {'steps':True}, {'capacity':5000},
    {'capacity':672,'steps':5000}, {'duration_million_years':'0.5'},
    {'duration_million_years':'NaN'}, {'mutation_rate':.9}, {'seed':-1},
    {'environments':['static','static']}, {'speed':1000000}, {'secret':'unknown'}])
def test_gui_rejects_invalid_or_unbounded_work(data):
    with pytest.raises(SessionError):
        Settings.parse(data)


def test_one_global_catastrophe_and_eight_million_year_gap_after_end(tmp_path):
    lab = make_session(tmp_path)
    event = lab.catastrophe({'kind':'drought','target':'static','duration_million_years':'1'})
    assert event['mortality']==0
    assert event['duration_ticks']==5
    assert event['next_allowed_tick']==45  # 1M duration + 8M gap, at .2M/update
    with pytest.raises(SessionError) as caught:
        lab.catastrophe({'kind':'bottleneck','target':'periodic'})
    assert caught.value.code=='catastrophe_active'
    lab.advance_ticks(5)
    assert lab.active is None
    with pytest.raises(SessionError) as caught:
        lab.catastrophe({'kind':'combined'})
    assert caught.value.code=='catastrophe_cooldown'
    lab.advance_ticks(39)
    with pytest.raises(SessionError) as caught:
        lab.catastrophe({})
    assert caught.value.code=='catastrophe_cooldown'
    lab.advance_ticks(1)
    second=lab.catastrophe({'kind':'bottleneck','duration_million_years':'1'})
    assert second['tick']==45
    assert second['resource_loss']==0 and second['renewal_factor']==1


def test_policy_rounds_up_at_coarse_calendar_resolution(tmp_path):
    lab = make_session(tmp_path, duration_million_years='3000')
    first = lab.catastrophe({'duration_million_years':'1'})
    assert first['duration_ticks']==1
    assert first['next_allowed_tick']==2
    assert lab.settings.million_years_at(first['next_allowed_tick']-first['end_tick'])>=8


def test_double_click_is_serialized_by_backend_lock(tmp_path):
    lab = make_session(tmp_path)
    results=[]
    def inject():
        try:
            results.append(lab.catastrophe({})['tick'])
        except SessionError as exc:
            results.append(exc.code)
    threads=[threading.Thread(target=inject) for _ in range(4)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert results.count(0)==1
    assert results.count('catastrophe_active')==3
    assert len(lab.actions)==1


def test_targeted_disaster_does_not_modify_other_worlds(tmp_path):
    first=make_session(tmp_path/'a')
    control=make_session(tmp_path/'b')
    first.catastrophe({'kind':'bottleneck','target':'static','mortality':1,'duration_million_years':'1'})
    first.advance_ticks(1)
    control.advance_ticks(1)
    assert len(first.worlds['static'].ids)==0
    for name in ('periodic','autocorrelated'):
        assert fingerprint(first.worlds[name])==fingerprint(control.worlds[name])


@pytest.mark.parametrize('pending',[False,True])
def test_export_and_journal_replay_are_exact(tmp_path,pending):
    lab=make_session(tmp_path)
    lab.catastrophe({'kind':'combined','target':'static','duration_million_years':'1','mortality':.2})
    lab.advance_ticks(45)
    lab.control('pause')
    lab.catastrophe({'kind':'drought','target':'all','duration_million_years':'2','resource_loss':.2})
    if not pending:lab.advance_ticks(8)
    saved=lab.export()
    folder=Path(saved['directory'])
    assert folder.with_suffix('.zip').exists()
    assert (folder/'REPORT.html').exists()
    restored=replay_session(folder/'session.json')
    for name in lab.worlds:
        assert fingerprint(restored.worlds[name])==fingerprint(lab.worlds[name])
        assert restored.worlds[name].ledger==lab.worlds[name].ledger
        assert restored.worlds[name].resource_ledger==lab.worlds[name].resource_ledger
    assert restored.actions==lab.actions
    assert restored.active==lab.active


def test_pause_freezes_clock_and_disconnected_client_auto_pauses(tmp_path):
    lab=LabSession(tmp_path/'out')
    lab.configure({'steps':100,'capacity':168,'speed':20},True,background=True)
    try:
        lab.control('pause')
        tick=lab.tick
        time.sleep(.13)
        assert lab.tick==tick
        lab.control('resume')
        with lab.lock:lab.last_client=time.monotonic()-30
        time.sleep(.15)
        assert lab.status=='paused'
        assert 'انقطاع' in lab.error
    finally:
        lab.control('stop')
        lab.thread.join(timeout=2)
    assert lab.latest_export


def test_snapshot_dots_are_actual_individuals_and_incremental_history(tmp_path):
    lab=make_session(tmp_path)
    lab.advance_ticks(3)
    snapshot=lab.snapshot(after=1)
    assert [r['tick'] for r in snapshot['history']]==[2,3]
    for world in snapshot['worlds']:
        state=lab.worlds[world['id']]
        assert len(world['dots'])<=140
        for dot in world['dots']:
            index=int(np.flatnonzero(state.ids==dot['id'])[0])
            assert dot['strategy']==state.strategy[index]
            assert dot['genome']==''.join(str(int(b)) for b in state.genomes[index].ravel())


@pytest.fixture
def http_lab(tmp_path):
    server=LabServer(('127.0.0.1',0),tmp_path/'exports')
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield server
    if server.lab.status in ('running','paused'):server.lab.control('stop')
    server.shutdown();server.server_close();thread.join(timeout=2)


def request(server,path,body=None,headers=None):
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
    default={'Content-Type':'application/json','X-Evolution-Token':server.token}
    default.update(headers or {})
    connection.request('POST' if body is not None else 'GET',path,
                       json.dumps(body) if body is not None else None,default)
    response=connection.getresponse();raw=response.read();status=response.status
    connection.close()
    return status,raw


def test_http_interface_static_files_and_resource_gate(http_lab):
    status,page=request(http_lab,'/')
    assert status==200 and '__TOKEN__' not in page.decode()
    assert http_lab.token in page.decode()
    for name in ('/app.js','/style.css'):
        assert request(http_lab,name)[0]==200
    assert request(http_lab,'/api/estimate',{'steps':100})[0]==200
    status,data=request(http_lab,'/api/start',{'settings':{'steps':100}})
    assert status==400 and json.loads(data)['error']=='resources_not_acknowledged'
    assert not http_lab.lab.worlds


def test_http_rejects_cross_origin_bad_token_and_file_traversal(http_lab):
    assert request(http_lab,'/api/control',{'action':'speed','speed':10}, {'Origin':'https://example.com'})[0]==403
    assert request(http_lab,'/api/control',{'action':'speed','speed':10}, {'X-Evolution-Token':'bad'})[0]==403
    assert request(http_lab,'/api/state',headers={'Host':'evil.example'})[0]==403
    assert request(http_lab,'/../AGENTS.md')[0]==404
    assert request(http_lab,'/api/state?after=NaN')[0]==400


def test_http_full_live_flow_and_export(http_lab):
    status,data=request(http_lab,'/api/start',{'settings':{'steps':100,'capacity':168,'speed':1},'acknowledge_resources':True})
    assert status==200
    assert request(http_lab,'/api/control',{'action':'pause'})[0]==200
    assert request(http_lab,'/api/catastrophe',{'duration_million_years':'1'})[0]==200
    status,body=request(http_lab,'/api/catastrophe',{})
    assert status==409 and json.loads(body)['error']=='catastrophe_active'
    status,body=request(http_lab,'/api/export',{})
    assert status==200
    saved=json.loads(body)
    assert request(http_lab,saved['download'])[1][:2]==b'PK'
    assert b'<table>' in request(http_lab,saved['report'])[1]
    assert request(http_lab,'/api/control',{'action':'stop'})[0]==200


def test_http_removal_route_reserves_applies_and_exports_separate_cause(http_lab):
    lab=http_lab.lab
    lab.configure({'steps':100,'capacity':168,'seed':42},True)
    lab.control('pause')
    body={'strategy':'two_parent','target':'static'}
    assert request(http_lab,'/api/remove-program',body,{'X-Evolution-Token':'bad'})[0]==403
    status,data=request(http_lab,'/api/remove-program',body)
    event=json.loads(data)
    assert status==200 and event['scheduled_count']==16 and event['execution_tick']==1
    assert request(http_lab,'/api/remove-program',body)[0]==409
    assert lab.tick==0 and np.count_nonzero(lab.worlds['static'].strategy==1)==16
    lab.advance_ticks(1)
    status,data=request(http_lab,'/api/state')
    observed=json.loads(data)['worlds'][0]['strategies'][1]
    assert status==200 and observed['population']==0
    assert observed['cumulative']['experimental_removals']==16
    assert observed['extinction_cause']=='experimental_removal'
    status,data=request(http_lab,'/api/export',{})
    assert status==200
    saved=json.loads(data)
    assert request(http_lab,saved['download'])[1][:2]==b'PK'
    assert 'إزالة تجريبية' in request(http_lab,saved['report'])[1].decode('utf-8')


def test_isolated_worlds_have_equal_budgets_and_paired_founders(tmp_path):
    lab=make_session(tmp_path,comparison_mode='isolated',initial_population=32,
                     resource_capacity=400,initial_resources=300,resource_renewal=40)
    assert len(lab.worlds)==21
    reference=lab.worlds['static__clone']
    for environment in ('static','periodic','autocorrelated'):
        states=[lab.worlds[environment+'__'+s] for s in STRATEGIES]
        for i,state in enumerate(states):
            assert len(state.ids)==32 and np.all(state.strategy==i)
            assert state.config.capacity==168
            assert (state.config.resource_capacity,state.resources,state.config.resource_renewal)==(400,300,40)
            np.testing.assert_array_equal(state.genomes,reference.genomes)
            np.testing.assert_array_equal(state.birth_tick,reference.birth_tick)
            np.testing.assert_array_equal(state.mating_type,reference.mating_type)
            np.testing.assert_array_equal(state.environment,states[0].environment)
    estimate=lab.settings.estimate()
    assert estimate['worlds']==21 and estimate['total_initial_population']==672
    assert estimate['total_initial_resources']==6300
    assert estimate['upper_individual_updates']==100*168*21


def test_competition_defaults_preserve_original_engine_configuration(tmp_path):
    lab=make_session(tmp_path)
    control=ecology.initialize(EcoConfig(seed=42,steps=100,capacity=168,initial_counts=(16,)*7,
        record_parentage=False,log_every=5,catastrophe_regime='combined',catastrophe_probability=0,
        resource_capacity=300.0,initial_resources=300.0,resource_renewal=75.0))
    lab.advance_ticks(5);ecology.advance(control,until=5)
    assert fingerprint(lab.worlds['static'])==fingerprint(control)


def test_isolated_worlds_cannot_share_food_or_recruit_other_programs(tmp_path):
    lab=make_session(tmp_path/'a',comparison_mode='isolated')
    control=make_session(tmp_path/'b',comparison_mode='isolated')
    starving=lab.worlds['static__clone']
    starving.resources=0;starving.config=replace(starving.config,resource_renewal=0)
    lab.advance_ticks(4);control.advance_ticks(4)
    assert len(starving.ids)==0
    for name,state in lab.worlds.items():
        if name=='static__clone':continue
        assert fingerprint(state)==fingerprint(control.worlds[name])
        expected=STRATEGIES.index(name.split('__')[1])
        assert np.all(state.strategy==expected)


def test_isolation_enforces_identical_global_intervention_and_existing_spacing(tmp_path):
    lab=make_session(tmp_path,comparison_mode='isolated',initial_resources=300)
    with pytest.raises(SessionError) as caught:lab.catastrophe({'target':'static'})
    assert caught.value.code=='isolated_global_event'
    event=lab.catastrophe({'target':'all','kind':'combined','duration_million_years':'1','mortality':.4})
    assert event['duration_ticks']==5 and event['next_allowed_tick']==45
    lab.advance_ticks(1)
    for state in lab.worlds.values():
        assert len(state.catastrophe_events)==1
        applied=state.catastrophe_events[0]
        assert applied['tick']==1 and applied['regime']=='combined'
        assert applied['stock_lost']==225
        assert state.config.catastrophe_mortality==.4
    with pytest.raises(SessionError) as caught:lab.catastrophe({})
    assert caught.value.code=='catastrophe_active'
    lab.advance_ticks(4)
    with pytest.raises(SessionError) as caught:lab.catastrophe({})
    assert caught.value.code=='catastrophe_cooldown'


@pytest.mark.parametrize('values',[
    {'comparison_mode':'unknown'}, {'comparison_mode':'isolated','compatibility_scope':'all_mixing'},
    {'initial_population':25,'capacity':168}, {'initial_population':True}, {'initial_population':0},
    {'comparison_mode':'isolated','initial_population':169,'capacity':168},
    {'initial_resources':401,'resource_capacity':400}, {'resource_capacity':0}, {'resource_renewal':float('nan')},
    {'comparison_mode':'isolated','steps':1800},
])
def test_isolation_and_common_budget_validation(values):
    with pytest.raises(SessionError):Settings.parse(values)


def test_ledger_budget_counts_all_twenty_one_worlds():
    estimate=Settings.parse({'comparison_mode':'isolated','steps':1700}).estimate()
    assert estimate['retained_ledger_rows']==249900
    assert Settings.parse({'steps':5000}).estimate()['retained_ledger_rows']==105000


def test_isolated_export_replay_and_report_risk_sets(tmp_path):
    lab=make_session(tmp_path,comparison_mode='isolated')
    lab.catastrophe({'kind':'combined','duration_million_years':'1','mortality':.2})
    lab.advance_ticks(12)
    saved=lab.export();folder=Path(saved['directory'])
    manifest=json.loads((folder/'session.json').read_text())
    assert manifest['schema']=='interactive-3' and len(manifest['world_layout'])==21
    restored=replay_session(folder/'session.json')
    for name,state in lab.worlds.items():
        assert fingerprint(state)==fingerprint(restored.worlds[name])
        assert state.ledger==restored.worlds[name].ledger
    report=(folder/'REPORT.html').read_text(encoding='utf-8')
    assert report.count('<tr>')==46  # 21 worlds + 21 programs + one intervention + three headers
    assert 'None' not in report
    restart=LabSession(lab.output_root)
    assert restart.exports[saved['id']].is_file()


def test_export_registry_ignores_traversal_and_wrong_prefix(tmp_path):
    (tmp_path/'.gui-export-index.json').write_text(json.dumps({'a'*32:'../secrets.zip','b'*32:'gui_20261026_120000_aaaaaaaa.zip'}))
    assert not LabSession(tmp_path).exports
