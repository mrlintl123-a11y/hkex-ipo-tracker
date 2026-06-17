#!/usr/bin/env python3
"""
Search Provider — 可插拔的搜索后端适配器

支持的后端：
  - "agent_native" : 输出结构化 JSON，由 Codex/LLM agent 消费后自行搜索
  - "mmx"          : 调用 MiniMax mmx CLI（向后兼容）
  - "web_api"      : 使用 requests + BeautifulSoup 直接抓取 URL
  - "custom"       : 用户通过环境变量 CUSTOM_SEARCH_CMD 指定模板

环境变量 SEARCH_PROVIDER 选择后端（默认 agent_native）。
"""

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SearchQuery:
    """一条搜索查询"""
    source: str           # 数据源名称（智通财经、金吾资讯、港交所披露易等）
    query: str            # 搜索关键词
    url: Optional[str] = None   # 直接 fetch 的 URL（如果有）
    priority: int = 1     # 1=高优 2=低优


@dataclass
class SearchResult:
    """一条搜索结果"""
    source: str
    query: str
    url: Optional[str] = None
    success: bool = False
    status: str = "pending"   # pending / success / failed / timeout
    raw_text: str = ""
    error: str = ""


@dataclass
class FetchBatch:
    """一批待搜索的查询 + 结果"""
    queries: list = field(default_factory=list)
    results: list = field(default_factory=list)
    provider: str = "agent_native"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, data: str | dict) -> "FetchBatch":
        if isinstance(data, str):
            data = json.loads(data)
        batch = cls()
        batch.queries = [SearchQuery(**q) for q in data.get("queries", [])]
        batch.results = [SearchResult(**r) for r in data.get("results", [])]
        batch.provider = data.get("provider", "agent_native")
        return batch


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class SearchProvider(ABC):
    """搜索后端抽象基类"""

    name: str = "base"

    @abstractmethod
    def search(self, query: SearchQuery, timeout: int = 30) -> SearchResult:
        ...

    def batch_search(self, queries: list[SearchQuery], timeout: int = 30) -> list[SearchResult]:
        return [self.search(q, timeout) for q in queries]


# ---------------------------------------------------------------------------
# Provider: agent_native
# ---------------------------------------------------------------------------

class AgentNativeProvider(SearchProvider):
    """
    Codex / LLM agent 原生模式。

    不发起任何网络请求，只输出结构化 JSON 到 stdout。
    上层 agent（Codex / Claude / GPT）读取 JSON 后用自己的搜索工具执行，
    然后把结果写回 JSONL 格式的 stdin 或文件。
    """

    name = "agent_native"

    def __init__(self, output_file: Optional[str] = None):
        self.output_file = output_file

    def search(self, query: SearchQuery, timeout: int = 30) -> SearchResult:
        return SearchResult(
            source=query.source,
            query=query.query,
            url=query.url,
            status="pending",
        )

    def emit_queries(self, queries: list[SearchQuery]) -> dict:
        """
        输出搜索任务清单，供 agent 消费。

        Returns:
            {
                "mode": "agent_native",
                "instructions": "请使用你的 web search / web_fetch 工具执行以下查询...",
                "queries": [...]
            }
        """
        batch = FetchBatch(queries=queries, provider="agent_native")
        payload = {
            "mode": "agent_native",
            "instructions": (
                "请使用你的网络搜索能力执行以下查询，收集港股 IPO 相关数据。"
                "每条查询返回关键信息摘要，保留具体数字（孖展倍数、截止日、手数等）。"
                "完成后将结果以 JSON Lines 格式写入 results.jsonl，"
                "每行一个 SearchResult 对象。"
            ),
            "queries": [asdict(q) for q in queries],
        }
        if self.output_file:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload


# ---------------------------------------------------------------------------
# Provider: mmx (MiniMax)
# ---------------------------------------------------------------------------

class MiniMaxProvider(SearchProvider):
    """通过 subprocess 调用 mmx CLI"""

    name = "mmx"

    def search(self, query: SearchQuery, timeout: int = 30) -> SearchResult:
        try:
            result = subprocess.run(
                ["mmx", "search", "query", query.query],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
            )
            if result.returncode != 0:
                return SearchResult(
                    source=query.source,
                    query=query.query,
                    success=False,
                    status="failed",
                    error=result.stderr.strip(),
                )
            return SearchResult(
                source=query.source,
                query=query.query,
                success=True,
                status="success",
                raw_text=result.stdout.strip(),
            )
        except FileNotFoundError:
            return SearchResult(
                source=query.source,
                query=query.query,
                success=False,
                status="failed",
                error="mmx CLI 未安装。请安装 MiniMax Token Plan 或切换 SEARCH_PROVIDER=agent_native",
            )
        except subprocess.TimeoutExpired:
            return SearchResult(
                source=query.source,
                query=query.query,
                success=False,
                status="timeout",
                error=f"超时 ({timeout}s)",
            )


