'use strict';
// Survival is observed from the start of this session, at census-update resolution.
// A living group is right-censored; the current time is not an extinction time.
function survivalSummary(row, session) {
  if (!row || !session?.settings) return null;
  const event = Number.isInteger(row.extinction_tick);
  const observed = event ? row.extinction_tick : row.population > 0 ? session.tick : null;
  const yearsAt = tick => tick === null ? null : tick * Number(session.settings.duration_million_years) / session.settings.steps;
  return {
    status: event ? 'extinct' : row.population === 0 ? 'unknown' : ['running','paused'].includes(session.status) ? 'ongoing' : 'censored',
    event_observed: event,
    observed_tick: observed,
    observed_million_years: yearsAt(observed),
    extinction_tick: event ? row.extinction_tick : null,
    extinction_million_years: event ? yearsAt(row.extinction_tick) : null
  };
}
function survivalRecords(session) {
  return (session?.worlds || []).flatMap(world => world.strategies.map(row => ({
    environment: world.id, strategy: row.strategy, population: row.population,
    ...survivalSummary(row, session), clock: 'uncalibrated_scenario_years'
  })));
}
function survivalCsv(session) {
  const columns = ['environment','strategy','population','status','event_observed','observed_tick',
    'observed_million_years','extinction_tick','extinction_million_years','clock'];
  const cell = value => '"'+String(value ?? '').replaceAll('"','""')+'"';
  return '\uFEFF'+[columns.join(','), ...survivalRecords(session).map(row => columns.map(key => cell(row[key])).join(','))].join('\r\n')+'\r\n';
}
if (typeof module !== 'undefined' && module.exports) module.exports = {survivalSummary, survivalRecords, survivalCsv};
if (typeof document !== 'undefined') {
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="evolution-token"]').content;
const ENV = [{id:'static',label:'بيئة ثابتة',code:'ENV / 01',color:'#63e6be'}, {id:'periodic',label:'بيئة دورية',code:'ENV / 02',color:'#ffd166'}, {id:'autocorrelated',label:'بيئة متقلبة',code:'ENV / 03',color:'#a8a4ff'}];
const LABELS = ['لاجنسي','جنسي بأبوين','اختياري','دوري','عند الضغط','أربعة آباء','ثمانية آباء'];
const COLORS = ['#63e6be','#6ca7ff','#ffd166','#bd9bff','#ff9b70','#f58abb','#54cfdb'];
const KINDS = {bottleneck:'صدمة سكانية',drought:'جفاف',combined:'كارثة مركّبة'};
const STATES = {idle:'جاهز للرصد',running:'المحاكاة تعمل',paused:'متوقفة مؤقتًا',stopped:'تم إنهاء التجربة',completed:'اكتمل الأفق المحدد',extinct:'انقرضت التجمعات',failed:'تعذّر إكمال التشغيل'};
const fmt = new Intl.NumberFormat('en-US', {maximumFractionDigits:1});
const count = new Intl.NumberFormat('en-US', {maximumFractionDigits:0});
const short = new Intl.NumberFormat('en-US', {notation:'compact',maximumFractionDigits:1});
const survivalNumber = new Intl.NumberFormat('en-US', {maximumSignificantDigits:8});
let state = null, history = [], cursor = -1, sessionId = null, focus = 'static', chartMode = 'population', kind = 'combined';
let pollBusy = false, pendingSettings = null, toastTimer = null, exporting = false;
let lastEventKey = '';
const terrains = new Map(), hitPoints = new Map();

