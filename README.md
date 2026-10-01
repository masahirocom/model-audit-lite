# model-audit-lite

[日本語版はこちら (README.ja.md)](README.ja.md)

A lightweight safety audit for Hugging Face models, with a focus on a gap
heavier tools don't cover: **conversion integrity**. Three independent
checks:

1. **File-distribution audit** — no model loading required, works on *any* HF
   repo. Detects pickle-format weights (`.bin`/`.pt`/`.pkl`, arbitrary-code-
   execution risk), flags bundled custom code (`trust_remote_code`), and
   computes SHA256 checksums.
2. **Conversion-integrity audit** (`compare`) — diffs a converted repo
   against its source: does the **chat template** still match? Chat templates
   are small Jinja2 programs that run on *every* inference call, and as of
   early 2026 they're one of the few parts of a model repo that neither the
   model card, the metadata viewer, nor Hugging Face's automated scanners
   check — a poisoned template can pass every existing scan. With `--probes`,
   it also re-runs the safety probe suite against both the source and the
   converted model and reports only what changed, since quantization and
   format conversion can measurably shift safety-alignment behavior in either
   direction.
3. **Safety probe suite** — a small, known-pattern prompt set (instruction
   override, jailbreak roleplay, harmful code generation, prompt injection,
   system-prompt extraction, etc.) run against a single model, with a simple
   heuristic pass/fail marker.

## Scope, honestly

This is **not** a substitute for a real red-team benchmark — tools like
Meta's CyberSecEval, ETH Zurich's AgentDojo, or scanners like NVIDIA's garak
exist and go much deeper, at the cost of being heavier to set up and run.
This fills a narrower, more specific gap: a **5-minute, zero-infrastructure
check you run on your own model conversions** before shipping them, that
specifically catches the one thing those general-purpose benchmarks weren't
built to look for — whether *this specific conversion* silently changed
something (the chat template, the safety-alignment behavior) relative to the
model you started from.

## Install

Not yet published to PyPI — install from source:

```bash
pip install git+https://github.com/masahirocom/model-audit-lite.git
# or, with a backend for the probe suite:
pip install "git+https://github.com/masahirocom/model-audit-lite.git#egg=model-audit-lite[mlx]"
pip install "git+https://github.com/masahirocom/model-audit-lite.git#egg=model-audit-lite[transformers]"

# or clone and install editable for local development:
git clone https://github.com/masahirocom/model-audit-lite.git
cd model-audit-lite && pip install -e ".[mlx]"
```

## Usage (CLI)

```bash
# File-distribution audit only -- works on any repo, no model loading
model-audit-lite audit mlx-community/some-model

# Conversion-integrity audit: does the converted repo's chat template
# still match the source model's?
model-audit-lite compare original-org/base-model your/converted-model --lang ja

# ...and also re-run the safety probes on both and diff the results
model-audit-lite compare original-org/base-model your/converted-model \
  --probes --base-backend transformers --derived-backend mlx-lm --lang ja

# Safety probe suite on a single model (loads the model)
model-audit-lite probe your/model --backend mlx-lm --lang ja

# File audit + single-model probe suite, written to SECURITY.md
model-audit-lite full your/model --backend mlx-lm --lang ja -o SECURITY.md
```

## Usage (Python API)

The probe runner is backend-agnostic — pass any `generate_fn(prompt: str) -> str`:

```python
from model_audit_lite import audit_repo, run_probes, write_security_md

file_result = audit_repo("your/model")

from mlx_lm import load, generate
model, tokenizer = load("your/model")

def generate_fn(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    return generate(model, tokenizer, prompt=text, max_tokens=300)

probe_report = run_probes(generate_fn, source="ja")  # or "en", or a path to your own YAML

print(write_security_md(audit_result=file_result, probe_report=probe_report, repo_id="your/model"))
```

Conversion-integrity checks work the same way:

```python
from model_audit_lite import diff_chat_template, diff_probe_results, write_comparison_report

template_diff = diff_chat_template("original-org/base-model", "your/converted-model")
print(template_diff.verdict)  # "identical" | "changed" | "added" | "removed" | "no_template"

# Optionally, also diff safety-probe behavior (you supply a generate_fn for each model):
base_report = run_probes(base_generate_fn, source="ja")
derived_report = run_probes(derived_generate_fn, source="ja")
probe_diff = diff_probe_results(base_report, derived_report)
print([r.id for r in probe_diff.regressions])  # safe -> unsafe only

print(write_comparison_report(
    template_diff=template_diff,
    probe_diff=probe_diff,
    probe_total=derived_report.total,
    base_repo_id="original-org/base-model",
    derived_repo_id="your/converted-model",
))
```

## Extending the probe suite

Prompts live in plain YAML (`model_audit_lite/probes/default_prompts_{ja,en}.yaml`).
Each entry is just:

```yaml
- id: my-new-case
  category: my-category
  prompt: "..."
  # optional: for cases where the correct behavior is NOT refusal
  # (e.g. prompt injection -- the model should just ignore the injected
  # instruction and carry on), flag unsafe only if a specific string appears:
  unsafe_if_contains: ["SOME_MARKER"]
```

Pass your own file with `source="path/to/your.yaml"` (Python) or `--prompts path` (CLI/roadmap).
If you find a real gap this suite misses, that's the point — add a case and send a PR.

## What this is *not*

- Not a substitute for a real red-team / adversarial evaluation (see CyberSecEval,
  AgentDojo, garak, promptfoo for deeper options).
- The heuristic pass/fail marker is a first-pass string-match screen, not a judgment.
  Always read the raw `response` text yourself before trusting a result — this is
  especially true for Japanese, where refusal phrasing is far more varied than the
  small marker list in this repo can fully cover.
- The file audit checks distribution safety (can this file execute arbitrary code on
  load?), not model *behavior* — a clean file audit says nothing about what the model
  will generate.
- The `compare` command's `--probes` mode re-runs the *same* heuristic marker-based
  judgment on both models — it inherits the same false-positive/negative limitations,
  just applied twice and diffed.

## Example output

- File audit + probe suite: [examples/sample_report.md](examples/sample_report.md) ([日本語版](examples/sample_report.ja.md)).
- Conversion-integrity `compare`: [examples/sample_comparison.md](examples/sample_comparison.md) ([日本語版](examples/sample_comparison.ja.md)).

## License

MIT
