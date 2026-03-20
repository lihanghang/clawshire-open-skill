#!/usr/bin/env python3
"""
财务报告分析客户端

调用 ClawShire 财务分析 API，对 PDF 年报进行深度风险评估。

用法：
    python financial_analysis_client.py analyze path/to/年报.pdf
    python financial_analysis_client.py analyze path/to/年报.pdf --lang en
    python financial_analysis_client.py rules

前置条件：
    设置环境变量 CLAWSHIRE_API_KEY
    控制台开通财务分析权限（即将支持）

获取 API Key：https://clawshire.cn
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("缺少依赖，请先运行: pip install httpx")
    sys.exit(1)

BASE_URL = "https://api.clawshire.cn"
CONSOLE_URL = "https://clawshire.cn"

RISK_LABEL = {"low": "低风险", "medium": "中风险", "high": "高风险", None: "不适用", "": "不适用"}
RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴", None: "⚪", "": "⚪"}

STAGE_ORDER = ["pending", "parsing", "chunking", "extracting", "analyzing", "completed"]
STAGE_WEIGHT = {"pending": 5, "parsing": 15, "parsing_pdf": 15, "chunking": 10, "extracting": 20, "analyzing": 50}


def _require_api_key() -> str:
    key = os.environ.get("CLAWSHIRE_API_KEY")
    if not key:
        print(
            f"错误：未设置 CLAWSHIRE_API_KEY 环境变量。\n"
            f"请登录控制台创建 API Key：{CONSOLE_URL}\n"
            f"创建后执行：export CLAWSHIRE_API_KEY='sk-xxxxxxxx'",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _progress(stage: str, stage_pct: int) -> int:
    idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 0
    base = sum(STAGE_WEIGHT.get(s, 0) for s in STAGE_ORDER[:idx])
    weight = STAGE_WEIGHT.get(stage, 0)
    return min(100, base + int(weight * stage_pct / 100))


def _bar(pct: int, width: int = 24) -> str:
    filled = int(width * pct / 100)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:3d}%"


def cmd_analyze(args: argparse.Namespace) -> None:
    """上传 PDF 并等待分析完成。"""
    api_key = _require_api_key()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"文件不存在：{pdf_path}", file=sys.stderr)
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print("仅支持 PDF 文件", file=sys.stderr)
        sys.exit(1)

    size_mb = pdf_path.stat().st_size / 1024 / 1024
    print(f"  文件：{pdf_path.name} ({size_mb:.1f} MB)")
    print(f"  正在上传...", end="", flush=True)

    # 上传
    with open(pdf_path, "rb") as f:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/financial-analysis/jobs",
            files={"file": (pdf_path.name, f, "application/pdf")},
            data={"language": args.lang},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120,
        )
    resp.raise_for_status()
    job = resp.json()
    job_id = job.get("id")
    print(f" ✓")
    print(f"  job_id: {job_id}")

    # 轮询
    print(f"\n  ▶ 等待分析")
    poll_start = time.time()
    prev_stage = None

    while True:
        time.sleep(5)
        resp = httpx.get(
            f"{BASE_URL}/api/v1/financial-analysis/jobs/{job_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        job = resp.json()

        stage = job.get("status", "unknown")
        stage_pct = job.get("progress", 0)
        total_pct = _progress(stage, stage_pct)

        if stage != prev_stage:
            if prev_stage is not None:
                print(f"     ✓")
            print(f"     {stage}: ", end="", flush=True)
            prev_stage = stage

        print(f"\r  ▶ {_bar(total_pct)}", end="\r", flush=True)

        if stage in ("completed", "failed"):
            print()  # 换行
            break

    elapsed = int(time.time() - poll_start)
    if job.get("status") == "failed":
        print(f"\n✗ 分析失败：{job.get('error_message', '未知错误')}")
        sys.exit(1)

    # 输出结果
    _print_result(job, elapsed, args.lang)


def _print_result(job: dict, elapsed: int, lang: str) -> None:
    overall = job.get("overall_risk_level", "unknown")
    rules = job.get("rule_results", [])

    name_key = "display_name_zh" if lang == "zh" else "display_name_en"

    high = [r for r in rules if r.get("risk_level") == "high"]
    medium = [r for r in rules if r.get("risk_level") == "medium"]
    low = [r for r in rules if r.get("risk_level") == "low"]
    na = [r for r in rules if not r.get("risk_level")]

    W = 52
    print("\n" + "─" * W)
    print(f"  总体风险：{RISK_EMOJI.get(overall, '')} {RISK_LABEL.get(overall, overall).upper()}")
    print(f"  规则数量：共 {len(rules)} 条  🔴 {len(high)}  🟡 {len(medium)}  🟢 {len(low)}  ⚪ {len(na)}")
    print(f"  分析耗时：{elapsed // 60} 分 {elapsed % 60} 秒")
    print("─" * W)

    if high:
        print("\n  🔴 高风险项：")
        for r in high:
            print(f"     • {r.get(name_key) or r.get('display_name_zh', '')}")

    if medium:
        print("\n  🟡 中风险项：")
        for r in medium:
            print(f"     • {r.get(name_key) or r.get('display_name_zh', '')}")

    if not high and not medium:
        print("\n  🟢 未发现高风险或中风险项")

    print("─" * W + "\n")


def cmd_rules(args: argparse.Namespace) -> None:
    """列出所有分析规则。"""
    api_key = _require_api_key()

    resp = httpx.get(
        f"{BASE_URL}/api/v1/financial-analysis/rules",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    rules = resp.json()

    if isinstance(rules, dict) and "data" in rules:
        rules = rules["data"]
    if not isinstance(rules, list):
        rules = [rules]

    print(f"\n共 {len(rules)} 条分析规则：\n")
    for r in rules:
        name = r.get("display_name_zh") or r.get("display_name_en") or r.get("name", "")
        cat = r.get("rule_category", "")
        desc = r.get("description_zh") or r.get("description_en", "")
        print(f"  • {name}")
        if cat:
            print(f"    分类：{cat}")
        if desc:
            print(f"    描述：{desc}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="财务报告分析客户端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="上传 PDF 并分析风险")
    p_analyze.add_argument("pdf", help="PDF 文件路径")
    p_analyze.add_argument("--lang", choices=["zh", "en"], default="zh", help="报告语言（默认 zh）")

    # rules
    sub.add_parser("rules", help="列出所有分析规则")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "cmd_rules":
        cmd_rules(args)


if __name__ == "__main__":
    main()
