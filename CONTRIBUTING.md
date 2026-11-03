# Contributing / المساهمة

Thanks for wanting to help! / شكرًا لاهتمامك بالمساهمة!

## Ground rules

1. **Tests first.** Run `python -m pytest -q` before and after your change. New behaviour needs a test.
2. **Assumptions stay visible.** Any change to how the model works must also update `ECO_MODEL.md` (or `MODEL_ASSUMPTIONS.md` for the reference engine). These files are hashed into every run's provenance on purpose.
3. **Do not edit the preserved baseline.** `evolution_lab_verified.py` and `test_evolution_lab.py` are byte-checked against `baseline_sha256.json`.
4. **No result claims in code or docs.** The simulator compares programs *under declared assumptions*; please keep wording that way.
5. **Keep it small.** Configuration limits prevent huge runs; raise them only with a benchmark.

## Workflow

```bash
git clone https://github.com/ASSOLI99/-genetic_algorithm_for_evolution_theory.git
cd -- -genetic_algorithm_for_evolution_theory
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock   # Windows: .venv\Scripts\python.exe
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Open a pull request with a short description of *what* changed and *why*. Arabic or English are both welcome.

## أفكار مفيدة للمساهمة

- تجارب جديدة على شكل ملفات إعداد داخل `configs/`.
- تحسين التقارير والرسوم البيانية.
- اختبارات إضافية تتحقق من صحة النموذج.
- ترجمة أو تبسيط الشرح.

## Making a release

The downloadable zip in `release/` is built from the committed source with `git archive`, so it never contains `.venv`, `runs/` or other local files:

```bash
git archive --format=zip --prefix=Evolution-Lab/ -o release/Evolution-Lab-v0.8.0.zip HEAD
```

Pushing a tag such as `v0.8.1` also builds the zip automatically and attaches it to a GitHub Release (`.github/workflows/release.yml`).
