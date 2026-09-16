#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取中国银行外汇牌价，输出结构化 JSON。

数据来源：中国银行官网外汇牌价页面 https://www.boc.cn/sourcedb/whpj/
主要用途：为手机桌面小组件（KWGT 等）提供一个干净的 UTF-8 JSON 数据源。

用法：
    python boc_rate.py                    # 抓取并写入 rate.json，同时打印摘要
    python boc_rate.py -o out.json        # 指定输出文件
    python boc_rate.py --stdout           # 只打印 JSON，不写文件
    python boc_rate.py --currency 美元 港币  # 只保留指定币种
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

SOURCE_URL = "https://www.boc.cn/sourcedb/whpj/"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "rate.json"

# 中行牌价表列顺序（美元等主要币种为完整 8 列）
COLUMNS = [
    "currency",
    "spot_buy",      # 现汇买入价
    "cash_buy",      # 现钞买入价
    "spot_sell",     # 现汇卖出价
    "cash_sell",     # 现钞卖出价
    "mid",           # 中行折算价
    "publish_date",
    "publish_time",
]

# 输出 JSON 里用的英文键，避免中文键在部分客户端出问题
CURRENCY_CODES = {
    "美元": "usd", "港币": "hkd", "欧元": "eur", "日元": "jpy",
    "英镑": "gbp", "澳大利亚元": "aud", "加拿大元": "cad",
    "新加坡元": "sgd", "瑞士法郎": "chf", "新西兰元": "nzd",
}

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch(url: str, retries: int = 3, timeout: int = 20) -> str:
    """下载中行牌价页面并解码为文本。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.boc.cn/sourcedb/whpj/",
    }
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            return _decode(raw)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"抓取失败（重试 {retries} 次）：{last_err}")


def _decode(raw: bytes) -> str:
    """按页面 meta 声明的编码解码；未声明则依次尝试 utf-8 / gbk。

    中行页面的响应头不带 charset，但 meta 里写了 utf-8，不能想当然按 GBK 解。
    """
    head = raw[:2048].decode("latin-1", errors="ignore")
    m = re.search(r'charset\s*=\s*["\']?\s*([\w-]+)', head, re.I)
    candidates = [m.group(1)] if m else []
    candidates += ["utf-8", "gbk"]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _cell_text(raw_cell: str) -> str:
    """去掉标签与多余空白，还原 HTML 实体。"""
    return html.unescape(_TAG_RE.sub("", raw_cell)).replace("\xa0", " ").strip()


def parse_rates(page: str) -> list[dict[str, str]]:
    """解析牌价表格，返回每行币种的字典列表。"""
    rates: list[dict[str, str]] = []
    for row_html in _ROW_RE.findall(page):
        cells = [_cell_text(c) for c in _CELL_RE.findall(row_html)]
        # 数据行至少要有币种 + 4 个价格；表头行第一格是"货币名称"
        if len(cells) < 5 or cells[0] in ("", "货币名称"):
            continue
        if not any(re.fullmatch(r"\d+(\.\d+)?", c) for c in cells[1:]):
            continue
        # 部分币种（新台币、文莱元等）没有现汇价，只有现钞买入/现钞卖出/折算价
        record = {col: "" for col in COLUMNS}
        record["currency"] = cells[0]
        prices = cells[1:-2]           # 去掉币种名和末尾的日期、时间
        if len(prices) >= 5:
            for col, val in zip(COLUMNS[1:], prices):
                record[col] = val
        elif len(prices) == 3:
            record["cash_buy"], record["cash_sell"], record["mid"] = prices
        else:
            continue                   # 结构无法识别，跳过而不是错位填充
        record["publish_date"] = cells[-2].split()[0]
        record["publish_time"] = cells[-1]
        rates.append(record)
    return rates


def build_payload(rates: list[dict[str, str]]) -> dict:
    """组装最终 JSON：头部为原始明细，currencies 为便于取值的中英对照。"""
    updated = ""
    for r in rates:
        if r.get("publish_date"):
            updated = f"{r['publish_date']} {r['publish_time']}".strip()
            break

    currencies: dict[str, dict] = {}
    for r in rates:
        name = r["currency"]
        code = CURRENCY_CODES.get(name)
        if not code:
            continue
        currencies[code] = {
            "name": name,
            "spot_buy": r["spot_buy"],
            "cash_buy": r["cash_buy"],
            "spot_sell": r["spot_sell"],
            "cash_sell": r["cash_sell"],
            "mid": r["mid"],
        }

    return {
        "source": SOURCE_URL,
        "updated": updated,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "currencies": currencies,
        "rates": rates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取中国银行外汇牌价并输出 JSON")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT),
                        help="输出文件路径（默认 rate.json）")
    parser.add_argument("--stdout", action="store_true", help="只打印 JSON，不写文件")
    parser.add_argument("--currency", nargs="*", default=None,
                        help="只保留指定币种（中文名，如 美元 港币）")
    args = parser.parse_args(argv)

    page = fetch(SOURCE_URL)
    rates = parse_rates(page)
    if not rates:
        print("解析失败：未从页面中提取到任何牌价数据", file=sys.stderr)
        return 1

    if args.currency:
        wanted = set(args.currency)
        rates = [r for r in rates if r["currency"] in wanted]
        if not rates:
            print(f"未匹配到币种：{args.currency}", file=sys.stderr)
            return 1

    payload = build_payload(rates)

    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    usd = payload["currencies"].get("usd")
    print(f"已写入 {out}")
    print(f"牌价时间：{payload['updated']}  （共 {len(rates)} 个币种）")
    if usd:
        print(f"美元 现钞买入价 {usd['cash_buy']} / 现钞卖出价 {usd['cash_sell']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
