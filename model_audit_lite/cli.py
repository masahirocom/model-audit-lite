"""model-audit-lite CLI

使い方:
    model-audit-lite audit <repo_id>
        配布物としての安全性監査のみ（pickle検出・カスタムコード検出・チェックサム）。
        モデルのロードは不要で、どんなリポジトリにも使える。

    model-audit-lite probe <repo_id> --backend mlx-lm [--lang ja|en]
        簡易安全性プローブ（既知の攻撃パターンでの生成テスト）。モデルのロードが必要。

    model-audit-lite full <repo_id> --backend mlx-lm [--lang ja|en] [-o SECURITY.md]
        両方を実行し、Markdownレポートを書き出す。
"""
from __future__ import annotations

import argparse
import sys

from .file_audit import audit_repo
from .probes.runner import run_probes
from .report import build_file_audit_section, build_probe_section, write_security_md


def _make_generate_fn(backend: str, repo_id: str, max_tokens: int):
    if backend == "mlx-lm":
        from mlx_lm import load, generate

        model, tokenizer = load(repo_id)

        def generate_fn(prompt: str) -> str:
            messages = [{"role": "user", "content": prompt}]
            text = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
            return generate(model, tokenizer, prompt=text, max_tokens=max_tokens, verbose=False)

        return generate_fn

    if backend == "transformers":
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(repo_id)
        model = AutoModelForCausalLM.from_pretrained(repo_id)
        model.eval()

        def generate_fn(prompt: str) -> str:
            messages = [{"role": "user", "content": prompt}]
            inputs = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt"
            )
            with torch.no_grad():
                out = model.generate(inputs, max_new_tokens=max_tokens, do_sample=False)
            return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)

        return generate_fn

    raise ValueError(f"Unknown backend: {backend}. Use 'mlx-lm' or 'transformers', or use the Python API with a custom generate_fn.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="model-audit-lite")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="File-distribution safety audit only (no model loading)")
    p_audit.add_argument("repo_id")
    p_audit.add_argument("-o", "--output", default=None, help="Write markdown to this file instead of stdout")

    p_probe = sub.add_parser("probe", help="Run the safety-probe prompt suite (requires loading the model)")
    p_probe.add_argument("repo_id")
    p_probe.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_probe.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_probe.add_argument("--max-tokens", type=int, default=300)
    p_probe.add_argument("-o", "--output", default=None)

    p_full = sub.add_parser("full", help="Run both file audit and safety probes")
    p_full.add_argument("repo_id")
    p_full.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_full.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_full.add_argument("--max-tokens", type=int, default=300)
    p_full.add_argument("-o", "--output", default="SECURITY.md")

    args = parser.parse_args(argv)

    if args.command == "audit":
        result = audit_repo(args.repo_id)
        md = build_file_audit_section(result)
        _emit(md, args.output)

    elif args.command == "probe":
        generate_fn = _make_generate_fn(args.backend, args.repo_id, args.max_tokens)
        report = run_probes(generate_fn, source=args.lang)
        md = build_probe_section(report, lang=args.lang)
        _emit(md, args.output)

    elif args.command == "full":
        audit_result = audit_repo(args.repo_id)
        generate_fn = _make_generate_fn(args.backend, args.repo_id, args.max_tokens)
        probe_report = run_probes(generate_fn, source=args.lang)
        md = write_security_md(audit_result=audit_result, probe_report=probe_report, repo_id=args.repo_id)
        _emit(md, args.output)


def _emit(text: str, output: str | None):
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Written to {output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
