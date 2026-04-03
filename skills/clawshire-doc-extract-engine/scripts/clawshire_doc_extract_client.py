#!/usr/bin/env python3
"""
ClawShire 文档提取引擎 CLI — /api/v1/doc-extract-engine/*

无需安装任何第三方依赖，仅使用 Python 标准库。
环境: CLAWSHIRE_API_KEY
可选: CLAWSHIRE_API_BASE_URL（默认 https://api.clawshire.cn）

快速开始（三步）：
    1. python clawshire_doc_extract_client.py upload a.pdf
    2. python clawshire_doc_extract_client.py schema-create --doc-ids <id>
       python clawshire_doc_extract_client.py schema-chat <conv_id> "提取甲方、乙方、金额"
       python clawshire_doc_extract_client.py session-create --name 任务 --schema-file schema.json --doc-ids <id>
    3. python clawshire_doc_extract_client.py extract --session-id <sid> --doc-ids <id> --out result.json --auto-end

高级用法（省 Token / 省额度）：
    --quiet       不打印完整 JSON，仅打印字段覆盖率概要（配合 --out 使用）
    --use-cache   命中本地缓存时读取已有 batch 结果，不消耗提取额度
    --summary     batch-result 仅显示覆盖率和首条预览
    --from-lib    从本地 schema 库复用，跳过 schema-chat 流程
    --search      schema-lib-list 关键字模糊过滤

缓存文件：~/.clawshire/cache.json（按 API Key + BaseURL + session_id + doc_ids 隔离）
Schema 库：~/.clawshire/schemas.json（跨 key 复用）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import io
import uuid
import email.generator
import email.mime.multipart
import email.mime.base
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

DEFAULT_BASE = "https://api.clawshire.cn"
TIMEOUT_LONG = 600
SCHEMA_LIB_PATH = Path.home() / ".clawshire" / "schemas.json"
CACHE_PATH = Path.home() / ".clawshire" / "cache.json"


# ──────────────────────────────────────────────
# 基础工具
# ──────────────────────────────────────────────

def base_url() -> str:
    return os.environ.get("CLAWSHIRE_API_BASE_URL", DEFAULT_BASE).rstrip("/")


def api_key() -> str:
    k = os.environ.get("CLAWSHIRE_API_KEY")
    if not k:
        print("请设置 CLAWSHIRE_API_KEY", file=sys.stderr)
        sys.exit(1)
    return k


def _headers(extra: dict | None = None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key()}",
        "Accept": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _do_request(req: Request, timeout: int = 120) -> Any:
    """执行 urllib 请求，返回解析后的 JSON。HTTP 错误时打印响应体并退出。"""
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_http_error": e.code, "_body": body, "_status": e.code}
    except URLError as e:
        return {"_url_error": str(e)}


def _request_json(method: str, url: str, payload: Any = None, timeout: int = 120) -> Any:
    """发送 JSON 请求，返回响应数据。出错时打印并退出。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, method=method)
    for k, v in _headers({"Content-Type": "application/json"} if data else {}).items():
        req.add_header(k, v)
    result = _do_request(req, timeout=timeout)
    _check_error(result)
    return result


def _request_get(url: str, timeout: int = 120) -> Any:
    req = Request(url, method="GET")
    for k, v in _headers().items():
        req.add_header(k, v)
    result = _do_request(req, timeout=timeout)
    _check_error(result)
    return result


def _check_error(result: dict, fatal: bool = True) -> bool:
    """检查响应是否为错误，fatal=True 时打印并退出。"""
    if not isinstance(result, dict):
        return False
    status = result.get("_http_error") or result.get("_status")
    if status and int(status) >= 400:
        body = result.get("_body", "")
        print(f"HTTP {status}: {body}", file=sys.stderr)
        if fatal:
            sys.exit(1)
        return True
    if "_url_error" in result:
        print(f"网络错误: {result['_url_error']}", file=sys.stderr)
        if fatal:
            sys.exit(1)
        return True
    return False


