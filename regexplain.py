#!/usr/bin/env python3
"""regexplain — 正则表达式解释 + 本地测试工作台。

一半是 LLM 解释器（逐段讲解正则 / 根据中文描述生成正则），
一半是本地正则工作台（纯 re 测试，无需联网、无需 API key）。

用法示例：
    regexplain "(\\d{4})-(\\d{2})" --explain          # LLM 中文逐段解释
    regexplain "^[\\w.]+@\\w+\\.\\w+$" --test "a@b.com" "bad"   # 本地测试
    regexplain --gen "匹配中国手机号" --test "13812345678" "12345"  # 生成+本地验证
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

VERSION = "0.1.0"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

EXPLAIN_PROMPT_ZH = """你是一位正则表达式专家。请用中文逐段解释下面的正则表达式。

正则表达式：
{pattern}

要求：
1. 用一张 Markdown 表格逐个拆解有意义的片段，表格列为：片段 | 含义 | 示例匹配。
   把相邻的字符类和量词组合成一个片段（例如把 \\d{{4}} 作为一个片段），不要把每个字符都拆开。
2. 表格之后，用 2-3 句话总结这个正则整体匹配什么样的字符串。
3. 如果正则中有捕获组（包括命名捕获组 (?P<name>...)），单独列出每个组的编号、名称和作用。
4. 用中文回答，保留必要的英文术语（如 lookahead、backreference）。
"""

EXPLAIN_PROMPT_EN = """You are a regex expert. Explain the following regular expression piece by piece, in English.

Regex:
{pattern}

Requirements:
1. Break it into meaningful tokens in a Markdown table with columns: Token | Meaning | Example match.
   Group adjacent character classes with their quantifiers into one token (e.g. \\d{{4}} is one token); do not split every single character.
2. After the table, summarize in 2-3 sentences what kind of strings this regex matches overall.
3. If the regex has capture groups (including named groups (?P<name>...)), list each group's number, name and purpose separately.
"""

GEN_PROMPT = """你是一位正则表达式专家。请根据下面的描述，写出一个 Python re 模块可以直接编译使用的正则表达式。

描述：
{desc}

