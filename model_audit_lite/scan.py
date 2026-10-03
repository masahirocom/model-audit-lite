"""`scan`: one command that runs the file audit, (optionally) the conversion-integrity compare and the safety probes,
and writes everything to one output directory: report.md (human), bom.json (CycloneDX 1.6) and summary.json (CI).

Pure assembly over the other modules; `run_scan` takes already-computed results so it can be tested without network.
"""
from __future__ import annotations

import json
from pathlib import Path

from .bom import build_bom
from .report import build_chat_template_diff_section, build_file_audit_section, build_probe_diff_section, build_probe_section


def assess(audit_result: dict, template_diff=None, probe_diff=None, probe_report=None) -> dict:
    """Machine-readable verdict. `fail` reasons are the ones a CI gate should stop on."""
    fail, warn = [], []
    if audit_result.get("risky_pickle_files"):
        fail.append("pickle-files")
    if audit_result.get("custom_code_files"):
        warn.append("custom-code-files")
    if template_diff is not None and template_diff.changed:
        fail.append("chat-template-changed")
    if probe_diff is not None:
        regressions = [i for i in probe_diff.items if i.base_safe and not i.derived_safe]
        if regressions:
            fail.append("probe-regressions")
    summary = {
        "repo_id": audit_result["repo_id"],
        "status": "fail" if fail else ("warn" if warn else "pass"),
        "fail": fail,
        "warn": warn,
        "files": audit_result.get("total_files"),
        "pickle_files": len(audit_result.get("risky_pickle_files", [])),
        "custom_code_files": len(audit_result.get("custom_code_files", [])),
    }
    if template_diff is not None:
        summary["chat_template_changed"] = bool(template_diff.changed)
    if probe_report is not None:
        summary["probe_safe"] = f"{probe_report.safe_count}/{probe_report.total}"
    if probe_diff is not None:
        summary["probe_regressions"] = sum(1 for i in probe_diff.items if i.base_safe and not i.derived_safe)
    return summary


def run_scan(
    audit_result: dict,
    out_dir: str | Path,
    *,
    lang: str = "ja",
    base_repo_id: str | None = None,
    template_diff=None,
    probe_report=None,
    probe_diff=None,
    probe_total: int = 0,
    revision: str | None = None,
    base_revision: str | None = None,
    license_id: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    parts = [f"# model-audit-lite scan: {audit_result['repo_id']}", build_file_audit_section(audit_result, lang=lang)]
    if template_diff is not None:
        parts.append(build_chat_template_diff_section(template_diff, lang=lang))
    if probe_diff is not None:
        parts.append(build_probe_diff_section(probe_diff, probe_total, lang=lang))
    if probe_report is not None:
        parts.append(build_probe_section(probe_report, lang=lang))
    (out / "report.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    bom = build_bom(
        audit_result, base_repo_id=base_repo_id, base_revision=base_revision, revision=revision, license_id=license_id,
        tags=tags, template_diff=template_diff, probe_diff=probe_diff, probe_total=probe_total,
    )
    (out / "bom.json").write_text(json.dumps(bom, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = assess(audit_result, template_diff, probe_diff, probe_report)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