def _build_multipart(fields: list[tuple[str, Any]]) -> tuple[bytes, str]:
    """
    手动构建 multipart/form-data。
    fields: [(name, (filename, data, content_type)), ...]
    返回 (body_bytes, content_type_header)
    """
    boundary = uuid.uuid4().hex
    lines = []
    for name, value in fields:
        if isinstance(value, tuple):
            filename, data, mime = value
            lines.append(f"--{boundary}".encode())
            lines.append(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
            )
            lines.append(f"Content-Type: {mime}".encode())
            lines.append(b"")
            lines.append(data if isinstance(data, bytes) else data.encode())
        else:
            lines.append(f"--{boundary}".encode())
            lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
            lines.append(b"")
            lines.append(str(value).encode())
    lines.append(f"--{boundary}--".encode())
    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _retry_request(func, max_retries: int = 2, desc: str = "请求") -> Any:
    """重试机制：处理 504 等超时错误"""
    for attempt in range(max_retries + 1):
        try:
            result = func()
            status = result.get("_http_error") or result.get("_status") if isinstance(result, dict) else None
            if status == 504 and attempt < max_retries:
                print(f"  ⚠ {desc}超时 (504)，{attempt + 1}/{max_retries} 次重试中...", file=sys.stderr)
                continue
            return result
        except Exception as e:
            if attempt < max_retries:
                print(f"  ⚠ {desc}异常: {e}，{attempt + 1}/{max_retries} 次重试中...", file=sys.stderr)
                continue
            raise
    raise Exception(f"{desc}失败，已重试 {max_retries} 次")


def _save_json(data: Any, out: str, label: str = "result") -> str:
    """将 data 写入 JSON 文件，out 为空时自动生成文件名，返回实际路径。"""
    if not out:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = f"{label}_{ts}.json"
    path = Path(out)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已保存: {path}", file=sys.stderr)
    return str(path)


def _extract_fields(result_item: dict) -> dict:
    """
    从结果条目中提取字段数据，兼容多种 API 响应结构。
    按优先级尝试已知字段名，最终 fallback 为去掉元数据字段后的剩余内容。
    """
    for key in ("extracted_data", "result", "data", "extraction", "fields"):
        v = result_item.get(key)
        if isinstance(v, dict) and v:
            return v
    # Fallback：排除已知元数据键，返回剩余字段
    meta_keys = {"document_id", "batch_id", "id", "status", "created_at", "updated_at", "error"}
    return {k: v for k, v in result_item.items() if k not in meta_keys}


def _print_summary(data: Any, *, as_result: bool = False) -> None:
    """打印提取结果的统计概要（输出到 stderr，节省 Token）。"""
    if not isinstance(data, dict):
        _print_json(data)
        return

    batch_id = data.get("batch_id", data.get("id", "-"))
    results = data.get("results", [])
    doc_count = len(results)

    if as_result:
        print(f"\n  batch_id    : {batch_id}", file=sys.stderr)
        print(f"  文档数量    : {doc_count}", file=sys.stderr)
    else:
        print(f"\n  batch_id    : {batch_id}", file=sys.stderr)
        print(f"  文档数量    : {doc_count}", file=sys.stderr)

    if results:
        # 统计字段覆盖率
        all_keys: set[str] = set()
        filled: dict[str, int] = {}
        for r in results:
            extracted = _extract_fields(r)
            for k, v in extracted.items():
                all_keys.add(k)
                if v not in (None, "", [], {}):
                    filled[k] = filled.get(k, 0) + 1

        if all_keys:
            total_fields = len(all_keys)
            filled_fields = sum(1 for k in all_keys if filled.get(k, 0) > 0)
            print(f"  字段覆盖率  :", file=sys.stderr)
            for k in sorted(all_keys):
                cnt = filled.get(k, 0)
                bar = "█" if cnt > 0 else "░"
                print(f"    {k:<20} {bar}  {cnt}/{doc_count}", file=sys.stderr)
        else:
            print("  ⚠ 未识别到提取字段，建议直接用 batch-result 查看完整响应", file=sys.stderr)

        # 首条文档预览（stderr）
        first = results[0]
        doc_id = first.get("document_id", "-")
        extracted = _extract_fields(first)
        print(f"\n  首文档预览  : (doc={doc_id})", file=sys.stderr)
        if extracted:
            for k, v in list(extracted.items())[:5]:
                val_str = str(v)[:60] + ("..." if len(str(v)) > 60 else "")
                print(f"    {k}: {val_str}", file=sys.stderr)
            if len(extracted) > 5:
                print(f"    ... 共 {len(extracted)} 个字段", file=sys.stderr)
        else:
            print("    (无可识别字段)", file=sys.stderr)
    print(file=sys.stderr)


