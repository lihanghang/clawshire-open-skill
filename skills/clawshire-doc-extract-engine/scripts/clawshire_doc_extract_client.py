#!/usr/bin/env python3
"""
ClawShire 文档提取引擎 CLI — /api/v1/doc-extract-engine/*

依赖: pip install httpx
环境: CLAWSHIRE_API_KEY
可选: CLAWSHIRE_API_BASE_URL（默认 https://api.clawshire.cn）

记忆复用流程（推荐）：
    # 查看历史任务及 schema 预览，判断是否有可复用的
    python clawshire_doc_extract_client.py sessions-summary

    # 有相似任务时，直接复用其 schema 创建新 session（跳过 schema-chat）
    python clawshire_doc_extract_client.py session-create \\
        --name "新任务" --from-session 2 --doc-ids "new_doc_id"

    # 导出历史 schema 到文件（便于查看或手动修改后复用）
    python clawshire_doc_extract_client.py schema-export 2 --out schema.json

完整首次流程：
    python clawshire_doc_extract_client.py upload a.pdf
    python clawshire_doc_extract_client.py schema-create --doc-ids id1
    python clawshire_doc_extract_client.py schema-chat 1 "提取标题和摘要"
    python clawshire_doc_extract_client.py session-create --name "任务" --schema-file schema.json --doc-ids id1
    python clawshire_doc_extract_client.py extract --session-id 1 --doc-ids id1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("缺少依赖: pip install httpx", file=sys.stderr)
    sys.exit(1)

DEFAULT_BASE = "https://api.clawshire.cn"
TIMEOUT_LONG = 600.0


def base_url() -> str:
    return os.environ.get("CLAWSHIRE_API_BASE_URL", DEFAULT_BASE).rstrip("/")


def api_key() -> str:
    k = os.environ.get("CLAWSHIRE_API_KEY")
    if not k:
        print("请设置 CLAWSHIRE_API_KEY", file=sys.stderr)
        sys.exit(1)
    return k


def headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Accept": "application/json",
    }


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _fetch_session_schema(client: httpx.Client, session_id: int) -> dict | None:
    """从 session history 中还原 extraction_schema。"""
    try:
        r = client.get(
            f"{base_url()}/api/v1/doc-extract-engine/sessions/{session_id}/history",
            headers=headers(),
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        # history 可能是列表或含 extraction_schema 字段的对象，兼容两种格式
        if isinstance(data, dict):
            return data.get("extraction_schema") or data.get("schema")
        if isinstance(data, list) and data:
            first = data[0]
            return first.get("extraction_schema") or first.get("schema")
    except Exception:
        pass
    return None


def _schema_field_preview(schema: dict | None, max_fields: int = 8) -> str:
    """将 schema properties 展开为可读的字段预览字符串。"""
    if not schema or not isinstance(schema, dict):
        return "(无 schema)"
    props = schema.get("properties", {})
    if not props:
        return "(schema 无字段)"

    def _collect(obj: dict, prefix: str = "") -> list[str]:
        fields = []
        for k, v in obj.get("properties", {}).items():
            full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict) and "properties" in v:
                fields.extend(_collect(v, full))
            else:
                fields.append(full)
        return fields

    fields = _collect(schema)
    preview = ", ".join(fields[:max_fields])
    if len(fields) > max_fields:
        preview += f" ... (共 {len(fields)} 个字段)"
    return preview


# ──────────────────────────────────────────────
# 命令实现
# ──────────────────────────────────────────────

def cmd_status(_: argparse.Namespace) -> None:
    with httpx.Client(timeout=60.0) as c:
        r = c.get(f"{base_url()}/api/v1/doc-extract-engine/status", headers=headers())
    r.raise_for_status()
    _print_json(r.json())


def cmd_upload(args: argparse.Namespace) -> None:
    paths = [Path(p) for p in args.files]
    for p in paths:
        if not p.exists():
            print(f"文件不存在: {p}", file=sys.stderr)
            sys.exit(1)
        if p.suffix.lower() != ".pdf":
            print(f"非 PDF: {p}", file=sys.stderr)
            sys.exit(1)
    multipart: list[tuple[str, Any]] = []
    for p in paths:
        multipart.append(
            ("files", (p.name, p.read_bytes(), "application/pdf")),
        )
    with httpx.Client(timeout=TIMEOUT_LONG) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/upload",
            headers=headers(),
            files=multipart,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_schema_create(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]
    body = {"document_ids": ids}
    with httpx.Client(timeout=120.0) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/schema-conversations",
            headers={**headers(), "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_schema_chat(args: argparse.Namespace) -> None:
    cid = int(args.conversation_id)
    body = {"message": args.message}
    with httpx.Client(timeout=TIMEOUT_LONG) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/schema-conversations/{cid}/chat",
            headers={**headers(), "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_schema_get(args: argparse.Namespace) -> None:
    cid = int(args.conversation_id)
    with httpx.Client(timeout=120.0) as c:
        r = c.get(
            f"{base_url()}/api/v1/doc-extract-engine/schema-conversations/{cid}",
            headers=headers(),
        )
    r.raise_for_status()
    _print_json(r.json())


def cmd_sessions_summary(_: argparse.Namespace) -> None:
    """列出所有历史 Session，并附带 schema 字段预览，供 AI 判断是否可复用。"""
    with httpx.Client(timeout=120.0) as c:
        r = c.get(f"{base_url()}/api/v1/doc-extract-engine/sessions", headers=headers())
        r.raise_for_status()
        sessions = r.json()

        if isinstance(sessions, dict):
            sessions = sessions.get("data") or sessions.get("sessions") or sessions.get("items") or []

        if not sessions:
            print("暂无历史提取任务。")
            return

        print(f"\n{'─' * 64}")
        print(f"  历史提取任务（共 {len(sessions)} 条）")
        print(f"{'─' * 64}")

        for s in sessions:
            sid = s.get("id") or s.get("session_id")
            name = s.get("session_name") or s.get("name") or "(无名称)"
            created = str(s.get("created_at") or s.get("create_time") or "")[:10]
            doc_count = len(s.get("document_ids") or [])

            schema = _fetch_session_schema(c, int(sid))
            preview = _schema_field_preview(schema)

            print(f"\n  [{sid}] {name}  {created}  文档数: {doc_count}")
            print(f"       字段: {preview}")

        print(f"\n{'─' * 64}")
        print("  复用方式: session-create --name <名称> --from-session <id> --doc-ids <ids>")
        print(f"{'─' * 64}\n")


def cmd_schema_export(args: argparse.Namespace) -> None:
    """从历史 Session 导出 schema 到本地文件。"""
    sid = int(args.session_id)
    with httpx.Client(timeout=120.0) as c:
        schema = _fetch_session_schema(c, sid)

    if not schema:
        print(f"未能从 session {sid} 获取 schema，请确认 session_id 正确。", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out) if args.out else Path(f"schema_from_session_{sid}.json")
    out_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"schema 已导出到: {out_path}")
    print(f"字段预览: {_schema_field_preview(schema)}")


def cmd_session_create(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]

    # 复用历史 schema
    if args.from_session:
        print(f"  正在从 session {args.from_session} 读取 schema...", end="", flush=True)
        with httpx.Client(timeout=120.0) as c:
            extraction_schema = _fetch_session_schema(c, int(args.from_session))
        if not extraction_schema:
            print(f"\n未能从 session {args.from_session} 获取 schema。", file=sys.stderr)
            sys.exit(1)
        print(f" ✓  字段: {_schema_field_preview(extraction_schema)}")

    # 从文件读取 schema
    elif args.schema_file:
        schema_path = Path(args.schema_file)
        if not schema_path.exists():
            print(f"找不到 schema 文件: {schema_path}", file=sys.stderr)
            sys.exit(1)
        extraction_schema = json.loads(schema_path.read_text(encoding="utf-8"))

    else:
        print("需要 --schema-file 或 --from-session 之一。", file=sys.stderr)
        sys.exit(1)

    body = {
        "session_name": args.name,
        "extraction_schema": extraction_schema,
        "document_ids": ids,
    }
    with httpx.Client(timeout=120.0) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/sessions",
            headers={**headers(), "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_session_list(_: argparse.Namespace) -> None:
    with httpx.Client(timeout=120.0) as c:
        r = c.get(f"{base_url()}/api/v1/doc-extract-engine/sessions", headers=headers())
    r.raise_for_status()
    _print_json(r.json())


def cmd_history(args: argparse.Namespace) -> None:
    sid = int(args.session_id)
    with httpx.Client(timeout=120.0) as c:
        r = c.get(
            f"{base_url()}/api/v1/doc-extract-engine/sessions/{sid}/history",
            headers=headers(),
        )
    r.raise_for_status()
    _print_json(r.json())


def cmd_extract(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]
    body = {"session_id": int(args.session_id), "document_ids": ids}
    with httpx.Client(timeout=TIMEOUT_LONG) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/extract",
            headers={**headers(), "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_batch_chat(args: argparse.Namespace) -> None:
    bid = int(args.batch_id)
    body = {"message": args.message}
    with httpx.Client(timeout=TIMEOUT_LONG) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/batches/{bid}/chat",
            headers={**headers(), "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def cmd_batch_end(args: argparse.Namespace) -> None:
    bid = int(args.batch_id)
    with httpx.Client(timeout=120.0) as c:
        r = c.post(
            f"{base_url()}/api/v1/doc-extract-engine/batches/{bid}/end",
            headers=headers(),
        )
    if r.status_code >= 400:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    _print_json(r.json())


def main() -> None:
    p = argparse.ArgumentParser(description="ClawShire 文档提取引擎 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="引擎状态")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("upload", help="上传 PDF（可多文件）")
    sp.add_argument("files", nargs="+", help="本地 .pdf 路径")
    sp.set_defaults(func=cmd_upload)

    sp = sub.add_parser("schema-create", help="创建 Schema 对话")
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.set_defaults(func=cmd_schema_create)

    sp = sub.add_parser("schema-chat", help="Schema 对话一轮")
    sp.add_argument("conversation_id", help="conversation_id")
    sp.add_argument("message", help="自然语言需求")
    sp.set_defaults(func=cmd_schema_chat)

    sp = sub.add_parser("schema-get", help="获取 Schema 对话状态")
    sp.add_argument("conversation_id", help="conversation_id")
    sp.set_defaults(func=cmd_schema_get)

    sp = sub.add_parser("sessions-summary", help="列出历史任务及 schema 字段预览（复用入口）")
    sp.set_defaults(func=cmd_sessions_summary)

    sp = sub.add_parser("schema-export", help="从历史 Session 导出 schema 到文件")
    sp.add_argument("session_id", help="session_id")
    sp.add_argument("--out", default="", help="输出文件路径（默认 schema_from_session_{id}.json）")
    sp.set_defaults(func=cmd_schema_export)

    sp = sub.add_parser("session-create", help="创建提取 Session（支持复用历史 schema）")
    sp.add_argument("--name", required=True, help="session 名称")
    sp.add_argument("--schema-file", default="", help="JSON Schema 文件路径")
    sp.add_argument("--from-session", default="", help="从历史 session 复用 schema（优先级高于 --schema-file）")
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.set_defaults(func=cmd_session_create)

    sp = sub.add_parser("sessions", help="列出引擎 Session（原始 JSON）")
    sp.set_defaults(func=cmd_session_list)

    sp = sub.add_parser("history", help="Session 历史")
    sp.add_argument("session_id", help="session_id")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("extract", help="执行提取")
    sp.add_argument("--session-id", required=True)
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("batch-chat", help="批次修正一轮")
    sp.add_argument("batch_id", help="batch_id")
    sp.add_argument("message", help="修正说明")
    sp.set_defaults(func=cmd_batch_chat)

    sp = sub.add_parser("batch-end", help="结束批次")
    sp.add_argument("batch_id", help="batch_id")
    sp.set_defaults(func=cmd_batch_end)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
