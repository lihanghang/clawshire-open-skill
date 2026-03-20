#!/usr/bin/env python3
"""
财务报告分析客户端

调用 ClawShire 财务分析 API，对 PDF 年报进行深度风险评估。

用法：
    python financial_analysis_client.py analyze path/to/年报.pdf
    python financial_analysis_client.py analyze path/to/年报.pdf --lang en
    python financial_analysis_client.py analyze path/to/年报.pdf --output html
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
from datetime import datetime
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
    if getattr(args, "output", None) == "html":
        out_path = _default_html_name(pdf_path)
        _export_html(job, elapsed, args.lang, out_path)
        print(f"  已生成报告：{out_path}")
    else:
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


def _default_html_name(pdf_path: Path) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(pdf_path.parent / f"{pdf_path.stem}_risk_{ts}.html")


def _export_html(job: dict, elapsed: int, lang: str, out_path: str) -> None:
    """将分析结果渲染为独立 HTML 报告。"""
    overall = job.get("overall_risk_level", "unknown")
    rules = job.get("rule_results", [])
    name_key = "display_name_zh" if lang == "zh" else "display_name_en"
    conclusion_key = "conclusion_zh" if lang == "zh" else "conclusion_en"

    high = [r for r in rules if r.get("risk_level") == "high"]
    medium = [r for r in rules if r.get("risk_level") == "medium"]
    low = [r for r in rules if r.get("risk_level") == "low"]
    na = [r for r in rules if not r.get("risk_level")]

    risk_color = {"high": "#e53e3e", "medium": "#d97706", "low": "#16a34a"}.get(overall, "#6b7280")
    risk_label = RISK_LABEL.get(overall, overall)
    risk_emoji = RISK_EMOJI.get(overall, "⚪")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def rule_cards(rule_list: list, level: str) -> str:
        if not rule_list:
            return ""
        color = {"high": "#fef2f2", "medium": "#fffbeb", "low": "#f0fdf4"}.get(level, "#f9fafb")
        border = {"high": "#fca5a5", "medium": "#fcd34d", "low": "#86efac"}.get(level, "#e5e7eb")
        badge_bg = {"high": "#e53e3e", "medium": "#d97706", "low": "#16a34a"}.get(level, "#6b7280")
        label = {"high": "高风险", "medium": "中风险", "low": "低风险"}.get(level, "不适用")
        cards = []
        for r in rule_list:
            name = r.get(name_key) or r.get("display_name_zh", "")
            conclusion = r.get(conclusion_key) or r.get("conclusion_zh", "")
            category = r.get("rule_category", "")
            evidence_list = r.get("evidence", [])
            evidence_html = ""
            if evidence_list:
                items = "".join(f"<li>{e}</li>" for e in evidence_list)
                evidence_html = f'<ul class="evidence">{items}</ul>'
            cards.append(f"""
            <div class="rule-card" style="background:{color};border-color:{border}">
              <div class="rule-header">
                <span class="rule-name">{name}</span>
                <span class="badge" style="background:{badge_bg}">{label}</span>
                {"<span class='category'>" + category + "</span>" if category else ""}
              </div>
              {"<p class='conclusion'>" + conclusion + "</p>" if conclusion else ""}
              {evidence_html}
            </div>""")
        return "\n".join(cards)

    sections = ""
    if high:
        sections += f"""
        <section>
          <h2 class="section-title high">🔴 高风险项（{len(high)} 条）</h2>
          {rule_cards(high, "high")}
        </section>"""
    if medium:
        sections += f"""
        <section>
          <h2 class="section-title medium">🟡 中风险项（{len(medium)} 条）</h2>
          {rule_cards(medium, "medium")}
        </section>"""
    if low:
        sections += f"""
        <section>
          <h2 class="section-title low">🟢 低风险项（{len(low)} 条）</h2>
          {rule_cards(low, "low")}
        </section>"""
    if not high and not medium:
        sections += """
        <section>
          <div class="no-risk">🟢 未发现高风险或中风险项</div>
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>财务风险分析报告</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
           background: #f1f5f9; color: #1e293b; line-height: 1.6; }}
    .container {{ max-width: 900px; margin: 32px auto; padding: 0 16px 64px; }}

    /* 顶部摘要卡 */
    .summary {{ background: #fff; border-radius: 16px; padding: 32px;
               box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 32px; }}
    .summary-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }}
    .risk-badge {{ font-size: 2rem; font-weight: 700; color: {risk_color};
                  padding: 8px 20px; border: 3px solid {risk_color};
                  border-radius: 12px; white-space: nowrap; }}
    .summary-title h1 {{ font-size: 1.4rem; font-weight: 600; color: #0f172a; }}
    .summary-title p {{ font-size: 0.85rem; color: #64748b; margin-top: 4px; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .stat {{ background: #f8fafc; border-radius: 10px; padding: 14px 16px; text-align: center; }}
    .stat-num {{ font-size: 1.6rem; font-weight: 700; }}
    .stat-label {{ font-size: 0.75rem; color: #64748b; margin-top: 2px; }}
    .stat.red .stat-num {{ color: #e53e3e; }}
    .stat.yellow .stat-num {{ color: #d97706; }}
    .stat.green .stat-num {{ color: #16a34a; }}
    .stat.gray .stat-num {{ color: #6b7280; }}
    .meta {{ margin-top: 20px; font-size: 0.8rem; color: #94a3b8;
             display: flex; gap: 24px; flex-wrap: wrap; }}

    /* 规则区块 */
    section {{ margin-bottom: 28px; }}
    .section-title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 14px; padding-bottom: 8px;
                      border-bottom: 2px solid #e2e8f0; }}
    .section-title.high {{ color: #e53e3e; border-color: #fca5a5; }}
    .section-title.medium {{ color: #d97706; border-color: #fcd34d; }}
    .section-title.low {{ color: #16a34a; border-color: #86efac; }}

    /* 规则卡片 */
    .rule-card {{ border: 1px solid; border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }}
    .rule-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }}
    .rule-name {{ font-weight: 600; font-size: 0.95rem; }}
    .badge {{ font-size: 0.7rem; font-weight: 600; color: #fff;
              padding: 2px 8px; border-radius: 20px; white-space: nowrap; }}
    .category {{ font-size: 0.75rem; color: #64748b; background: #f1f5f9;
                 padding: 2px 8px; border-radius: 20px; }}
    .conclusion {{ font-size: 0.875rem; color: #374151; margin-top: 4px; }}
    .evidence {{ margin-top: 10px; padding-left: 18px; font-size: 0.8rem; color: #64748b; }}
    .evidence li {{ margin-bottom: 4px; }}
    .no-risk {{ background: #f0fdf4; border: 1px solid #86efac; border-radius: 10px;
                padding: 20px; text-align: center; font-size: 1rem;
                color: #16a34a; font-weight: 500; }}

    /* 页脚 */
    .footer {{ text-align: center; font-size: 0.75rem; color: #94a3b8; margin-top: 48px; }}
    .footer a {{ color: #94a3b8; }}

    @media (max-width: 600px) {{
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .summary-header {{ flex-direction: column; align-items: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="summary">
      <div class="summary-header">
        <div class="risk-badge">{risk_emoji} {risk_label}</div>
        <div class="summary-title">
          <h1>财务风险分析报告</h1>
          <p>由 ClawShire 财务分析引擎生成 · {generated_at}</p>
        </div>
      </div>
      <div class="stats">
        <div class="stat red">
          <div class="stat-num">{len(high)}</div>
          <div class="stat-label">高风险</div>
        </div>
        <div class="stat yellow">
          <div class="stat-num">{len(medium)}</div>
          <div class="stat-label">中风险</div>
        </div>
        <div class="stat green">
          <div class="stat-num">{len(low)}</div>
          <div class="stat-label">低风险</div>
        </div>
        <div class="stat gray">
          <div class="stat-num">{len(na)}</div>
          <div class="stat-label">不适用</div>
        </div>
      </div>
      <div class="meta">
        <span>共分析 {len(rules)} 条规则</span>
        <span>耗时 {elapsed // 60} 分 {elapsed % 60} 秒</span>
      </div>
    </div>

    {sections}

    <div class="footer">
      <p>报告由 <a href="https://clawshire.cn">ClawShire</a> 生成，仅供参考，不构成投资建议。</p>
    </div>
  </div>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


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
    p_analyze.add_argument("--output", choices=["html"], default=None, help="导出格式（html）")

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