def _print_extracted_data(data: Any) -> None:
    """
    将实际提取结果（results[].data 或 results[].extracted_data）输出到 stdout。
    让 Claude 和用户都能直接看到结构化内容，而不只是摘要。
    """
    if not isinstance(data, dict):
        _print_json(data)
        return
    results = data.get("results", [])
    if not results:
        _print_json(data)
        return

    output = {
        "batch_id": data.get("batch_id"),
        "results": [
            {
                "document_id": r.get("document_id"),
                "data": _extract_fields(r),
            }
            for r in results
        ],
    }
    _print_json(output)


# ──────────────────────────────────────────────
# 本地 schema 库（~/.clawshire/schemas.json）
# ──────────────────────────────────────────────

def _lib_load() -> dict:
    if SCHEMA_LIB_PATH.exists():
        return json.loads(SCHEMA_LIB_PATH.read_text(encoding="utf-8"))
    return {}


def _lib_save(lib: dict) -> None:
    SCHEMA_LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_LIB_PATH.write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")


def _schema_field_preview(schema: dict | None, max_fields: int = 8) -> str:
    if not schema or not isinstance(schema, dict):
        return "(无 schema)"

    def _collect(obj: dict, prefix: str = "") -> list[str]:
        fields = []
        for k, v in obj.get("properties", {}).items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and "properties" in v:
                fields.extend(_collect(v, full))
            else:
                fields.append(full)
        return fields

    fields = _collect(schema)
    preview = ", ".join(fields[:max_fields])
    if len(fields) > max_fields:
        preview += f" ... (共 {len(fields)} 个字段)"
    return preview or "(schema 无字段)"


def cmd_schema_lib_list(args: argparse.Namespace) -> None:
    """列出本地 schema 库中所有已保存的 schema，支持关键字过滤。"""
    lib = _lib_load()
    if not lib:
        print("本地 schema 库为空。\n使用 schema-lib-save 保存 schema 后可跨 key 复用。")
        return

    search = (args.search or "").strip().lower()
    matched = {
        name: entry for name, entry in lib.items()
        if not search or search in name.lower() or search in (entry.get("description") or "").lower()
    }

    if not matched:
        print(f"未找到包含 '{search}' 的 schema，使用 schema-lib-list 查看所有。")
        return

    print(f"\n{'─' * 60}")
    print(f"  本地 schema 库  ({SCHEMA_LIB_PATH})")
    if search:
        print(f"  过滤关键字: {search}  ({len(matched)}/{len(lib)} 条)")
    print(f"{'─' * 60}")
    for name, entry in matched.items():
        saved_at = entry.get("saved_at", "")[:10]
        desc = entry.get("description", "")
        preview = _schema_field_preview(entry.get("schema"))
        print(f"\n  [{name}]  {saved_at}  {desc}")
        print(f"    字段: {preview}")
    print(f"\n{'─' * 60}")
    print("  复用方式: session-create --name <任务名> --from-lib <name> --doc-ids <ids>")
    print(f"{'─' * 60}\n")


def cmd_schema_lib_save(args: argparse.Namespace) -> None:
    """将 schema 文件保存到本地库，供跨 key 复用。"""
    schema_path = Path(args.file)
    if not schema_path.exists():
        print(f"找不到文件: {schema_path}", file=sys.stderr)
        sys.exit(1)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    lib = _lib_load()
    if args.name in lib:
        existing_at = lib[args.name].get("saved_at", "")[:10]
        print(f"  已覆盖更新 [{args.name}]（原保存于 {existing_at}）")
    else:
        print(f"  已保存 [{args.name}] 到本地 schema 库")
    lib[args.name] = {
        "schema": schema,
        "description": args.description or "",
        "saved_at": datetime.now().isoformat(),
    }
    _lib_save(lib)
    print(f"  字段: {_schema_field_preview(schema)}")


def cmd_schema_lib_delete(args: argparse.Namespace) -> None:
    """从本地库删除指定 schema。"""
    lib = _lib_load()
    if args.name not in lib:
        print(f"未找到 [{args.name}]，请先用 schema-lib-list 查看可用名称。", file=sys.stderr)
        sys.exit(1)
    del lib[args.name]
    _lib_save(lib)
    print(f"  已删除 [{args.name}]")


