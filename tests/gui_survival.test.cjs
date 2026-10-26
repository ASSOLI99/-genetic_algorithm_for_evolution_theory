// Run with: node --test tests/gui_survival.test.cjs
// No browser or frontend dependencies are needed for the survival contract.
const test = require('node:test');
const assert = require('node:assert/strict');
const {survivalSummary, survivalRecords, survivalCsv} = require('../src/evolution_lab_v2/web/app.js');

const session = (overrides={}) => ({status:'running',tick:500,
  settings:{duration_million_years:'100',steps:1000},...overrides});
const row = (overrides={}) => ({strategy:'two_parent',population:0,extinction_tick:137,...overrides});

test('extinction uses the exact recorded census, even between sparse metric samples',()=>{
  const result=survivalSummary(row(),session());
  assert.equal(result.status,'extinct');
  assert.equal(result.event_observed,true);
  assert.equal(result.observed_tick,137);
  assert.equal(result.extinction_million_years,13.7);
  assert.deepEqual(result,survivalSummary(row(),session({tick:900,status:'completed'})));
});
test('a valid zero extinction tick is preserved',()=>{
  const result=survivalSummary(row({extinction_tick:0}),session());
  assert.equal(result.event_observed,true);
  assert.equal(result.observed_tick,0);
  assert.equal(result.extinction_million_years,0);
});
test('living populations at completion are censored, without an invented extinction',()=>{
  const result=survivalSummary(row({population:10,extinction_tick:null}),session({status:'completed',tick:1000}));
  assert.equal(result.status,'censored');
  assert.equal(result.observed_million_years,100);
  assert.equal(result.event_observed,false);
  assert.equal(result.extinction_tick,null);
  assert.equal(result.extinction_million_years,null);
});
test('early stop uses elapsed observation, not the requested horizon',()=>{
  const result=survivalSummary(row({population:10,extinction_tick:null}),session({status:'stopped',tick:230}));
  assert.equal(result.status,'censored');
  assert.equal(result.observed_million_years,23);
});
test('paused living populations remain ongoing',()=>{
  const result=survivalSummary(row({population:10,extinction_tick:null}),session({status:'paused',tick:23}));
  assert.equal(result.status,'ongoing');
  assert.equal(result.observed_tick,23);
});
test('fine display clocks retain sub-million timing',()=>{
  const result=survivalSummary(row({extinction_tick:1}),session({settings:{duration_million_years:'1',steps:5000}}));
  assert.equal(result.extinction_million_years,.0002);
});
test('missing observations are unknown instead of a false survival or extinction',()=>{
  assert.equal(survivalSummary(undefined,session()),null);
  assert.equal(survivalSummary(row(),{}),null);
  const result=survivalSummary(row({extinction_tick:null}),session());
  assert.equal(result.status,'unknown');
  assert.equal(result.observed_tick,null);
});
test('records and CSV keep environment-specific extinction and censoring',()=>{
  const input=session({status:'completed',tick:1000,worlds:[
    {id:'static',strategies:[row()]},
    {id:'periodic',strategies:[row({population:20,extinction_tick:null})]}
  ]});
  const records=survivalRecords(input);
  assert.equal(records.length,2);
  assert.equal(records[0].environment,'static');
  assert.equal(records[0].extinction_tick,137);
  assert.equal(records[1].status,'censored');
  assert.equal(records[1].extinction_tick,null);
  const csv=survivalCsv(input);
  assert.ok(csv.startsWith('\uFEFFenvironment,strategy,'));
  assert.ok(csv.includes('"true","137","13.7","137","13.7"'));
  assert.ok(csv.includes('"false","1000","100","",""'));
  assert.ok(csv.includes('uncalibrated_scenario_years'));
});
