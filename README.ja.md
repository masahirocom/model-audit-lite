# model-audit-lite

[English version here (README.md)](README.md)

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

## インストール

```bash
pip install model-audit-lite
pip install "model-audit-lite[mlx]"          # mlx-lmバックエンド
pip install "model-audit-lite[transformers]" # transformersバックエンド
```

## 使い方（CLI）

```bash
# 配布物としての安全性監査のみ（モデルロード不要、どんなリポジトリにも使える）
model-audit-lite audit mlx-community/some-model

# 簡易安全性プローブ（モデルのロードが必要）
model-audit-lite probe your/model --backend mlx-lm --lang ja

# 両方実行してSECURITY.mdに書き出す
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

- 本格的なレッドチーミング・敵対的評価の代替にはなりません。
- ヒューリスティックな合否判定は単純な文字列マッチによる一次スクリーニングです。
  最終判断は必ず`response`の本文を人間が読んで行ってください。
- 配布物監査は「読み込み時に任意コードが実行されないか」を見るものであり、
  モデルの**挙動**そのものを保証するものではありません。

## 出力例

[examples/sample_report.ja.md](examples/sample_report.ja.md)（[English](examples/sample_report.md)）を参照してください。

## License

MIT
