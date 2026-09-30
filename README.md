# model-audit-lite

A lightweight, extensible safety audit for Hugging Face models. Two independent checks:

1. **File-distribution audit** — no model loading required, works on *any* HF repo.
   Detects pickle-format weights (`.bin`/`.pt`/`.pkl`, arbitrary-code-execution risk),
   flags bundled custom code (`trust_remote_code`), and computes SHA256 checksums.
2. **Safety probe suite** — a small, known-pattern prompt set (instruction override,
   jailbreak roleplay, harmful code generation, prompt injection, system-prompt
   extraction, etc.) run against the model, with a simple heuristic pass/fail marker.

This is **not** a comprehensive red-team benchmark — there aren't many lightweight,
easy-to-run options in this space yet, and that's exactly the gap this fills. It's
meant to be a first-pass sanity check you run before shipping a model conversion,
and a small, hackable base you extend with your own test cases when you find a gap.

## Install

```bash
pip install model-audit-lite
# or, with a backend for the probe suite:
pip install "model-audit-lite[mlx]"          # mlx-lm backend
pip install "model-audit-lite[transformers]" # transformers backend
```

## Usage (CLI)

```bash
# File-distribution audit only -- works on any repo, no model loading
model-audit-lite audit mlx-community/some-model

# Safety probe suite (loads the model)
model-audit-lite probe your/model --backend mlx-lm --lang ja

# Both, written to SECURITY.md
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

- Not a substitute for a real red-team / adversarial evaluation.
- The heuristic pass/fail marker is a first-pass string-match screen, not a judgment.
  Always read the raw `response` text yourself before trusting a result.
- The file audit checks distribution safety (can this file execute arbitrary code on
  load?), not model *behavior* — a clean file audit says nothing about what the model
  will generate.

---

## 日本語版

Hugging Face上のモデルに対する、軽量で拡張しやすい安全性監査ツールです。2種類の独立したチェックを提供します。

1. **配布物としての安全性監査** — モデルのロード不要、どんなHFリポジトリにも使えます。
   pickle形式の重み（`.bin`/`.pt`/`.pkl`、任意コード実行のリスク）の検出、
   同梱されたカスタムコード（`trust_remote_code`）の検出、SHA256チェックサムの計算を行います。
2. **簡易安全性プローブ** — 既知の代表的な攻撃パターン（指示上書き、ロールプレイ脱獄、
   有害コード生成、プロンプトインジェクション、システムプロンプト抽出など）の小さなプロンプト集を
   実際にモデルへ投げ、簡易的なヒューリスティックで合否を判定します。

これは**包括的なレッドチーミングベンチマークではありません**。この分野には手軽に実行できる
選択肢がまだ多くなく、それこそがこのツールが埋めようとしているギャップです。モデル変換を
公開する前の一次スクリーニングとして、また「ここに穴がある」と気づいたときに自分でテストケースを
足しやすい、小さくてハックしやすい土台として使うことを想定しています。

### インストール

```bash
pip install model-audit-lite
pip install "model-audit-lite[mlx]"          # mlx-lmバックエンド
pip install "model-audit-lite[transformers]" # transformersバックエンド
```

### 使い方（CLI）

```bash
# 配布物としての安全性監査のみ（モデルロード不要、どんなリポジトリにも使える）
model-audit-lite audit mlx-community/some-model

# 簡易安全性プローブ（モデルのロードが必要）
model-audit-lite probe your/model --backend mlx-lm --lang ja

# 両方実行してSECURITY.mdに書き出す
model-audit-lite full your/model --backend mlx-lm --lang ja -o SECURITY.md
```

### プロンプトの拡張方法

`model_audit_lite/probes/default_prompts_ja.yaml`に追記するだけです。判定基準を
「拒否したか」ではなく「特定の文字列を出力しなかったか」にしたい場合（プロンプト
インジェクション系のテストなど）は`unsafe_if_contains`を指定してください。
自分のモデルで見つけた穴があれば、ケースを追加してPRを送ってください。

### これは何ではないか

- 本格的なレッドチーミング・敵対的評価の代替にはなりません。
- ヒューリスティックな合否判定は単純な文字列マッチによる一次スクリーニングです。
  最終判断は必ず`response`の本文を人間が読んで行ってください。
- 配布物監査は「読み込み時に任意コードが実行されないか」を見るものであり、
  モデルの**挙動**そのものを保証するものではありません。

## License

MIT