# ──────────────────────────────────────────────
# 本地提取缓存（~/.clawshire/cache.json）
# ──────────────────────────────────────────────

def _env_sig() -> str:
    """生成环境签名（API Key + BaseURL 的 hash 前缀），防止明文 Key 存储。"""
    key = os.environ.get("CLAWSHIRE_API_KEY", "")
    url = os.environ.get("CLAWSHIRE_API_BASE_URL", DEFAULT_BASE)
    return hashlib.md5(f"{url}:{key}".encode()).hexdigest()[:8]


def _cache_key(session_id: int | str, doc_ids: list[str]) -> str:
    ids_str = ",".join(sorted(doc_ids))
    return f"{_env_sig()}:{session_id}:{ids_str}"


def _cache_load() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _cache_save(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_get(session_id: int | str, doc_ids: list[str]) -> dict | None:
    cache = _cache_load()
    return cache.get(_cache_key(session_id, doc_ids))


def _cache_put(session_id: int | str, doc_ids: list[str], batch_id: int | str) -> None:
    cache = _cache_load()
    cache[_cache_key(session_id, doc_ids)] = {
        "batch_id": batch_id,
        "session_id": str(session_id),
        "doc_ids": sorted(doc_ids),
        "created_at": datetime.now().isoformat(),
        "archived": False,
    }
    _cache_save(cache)
    print(f"  缓存已写入: session={session_id} batch_id={batch_id}", file=sys.stderr)


def _cache_mark_archived(session_id: int | str, doc_ids: list[str]) -> None:
    cache = _cache_load()
    key = _cache_key(session_id, doc_ids)
    if key in cache:
        cache[key]["archived"] = True
        cache[key]["archived_at"] = datetime.now().isoformat()
        _cache_save(cache)


# ──────────────────────────────────────────────
# API 命令
# ──────────────────────────────────────────────

def cmd_status(_: argparse.Namespace) -> None:
    data = _request_get(f"{base_url()}/api/v1/doc-extract-engine/status", timeout=60)
    _print_json(data)


def _fetch_pdf_from_url(url: str) -> tuple[str, bytes]:
    """下载 URL 指向的 PDF，返回 (文件名, 内容字节)。"""
    print(f"  正在下载: {url}", file=sys.stderr)
    req = Request(url)
    try:
        with urlopen(req, timeout=TIMEOUT_LONG) as resp:
            content = resp.read()
    except HTTPError as e:
        print(f"下载失败 [{e.code}]: {url}", file=sys.stderr)
        sys.exit(1)
    name = url.rstrip("/").split("/")[-1]
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf" if name else "downloaded.pdf"
    print(f"  已下载: {name} ({len(content)} bytes)", file=sys.stderr)
    return name, content


def cmd_upload(args: argparse.Namespace) -> None:
    multipart: list[tuple[str, Any]] = []
    for item in args.files:
        if item.startswith("http://") or item.startswith("https://"):
            name, data = _fetch_pdf_from_url(item)
            multipart.append(("files", (name, data, "application/pdf")))
        else:
            p = Path(item)
            if not p.exists():
                print(f"文件不存在: {p}", file=sys.stderr)
                sys.exit(1)
            if p.suffix.lower() != ".pdf":
                print(f"非 PDF: {p}", file=sys.stderr)
                sys.exit(1)
            multipart.append(("files", (p.name, p.read_bytes(), "application/pdf")))

    body, content_type = _build_multipart(multipart)
    req = Request(
        f"{base_url()}/api/v1/doc-extract-engine/upload",
        data=body,
        method="POST",
    )
    for k, v in _headers({"Content-Type": content_type}).items():
        req.add_header(k, v)
    result = _do_request(req, timeout=TIMEOUT_LONG)
    _check_error(result)
    _print_json(result)


def cmd_schema_create(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]
    data = _request_json(
        "POST",
        f"{base_url()}/api/v1/doc-extract-engine/schema-conversations",
        {"document_ids": ids},
        timeout=120,
    )
    _print_json(data)


def _save_schema_to_lib(schema: dict, save_as: str, description: str = "") -> None:
    lib = _lib_load()
    if save_as in lib:
        existing_at = lib[save_as].get("saved_at", "")[:10]
        print(f"\n  ⚠ 本地库中已存在 [{save_as}]（保存于 {existing_at}），跳过覆盖。", file=sys.stderr)
        print(f"    如需更新，请用: schema-lib-save --name {save_as} --file <path>", file=sys.stderr)
    else:
        lib[save_as] = {
            "schema": schema,
            "description": description,
            "saved_at": datetime.now().isoformat(),
        }
        _lib_save(lib)
        print(f"\n  schema 已自动保存到本地库 [{save_as}]", file=sys.stderr)
        print(f"  字段: {_schema_field_preview(schema)}", file=sys.stderr)


def cmd_schema_chat(args: argparse.Namespace) -> None:
    cid = int(args.conversation_id)
    print("  ⏳ Schema 设计中，预计需要 30秒～3分钟...", file=sys.stderr)

    def _do_request_fn():
        result = _request_json(
            "POST",
            f"{base_url()}/api/v1/doc-extract-engine/schema-conversations/{cid}/chat",
            {"message": args.message},
            timeout=TIMEOUT_LONG,
        )
        # 504：服务端可能已完成 schema 生成，fallback 到 schema-get
        status = result.get("_http_error") or result.get("_status")
        if status == 504:
            print("  ⚠ Schema 请求超时（504），服务端可能已完成生成，正在拉取结果...", file=sys.stderr)
            return _request_get(
                f"{base_url()}/api/v1/doc-extract-engine/schema-conversations/{cid}",
                timeout=120,
            )
        return result

    data = _retry_request(_do_request_fn, max_retries=2, desc="Schema 设计")
    _print_json(data)

    schema = data.get("schema") or data.get("current_schema")
    if args.save_as and schema:
        _save_schema_to_lib(schema, args.save_as, args.description or "")


def cmd_schema_get(args: argparse.Namespace) -> None:
    cid = int(args.conversation_id)
    data = _request_get(
        f"{base_url()}/api/v1/doc-extract-engine/schema-conversations/{cid}",
        timeout=120,
    )
    _print_json(data)


def cmd_session_create(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]

    if args.from_lib:
        lib = _lib_load()
        if args.from_lib not in lib:
            print(f"本地库中未找到 [{args.from_lib}]，请先用 schema-lib-list 查看可用名称。", file=sys.stderr)
            sys.exit(1)
        extraction_schema = lib[args.from_lib]["schema"]
        print(f"  复用本地 schema [{args.from_lib}]", file=sys.stderr)
        print(f"  字段: {_schema_field_preview(extraction_schema)}", file=sys.stderr)
    elif args.schema_file:
        schema_path = Path(args.schema_file)
        if not schema_path.exists():
            print(f"找不到 schema 文件: {schema_path}", file=sys.stderr)
            sys.exit(1)
        extraction_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    else:
        print("需要 --schema-file 或 --from-lib 之一。", file=sys.stderr)
        sys.exit(1)

    data = _request_json(
        "POST",
        f"{base_url()}/api/v1/doc-extract-engine/sessions",
        {
            "session_name": args.name,
            "extraction_schema": extraction_schema,
            "document_ids": ids,
        },
        timeout=120,
    )
    _print_json(data)


def cmd_session_list(_: argparse.Namespace) -> None:
    data = _request_get(f"{base_url()}/api/v1/doc-extract-engine/sessions", timeout=120)
    _print_json(data)


def cmd_history(args: argparse.Namespace) -> None:
    sid = int(args.session_id)
    data = _request_get(
        f"{base_url()}/api/v1/doc-extract-engine/sessions/{sid}/history",
        timeout=120,
    )
    _print_json(data)


def cmd_extract(args: argparse.Namespace) -> None:
    ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]
    session_id = int(args.session_id)
    quiet = getattr(args, "quiet", False)

    if args.use_cache:
        hit = _cache_get(session_id, ids)
        if hit:
            batch_id = hit["batch_id"]
            created_at = hit.get("created_at", "")[:19]
            is_archived = hit.get("archived", False)
            archived_at = hit.get("archived_at", "")[:19]

            if is_archived:
                print(f"  ⚠ 缓存命中但该 batch 已归档（batch_id={batch_id}，归档于 {archived_at}）", file=sys.stderr)
                print("    归档后结果为只读快照，如需重新提取请去掉 --use-cache", file=sys.stderr)
            else:
                print(f"  缓存命中: session={session_id} batch_id={batch_id}  (创建于 {created_at})", file=sys.stderr)
                print("  直接读取已有 batch 结果，不消耗提取额度", file=sys.stderr)

            data = _request_get(
                f"{base_url()}/api/v1/doc-extract-engine/batches/{batch_id}",
                timeout=120,
            )
            if not _check_error(data, fatal=False):
                _print_extracted_data(data)
                if quiet:
                    _print_summary(data)
                if args.out is not None:
                    _save_json(data, args.out, label=f"extract_session{session_id}")
                return
            else:
                print("  缓存条目可能已失效，将重新提取（消耗提取额度）...", file=sys.stderr)
        else:
            print("  缓存未命中，将执行真实提取（消耗提取额度）", file=sys.stderr)
            print("  提示: 提取完成后缓存将自动写入，下次可用 --use-cache 命中", file=sys.stderr)

    body = {"session_id": session_id, "document_ids": ids}
    print("  ⏳ 文档提取中，预计需要 1～5分钟...", file=sys.stderr)

    def _do_extract():
        return _request_json(
            "POST",
            f"{base_url()}/api/v1/doc-extract-engine/extract",
            body,
            timeout=TIMEOUT_LONG,
        )

    data = _retry_request(_do_extract, max_retries=2, desc="文档提取")

    # 始终输出实际接口响应的结构化数据（stdout，供 Claude 和用户阅读）
    _print_extracted_data(data)

    # 打印摘要（stderr，供进度感知）
    _print_summary(data)

    # 写入本地缓存
    batch_id = data.get("batch_id")
    if batch_id:
        _cache_put(session_id, ids, batch_id)

    if args.out is not None:
        _save_json(data, args.out, label=f"extract_session{session_id}")

    # 自动归档
    if args.auto_end:
        if batch_id:
            end_data = _request_json(
                "POST",
                f"{base_url()}/api/v1/doc-extract-engine/batches/{batch_id}/end",
                None,
                timeout=120,
            )
            if not _check_error(end_data, fatal=False):
                _cache_mark_archived(session_id, ids)
                exp_id = end_data.get("experience_task_id", "")
                print(f"\n  已自动归档 batch_id={batch_id}", file=sys.stderr)
                if exp_id:
                    print(f"  experience_task_id={exp_id}（平台将异步学习本次提取经验）", file=sys.stderr)
            else:
                print(f"  归档失败", file=sys.stderr)


