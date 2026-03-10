#!/usr/bin/env python3
"""
ClawShire 公告数据 API 客户端
A 股上市公司公告提取结果查询工具

用法：
    python clawshire_client.py announcements --start-date 2026-03-10 --end-date 2026-03-10
    python clawshire_client.py stock 000001 --start-date 2026-03-01 --end-date 2026-03-10
    python clawshire_client.py met-link "http://www.szse.cn/api/..."
    python clawshire_client.py api-key-info

获取 API Key：登录控制台 https://clawshire.cn 手动创建
设置环境变量：export CLAWSHIRE_API_KEY="sk-xxxxxxxx"
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

BASE_URL = "https://api.clawshire.cn"
CONSOLE_URL = "https://clawshire.cn"
DEFAULT_PAGE_SIZE = 20
MAX_RETRIES = 3
TIMEOUT = 30


def _request(
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
    api_key: str | None = None,
) -> dict:
    """执行 HTTP 请求，内置重试逻辑。"""
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(body).encode("utf-8") if body else None

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = {}
            try:
                error_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                pass
            print(
                json.dumps(
                    {"error": f"HTTP {e.code}", "detail": error_body},
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"请求失败（{e.reason}），{wait}s 后重试...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
                sys.exit(1)

    sys.exit(1)


def _require_api_key(args_key: str | None) -> str:
    """获取 API Key，未设置则退出并提示用户去控制台创建。"""
    key = args_key or os.environ.get("CLAWSHIRE_API_KEY")
    if not key:
        print(
            f"错误：未设置 CLAWSHIRE_API_KEY 环境变量。\n"
            f"请登录控制台创建 API Key：{CONSOLE_URL}\n"
            f"创建后执行：export CLAWSHIRE_API_KEY='sk-xxxxxxxx'",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def cmd_announcements(args: argparse.Namespace) -> dict:
    """按日期范围查询公告提取结果。"""
    api_key = _require_api_key(args.api_key)
    params: dict[str, Any] = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "page": args.page,
        "page_size": args.page_size,
    }
    if args.infotype:
        params["infotype"] = args.infotype
    return _request("GET", "/api/v1/announcements", params=params, api_key=api_key)


def cmd_stock_announcements(args: argparse.Namespace) -> dict:
    """查询指定证券代码的公告。"""
    api_key = _require_api_key(args.api_key)
    params: dict[str, Any] = {
        "page": args.page,
        "page_size": args.page_size,
    }
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date
    if args.infotype:
        params["infotype"] = args.infotype
    return _request(
        "GET",
        f"/api/v1/stock/{args.sec_code}/announcements",
        params=params,
        api_key=api_key,
    )


def cmd_met_link(args: argparse.Namespace) -> dict:
    """根据公告原文链接查询提取结果。"""
    api_key = _require_api_key(args.api_key)
    params: dict[str, Any] = {"met_link": args.link}
    if args.infotype:
        params["infotype"] = args.infotype
    return _request("GET", "/api/v1/met_link", params=params, api_key=api_key)


def cmd_api_key_info(args: argparse.Namespace) -> dict:
    """查看当前 API Key 信息（需认证）。"""
    api_key = _require_api_key(args.api_key)
    return _request("GET", "/api/v1/api-key/info", api_key=api_key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ClawShire 公告数据 API 客户端",
        epilog=f"获取 API Key：登录控制台 {CONSOLE_URL} 手动创建",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-key", help="API Key（默认读取 CLAWSHIRE_API_KEY 环境变量）")

    sub = parser.add_subparsers(dest="command", required=True)

    # announcements
    p_ann = sub.add_parser("announcements", help="按日期范围查询公告")
    p_ann.add_argument("--start-date", default=date.today().isoformat(), help="开始日期 YYYY-MM-DD（默认今天）")
    p_ann.add_argument("--end-date", default=date.today().isoformat(), help="结束日期 YYYY-MM-DD（默认今天）")
    p_ann.add_argument("--infotype", default="", help="公告类别，如「董事会决议」")
    p_ann.add_argument("--page", type=int, default=1, help="页码（默认 1）")
    p_ann.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="每页数量（默认 20，最大 100）")

    # stock
    p_stock = sub.add_parser("stock", help="按证券代码查询公告")
    p_stock.add_argument("sec_code", help="六位证券代码，如 000001")
    p_stock.add_argument("--start-date", default="", help="开始日期 YYYY-MM-DD（默认今天）")
    p_stock.add_argument("--end-date", default="", help="结束日期 YYYY-MM-DD（默认今天）")
    p_stock.add_argument("--infotype", default="", help="公告类别筛选")
    p_stock.add_argument("--page", type=int, default=1)
    p_stock.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)

    # met-link
    p_link = sub.add_parser("met-link", help="按公告原文链接查询")
    p_link.add_argument("link", help="公告原文 URL")
    p_link.add_argument("--infotype", default="", help="指定提取类别（可选）")

    # api-key-info
    sub.add_parser("api-key-info", help="查看当前 API Key 信息")

    return parser


COMMAND_MAP = {
    "announcements": cmd_announcements,
    "stock": cmd_stock_announcements,
    "met-link": cmd_met_link,
    "api-key-info": cmd_api_key_info,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handler = COMMAND_MAP.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