要求：
1. 只输出正则表达式本身，不要输出任何解释、前言、代码围栏或多余文字。
2. 正则必须能被 Python 的 re 模块直接编译，不要使用其他语言特有的语法。
3. 尽量精确，避免过度宽松；如需锚定请自行加上 ^ 和 $。
"""


# ---------------------------------------------------------------------------
# LLM 调用（仅 --explain / --gen 需要）
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("error: 未找到 API key。LLM 模式需要设置环境变量 OPENAI_API_KEY。", file=sys.stderr)
        print("       （本地 --test 模式不需要 key，可直接使用。）", file=sys.stderr)
        sys.exit(1)
    return key


def _llm_complete(prompt: str, model: str, base_url: str, timeout: int = 60) -> str:
    """调用 OpenAI 兼容的 /chat/completions，返回模型回复文本。"""
    key = _api_key()
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"error: API 请求失败（HTTP {e.code}）：{body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"error: 网络请求失败：{e.reason}（输出中不包含 key）", file=sys.stderr)
        sys.exit(1)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("error: API 返回的不是合法 JSON。", file=sys.stderr)
        sys.exit(1)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("error: API 返回格式异常，无法解析模型回复。", file=sys.stderr)
        sys.exit(1)


def extract_regex(text: str) -> str:
    """从模型回复中剥离代码围栏/反引号，提取正则表达式本体。"""
    t = text.strip()
    t = re.sub(r"^```[\w+-]*\s*", "", t)   # 开头的 ``` 或 ```regex
    t = re.sub(r"\s*```$", "", t)          # 结尾的 ```
    return t.strip().strip("`").strip()


# ---------------------------------------------------------------------------
# 本地测试（纯 re，无需联网）
# ---------------------------------------------------------------------------

def compile_pattern(pattern: str) -> "re.Pattern[str]":
    try:
        return re.compile(pattern)
    except re.error as e:
        print(f"error: 正则表达式无效：{e}", file=sys.stderr)
        sys.exit(1)


def run_local_tests(pattern: str, strings: list[str], title: str = "本地测试") -> int:
    """用 re.search 语义逐个测试字符串，打印匹配表。返回 exit code。"""
    rx = compile_pattern(pattern)
    print(f"{title}：{pattern!r}，共 {len(strings)} 个字符串（re.search 语义）\n")
    matched = 0
    for i, s in enumerate(strings, 1):
        m = rx.search(s)
        print(f"[{i}] {s!r}")
        if m:
            matched += 1
            line = f"    ✅ 匹配 → {m.group(0)!r}"
            if m.groupdict():
                gd = ", ".join(f"{k}={v!r}" for k, v in m.groupdict().items())
                print(line + f"   命名捕获组：{gd}")
            elif m.groups():
                print(line + f"   捕获组（{len(m.groups())}）：{m.groups()!r}")
            else:
                print(line)
        else:
            print("    ❌ 未匹配")
    print(f"\n结果：{matched}/{len(strings)} 匹配")
    return 0


def compile_check(pattern: str) -> int:
    """无模式参数时的默认行为：只做编译检查。"""
    rx = compile_pattern(pattern)
    print("✅ 正则有效")
    named = rx.groupindex
    print(f"捕获组：{rx.groups} 个" + (f"，命名组：{', '.join(sorted(named))}" if named else "（无命名组）"))
    return 0


# ---------------------------------------------------------------------------
# 各模式
# ---------------------------------------------------------------------------

def cmd_explain(args: argparse.Namespace) -> int:
    if not args.pattern:
        print("error: --explain 需要提供一个正则表达式作为位置参数。", file=sys.stderr)
        return 2
    template = EXPLAIN_PROMPT_EN if args.lang == "en" else EXPLAIN_PROMPT_ZH
    prompt = template.format(pattern=args.pattern)
    if args.dry_run:
        print(f"[dry-run] 将调用模型 {args.model}（{DEFAULT_BASE_URL}）")
        print("[dry-run] 发送的 prompt：")
        print("─" * 40)
        print(prompt.rstrip())
        print("─" * 40)
        return 0
    print(f"正在用 {args.model} 解释正则…\n")
    print(_llm_complete(prompt, args.model, DEFAULT_BASE_URL))
    return 0


def cmd_gen(args: argparse.Namespace) -> int:
    if args.pattern:
        print("注意：--gen 模式下位置参数 PATTERN 会被忽略，以 --gen 的描述为准。", file=sys.stderr)
    prompt = GEN_PROMPT.format(desc=args.gen)
    if args.dry_run:
        print(f"[dry-run] 将调用模型 {args.model}（{DEFAULT_BASE_URL}）")
        print("[dry-run] 发送的 prompt：")
        print("─" * 40)
        print(prompt.rstrip())
        print("─" * 40)
        if args.test:
            print(f"[dry-run] 之后将在本地用 re 测试 {len(args.test)} 个字符串：{args.test}")
        return 0
    print(f"正在用 {args.model} 生成正则…\n")
    raw = _llm_complete(prompt, args.model, DEFAULT_BASE_URL)
    pattern = extract_regex(raw)
    if not pattern:
        print("error: 模型没有返回可用的正则表达式。", file=sys.stderr)
        return 1
    print(f"生成的正则：{pattern!r}\n")
    if args.test:
        # 闭环：立刻在本地用 re 验证
        return run_local_tests(pattern, args.test, title="本地验证（闭环）")
    return compile_check(pattern)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="regexplain",
        description="正则表达式解释 + 本地测试工作台（一半 LLM，一半本地 re）",
    )
    p.add_argument("pattern", nargs="?", help="正则表达式（--gen 模式下可省略）")
    p.add_argument("--explain", action="store_true", help="用 LLM 逐段解释正则（中文，可用 --lang en）")
    p.add_argument("--gen", metavar="描述", help="用 LLM 根据中文描述生成正则，可配合 --test 做本地闭环验证")
    p.add_argument("--test", nargs="+", metavar="字符串", help="在本地用 re 测试这些字符串（无需 API key）")
    p.add_argument("--lang", default="zh", choices=["zh", "en"], help="解释语言（默认 zh）")
    p.add_argument("--dry-run", action="store_true", help="LLM 模式下只打印将要发送的 prompt，不实际调用")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM 模型（默认 {DEFAULT_MODEL}，可用 OPENAI_MODEL 覆盖）")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gen:
        return cmd_gen(args)
    if args.explain:
        return cmd_explain(args)
    if args.test:
        if not args.pattern:
            print("error: --test 需要提供一个正则表达式作为位置参数。", file=sys.stderr)
            return 2
        return run_local_tests(args.pattern, args.test)
    if args.pattern:
        return compile_check(args.pattern)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