def cmd_batch_result(args: argparse.Namespace) -> None:
    """查询已有批次的提取结果，无需重新提取（不消耗额度）。"""
    bid = int(args.batch_id)
    data = _request_get(
        f"{base_url()}/api/v1/doc-extract-engine/batches/{bid}",
        timeout=120,
    )

    # 始终输出实际结构化数据
    _print_extracted_data(data)

    if getattr(args, "summary", False):
        _print_summary(data)

    if args.out is not None:
        _save_json(data, args.out, label=f"batch{bid}_result")


def cmd_batch_chat(args: argparse.Namespace) -> None:
    bid = int(args.batch_id)
    quiet = getattr(args, "quiet", False)
    print("  ⏳ 批次修正中，预计需要 30秒～3分钟...", file=sys.stderr)

    def _do_chat():
        return _request_json(
            "POST",
            f"{base_url()}/api/v1/doc-extract-engine/batches/{bid}/chat",
            {"message": args.message},
            timeout=TIMEOUT_LONG,
        )

    data = _retry_request(_do_chat, max_retries=2, desc="批次修正")

    # 始终输出实际结构化数据
    _print_extracted_data(data)

    if quiet:
        _print_summary(data)

    if args.out is not None:
        _save_json(data, args.out, label=f"batch{bid}_chat")


