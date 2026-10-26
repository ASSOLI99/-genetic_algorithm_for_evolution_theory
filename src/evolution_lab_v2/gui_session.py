"""Bounded live sessions with exact scenario-clock catastrophe policy and replay."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import html
import hashlib
import json
from pathlib import Path
import re
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
MAX_GUI_LEDGER_ROWS = 250_000


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
    comparison_mode: str = 'competition'
    initial_population: int | None = None
    resource_capacity: float | None = None
    initial_resources: float | None = None
    resource_renewal: float | None = None
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
        if cfg.comparison_mode not in ('competition', 'isolated'):
            raise SessionError('invalid_mode', 'اختر منافسة مشتركة أو عوالم منفصلة.')
        maximum_initial = cfg.capacity if cfg.comparison_mode == 'isolated' else cfg.capacity//7
        if cfg.initial_population is not None and (type(cfg.initial_population) is not int or not 1 <= cfg.initial_population <= maximum_initial):
            raise SessionError('invalid_initial', f'عدد البداية لكل طريقة يجب أن يكون بين 1 و{maximum_initial}.')
        if cfg.comparison_mode == 'isolated' and cfg.compatibility_scope != 'within_strategy':
            raise SessionError('isolated_compatibility', 'الشركاء في وضع العزلة من داخل العالم نفسه فقط.')
        for name in ('resource_capacity', 'initial_resources', 'resource_renewal'):
            value = getattr(cfg, name)
            if value is not None:
                finite_number(value, 'الموارد', 0, 100000)
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
        world_count = len(cfg.environments)*(7 if cfg.comparison_mode == 'isolated' else 1)
        work = cfg.steps*cfg.capacity*world_count
        if work > MAX_BATCH_CENSUS_TICKS or work*16 > MAX_BATCH_LOCUS_TICKS:
            raise SessionError('work_limit', 'الحجم الكلي يتجاوز ميزانية المحرك.')
        if cfg.steps*world_count*7 > MAX_GUI_LEDGER_ROWS:
            raise SessionError('log_limit', 'سجل العوالم يتجاوز ميزانية الذاكرة؛ قلّل عدد التحديثات الفعلية.')
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

    @property
    def starting_count(self):
        return self.initial_population if self.initial_population is not None else max(8, self.capacity//(7*3)*2)

    def resource_budget(self):
        scale = self.capacity/336
        cap = self.resource_capacity if self.resource_capacity is not None else 600*scale
        return {'resource_capacity': cap,
                'initial_resources': self.initial_resources if self.initial_resources is not None else cap,
                'resource_renewal': self.resource_renewal if self.resource_renewal is not None else 150*scale}

    def configs(self):
        result = {}
        for environment in self.environments:
            programs = range(7) if self.comparison_mode == 'isolated' else (None,)
            for program in programs:
                initial = tuple(self.starting_count if program is None or i == program else 0 for i in range(7))
                name = environment if program is None else environment+'__'+STRATEGIES[program]
                result[name] = EcoConfig(seed=self.seed, steps=self.steps, capacity=self.capacity,
                    initial_counts=initial, environment=environment, mutation_rate=self.mutation_rate,
                    mating_cost=self.mating_cost, extra_parent_cost=self.extra_parent_cost,
                    recombination_rate=self.recombination_rate, selection_coefficient=self.selection_coefficient,
                    compatibility_scope=self.compatibility_scope, multiparent_mechanism=self.multiparent_mechanism,
                    parasite=self.parasite,
                    record_parentage=False, log_every=5, catastrophe_regime='combined',
                    catastrophe_probability=0, **self.resource_budget())
        return result

    def to_dict(self):
        return {name: list(value) if name == 'environments' else value for name, value in self.__dict__.items()}

    def estimate(self):
        configs = self.configs()
        work = self.steps*self.capacity*len(configs)
        return {'settings': self.to_dict(), 'actual_steps': self.steps, 'worlds': len(configs),
                'initial_per_strategy': self.starting_count,
                'total_initial_population': sum(sum(c.initial_counts) for c in configs.values()),
                'resource_budget_per_world': self.resource_budget(),
                'total_initial_resources': len(configs)*self.resource_budget()['initial_resources'],
                'retained_ledger_rows': self.steps*len(configs)*7,
                'upper_individual_updates': work, 'upper_locus_updates': work*16,
                'scenario_million_years_per_update': float(Decimal(self.duration_million_years)/self.steps),
                'cooldown_steps': self.ticks_for_years(COOLDOWN_YEARS),
                'load': 'مرتفع' if work > 4_000_000 or self.steps*len(configs)*7 > 150000 else 'متوسط' if work > 1_000_000 else 'خفيف',
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
        self.pending_removal = None
        self.next_allowed_tick = 0
        self.speed = 20.0
        self.last_client = time.monotonic()
        self.started = None
        self.error = None
        self.thread = None
        self.stop_signal = threading.Event()
        self.exports = {}
        index = self.output_root/'.gui-export-index.json'
        if index.is_file():
            try:
                saved = json.loads(index.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    raise ValueError('Invalid export index')
                for identity, filename in saved.items():
                    if not isinstance(filename, str) or not re.fullmatch(r'[0-9a-f]{32}', identity):
                        continue
                    if not re.fullmatch(r'gui_\d{8}_\d{6}_'+identity[:8]+r'\.zip', filename):
                        continue
                    archive = (self.output_root/filename).resolve()
                    if archive.parent == self.output_root.resolve() and archive.is_file() and (archive.with_suffix('')/'REPORT.html').is_file():
                        self.exports[identity] = archive
            except (ValueError, OSError):
                pass
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
            self.pending_removal = None
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
        pending = self.pending_removal
        for name, state in self.worlds.items():
            affected = pending is not None and name in pending['counts_by_world']
            program = STRATEGIES.index(pending['strategy']) if affected else None
            previous = state.cumulative['experimental_removals'][program] if affected else 0
            step(state, remove_programs=(program,) if affected else ())
            if affected and state.cumulative['experimental_removals'][program]-previous != pending['counts_by_world'][name]:
                raise ValueError('Reserved experimental removal count changed')
        self.pending_removal = None
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
            if self.pending_removal:
                raise SessionError('intervention_pending', 'نفّذ الإزالة المجدولة قبل إضافة كارثة.', 409)
            if self.tick < self.next_allowed_tick:
                raise SessionError('catastrophe_cooldown', 'يجب مرور 8 ملايين سنة افتراضية على الأقل بعد انتهاء الكارثة السابقة.', 409)
            allowed = {'kind', 'target', 'mortality', 'resource_loss', 'renewal_factor', 'duration_million_years'}
            if not isinstance(values, dict) or set(values)-allowed:
                raise SessionError('invalid_catastrophe', 'إعدادات كارثة غير معروفة.')
            kind, target = values.get('kind', 'combined'), values.get('target', 'all')
            if self.settings.comparison_mode == 'isolated' and target != 'all':
                raise SessionError('isolated_global_event', 'في المقارنة المنفصلة تُطبّق الكارثة على جميع العوالم بالتساوي.')
            if kind not in ('bottleneck', 'drought', 'combined') or target not in (*self.worlds, 'all'):
                raise SessionError('invalid_catastrophe', 'نوع الكارثة أو البيئة غير صالح.')
            duration = decimal_value(values.get('duration_million_years', '2'), 'مدة الكارثة', Decimal('.01'))
            if duration > Decimal(self.settings.duration_million_years):
                raise SessionError('invalid_catastrophe', 'مدة الكارثة أطول من السيناريو الكامل.')
            ticks = self.settings.ticks_for_years(duration*1_000_000)
            event = {'type': 'catastrophe', 'kind': kind, 'target': target, 'tick': self.tick, 'end_tick': self.tick+ticks,
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

    def remove_program(self, values):
        with self.lock:
            if self.status not in ('running', 'paused'):
                raise SessionError('not_running', 'ابدأ تجربة منافسة قبل إزالة طريقة.', 409)
            if self.settings.comparison_mode != 'competition':
                raise SessionError('removal_requires_competition', 'الإزالة متاحة في العالم المشترك فقط.', 409)
            if self.active or self.pending_removal:
                raise SessionError('intervention_pending', 'انتظر انتهاء الكارثة أو تنفيذ الإزالة المجدولة.', 409)
            if not isinstance(values, dict) or set(values) != {'strategy', 'target'}:
                raise SessionError('invalid_removal', 'حدّد طريقة تكاثر ونطاق الإزالة فقط.')
            strategy, target = values['strategy'], values['target']
            if strategy not in STRATEGIES or target not in (*self.worlds, 'all'):
                raise SessionError('invalid_removal', 'طريقة التكاثر أو البيئة غير صالحة.')
            program = STRATEGIES.index(strategy)
            affected = {name: int(np.count_nonzero(state.strategy == program)) for name,state in self.worlds.items() if target in ('all',name)}
            total = sum(affected.values())
            if not total:
                raise SessionError('program_absent', 'لا يوجد أفراد أحياء من هذه الطريقة في النطاق المختار.', 409)
            event = {'type': 'remove_program', 'strategy': strategy, 'target': target,
                     'tick': self.tick, 'execution_tick': self.tick+1,
                     'counts_by_world': affected, 'scheduled_count': total}
            self.pending_removal = dict(event)
            self.actions.append(dict(event))
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
                    row['initial_count'] = state.config.initial_counts[i]
                    row['extinction_cause'] = ('experimental_removal' if state.cumulative['experimental_removals'][i] else 'population_dynamics') if row['extinction_tick'] is not None else None
                n = len(state.ids)
                p = state.genomes.mean(axis=(0, 1)) if n else None
                scores = performance(state)
                sample = np.linspace(0, n-1, min(n, 140), dtype=int) if n else []
                dots = [{'id': int(state.ids[i]), 'strategy': int(state.strategy[i]),
                         'age': int(state.tick-state.birth_tick[i]), 'score': float(scores[i]),
                         'genome': ''.join(str(int(b)) for b in state.genomes[i].ravel())} for i in sample]
                program = next((i for i, count in enumerate(state.config.initial_counts) if count), None) if self.settings.comparison_mode == 'isolated' else None
                label = ENVIRONMENTS[state.config.environment]+(' · '+LABELS[program] if program is not None else '')
                worlds.append({'id': name, 'label': label, 'environment': state.config.environment,
                    'strategy_index': program, 'initial_population': sum(state.config.initial_counts), 'population': n,
                    'capacity': state.config.capacity, 'resources': state.resources,
                    'initial_resources': state.config.initial_resources, 'resource_renewal': state.config.resource_renewal,
                    'resource_capacity': state.config.resource_capacity, 'strategies': metrics,
                    'diversity': float(np.mean(2*p*(1-p))) if n else None,
                    'births': int(sum(state.cumulative['realized_newborns'])),
                    'deaths': int(sum(sum(state.cumulative[k]) for k in ('survival_deaths', 'catastrophe_deaths', 'maintenance_deaths', 'capacity_adult_deaths'))),
                    'catastrophe_deaths': int(sum(state.cumulative['catastrophe_deaths'])),
                    'experimental_removals': int(sum(state.cumulative['experimental_removals'])),
                    'dots': dots, 'extinct': not n})
            return {'status': self.status, 'session_id': self.session_id, 'tick': self.tick,
                'settings': self.settings.to_dict() if self.settings else None,
                'million_years': self.settings.million_years_at(self.tick) if self.settings else 0,
                'progress': self.tick/self.settings.steps if self.settings else 0,
                'worlds': worlds, 'history': [h for h in self.history if h['tick'] > after],
                'actions': list(self.actions), 'active': dict(self.active) if self.active else None,
                'pending_removal': dict(self.pending_removal) if self.pending_removal else None,
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
        manifest = {'schema': 'interactive-3', 'settings': self.settings.to_dict(),
            'world_layout': {name: {'environment': state.config.environment, 'initial_counts': list(state.config.initial_counts),
                                   'capacity': state.config.capacity, 'resources': {k: getattr(state.config,k) for k in ('initial_resources','resource_capacity','resource_renewal')}} for name,state in self.worlds.items()},
            'clock': 'Scenario display clock; not empirically calibrated biological years',
            'cooldown': 'At least 8,000,000 scenario years after the previous disaster ends; rounded up to a full update',
            'status': self.status, 'tick': self.tick, 'actions': self.actions,
            'pending_removal': self.pending_removal,
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
        write_json(self.output_root/'.gui-export-index.json', {identity: path.name for identity, path in self.exports.items()})
        self.latest_export = {'id': export_id, 'directory': str(folder), 'download': f'/api/download/{export_id}',
                              'report': f'/api/report/{export_id}', 'tick': self.tick}
        return dict(self.latest_export)

    def _write_report(self, folder, summaries):
        rows = []
        totals = []
        for name, summary in summaries.items():
            config = summary['config']
            environment = ENVIRONMENTS[config['environment']]
            programs = [LABELS[i] for i, n in enumerate(config['initial_counts']) if n]
            label = environment+(' · '+programs[0] if len(programs) == 1 else '')
            totals.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
                (label, sum(config['initial_counts']), config['capacity'], config['initial_resources'],
                 config['resource_renewal'], summary['total_population'], sum(e['population']>0 for e in summary['strategies'].values())))+'</tr>')
            for label, strategy in zip(LABELS, STRATEGIES):
                entry = summary['strategies'][strategy]
                if not entry['initial_count']:
                    continue
                event = entry['extinction_tick']
                removed = int(entry['cumulative']['experimental_removals'])
                loss = f'إزالة تجريبية · تحديث {event}' if removed else event if event is not None else 'باقٍ عند نهاية الرصد'
                cells = (environment, label, entry['population'], int(entry['cumulative']['realized_newborns']),
                         int(entry['cumulative']['catastrophe_deaths']), removed, loss,
                         self.settings.million_years_at(event if event is not None else self.tick))
                rows.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in cells)+'</tr>')
        interventions = []
        for action in self.actions:
            removal = action.get('type') == 'remove_program'
            tick = action['execution_tick'] if removal else action['tick']+1
            values = (('إزالة '+LABELS[STRATEGIES.index(action['strategy'])]) if removal else action['kind'],
                      'جميع البيئات' if action['target'] == 'all' else ENVIRONMENTS[action['target']],
                      tick, 'نُفّذت' if tick <= self.tick else 'لم تُنفّذ', action['scheduled_count'] if removal else '—')
            interventions.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in values)+'</tr>')
        document = ('<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>Evolution Lab — جلسة تفاعلية</title>'
            '<style>body{font:16px Tahoma,Arial;max-width:1100px;margin:40px auto;padding:20px;line-height:1.8;color:#172333}'
            'table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccd6df}th{background:#eef4f7}</style>'
            '<h1>Evolution Lab — سجل تجربة تفاعلية</h1>'
            f'<p>تصميم التجربة: {"عوالم منفصلة" if self.settings.comparison_mode == "isolated" else "منافسة مشتركة"}؛ العوالم: {len(self.worlds)}.</p>'
            f'<p>التحديثات المنفذة: {self.tick} من {self.settings.steps}؛ زمن السيناريو المعروض: {self.settings.million_years_at(self.tick):g} مليون سنة.</p>'
            '<p>الزمن افتراضي وغير معاير بيولوجيًا. هذه تجربة واحدة بتدخلات يدوية مسجلة؛ لا تمثل تكرارات مستقلة أو دليل تفوق إحصائي. '
            'الميكانيكيات ذات 4/8 مساهمين افتراضية. النقاط في الواجهة عينة من أفراد المحاكاة وليست خريطة مكانية أو نموذج هجرة.</p>'
            f'<p>الكوارث المسجلة: {sum(e.get("type") != "remove_program" for e in self.actions)}؛ طلبات الإزالة: {sum(e.get("type") == "remove_program" for e in self.actions)}. كل ملفات الأرقام والجينات والحفظ والبذور موجودة في مجلدات البيئات. '
            'session.json يسجل المدخلات والتوقيت وبصمات المصدر لإعادة التجربة؛ history.json يحفظ السلاسل الزمنية.</p>'
            '<p>الإزالة التجريبية تدخل متعمد قبل الوفيات والتكاثر في التحديث التالي، وتُسجّل منفصلة عن الوفيات. لا تضيف غذاءً أو تعيد تكاليف سابقة ولا تغيّر السعة. فقدان المجموعة بالإزالة ليس دليلًا على انقراضها الطبيعي. الطلب المعلّق لم يُنفّذ إذا انتهى الرصد قبل تحديثه.</p>'
            '<p>في العزلة كل طريقة تملك مجتمعًا وموارد منفصلة؛ الميزانية الكلية أكبر من المنافسة. نفس البذرة تقرن المؤسسين والبيئة حيث ينطبق، ولا تجعل العوالم تكرارات مستقلة. الكارثة موحّدة الاحتمال والتوقيت، وقد تختلف الوفيات الفعلية.</p>'
            '<h2>حالة العوالم</h2><table><tr><th>العالم</th><th>البداية</th><th>السعة</th><th>غذاء البداية</th><th>تجدد الغذاء</th><th>الأحياء</th><th>طرق باقية</th></tr>'
            +''.join(totals)+'</table><h2>طرق التكاثر</h2><table><tr><th>البيئة</th><th>طريقة التكاثر</th><th>العدد</th><th>مواليد مقبولون</th><th>وفيات الكوارث المباشرة</th><th>أُزيلوا بتدخل</th><th>تحديث الانقراض / الحالة</th><th>صمود مرصود · مليون سنة افتراضية</th></tr>'
            +''.join(rows)+'</table><h2>سجل التدخلات</h2><table><tr><th>التدخل</th><th>النطاق</th><th>تحديث التنفيذ</th><th>الحالة</th><th>عدد الإزالة</th></tr>'
            +''.join(interventions)+'</table></html>')
        (folder/'REPORT.html').write_text(document, encoding='utf-8')


def replay_session(path):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if manifest.get('schema') not in ('interactive-1', 'interactive-2', 'interactive-3') or manifest.get('signature') != signature():
        raise ValueError('Interactive replay source/runtime signature mismatch')
    session = LabSession(Path(path).parent/'unused_replay_output')
    session.configure(manifest['settings'], acknowledge_resources=True)
    if manifest['schema'] in ('interactive-2', 'interactive-3'):
        layout = {name: {'environment': state.config.environment, 'initial_counts': list(state.config.initial_counts),
                         'capacity': state.config.capacity, 'resources': {k: getattr(state.config,k) for k in ('initial_resources','resource_capacity','resource_renewal')}} for name,state in session.worlds.items()}
        if layout != manifest.get('world_layout'):
            raise ValueError('Interactive world layout mismatch')
    target = manifest['tick']
    if type(target) is not int or not 0 <= target <= session.settings.steps:
        raise ValueError('Invalid replay tick')
    actions = manifest['actions']
    def replay_action(event):
        if event.get('type') == 'remove_program':
            return session.remove_program({k: event[k] for k in ('strategy', 'target')})
        if event.get('type', 'catastrophe') != 'catastrophe':
            raise ValueError('Unknown intervention type')
        return session.catastrophe({k: event[k] for k in ('kind', 'target', 'mortality', 'resource_loss', 'renewal_factor', 'duration_million_years')})
    next_action = 0
    while session.tick < target:
        while next_action < len(actions) and actions[next_action]['tick'] == session.tick:
            event = actions[next_action]
            actual = replay_action(event)
            if actual != event:
                raise ValueError('Interactive event policy mismatch')
            next_action += 1
        session.advance_ticks(1)
        if session.status not in ('running', 'paused') and session.tick < target:
            raise ValueError('Replay terminated before recorded tick')
    # A paused export may include an accepted event not yet executed.
    while next_action < len(actions) and actions[next_action]['tick'] == target:
        event = actions[next_action]
        actual = replay_action(event)
        if actual != event:
            raise ValueError('Pending event policy mismatch')
        next_action += 1
    if (next_action != len(actions) or session.pending_removal != manifest.get('pending_removal') or {name: state_digest(state) for name, state in session.worlds.items()} != manifest['final_state_sha256']
            or {name: fingerprint(state) for name, state in session.worlds.items()} != manifest['final_fingerprint']):
        raise ValueError('Interactive replay state mismatch')
    return session
