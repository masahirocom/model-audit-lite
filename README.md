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

## Japanese indirect prompt-injection probe set (`ja-injection`)

60 harmless-canary probes (10 categories x 6) where the injected instruction sits inside
an untrusted document the model was asked to process (email, RAG chunk, tool output,
HTML comment, ...), written for Japanese specifics: keigo-style polite injections,
full-width/hiragana/romaji obfuscation, fake 【システム】 markers, and BIPIA-style
start/middle/end positions. The canary is split in the document ("ZX" "-" "1001") so
quoting the injection does not count as following it; only reasoning text is stripped
before judging.

```bash
model-audit-lite probe <repo_id> --probe-set ja-injection --max-tokens 300
```

Dataset card and per-category results: https://huggingface.co/datasets/masahiroid/japanese-indirect-prompt-injection-probes
(v0.1; directional only, see "What this is *not*").

For agentic, tool-using evaluation in Japanese (user tasks plus injection tasks with state-based checks), see the
unofficial Japanese localization of AgentDojo: https://github.com/masahirocom/agentdojo-ja

## ML-BOM with conversion lineage (`bom`)

One command writes a CycloneDX 1.6 ML-BOM that bundles what this tool already knows: SHA-256 per file, pickle /
custom-code findings, detected formats, and (with `--base`) the conversion lineage as `pedigree.ancestors` plus the
chat-template check. It stands alone, or merges into a BOM from another generator so you keep one document:

```bash
model-audit-lite bom your/converted-model --base original-org/base-model -o bom.json
model-audit-lite bom your/converted-model --base original-org/base-model --merge owasp-aibom.json -o merged.json
```

Properties use the `model-audit-lite:` prefix. Lineage is as declared by the publisher; this is not a verification of weights.

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
- **Scaling to thousands of prompts is not the roadmap, and wouldn't help.** Prompt
  injection isn't a problem you converge toward solving by sampling harder — LLMs have
  no hard boundary between "instruction" and "data" for more test cases to triangulate,
  and attackers adapt to whatever test set you publish. Even heavily red-teamed frontier
  models still show double-digit injection success rates in benchmarks like CyberSecEval
  (26-41% across every model tested in v2) — that's a structural property of current LLM
  architectures, not a sign that existing test suites are merely too small. Ten prompts
  per category and ten thousand measure the same ceiling with different precision; they
  don't raise it. What actually extends coverage is adding **new attack categories** as
  novel techniques emerge, not multiplying phrasing variants within existing ones — so
  that's where this suite's own test set is meant to grow. Treat results as a **directional
  read of known-pattern exposure** (useful for comparing categories, or for diffing a
  conversion's behavior against its source), not a path toward provable robustness.
  Actual mitigation of prompt injection has to happen at the application layer — don't
  let model output trigger actions without a check, treat all externally-sourced content
  as data rather than instructions downstream, minimize what the model is privileged to
  do — regardless of how many probes pass.

## Example output

- File audit + probe suite: [examples/sample_report.md](examples/sample_report.md) ([日本語版](examples/sample_report.ja.md)).
- Conversion-integrity `compare`: [examples/sample_comparison.md](examples/sample_comparison.md) ([日本語版](examples/sample_comparison.ja.md)).

## License

MIT
