# model-audit-lite

[English version here (README.md)](README.md)

Hugging Face上のモデルに対する、軽量な安全性監査ツールです。特に、重量級のツールでは
カバーされていない1つの盲点に焦点を当てています: **変換の完全性**。3種類の独立した
チェックを提供します。

1. **配布物としての安全性監査** — モデルのロード不要、どんなHFリポジトリにも使えます。
   pickle形式の重み（`.bin`/`.pt`/`.pkl`、任意コード実行のリスク）の検出、
   同梱されたカスタムコード（`trust_remote_code`）の検出、SHA256チェックサムの計算を行います。
2. **変換の完全性監査**（`compare`） — 変換後リポジトリを変換元と比較し、**chat template**
   が変わっていないか確認します。chat templateは推論のたびに実行される小さなJinja2
   プログラムですが、2026年初頭時点で、モデルカードにもメタデータビューアにもHugging Face
   の自動スキャンにもチェックされていない、数少ない構成要素の一つです（毒入りテンプレートが
   既存のスキャンをすべて通過した実例が報告されています）。`--probes`を付けると、変換元・
   変換後の両モデルに同じ安全性プローブを実行し、結果の変化（判定が変わった項目）だけを
   報告します。量子化やフォーマット変換は、良くも悪くも安全性アライメントの挙動を
   計測可能な形で変化させることがあるためです。
3. **簡易安全性プローブ** — 既知の代表的な攻撃パターン（指示上書き、ロールプレイ脱獄、
   有害コード生成、プロンプトインジェクション、システムプロンプト抽出など）の小さなプロンプト集を
   単一モデルに投げ、簡易的なヒューリスティックで合否を判定します。

## スコープについて、正直に

これは**本格的なレッドチーミングベンチマークの代替ではありません**。MetaのCyberSecEval、
ETH ZurichのAgentDojo、NVIDIAのgarakのようなスキャナーなど、もっと深く踏み込んだツールは
既に存在します（その分、セットアップと実行コストも大きくなります）。このツールが埋めようと
しているのはもっと狭く具体的なギャップです: **自分のモデル変換を公開する前に、インフラ構築
無しで5分で回せるチェック**として、汎用ベンチマークが元々対象にしていないもの——
「この特定の変換が、元のモデルから何かを（chat templateを、安全性アライメントの挙動を）
密かに変えていないか」——を具体的に検出することに特化しています。

## インストール

まだPyPIには公開していません。ソースからインストールしてください:

```bash
pip install git+https://github.com/masahirocom/model-audit-lite.git
# バックエンド付き:
pip install "git+https://github.com/masahirocom/model-audit-lite.git#egg=model-audit-lite[mlx]"
pip install "git+https://github.com/masahirocom/model-audit-lite.git#egg=model-audit-lite[transformers]"

# ローカル開発用にクローンしてeditableインストール:
git clone https://github.com/masahirocom/model-audit-lite.git
cd model-audit-lite && pip install -e ".[mlx]"
```

## 使い方（CLI）

```bash
# 配布物としての安全性監査のみ（モデルロード不要、どんなリポジトリにも使える）
model-audit-lite audit mlx-community/some-model

# 変換の完全性監査: 変換後リポジトリのchat templateは変換元と一致しているか
model-audit-lite compare original-org/base-model your/converted-model --lang ja

# ...さらに両モデルに安全性プローブを実行し、結果の差分も見る
model-audit-lite compare original-org/base-model your/converted-model \
  --probes --base-backend transformers --derived-backend mlx-lm --lang ja

# 単一モデルの簡易安全性プローブ（モデルのロードが必要）
model-audit-lite probe your/model --backend mlx-lm --lang ja

# 配布物監査 + 単一モデルのプローブをSECURITY.mdに書き出す
model-audit-lite full your/model --backend mlx-lm --lang ja -o SECURITY.md
```

## 使い方（Python API）

プローブの実行部分はバックエンドに依存しません。`generate_fn(prompt: str) -> str`という
関数を渡すだけで動きます。

```python
from model_audit_lite import audit_repo, run_probes, write_security_md

file_result = audit_repo("your/model")

from mlx_lm import load, generate
model, tokenizer = load("your/model")

def generate_fn(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    return generate(model, tokenizer, prompt=text, max_tokens=300)

probe_report = run_probes(generate_fn, source="ja")  # "en" や、自作YAMLへのパスも指定可能

print(write_security_md(audit_result=file_result, probe_report=probe_report, repo_id="your/model"))
```

変換の完全性監査も同様のAPIです:

```python
from model_audit_lite import diff_chat_template, diff_probe_results, write_comparison_report

template_diff = diff_chat_template("original-org/base-model", "your/converted-model")
print(template_diff.verdict)  # "identical" | "changed" | "added" | "removed" | "no_template"

# 任意: 安全性プローブの挙動差分も見る（各モデル用にgenerate_fnを用意）
base_report = run_probes(base_generate_fn, source="ja")
derived_report = run_probes(derived_generate_fn, source="ja")
probe_diff = diff_probe_results(base_report, derived_report)
print([r.id for r in probe_diff.regressions])  # 安全→危険になった項目のみ

print(write_comparison_report(
    template_diff=template_diff,
    probe_diff=probe_diff,
    probe_total=derived_report.total,
    base_repo_id="original-org/base-model",
    derived_repo_id="your/converted-model",
))
```

## プロンプトの拡張方法

プロンプトは`model_audit_lite/probes/default_prompts_{ja,en}.yaml`という単純なYAMLで
管理されています。各エントリはこれだけです:

```yaml
- id: my-new-case
  category: my-category
  prompt: "..."
  # 「拒否」ではなく「特定の文字列を出力しなかったか」で判定したい場合
  # （プロンプトインジェクション系のテストなど）:
  unsafe_if_contains: ["SOME_MARKER"]
```

自作のYAMLファイルは`source="path/to/your.yaml"`（Python）で指定できます。
自分のモデルで見つけた穴があれば、ケースを追加してPRを送ってください。

## これは何ではないか

- 本格的なレッドチーミング・敵対的評価の代替にはなりません（より深く踏み込みたい場合は
  CyberSecEval、AgentDojo、garak、promptfooなどを検討してください）。
- ヒューリスティックな合否判定は単純な文字列マッチによる一次スクリーニングです。
  最終判断は必ず`response`の本文を人間が読んで行ってください——特に日本語は拒否の言い回しが
  このリポジトリの小さなマーカー一覧だけでは到底カバーしきれないほど多様なので、
  この点はより一層当てはまります。
- 配布物監査は「読み込み時に任意コードが実行されないか」を見るものであり、
  モデルの**挙動**そのものを保証するものではありません。
- `compare`コマンドの`--probes`モードも、両モデルに**同じ**ヒューリスティックな
  文字列マッチ判定を適用しているだけです。一次スクリーニングとしての限界は
  単一モデルのプローブと同じで、それを2回実行して差分を取っているに過ぎません。

## 出力例

- 配布物監査 + プローブ: [examples/sample_report.ja.md](examples/sample_report.ja.md)（[English](examples/sample_report.md)）
- 変換の完全性監査（`compare`）: [examples/sample_comparison.ja.md](examples/sample_comparison.ja.md)（[English](examples/sample_comparison.md)）

## License

MIT
