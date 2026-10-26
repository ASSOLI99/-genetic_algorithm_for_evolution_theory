"""Bounded live sessions with exact scenario-clock catastrophe policy and replay."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import html
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
import zipfile

import numpy as np

from .artifacts import provenance, signature, write_json
from .eco_config import EcoConfig, STRATEGIES, MAX_BATCH_CENSUS_TICKS, MAX_BATCH_LOCUS_TICKS
from .eco_io import save_checkpoint, write_outputs
from .ecology import initialize, observe, performance, state_digest, step

ENVIRONMENTS = {'static': 'بيئة ثابتة', 'periodic': 'بيئة دورية', 'autocorrelated': 'بيئة متقلبة'}
LABELS = ('لاجنسي', 'جنسي بأبوين', 'اختياري', 'دوري', 'عند الضغط', 'أربعة آباء', 'ثمانية آباء')
COLORS = ('#63e6be', '#6ca7ff', '#ffd166', '#bd9bff', '#ff9b70', '#f58abb', '#54cfdb')
COOLDOWN_YEARS = Decimal(8_000_000)


class SessionError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def decimal_value(value, label, minimum=Decimal('0')):
    try:
        if type(value) not in (str, int, float) or len(str(value)) > 48:
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < minimum or result.adjusted() > 24 or result.adjusted() < -12:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise SessionError('invalid_number', f'قيمة {label} غير صالحة.') from None


def finite_number(value, label, minimum, maximum):
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        raise SessionError('invalid_number', f'قيمة {label} خارج الحدود المسموحة.')
    return float(value)


@dataclass(frozen=True)
class Settings:
    duration_million_years: str = '100'
    steps: int = 1000
    capacity: int = 336
    seed: int = 20261026
    environments: tuple = ('static', 'periodic', 'autocorrelated')
    mutation_rate: float = .001
    mating_cost: float = 0.0
    extra_parent_cost: float = 0.0
    recombination_rate: float = .05
    selection_coefficient: float = .04
    compatibility_scope: str = 'within_strategy'
    multiparent_mechanism: str = 'locus_mosaic'
    parasite: str = 'none'
    speed: float = 20.0

    @classmethod
    def parse(cls, values):
        if not isinstance(values, dict) or set(values)-set(cls.__dataclass_fields__):
            raise SessionError('invalid_settings', 'إعدادات غير معروفة.')
        try:
            cfg = cls(**values)
        except TypeError:
            raise SessionError('invalid_settings', 'إعدادات غير صالحة.') from None
        duration = decimal_value(cfg.duration_million_years, 'مدة السيناريو', Decimal(1))
        if type(cfg.steps) is not int or not 100 <= cfg.steps <= 5000:
            raise SessionError('work_limit', 'الدقة المتاحة من 100 إلى 5000 تحديث فعلي.')
        if type(cfg.capacity) is not int or cfg.capacity not in (168, 336, 672):
            raise SessionError('work_limit', 'اختر سعة 168 أو 336 أو 672 فردًا لكل بيئة.')
        if type(cfg.seed) is not int or not 0 <= cfg.seed <= 2**31-1:
            raise SessionError('invalid_seed', 'البذرة يجب أن تكون عددًا صحيحًا من 0 إلى 2147483647.')
        env = cfg.environments
        if not isinstance(env, (tuple, list)) or not env or len(env) > 3 or any(type(e) is not str or e not in ENVIRONMENTS for e in env) or len(set(env)) != len(env):
            raise SessionError('invalid_environments', 'اختر بيئة واحدة على الأقل دون تكرار.')
        cfg = replace(cfg, duration_million_years=str(duration), environments=tuple(env),
                      mutation_rate=finite_number(cfg.mutation_rate, 'الطفرات', 0, .02),
                      mating_cost=finite_number(cfg.mating_cost, 'كلفة التزاوج', 0, 1),
                      extra_parent_cost=finite_number(cfg.extra_parent_cost, 'كلفة المساهم', 0, .2),
                      recombination_rate=finite_number(cfg.recombination_rate, 'إعادة التركيب', 0, .5),
                      selection_coefficient=finite_number(cfg.selection_coefficient, 'شدة الانتخاب', 0, .2),
                      speed=finite_number(cfg.speed, 'السرعة', 1, 60))
        try:
            cfg.configs()
        except ValueError as exc:
            raise SessionError('work_limit', 'الحجم يتجاوز ميزانية المحرك؛ قلّل الدقة أو سعة البيئة.') from exc
        work = cfg.steps*cfg.capacity*len(cfg.environments)
        if work > MAX_BATCH_CENSUS_TICKS or work*16 > MAX_BATCH_LOCUS_TICKS:
            raise SessionError('work_limit', 'الحجم الكلي يتجاوز ميزانية المحرك.')
        return cfg

    @property
    def years(self):
        return Decimal(self.duration_million_years)*1_000_000

    def ticks_for_years(self, years):
        with localcontext() as context:
            context.prec = 60
            return max(1, int((Decimal(years)*self.steps/self.years).to_integral_value(rounding=ROUND_CEILING)))

    def million_years_at(self, tick):
        return float(Decimal(self.duration_million_years)*tick/self.steps)

    def configs(self):
        initial = max(8, self.capacity//(7*3)*2)
        scale = self.capacity/336
        return {name: EcoConfig(seed=self.seed, steps=self.steps, capacity=self.capacity,
                    initial_counts=(initial,)*7, environment=name, mutation_rate=self.mutation_rate,
                    mating_cost=self.mating_cost, extra_parent_cost=self.extra_parent_cost,
                    recombination_rate=self.recombination_rate, selection_coefficient=self.selection_coefficient,
                    compatibility_scope=self.compatibility_scope, multiparent_mechanism=self.multiparent_mechanism,
                    parasite=self.parasite,
                    record_parentage=False, log_every=5, catastrophe_regime='combined',
                    catastrophe_probability=0, resource_capacity=600*scale,
                    initial_resources=600*scale, resource_renewal=150*scale) for name in self.environments}

    def to_dict(self):
        return {name: list(value) if name == 'environments' else value for name, value in self.__dict__.items()}

    def estimate(self):
        configs = self.configs()
        work = self.steps*self.capacity*len(configs)
        return {'settings': self.to_dict(), 'actual_steps': self.steps, 'worlds': len(configs),
                'initial_per_strategy': configs[self.environments[0]].initial_counts[0],
                'upper_individual_updates': work, 'upper_locus_updates': work*16,
                'scenario_million_years_per_update': float(Decimal(self.duration_million_years)/self.steps),
                'cooldown_steps': self.ticks_for_years(COOLDOWN_YEARS),
                'load': 'مرتفع' if work > 4_000_000 else 'متوسط' if work > 1_000_000 else 'خفيف',
                'calendar_mapping': 'زمن سيناريو افتراضي، غير معاير على سنوات بيولوجية حقيقية.',
                'resource_notice': 'المحاكاة تستخدم المعالج والذاكرة، والعرض يستهلك موارد المتصفح. زيادة الدقة والسكان ترفع الحمل. يمكنك الإيقاف المؤقت أو الإنهاء.'}


def process_memory_mb():
    try:
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize/1024**2
    except (AttributeError, OSError, ImportError):
        pass
    return None


def fingerprint(state):
    digest = hashlib.sha256(state_digest(state).encode())
    for name in ('environment', 'parasite', 'catastrophe_schedule'):
        digest.update(getattr(state, name).tobytes())
    detail = {'tick': state.tick, 'resources': state.resources, 'until': state.catastrophe_until,
              'cumulative': state.cumulative, 'config': state.config.to_dict(),
              'rngs': {name: rng.bit_generator.state for name, rng in state.rngs.items()}}
    digest.update(json.dumps(detail, sort_keys=True, allow_nan=False).encode())
    return digest.hexdigest()


class LabSession:
    def __init__(self, output_root):
        self.output_root = Path(output_root)
        self.lock = threading.RLock()
        self.status = 'idle'
        self.settings = None
        self.worlds = {}
        self.tick = 0
        self.history = []
        self.actions = []
        self.active = None
        self.next_allowed_tick = 0
        self.speed = 20.0
        self.last_client = time.monotonic()
        self.started = None
        self.error = None
        self.thread = None
        self.stop_signal = threading.Event()
        self.exports = {}
        self.latest_export = None
        self._cpu = (time.monotonic(), time.process_time(), 0.0)
        self.session_id = None

    def configure(self, values, acknowledge_resources=False, background=False):
        cfg = Settings.parse(values)
        if acknowledge_resources is not True:
            raise SessionError('resources_not_acknowledged', 'راجع تنبيه الموارد ووافق عليه قبل التشغيل.')
        with self.lock:
            if self.status in ('running', 'paused'):
                raise SessionError('session_active', 'أنهِ التجربة الحالية قبل إنشاء تجربة جديدة.', 409)
            self.settings = cfg
            self.worlds = {name: initialize(config) for name, config in cfg.configs().items()}
            self.tick, self.history, self.actions = 0, [], []
            self.active, self.next_allowed_tick = None, 0
            self.speed, self.error = cfg.speed, None
            self.session_id = uuid.uuid4().hex
            self.stop_signal = threading.Event()
            self.started = time.monotonic()
            self.last_client = self.started
            self.latest_export = None
            self.status = 'running'
            self._record()
            if background:
                self.thread = threading.Thread(target=self._worker, args=(self.session_id, self.stop_signal), daemon=True)
                self.thread.start()
        return cfg.estimate()

    def _record(self):
        self.history.append({'tick': self.tick, 'million_years': self.settings.million_years_at(self.tick),
                             'populations': {name: np.bincount(s.strategy, minlength=7).tolist() for name, s in self.worlds.items()},
                             'resources': {name: s.resources for name, s in self.worlds.items()}})

    def _advance(self):
        for state in self.worlds.values():
            step(state)
        self.tick += 1
        if self.active and self.tick >= self.active['end_tick']:
            self.active = None
        self._record()
        if self.tick >= self.settings.steps:
            self.status = 'completed'
        elif not any(len(s.ids) for s in self.worlds.values()):
            self.status = 'extinct'

    def advance_ticks(self, number):
        with self.lock:
            for _ in range(number):
                if self.status not in ('running', 'paused'):
                    break
                self._advance()

    def _worker(self, identity, signal):
        try:
            while not signal.is_set():
                started = time.monotonic()
                with self.lock:
                    if self.session_id != identity or self.status not in ('running', 'paused'):
                        break
                    if self.status == 'running' and started-self.last_client > 20:
                        self.status = 'paused'
                        self.error = 'توقفت التجربة مؤقتًا لانقطاع الواجهة. اضغط متابعة.'
                    if self.status == 'running':
                        self._advance()
                    delay = .08 if self.status == 'paused' else max(.002, 1/self.speed-(time.monotonic()-started))
                signal.wait(delay)
            with self.lock:
                if self.session_id == identity and self.status in ('completed', 'extinct', 'stopped') and (not self.latest_export or self.latest_export['tick'] != self.tick):
                    self._export_locked()
        except Exception as exc:
            with self.lock:
                self.status, self.error = 'failed', str(exc)

    def control(self, action, speed=None):
        with self.lock:
            if action == 'speed':
                self.speed = finite_number(speed, 'السرعة', 1, 60)
            elif action == 'pause' and self.status == 'running':
                self.status = 'paused'
            elif action == 'resume' and self.status == 'paused':
                self.status, self.error = 'running', None
                self.last_client = time.monotonic()
            elif action == 'stop' and self.status in ('running', 'paused'):
                self.status = 'stopped'
                self.stop_signal.set()
                self._export_locked()
            else:
                raise SessionError('invalid_control', 'هذا التحكم غير متاح الآن.', 409)

    def catastrophe(self, values):
        with self.lock:
            if self.status not in ('running', 'paused'):
                raise SessionError('not_running', 'ابدأ تجربة قبل إضافة كارثة.', 409)
            if self.active:
                raise SessionError('catastrophe_active', 'توجد كارثة نشطة بالفعل؛ لا يمكن تداخل الكوارث.', 409)
            if self.tick < self.next_allowed_tick:
                raise SessionError('catastrophe_cooldown', 'يجب مرور 8 ملايين سنة افتراضية على الأقل بعد انتهاء الكارثة السابقة.', 409)
            allowed = {'kind', 'target', 'mortality', 'resource_loss', 'renewal_factor', 'duration_million_years'}
            if not isinstance(values, dict) or set(values)-allowed:
                raise SessionError('invalid_catastrophe', 'إعدادات كارثة غير معروفة.')
            kind, target = values.get('kind', 'combined'), values.get('target', 'all')
            if kind not in ('bottleneck', 'drought', 'combined') or target not in (*self.worlds, 'all'):
                raise SessionError('invalid_catastrophe', 'نوع الكارثة أو البيئة غير صالح.')
            duration = decimal_value(values.get('duration_million_years', '2'), 'مدة الكارثة', Decimal('.01'))
            if duration > Decimal(self.settings.duration_million_years):
                raise SessionError('invalid_catastrophe', 'مدة الكارثة أطول من السيناريو الكامل.')
            ticks = self.settings.ticks_for_years(duration*1_000_000)
            event = {'kind': kind, 'target': target, 'tick': self.tick, 'end_tick': self.tick+ticks,
                     'duration_ticks': ticks, 'duration_million_years': str(duration),
                     'mortality': finite_number(values.get('mortality', .5), 'شدة الوفيات', 0, 1),
                     'resource_loss': finite_number(values.get('resource_loss', .75), 'خسارة الغذاء', 0, 1),
                     'renewal_factor': finite_number(values.get('renewal_factor', .25), 'تجدد الغذاء', 0, 1),
                     'next_allowed_tick': self.tick+ticks+self.settings.ticks_for_years(COOLDOWN_YEARS)}
            if kind == 'drought':
                event['mortality'] = 0.0
            elif kind == 'bottleneck':
                event['resource_loss'], event['renewal_factor'] = 0.0, 1.0
            self._apply_event(event)
            return dict(event)

    def _apply_event(self, event):
        for name, state in self.worlds.items():
            if event['target'] in ('all', name):
                state.config = replace(state.config, catastrophe_regime=event['kind'],
                      catastrophe_mortality=event['mortality'], catastrophe_resource_loss=event['resource_loss'],
                      catastrophe_renewal_factor=event['renewal_factor'], catastrophe_duration=event['duration_ticks'])
                state.catastrophe_schedule[self.tick] = True
        self.active = dict(event)
        self.next_allowed_tick = event['next_allowed_tick']
        self.actions.append(dict(event))

    def snapshot(self, after=-1):
        with self.lock:
            self.last_client = time.monotonic()
            now, cpu = time.monotonic(), time.process_time()
            last_time, last_cpu, percent = self._cpu
            if now-last_time >= .5:
                percent = max(0, (cpu-last_cpu)/(now-last_time)*100)
                self._cpu = (now, cpu, percent)
            worlds = []
            for name, state in self.worlds.items():
                metrics = observe(state)
                for i, row in enumerate(metrics):
                    row['cumulative'] = {key: values[i] for key, values in state.cumulative.items()}
                    row['extinction_tick'] = state.extinct.get(row['strategy'])
                n = len(state.ids)
                p = state.genomes.mean(axis=(0, 1)) if n else None
                scores = performance(state)
                sample = np.linspace(0, n-1, min(n, 140), dtype=int) if n else []
                dots = [{'id': int(state.ids[i]), 'strategy': int(state.strategy[i]),
                         'age': int(state.tick-state.birth_tick[i]), 'score': float(scores[i]),
                         'genome': ''.join(str(int(b)) for b in state.genomes[i].ravel())} for i in sample]
                worlds.append({'id': name, 'label': ENVIRONMENTS[name], 'population': n,
                    'capacity': state.config.capacity, 'resources': state.resources,
                    'resource_capacity': state.config.resource_capacity, 'strategies': metrics,
                    'diversity': float(np.mean(2*p*(1-p))) if n else None,
                    'births': int(sum(state.cumulative['realized_newborns'])),
                    'deaths': int(sum(sum(state.cumulative[k]) for k in ('survival_deaths', 'catastrophe_deaths', 'maintenance_deaths', 'capacity_adult_deaths'))),
                    'catastrophe_deaths': int(sum(state.cumulative['catastrophe_deaths'])),
                    'dots': dots, 'extinct': not n})
            return {'status': self.status, 'session_id': self.session_id, 'tick': self.tick,
                'settings': self.settings.to_dict() if self.settings else None,
                'million_years': self.settings.million_years_at(self.tick) if self.settings else 0,
                'progress': self.tick/self.settings.steps if self.settings else 0,
                'worlds': worlds, 'history': [h for h in self.history if h['tick'] > after],
                'actions': list(self.actions), 'active': dict(self.active) if self.active else None,
                'next_allowed_tick': self.next_allowed_tick, 'speed': self.speed,
                'remaining_cooldown_million_years': self.settings.million_years_at(max(0, self.next_allowed_tick-self.tick)) if self.settings else 0,
                'elapsed_seconds': now-self.started if self.started else 0,
                'cpu_percent_one_core': percent, 'memory_mb': process_memory_mb(),
                'error': self.error, 'latest_export': self.latest_export,
                'strategies': [{'id': name, 'label': label, 'color': color} for name, label, color in zip(STRATEGIES, LABELS, COLORS)]}

    def export(self):
        with self.lock:
            if not self.settings:
                raise SessionError('no_session', 'لا توجد تجربة لحفظها.', 409)
            return self._export_locked()

    def _export_locked(self):
        export_id = uuid.uuid4().hex
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        folder = self.output_root/f'gui_{stamp}_{export_id[:8]}'
        folder.mkdir(parents=True, exist_ok=False)
        summaries = {}
        for name, state in self.worlds.items():
            destination = folder/name
            destination.mkdir()
            save_checkpoint(destination/'checkpoint.npz', state)
            summaries[name] = write_outputs(destination, state, {'provenance': provenance(), 'interactive': True})
        manifest = {'schema': 'interactive-1', 'settings': self.settings.to_dict(),
            'clock': 'Scenario display clock; not empirically calibrated biological years',
            'cooldown': 'At least 8,000,000 scenario years after the previous disaster ends; rounded up to a full update',
            'status': self.status, 'tick': self.tick, 'actions': self.actions,
            'signature': signature(), 'provenance': provenance(),
            'final_fingerprint': {name: fingerprint(state) for name, state in self.worlds.items()},
            'final_state_sha256': {name: state_digest(state) for name, state in self.worlds.items()}}
        write_json(folder/'session.json', manifest)
        write_json(folder/'history.json', self.history)
        self._write_report(folder, summaries)
        archive = folder.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
            for path in folder.rglob('*'):
                if path.is_file():
                    stream.write(path, path.relative_to(folder))
        self.exports[export_id] = archive
        self.latest_export = {'id': export_id, 'directory': str(folder), 'download': f'/api/download/{export_id}',
                              'report': f'/api/report/{export_id}', 'tick': self.tick}
        return dict(self.latest_export)

    def _write_report(self, folder, summaries):
        rows = []
        for name, summary in summaries.items():
            for label, strategy in zip(LABELS, STRATEGIES):
                entry = summary['strategies'][strategy]
                cells = (ENVIRONMENTS[name], label, entry['population'], int(entry['cumulative']['realized_newborns']),
                         int(entry['cumulative']['catastrophe_deaths']), entry['extinction_tick'])
                rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in cells)+'</tr>')
        document = ('<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>Evolution Lab — جلسة تفاعلية</title>'
            '<style>body{font:16px Tahoma,Arial;max-width:1100px;margin:40px auto;padding:20px;line-height:1.8;color:#172333}'
            'table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccd6df}th{background:#eef4f7}</style>'
            '<h1>Evolution Lab — سجل تجربة تفاعلية</h1>'
            f'<p>التحديثات المنفذة: {self.tick} من {self.settings.steps}؛ زمن السيناريو المعروض: {self.settings.million_years_at(self.tick):g} مليون سنة.</p>'
            '<p>الزمن افتراضي وغير معاير بيولوجيًا. هذه تجربة واحدة بتدخلات يدوية مسجلة؛ لا تمثل تكرارات مستقلة أو دليل تفوق إحصائي. '
            'الميكانيكيات ذات 4/8 مساهمين افتراضية. النقاط في الواجهة عينة من أفراد المحاكاة وليست خريطة مكانية أو نموذج هجرة.</p>'
            f'<p>الكوارث المسجلة: {len(self.actions)}. كل ملفات الأرقام والجينات والحفظ والبذور موجودة في مجلدات البيئات. '
            'session.json يسجل المدخلات والتوقيت وبصمات المصدر لإعادة التجربة؛ history.json يحفظ السلاسل الزمنية.</p>'
            '<table><tr><th>البيئة</th><th>طريقة التكاثر</th><th>العدد</th><th>مواليد مقبولون</th><th>وفيات الكوارث المباشرة</th><th>خطوة الانقراض</th></tr>'
            +''.join(rows)+'</table></html>')
        (folder/'REPORT.html').write_text(document, encoding='utf-8')


def replay_session(path):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if manifest.get('schema') != 'interactive-1' or manifest.get('signature') != signature():
        raise ValueError('Interactive replay source/runtime signature mismatch')
    session = LabSession(Path(path).parent/'unused_replay_output')
    session.configure(manifest['settings'], acknowledge_resources=True)
    target = manifest['tick']
    if type(target) is not int or not 0 <= target <= session.settings.steps:
        raise ValueError('Invalid replay tick')
    actions = manifest['actions']
    next_action = 0
    while session.tick < target:
        while next_action < len(actions) and actions[next_action]['tick'] == session.tick:
            event = actions[next_action]
            actual = session.catastrophe({k: event[k] for k in ('kind', 'target', 'mortality', 'resource_loss', 'renewal_factor', 'duration_million_years')})
            if actual != event:
                raise ValueError('Interactive event policy mismatch')
            next_action += 1
        session.advance_ticks(1)
        if session.status not in ('running', 'paused') and session.tick < target:
            raise ValueError('Replay terminated before recorded tick')
    # A paused export may include an accepted event not yet executed.
    while next_action < len(actions) and actions[next_action]['tick'] == target:
        event = actions[next_action]
        actual = session.catastrophe({k: event[k] for k in ('kind', 'target', 'mortality', 'resource_loss', 'renewal_factor', 'duration_million_years')})
        if actual != event:
            raise ValueError('Pending event policy mismatch')
        next_action += 1
    if (next_action != len(actions) or {name: state_digest(state) for name, state in session.worlds.items()} != manifest['final_state_sha256']
            or {name: fingerprint(state) for name, state in session.worlds.items()} != manifest['final_fingerprint']):
        raise ValueError('Interactive replay state mismatch')
    return session
