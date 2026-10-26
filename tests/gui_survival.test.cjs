// Run with: node --test tests/gui_survival.test.cjs
// No browser or frontend dependencies are needed for the survival contract.
const test = require('node:test');
const assert = require('node:assert/strict');
const {survivalSummary, survivalRecords, survivalCsv, comparisonRows, comparisonSeries} = require('../src/evolution_lab_v2/web/app.js');

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

const programs=['clone','two_parent','facultative','periodic','stress','four_parent','eight_parent'];
function isolatedFixture(){
  return session({settings:{duration_million_years:'100',steps:1000,comparison_mode:'isolated'},
    worlds:['static','periodic','autocorrelated'].flatMap((environment,envIndex)=>programs.map((program,index)=>({
      id:environment+'__'+program,environment,strategy_index:index,
      strategies:programs.map((strategy,i)=>({strategy,initial_count:i===index?32:0,population:i===index?100*envIndex+index+1:0,extinction_tick:null}))
    })))});
}
test('isolated comparisons choose each program from its own world in the selected environment',()=>{
  const rows=comparisonRows(isolatedFixture(),'periodic');
  assert.equal(rows.length,7);
  assert.deepEqual(rows.map(r=>r.row.population),[101,102,103,104,105,106,107]);
  assert.equal(rows[1].world.id,'periodic__two_parent');
});
test('isolated population and resource curves use world-specific history',()=>{
  const current=isolatedFixture();
  const populations={},resources={};
  for(const world of current.worlds){populations[world.id]=world.strategies.map(row=>row.population);resources[world.id]=world.strategy_index*10+(world.environment==='periodic'?1000:0);}
  const history=[{populations,resources}];
  assert.deepEqual(comparisonSeries(current,history,'periodic','population').map(line=>line.values[0]),[101,102,103,104,105,106,107]);
  assert.deepEqual(comparisonSeries(current,history,'periodic','resources').map(line=>line.values[0]),[1000,1010,1020,1030,1040,1050,1060]);
});
test('isolated survival export has 21 at-risk observations rather than 147 mostly absent programs',()=>{
  const records=survivalRecords(isolatedFixture());
  assert.equal(records.length,21);
  assert.equal(records[1].environment,'static');
  assert.equal(records[1].world,'static__two_parent');
  assert.equal(records[1].strategy,'two_parent');
  assert.ok(records.every(record=>record.status==='ongoing'&&record.extinction_tick===null));
});
test('shared competition retains its original seven population curves and three resource curves',()=>{
  const current=session({worlds:[{id:'static',strategies:programs.map((strategy,i)=>({strategy,population:i+1}))}]});
  const history=[{populations:{static:[1,2,3,4,5,6,7]},resources:{static:10,periodic:20,autocorrelated:30}}];
  assert.deepEqual(comparisonRows(current,'static').map(row=>row.row.population),[1,2,3,4,5,6,7]);
  assert.deepEqual(comparisonSeries(current,history,'static','population').map(line=>line.values[0]),[1,2,3,4,5,6,7]);
  assert.deepEqual(comparisonSeries(current,history,'static','resources').map(line=>line.values[0]),[10,20,30]);
});
