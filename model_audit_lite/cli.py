"""model-audit-lite CLI

使い方:
    model-audit-lite audit <repo_id>
        配布物としての安全性監査のみ（pickle検出・カスタムコード検出・チェックサム）。
        モデルのロードは不要で、どんなリポジトリにも使える。

    model-audit-lite probe <repo_id> --backend mlx-lm [--lang ja|en]
        簡易安全性プローブ（既知の攻撃パターンでの生成テスト）。モデルのロードが必要。

    model-audit-lite full <repo_id> --backend mlx-lm [--lang ja|en] [-o SECURITY.md]
        両方を実行し、Markdownレポートを書き出す。

    model-audit-lite bom <repo_id> [--base <source_repo_id>] [--merge existing-bom.json] [-o bom.json]
        CycloneDX 1.6 ML-BOM（ファイルのチェックサム・指摘・変換系譜）。他ツールのBOMにマージ可能。

    model-audit-lite compare <base_repo_id> <derived_repo_id> [--probes] [--lang ja|en] [-o report.md]
        変換の完全性監査。変換元リポジトリと変換後リポジトリの`chat_template`を比較し、
        改変を検出する。`--probes`を付けると、同一の安全性プローブを両方のモデルに実行し、
        判定が変化した項目（特に安全→危険のレグレッション）だけを報告する。
"""
from __future__ import annotations

import argparse
import sys

from .conversion_audit import diff_chat_template, diff_probe_results
from .file_audit import audit_repo
from .probes.runner import run_probes
from .report import build_file_audit_section, build_probe_section, write_comparison_report, write_security_md


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
    p_audit.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_audit.add_argument("-o", "--output", default=None, help="Write markdown to this file instead of stdout")

    p_probe = sub.add_parser("probe", help="Run the safety-probe prompt suite (requires loading the model)")
    p_probe.add_argument("repo_id")
    p_probe.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_probe.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_probe.add_argument("--probe-set", default=None, help="Probe set: ja, en, ja-injection, or a YAML path (default: same as --lang)")
    p_probe.add_argument("--max-tokens", type=int, default=300)
    p_probe.add_argument("-o", "--output", default=None)

    p_full = sub.add_parser("full", help="Run both file audit and safety probes")
    p_full.add_argument("repo_id")
    p_full.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_full.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_full.add_argument("--probe-set", default=None, help="Probe set: ja, en, ja-injection, or a YAML path (default: same as --lang)")
    p_full.add_argument("--max-tokens", type=int, default=300)
    p_full.add_argument("-o", "--output", default="SECURITY.md")

    p_compare = sub.add_parser(
        "compare",
        help="Conversion-integrity audit: diff chat_template and (optionally) safety-probe results between a source and a converted repo",
    )
    p_compare.add_argument("base_repo_id", help="The original (pre-conversion) repo")
    p_compare.add_argument("derived_repo_id", help="The converted repo")
    p_compare.add_argument("--probes", action="store_true", help="Also run and diff the safety-probe suite (loads both models)")
    p_compare.add_argument("--base-backend", default="transformers", choices=["mlx-lm", "transformers"])
    p_compare.add_argument("--derived-backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_compare.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_compare.add_argument("--max-tokens", type=int, default=300)
    p_compare.add_argument("-o", "--output", default=None)

    p_bom = sub.add_parser(
        "bom",
        help="Write a CycloneDX 1.6 ML-BOM: file checksums, findings and (with --base) conversion lineage; optionally merge into another BOM",
    )
    p_bom.add_argument("repo_id")
    p_bom.add_argument("--base", default=None, help="Source repo this one was converted/derived from (adds pedigree + chat-template check)")
    p_bom.add_argument("--merge", default=None, help="Existing CycloneDX JSON (e.g. from OWASP AIBOM Generator / cdxgen) to merge into")
    p_bom.add_argument("-o", "--output", default=None)

    args = parser.parse_args(argv)

    if args.command == "audit":
        result = audit_repo(args.repo_id)
        md = build_file_audit_section(result, lang=getattr(args, "lang", "ja"))
        _emit(md, args.output)

    elif args.command == "probe":
        generate_fn = _make_generate_fn(args.backend, args.repo_id, args.max_tokens)
        report = run_probes(generate_fn, source=args.probe_set or args.lang)
        md = build_probe_section(report, lang=args.lang)
        _emit(md, args.output)

    elif args.command == "full":
        audit_result = audit_repo(args.repo_id)
        generate_fn = _make_generate_fn(args.backend, args.repo_id, args.max_tokens)
        probe_report = run_probes(generate_fn, source=args.probe_set or args.lang)
        md = write_security_md(audit_result=audit_result, probe_report=probe_report, repo_id=args.repo_id, lang=args.lang)
        _emit(md, args.output)

    elif args.command == "bom":
        import json

        from huggingface_hub import HfApi

        from .bom import build_bom, merge_into

        api = HfApi()
        info = api.model_info(args.repo_id)
        card = getattr(info, "card_data", None)
        base_rev = api.model_info(args.base).sha if args.base else None
        bom = build_bom(
            audit_repo(args.repo_id, api=api),
            base_repo_id=args.base,
            base_revision=base_rev,
            revision=info.sha,
            license_id=getattr(card, "license", None) if card else None,
            tags=list(info.tags or []),
            template_diff=diff_chat_template(args.base, args.repo_id) if args.base else None,
        )
        if args.merge:
            with open(args.merge, encoding="utf-8") as f:
                bom = merge_into(json.load(f), bom)
        _emit(json.dumps(bom, ensure_ascii=False, indent=2), args.output)

    elif args.command == "compare":
        template_diff = diff_chat_template(args.base_repo_id, args.derived_repo_id)
        probe_diff = None
        probe_total = 0
        if args.probes:
            base_fn = _make_generate_fn(args.base_backend, args.base_repo_id, args.max_tokens)
            derived_fn = _make_generate_fn(args.derived_backend, args.derived_repo_id, args.max_tokens)
            base_report = run_probes(base_fn, source=args.lang)
            derived_report = run_probes(derived_fn, source=args.lang)
            probe_diff = diff_probe_results(base_report, derived_report)
            probe_total = derived_report.total
        md = write_comparison_report(
            template_diff=template_diff,
            probe_diff=probe_diff,
            probe_total=probe_total,
            base_repo_id=args.base_repo_id,
            derived_repo_id=args.derived_repo_id,
            lang=args.lang,
        )
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