# ---------------------------------------------------------------------------
# Provider: custom (user shell command)
# ---------------------------------------------------------------------------

class CustomProvider(SearchProvider):
    """
    用户自定义命令模板。
    环境变量 CUSTOM_SEARCH_CMD 格式如: 'mmx search query {query}'
    """

    name = "custom"

    def __init__(self, cmd_template: Optional[str] = None):
        self.cmd_template = cmd_template or os.environ.get(
            "CUSTOM_SEARCH_CMD", "mmx search query {query}"
        )

    def search(self, query: SearchQuery, timeout: int = 30) -> SearchResult:
        cmd = self.cmd_template.replace("{query}", query.query)
        parts = cmd.split()
        try:
            result = subprocess.run(
                parts, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
            )
            if result.returncode != 0:
                return SearchResult(
                    source=query.source,
                    query=query.query,
                    success=False,
                    status="failed",
                    error=result.stderr.strip(),
                )
            return SearchResult(
                source=query.source,
                query=query.query,
                success=True,
                status="success",
                raw_text=result.stdout.strip(),
            )
        except FileNotFoundError:
            return SearchResult(
                source=query.source,
                query=query.query,
                success=False,
                status="failed",
                error=f"命令不可用: {parts[0]}",
            )
        except subprocess.TimeoutExpired:
            return SearchResult(
                source=query.source,
                query=query.query,
                success=False,
                status="timeout",
                error=f"超时 ({timeout}s)",
            )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

PROVIDER_MAP: dict[str, type[SearchProvider]] = {
    "agent_native": AgentNativeProvider,
    "mmx": MiniMaxProvider,
    "custom": CustomProvider,
}


def get_provider(name: Optional[str] = None) -> SearchProvider:
    """
    根据环境变量 SEARCH_PROVIDER 或显式 name 获取搜索后端。

    优先级：参数 > 环境变量 > 默认 agent_native
    """
    provider_name = name or os.environ.get("SEARCH_PROVIDER", "agent_native")
    cls = PROVIDER_MAP.get(provider_name)
    if cls is None:
        print(
            f"⚠️  未知搜索后端 '{provider_name}'，回退到 agent_native",
            file=sys.stderr,
        )
        cls = AgentNativeProvider
    return cls()


# ---------------------------------------------------------------------------
# Standard IPO search queries
# ---------------------------------------------------------------------------

def build_ipo_queries(today_str: str = "") -> list[SearchQuery]:
    """构建港股 IPO 标准搜索查询列表"""
    return [
        SearchQuery(
            source="智通财经",
            query=f"新股孖展 {today_str}",
            priority=1,
        ),
        SearchQuery(
            source="金吾资讯",
            query="港股 IPO 正在招股 认购倍数",
            url="https://ipo.jinwucj.com/",
            priority=1,
        ),
        SearchQuery(
            source="港交所披露易",
            query="港交所 招股章程 配发结果",
            url="https://www.hkex.com.hk/Listing/IPO/IPO-Documents",
            priority=1,
        ),
        SearchQuery(
            source="LiveReport",
            query="港股 IPO 招股周报 一手中签率",
            priority=2,
        ),
        SearchQuery(
            source="格隆汇",
            query="港股新股 招股公告 基石投资者",
            priority=2,
        ),
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="搜索后端适配器 CLI")
    parser.add_argument(
        "--emit-queries",
        action="store_true",
        help="输出查询任务清单（agent_native 模式）",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出 JSON 文件路径",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help=f"搜索后端 ({', '.join(PROVIDER_MAP)})",
    )
    args = parser.parse_args()

    provider = get_provider(args.provider)
    queries = build_ipo_queries()

    if isinstance(provider, AgentNativeProvider):
        payload = provider.emit_queries(queries)
        if args.output:
            print(f"✅ 查询清单已写入 {args.output}")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        results = provider.batch_search(queries)
        batch = FetchBatch(queries=queries, results=results, provider=provider.name)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(batch.to_json())
            print(f"✅ 搜索结果已写入 {args.output}")
        else:
            print(batch.to_json())


if __name__ == "__main__":
    main()