def cmd_batch_end(args: argparse.Namespace) -> None:
    bid = int(args.batch_id)
    data = _request_json(
        "POST",
        f"{base_url()}/api/v1/doc-extract-engine/batches/{bid}/end",
        None,
        timeout=120,
    )
    _print_json(data)
    exp_id = data.get("experience_task_id", "")
    if exp_id:
        print(f"\n  experience_task_id={exp_id}", file=sys.stderr)
        print("  平台将异步学习本次提取经验，下次同类文档提取质量将提升。", file=sys.stderr)


# ──────────────────────────────────────────────
# CLI 注册
# ──────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="ClawShire 文档提取引擎 CLI（无需第三方依赖）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="引擎状态")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("upload", help="上传 PDF（本地路径或 http/https URL，可混用多个）")
    sp.add_argument("files", nargs="+", help="本地 .pdf 路径 或 PDF URL（http/https）")
    sp.set_defaults(func=cmd_upload)

    sp = sub.add_parser("schema-create", help="创建 Schema 对话")
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.set_defaults(func=cmd_schema_create)

    sp = sub.add_parser("schema-chat", help="Schema 对话一轮")
    sp.add_argument("conversation_id", help="conversation_id")
    sp.add_argument("message", help="自然语言需求")
    sp.add_argument("--save-as", default="", help="将返回的 schema 保存到本地库（指定名称）；同名已存在时跳过，不覆盖")
    sp.add_argument("--description", default="", help="schema 描述，配合 --save-as 使用")
    sp.set_defaults(func=cmd_schema_chat)

    sp = sub.add_parser("schema-get", help="获取 Schema 对话状态")
    sp.add_argument("conversation_id", help="conversation_id")
    sp.set_defaults(func=cmd_schema_get)

    sp = sub.add_parser("schema-lib-list", help="列出本地 schema 库（跨 key 复用入口）")
    sp.add_argument("--search", default="", help="关键字模糊过滤（名称或描述）")
    sp.set_defaults(func=cmd_schema_lib_list)

    sp = sub.add_parser("schema-lib-save", help="保存 schema 文件到本地库（允许覆盖，会提示）")
    sp.add_argument("--name", required=True, help="schema 名称（如 人事变动、合同）")
    sp.add_argument("--file", required=True, help="schema JSON 文件路径")
    sp.add_argument("--description", default="", help="描述")
    sp.set_defaults(func=cmd_schema_lib_save)

    sp = sub.add_parser("schema-lib-delete", help="从本地库删除 schema")
    sp.add_argument("name", help="schema 名称")
    sp.set_defaults(func=cmd_schema_lib_delete)

    sp = sub.add_parser("session-create", help="创建提取 Session（支持本地库复用）")
    sp.add_argument("--name", required=True, help="session 名称")
    sp.add_argument("--schema-file", default="", help="JSON Schema 文件路径")
    sp.add_argument("--from-lib", default="", help="从本地 schema 库复用（优先级高于 --schema-file）")
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.set_defaults(func=cmd_session_create)

    sp = sub.add_parser("sessions", help="列出引擎 Session")
    sp.set_defaults(func=cmd_session_list)

    sp = sub.add_parser("history", help="Session 历史")
    sp.add_argument("session_id", help="session_id")
    sp.set_defaults(func=cmd_history)

    sp = sub.add_parser("extract", help="执行提取")
    sp.add_argument("--session-id", required=True)
    sp.add_argument("--doc-ids", required=True, help="逗号分隔 document_id")
    sp.add_argument("--out", nargs="?", const="", default=None,
                    help="保存结果 JSON（不指定路径时自动命名）")
    sp.add_argument("--auto-end", action="store_true",
                    help="提取完自动归档（batch-end），并标记缓存为 archived")
    sp.add_argument("--quiet", action="store_true",
                    help="额外打印字段覆盖率概要（默认始终输出结构化数据）")
    sp.add_argument("--use-cache", action="store_true",
                    help="优先读取本地缓存；未命中时明确提示后执行真实提取")
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("batch-result", help="查询已有批次结果（不重新提取，不消耗额度）")
    sp.add_argument("batch_id", help="batch_id")
    sp.add_argument("--out", nargs="?", const="", default=None,
                    help="保存结果 JSON（不指定路径时自动命名）")
    sp.add_argument("--summary", action="store_true",
                    help="额外显示字段覆盖率（默认始终输出结构化数据）")
    sp.set_defaults(func=cmd_batch_result)

    sp = sub.add_parser("batch-chat", help="批次修正一轮")
    sp.add_argument("batch_id", help="batch_id")
    sp.add_argument("message", help="修正说明")
    sp.add_argument("--out", nargs="?", const="", default=None,
                    help="保存修正结果 JSON")
    sp.add_argument("--quiet", action="store_true",
                    help="额外打印字段覆盖率概要（默认始终输出结构化数据）")
    sp.set_defaults(func=cmd_batch_chat)

    sp = sub.add_parser("batch-end", help="结束批次（归档，触发经验学习）")
    sp.add_argument("batch_id", help="batch_id")
    sp.set_defaults(func=cmd_batch_end)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