function notify(message, error=false) {
  $('toast').textContent = message;
  $('toast').className = 'visible'+(error?' error':'');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').className='', 5500);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache:'no-store'} : {
    method:'POST',headers:{'Content-Type':'application/json','X-Evolution-Token':token},body:JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'تعذر الاتصال بالمختبر.');
  return result;
}
function settings() {
  return {duration_million_years:$('duration').value,steps:Number($('steps').value),capacity:Number($('capacity').value),
    seed:Number($('seed').value),mutation_rate:Number($('mutation').value),mating_cost:Number($('matingCost').value),
    extra_parent_cost:Number($('partnerCost').value),speed:Number($('speed').value),
    recombination_rate:Number($('recombination').value),selection_coefficient:Number($('selection').value),
    compatibility_scope:$('compatibility').value,multiparent_mechanism:$('inheritance').value,parasite:$('parasite').value};
}
function restoreSessionSettings(values) {
  const fields={duration:'duration_million_years',steps:'steps',capacity:'capacity',seed:'seed',mutation:'mutation_rate',
    matingCost:'mating_cost',partnerCost:'extra_parent_cost',recombination:'recombination_rate',selection:'selection_coefficient',
    compatibility:'compatibility_scope',inheritance:'multiparent_mechanism',parasite:'parasite'};
  for(const [id,key] of Object.entries(fields)){
    const field=$(id),value=String(values[key]);
    if(field.tagName==='SELECT'&&![...field.options].some(option=>option.value===value))field.add(new Option(value+' · إعداد الجلسة',value));
    field.value=value;
  }
  updateSettingsHint();
}
function updateSettingsHint() {
  const max = Math.min(5000,Math.floor(2000000/Number($('capacity').value)),Math.floor(50000000/(Number($('capacity').value)*16)));
  $('steps').max = Math.floor(max/100)*100;
  if (Number($('steps').value)>Number($('steps').max)) $('steps').value=$('steps').max;
  $('stepsOutput').textContent = count.format($('steps').value)+' تحديث';
  const resolution = Number($('duration').value)/Number($('steps').value);
  if(Number($('duration').value)>=1&&Number($('disasterDuration').value)>Number($('duration').value))$('disasterDuration').value=$('duration').value;
  $('resolutionHint').textContent = 'كل تحديث يعرض '+fmt.format(resolution)+' مليون سنة افتراضية؛ الزمن غير معاير بيولوجيًا.';
  if (!state || !['running','paused'].includes(state.status)) {
    $('yearTarget').textContent='من '+fmt.format(Number($('duration').value))+' مليون';
    $('tickLabel').textContent='0 / '+count.format($('steps').value)+' تحديث فعلي';
  }
  document.querySelectorAll('[data-duration]').forEach(b=>b.classList.toggle('selected',b.dataset.duration===$('duration').value));
}
for (const id of ['duration','steps','capacity']) $(id).addEventListener('input',updateSettingsHint);
document.querySelectorAll('[data-duration]').forEach(b=>b.onclick=()=>{$('duration').value=b.dataset.duration;updateSettingsHint();});
$('mortality').oninput=()=> $('mortalityOutput').textContent=$('mortality').value+'%';
$('resourceLoss').oninput=()=> $('resourceLossOutput').textContent=$('resourceLoss').value+'%';
document.querySelectorAll('[data-kind]').forEach(button=>button.onclick=()=>{
  kind=button.dataset.kind;
  document.querySelectorAll('[data-kind]').forEach(b=>b.classList.toggle('selected',b===button));
  $('mortality').disabled=kind==='drought';
  $('resourceLoss').disabled=$('renewal').disabled=kind==='bottleneck';
});
$('helpButton').onclick=()=> $('helpDialog').showModal();
$('startButton').onclick=async()=>{
  try {
    pendingSettings=settings();
    const estimate=await api('/api/estimate',pendingSettings);
    const items=[['مدة السيناريو',fmt.format(Number(pendingSettings.duration_million_years))+' M'],['تحديثات فعلية',count.format(estimate.actual_steps)],
      ['سقف التحديثات الفردية',short.format(estimate.upper_individual_updates)],['الحمل الاسترشادي',estimate.load]];
    $('estimateGrid').innerHTML=items.map(([label,value])=>`<div class="estimate-item"><small>${label}</small><strong>${value}</strong></div>`).join('');
    $('mappingNotice').textContent=estimate.calendar_mapping+' كل طريقة تبدأ بـ'+estimate.initial_per_strategy+' فردًا في كل بيئة. مدة السيناريو تغيّر مقياس العرض؛ الدقة هي عدد الحسابات الفعلية.';
    $('resourceAck').checked=false; $('confirmStart').disabled=true; $('resourceDialog').showModal();
  } catch(error) {notify(error.message,true);}
};
$('resourceAck').onchange=()=> $('confirmStart').disabled=!$('resourceAck').checked;
$('confirmStart').onclick=async()=>{
  if (!$('resourceAck').checked) return;
  $('confirmStart').disabled=true;
  try {
    await api('/api/start',{settings:pendingSettings,acknowledge_resources:true});
    history=[];cursor=-1;sessionId=null;
    $('resourceDialog').close();notify('بدأت التجربة. يمكنك التدخل بعد اختيار الكارثة.'); await poll();
  } catch(error) {notify(error.message,true);$('confirmStart').disabled=false;}
};
$('pauseButton').onclick=async()=>{
  try {await api('/api/control',{action:state?.status==='paused'?'resume':'pause'});await poll();}
  catch(error){notify(error.message,true);}
};
$('stopButton').onclick=async()=>{
  $('stopButton').disabled=true;
  try {await api('/api/control',{action:'stop'});notify('انتهت التجربة وحُفظت لقطة بياناتها.');await poll();}
  catch(error){notify(error.message,true);}
};
$('speed').oninput=()=> $('speedOutput').textContent=$('speed').value+' تحديث/ث';
$('speed').onchange=async()=>{
  try {await api('/api/control',{action:'speed',speed:Number($('speed').value)});} catch(error){notify(error.message,true);}
};
$('disasterButton').onclick=async()=>{
  $('disasterButton').disabled=true;
  try {
    const event=await api('/api/catastrophe',{kind,target:$('target').value,mortality:Number($('mortality').value)/100,
      resource_loss:Number($('resourceLoss').value)/100,renewal_factor:Number($('renewal').value),duration_million_years:$('disasterDuration').value});
    notify('سُجّل التدخل عند التحديث '+event.tick+(state?.status==='paused'?'؛ اضغط متابعة لتنفيذه.':'.'));
    await poll();
  } catch(error){notify(error.message,true);await poll();}
};
$('exportButton').onclick=async()=>{
  if(exporting)return; exporting=true;$('exportButton').disabled=true;
  try {const saved=await api('/api/export',{});showExport(saved);notify('حُفظت الجينات والسجلات والتدخلات والحالة الحالية.');}
  catch(error){notify(error.message,true);} finally{exporting=false;await poll();}
};
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{
  chartMode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('selected',x===b));renderChart();renderLegend();
});
$('survivalExportButton').onclick=()=>{
  if(!state?.settings)return;
  const url=URL.createObjectURL(new Blob([survivalCsv(state)],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='evolution-lab-survival.csv';
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  notify('حُفظ جدول الصمود والانقراض للبيئات الثلاث؛ المستمرة مسجّلة دون حدث انقراض.');
};

for (const env of ENV) {
  const article=document.createElement('article');
  article.className='world-card'+(env.id===focus?' selected':'');article.dataset.world=env.id;article.tabIndex=0;article.setAttribute('role','button');article.setAttribute('aria-label','متابعة '+env.label);
  article.innerHTML=`<div class="world-header"><strong>${env.label}</strong><span class="world-code">${env.code}</span></div><canvas class="world-canvas" data-canvas="${env.id}" aria-label="عينة أفراد ${env.label}"></canvas><span class="world-status">بانتظار البداية</span><div class="world-footer"><div class="world-stat"><span>الأفراد الأحياء</span><strong data-pop>—</strong><small data-cap></small></div><div class="world-stat"><span>مخزون الموارد</span><strong data-res>—</strong><small> وحدة</small></div></div>`;
  article.onclick=()=>setFocus(env.id);article.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setFocus(env.id);}};
  article.querySelector('canvas').onclick=e=>{
    setFocus(env.id);
    const rect=e.target.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;
    const dot=(hitPoints.get(env.id)||[]).find(p=>Math.hypot(p.x-x,p.y-y)<8);
    if(dot) inspect(dot.data,env.label);
  };
  $('worldGrid').append(article);
}
function setFocus(id){focus=id;document.querySelectorAll('.world-card').forEach(x=>x.classList.toggle('selected',x.dataset.world===id));renderDetails();renderChart();}
function inspect(dot,environment){
  $('individualTitle').textContent='الفرد #'+dot.id;
  $('individualContent').innerHTML=`<div class="inspector-info"><span>البيئة</span><strong>${environment}</strong></div><div class="inspector-info"><span>طريقة التكاثر</span><strong>${LABELS[dot.strategy]}</strong></div><div class="inspector-info"><span>العمر الحسابي</span><strong>${dot.age} تحديث</strong></div><div class="inspector-info"><span>الأداء في النموذج</span><strong>${dot.score.toFixed(4)}</strong></div><div class="genome-strip">${dot.genome}</div><p>نسختان من جينوم ثنائي الحالات في النموذج. العرض ليس تسلسل DNA حقيقيًا.</p>`;
  $('individualDialog').showModal();
}
function showExport(saved){
  if(!saved)return;$('exportReady').hidden=false;$('exportPath').textContent=saved.directory;
  $('downloadLink').href=saved.download;$('reportLink').href=saved.report;
}
function render(){
  if(!state)return;
  const alive=['running','paused'].includes(state.status);
  $('statusBadge').className='run-state '+state.status;
  $('statusBadge').innerHTML='<i></i>'+STATES[state.status];
  $('startButton').disabled=alive;
  ['duration','steps','capacity','mutation','matingCost','partnerCost','seed','recombination','selection','compatibility','inheritance','parasite'].forEach(id=>$(id).disabled=alive);
  document.querySelectorAll('[data-duration]').forEach(b=>b.disabled=alive);
  $('pauseButton').disabled=$('stopButton').disabled=!alive;
  $('pauseButton').setAttribute('aria-label',state.status==='paused'?'متابعة':'إيقاف مؤقت');
  $('pauseButton').innerHTML=`<svg><use href="#i-${state.status==='paused'?'play':'pause'}"/></svg>`;
  $('exportButton').disabled=!state.settings||exporting;
  $('survivalExportButton').disabled=!state.settings;
  $('yearValue').textContent=fmt.format(state.million_years);
  if(state.settings){$('yearTarget').textContent='من '+fmt.format(Number(state.settings.duration_million_years))+' مليون';$('tickLabel').textContent=count.format(state.tick)+' / '+count.format(state.settings.steps)+' تحديث فعلي';}
  $('runProgress').value=state.progress;
  if(document.activeElement!==$('speed'))$('speed').value=state.speed;
  $('speedOutput').textContent=fmt.format(state.speed)+' تحديث/ث';
  const worlds=state.worlds||[];
  $('populationValue').textContent=worlds.length?count.format(worlds.reduce((s,w)=>s+w.population,0)):'—';
  $('birthsValue').textContent=worlds.length?count.format(worlds.reduce((s,w)=>s+w.births,0)):'—';
  $('deathsValue').textContent=worlds.length?count.format(worlds.reduce((s,w)=>s+w.catastrophe_deaths,0)):'—';
  $('populationHint').textContent=worlds.length?'في '+worlds.length+' بيئات مستقلة':'في البيئات الثلاث';
  $('memoryValue').textContent=state.memory_mb===null?'—':count.format(state.memory_mb);
  $('cpuValue').textContent=fmt.format(state.cpu_percent_one_core)+'%';
  for(const env of ENV){
    const card=document.querySelector(`[data-world="${env.id}"]`),world=worlds.find(w=>w.id===env.id);
    card.querySelector('[data-pop]').textContent=world?count.format(world.population):'—';
    card.querySelector('[data-cap]').textContent=world?' / '+world.capacity:'';
    card.querySelector('[data-res]').textContent=world?fmt.format(world.resources):'—';
    const affected=Boolean(state.active&&(state.active.target==='all'||state.active.target===env.id));
    card.classList.toggle('affected',affected);card.classList.toggle('extinct',Boolean(world?.extinct));
    card.querySelector('.world-status').textContent=world?.extinct?'انقرض المجتمع':affected?'تحت أثر الكارثة':world?(alive?'قيد الرصد':'رصد مكتمل'):'بانتظار البداية';
  }
  const ready=alive&&!state.active&&state.tick>=state.next_allowed_tick;
  $('disasterButton').disabled=!ready;
  $('activeDisaster').hidden=!state.active;
  if(state.active){
    const remaining=(state.active.end_tick-state.tick)*Number(state.settings.duration_million_years)/state.settings.steps;
    $('activeTitle').textContent=KINDS[state.active.kind]+' · '+(state.active.target==='all'?'جميع البيئات':ENV.find(e=>e.id===state.active.target).label);
    $('activeDescription').textContent=(state.status==='paused'&&state.tick===state.active.tick?'مسجّلة، تُنفّذ عند المتابعة. ':!alive?'انتهى التشغيل أثناء نافذة الأثر. ':'')+'المتبقي من نافذة الأثر: '+fmt.format(Math.max(0,remaining))+' مليون سنة افتراضية.';
  }
  $('cooldownText').textContent=!state.settings?'كارثة واحدة فقط. فاصل 8 ملايين سنة بعد انتهائها.':state.active?'كارثة نشطة. يبدأ فاصل 8 ملايين سنة بعد نهاية نافذة أثرها.':state.remaining_cooldown_million_years>0?'الكارثة التالية بعد '+fmt.format(state.remaining_cooldown_million_years)+' مليون سنة افتراضية على الأقل.':'التحكم جاهز. فاصل 8 ملايين سنة بعد نهاية كل كارثة.';
  $('eventCount').textContent=state.actions.length;
  const eventKey=state.session_id+':'+state.actions.length;
  if(state.actions.length&&eventKey!==lastEventKey){
    $('eventList').innerHTML=[...state.actions].reverse().map(e=>{
      const at=e.tick*Number(state.settings.duration_million_years)/state.settings.steps;
      const impact=e.kind==='drought'?'فقد غذاء '+Math.round(e.resource_loss*100)+'%':e.kind==='bottleneck'?'وفيات '+Math.round(e.mortality*100)+'%':'وفيات '+Math.round(e.mortality*100)+'% · فقد غذاء '+Math.round(e.resource_loss*100)+'%';
      return `<div class="event-item"><svg><use href="#i-spark"/></svg><div><strong>${KINDS[e.kind]}</strong><small>${e.target==='all'?'جميع البيئات':ENV.find(w=>w.id===e.target).label} · ${impact} · خطوة ${e.tick}</small></div><time>${fmt.format(at)} Ma</time></div>`;
    }).join('');
  } else if(!state.actions.length&&eventKey!==lastEventKey){
    $('eventList').innerHTML='<div class="empty-events"><svg><use href="#i-wave"/></svg><p>كل كارثة إلها أثر… وسجل.</p><small>النوع والشدة والتوقيت تُحفظ لإعادة التجربة.</small></div>';
  }
  lastEventKey=eventKey;
  if(state.latest_export)showExport(state.latest_export);else $('exportReady').hidden=true;
  renderDetails();renderChart();
}
function renderDetails(){
  const world=state?.worlds.find(w=>w.id===focus);
  $('focusBadge').textContent=ENV.find(e=>e.id===focus).label;
  if(!$('strategyRows').children.length){
    $('strategyRows').innerHTML=LABELS.map((label,i)=>`<tr data-strategy="${i}" tabindex="0" role="button" aria-label="تفاصيل ${label}"><td><i style="background:${COLORS[i]}"></i>${label}</td><td>—</td><td>—</td><td>—</td><td class="survival-cell"><strong></strong><span></span><small></small></td></tr>`).join('');
    document.querySelectorAll('[data-strategy]').forEach(tr=>{
      tr.onclick=()=>inspectStrategy(Number(tr.dataset.strategy));
      tr.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspectStrategy(Number(tr.dataset.strategy));}};
    });
  }
  LABELS.forEach((label,i)=>{
    const row=world?.strategies[i];
    const cells=$('strategyRows').children[i].children;
    cells[1].textContent=row?count.format(row.population):'—';
    cells[2].textContent=row?.gene_diversity==null?'—':row.gene_diversity.toFixed(3);
    cells[3].textContent=row?.mean_performance==null?'—':row.mean_performance.toFixed(3);
    const survival=survivalSummary(row,state),cell=cells[4];
    cell.className='survival-cell '+(survival?.status || '');
    cell.children[0].textContent=!survival?'—':survival.status==='extinct'?'انقرض':survival.status==='ongoing'?'مستمر حتى الآن':survival.status==='censored'?'باقٍ عند نهاية الرصد':'توقيت غير مسجّل';
    cell.children[1].textContent=survival?.observed_million_years==null?'':(survival.event_observed?'عند ':'≥ ')+survivalNumber.format(survival.observed_million_years);
    cell.children[2].textContent=survival?.observed_tick==null?'':count.format(survival.observed_tick)+' تحديث';
  });
}
function inspectStrategy(index){
  const world=state?.worlds.find(w=>w.id===focus),r=world?.strategies[index];
  if(!r){notify('ابدأ تجربة لعرض المقاييس الفعلية.');return;}
  $('strategyTitle').textContent=LABELS[index]+' · '+world.label;
  const survival=survivalSummary(r,state);
  const c=r.cumulative,items=[['حالة الصمود',survival.status==='extinct'?'انقرض':survival.status==='ongoing'?'مستمر حتى الآن':survival.status==='censored'?'باقٍ عند نهاية الرصد':'توقيت غير مسجّل'],
    ['مدة الصمود المرصودة · مليون سنة افتراضية',survival.observed_million_years==null?'—':(survival.event_observed?'':'≥ ')+survivalNumber.format(survival.observed_million_years)],
    ['التحديثات المرصودة من البداية',survival.observed_tick],['وقت الانقراض · مليون سنة افتراضية',survival.extinction_million_years==null?'لم يُرصد':survivalNumber.format(survival.extinction_million_years)],
    ['السكان الأحياء',r.population],['الناضجون',r.mature],['متوسط العمر بالتحديثات',r.mean_age],
    ['الأداء في النموذج',r.mean_performance],['التنوع الجيني',r.gene_diversity],['اختلاف النسختين الجينيتين',r.heterozygosity],
    ['عدم التطابق مع البيئة',r.adaptive_lag],['ارتباط المواضع D²',r.mean_linked_D2],['متوسط احتمال الخلط',r.mean_mix_probability],
    ['محاولات الإنجاب',c.attempts],['مواليد مقبولون',c.realized_newborns],['فشل إيجاد شريك',c.mate_failures],['فشل اللقاء',c.encounter_failures],
    ['وفيات عادية',c.survival_deaths],['وفيات الكوارث',c.catastrophe_deaths],['وفيات نقص الغذاء',c.maintenance_deaths],
    ['وفيات بالغين بسبب السعة',c.capacity_adult_deaths],['مواليد لم تستوعبهم السعة',c.capacity_newborn_deaths],
    ['جهد الإنجاب الاسمي',c.effort_spent],['موارد بناء الأبناء',c.offspring_resources],['خطوة الانقراض',r.extinction_tick]];
  $('strategyContent').innerHTML=items.map(([label,value])=>`<div class="inspector-info"><span>${label}</span><strong>${value==null?'—':typeof value==='string'?value:Number.isInteger(value)?count.format(value):Number(value).toFixed(4)}</strong></div>`).join('');
  $('strategyDialog').showModal();
}
function renderLegend(){
  const entries=chartMode==='population'?LABELS.map((label,i)=>({label,color:COLORS[i]})):ENV;
  $('strategyLegend').innerHTML=entries.map(e=>`<span class="legend-item"><i style="background:${e.color}"></i>${e.label}</span>`).join('');
}
function fitCanvas(canvas){
  const rect=canvas.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2),w=Math.max(1,rect.width),h=Math.max(1,rect.height);
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);return {ctx,w,h};
}
function renderChart(){
  const canvas=$('historyChart'),{ctx,w,h}=fitCanvas(canvas);
  ctx.clearRect(0,0,w,h);
  $('chartTitle').textContent=chartMode==='population'?'تغيّر السكان · '+ENV.find(e=>e.id===focus).label:'تغيّر مخزون الموارد · جميع البيئات';
  $('chartEmpty').hidden=history.length>1;
  const left=38,right=12,top=10,bottom=25,pw=w-left-right,ph=h-top-bottom;
  const series=chartMode==='population'?COLORS.map((color,i)=>({color,values:history.map(p=>p.populations[focus]?.[i]||0)})):ENV.map(e=>({color:e.color,values:history.map(p=>p.resources[e.id]||0)}));
  let max=chartMode==='population'?20:100;
  for(const line of series)for(const value of line.values)max=Math.max(max,value);
  max=Math.ceil(max*1.1/10)*10;
  const maxTime=state?.settings?Number(state.settings.duration_million_years):Number($('duration').value)||100;
  ctx.font='9px Consolas,monospace';ctx.lineWidth=1;ctx.textAlign='right';ctx.textBaseline='middle';
  for(let i=0;i<=4;i++){
    const y=top+ph*(1-i/4);ctx.strokeStyle='#233246';ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#758ba3';ctx.fillText(short.format(max*i/4),left-8,y);
  }
  ctx.textAlign='center';ctx.textBaseline='top';
  for(let i=0;i<=4;i++)ctx.fillText(short.format(maxTime*i/4)+' M',left+pw*i/4,top+ph+10);
  if(history.length<2)return;
  const stride=Math.max(1,Math.floor(history.length/Math.max(100,pw)));
  for(const line of series){
    ctx.strokeStyle=line.color;ctx.lineWidth=1.8;ctx.beginPath();
    for(let i=0;i<history.length;i+=stride){const x=left+pw*history[i].million_years/maxTime,y=top+ph*(1-line.values[i]/max);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
    const last=history.length-1;ctx.lineTo(left+pw*history[last].million_years/maxTime,top+ph*(1-line.values[last]/max));ctx.stroke();
  }
}
function hash(value){const x=Math.sin(value*127.1+311.7)*43758.5453;return x-Math.floor(x);}
function terrain(id,w,h){
  const key=id+':'+Math.round(w)+':'+Math.round(h);if(terrains.has(key))return terrains.get(key);
  const c=document.createElement('canvas');c.width=Math.ceil(w);c.height=Math.ceil(h);const ctx=c.getContext('2d'),index=ENV.findIndex(e=>e.id===id);
  ctx.fillStyle=['#0b2027','#22251e','#151c35'][index];ctx.fillRect(0,0,w,h);
  for(let x=0;x<w;x+=4)for(let y=0;y<h;y+=4){
    const n=Math.sin(x*.022+index)*Math.cos(y*.038)+.35*Math.sin(x*.07+y*.04+index*3);
    const edge=Math.sin(x/w*Math.PI)*Math.sin(y/h*Math.PI);
    const alpha=Math.max(0,(n*.18+edge*.35));ctx.fillStyle=[`rgba(42,114,100,${alpha})`,`rgba(123,120,65,${alpha})`,`rgba(83,92,150,${alpha})`][index];ctx.fillRect(x,y,4,4);
  }
  ctx.strokeStyle=['#63e6be0e','#ffd16610','#a8a4ff10'][index];ctx.lineWidth=1;
  for(let row=0;row<8;row++){ctx.beginPath();for(let x=0;x<=w;x+=5){const y=(row+1)*h/9+Math.sin(x*.018+row*2+index)*8+Math.sin(x*.06+row)*3;if(x===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.stroke();}
  const gradient=ctx.createRadialGradient(w/2,h/2,0,w/2,h/2,w*.7);gradient.addColorStop(0,'#06101a00');gradient.addColorStop(1,'#06101a88');ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);
  terrains.set(key,c);return c;
}
const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function animate(time){
  for(const env of ENV){
    const canvas=document.querySelector(`[data-canvas="${env.id}"]`),{ctx,w,h}=fitCanvas(canvas);
    ctx.drawImage(terrain(env.id,w,h),0,0,w,h);
    const world=state?.worlds.find(e=>e.id===env.id),points=[];
    if(world)for(const dot of world.dots){
      const wobble=reducedMotion?0:Math.sin(time*.0005+dot.id)*2;
      const x=12+hash(dot.id*3+1)*(w-24)+wobble,y=12+hash(dot.id*7+ENV.findIndex(e=>e.id===env.id)*13)*(h-24)+wobble;
      ctx.beginPath();ctx.fillStyle=COLORS[dot.strategy];ctx.globalAlpha=.75;ctx.arc(x,y,dot.age<2?1.4:2,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;
      if(dot.age<1){ctx.strokeStyle=COLORS[dot.strategy]+'44';ctx.lineWidth=.7;ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.stroke();}
      points.push({x,y,data:dot});
    }
    hitPoints.set(env.id,points);
    if(!world){ctx.font='10px Segoe UI,Tahoma';ctx.fillStyle='#78939d';ctx.textAlign='center';ctx.fillText('بيئة جاهزة · لا توجد بيانات بعد',w/2,h/2);}
  }
  requestAnimationFrame(animate);
}
async function poll(){
  if(pollBusy)return;pollBusy=true;
  try {
    const next=await api('/api/state?after='+cursor);
    const newSession=next.session_id!==sessionId;
    if(newSession){sessionId=next.session_id;history=[];cursor=-1;}
    history.push(...next.history);if(next.history.length)cursor=next.history[next.history.length-1].tick;
    state=next;if(newSession&&next.settings)restoreSessionSettings(next.settings);render();
  }catch(error){$('statusBadge').className='run-state failed';$('statusBadge').innerHTML='<i></i>الاتصال منقطع';}
  finally{pollBusy=false;}
}
async function pollLoop(){await poll();setTimeout(pollLoop,state?.status==='running'?250:800);}
new ResizeObserver(()=>{renderChart();}).observe($('historyChart').parentElement);
updateSettingsHint();renderLegend();renderDetails();requestAnimationFrame(animate);pollLoop();
}
