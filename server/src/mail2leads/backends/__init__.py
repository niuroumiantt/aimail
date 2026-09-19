"""模型后端:一份合同,两条后端。

- local  —— Spark,走 LiteLLM 网关的 OpenAI 兼容接口
- claude —— Anthropic 官方 SDK

合同(输入什么、输出什么、怎么核对)在 tasks/ 里,两条后端共用;同一套评测集跑出来的分数才可比。
知道"模型在哪"的只有这个目录(宪法第八条,tools/guard_hostnames.py 强制)。

小模型跟托管模型最大的差别不是聪明程度,是输出纪律:爱裹围栏、裹解释、写着写着截断。所以:
1. 按标准方式要 JSON(response_format,不支持的服务端会忽略)
2. 再给一份人类可读的字段模板——比原始 JSON Schema 对小模型更管用
3. 解析前剥围栏、取第一个括号平衡的 {...}
4. Pydantic 校验;不过就把错误原样丢回去让它改**一次**
5. 还不过就抛 LLMError——绝不编一个看起来像样的结果(宪法第六条)
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_CLAUDE_MODEL = "claude-opus-5"


class LLMError(RuntimeError):
    """模型没有给出合规输出。不要把它当成「摘要为空」处理。"""


def backend() -> str:
    value = os.environ.get("LLM_BACKEND", "local").strip().lower()
    if value not in {"local", "claude"}:
        raise LLMError(f"LLM_BACKEND 只能是 local 或 claude,拿到的是 {value!r}")
    return value


def model_name() -> str:
    if backend() == "local":
        return os.environ.get("LOCAL_MODEL", "").strip()
    return os.environ.get("MODEL", DEFAULT_CLAUDE_MODEL).strip()


def base_url() -> str:
    """显式 LOCAL_BASE_URL > 网关约定 DGX_GATEWAY_URL(不带 /v1,这里补)> 本机 Ollama。"""
    explicit = os.environ.get("LOCAL_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    gateway = os.environ.get("DGX_GATEWAY_URL", "").strip()
    if gateway:
        return gateway.rstrip("/") + "/v1"
    return DEFAULT_LOCAL_BASE_URL


def api_key() -> str:
    return (
        os.environ.get("LOCAL_API_KEY", "").strip()
        or os.environ.get("DGX_API_KEY", "").strip()
        or "not-needed"
    )


def describe() -> str:
    """一行字说明这次结果是谁算的——两个后端的输出长得一样,不标就分不清。"""
    name = model_name() or "(未设置)"
    return f"Spark · {name}" if backend() == "local" else f"Claude · {name}"


def ready() -> tuple[bool, str]:
    if backend() == "local":
        if not model_name():
            return False, "没有设置 LOCAL_MODEL(网关路由名,例如 fast 或 brain)"
        return True, f"本地模型 {model_name()} @ {base_url()}"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "没有设置 ANTHROPIC_API_KEY"
    return True, f"Claude {model_name()}"


def _shape_hint(model_cls: type[BaseModel]) -> str:
    """把 Pydantic 模型渲染成人读得懂的字段模板;原始 JSON Schema 的 $defs、anyOf 对小模型是噪音。"""
    schema = model_cls.model_json_schema()
    lines = []
    for name, spec in schema.get("properties", {}).items():
        kind = spec.get("type", "string")
        if kind == "array":
            kind = f"array<{spec.get('items', {}).get('type', 'string')}>"
        note = spec.get("description", "")
        lines.append(f'  "{name}": <{kind}>' + (f"   // {note}" if note else ""))
    return "{\n" + ",\n".join(lines) + "\n}"


def _extract_json(text: str) -> str:
    if not text or not text.strip():
        raise LLMError("模型返回了空内容")
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start < 0:
        raise LLMError(f"输出里没有 JSON:{text[:200]}")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise LLMError(f"JSON 没有闭合(多半被截断了):…{text[-200:]}")


def _call_local(system: str, user: str, shape: str) -> str:
    model = model_name()
    if not model:
        raise LLMError("没有设置 LOCAL_MODEL(网关路由名,例如 fast 或 brain)")
    url = f"{base_url()}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{system}\n\n严格只输出 JSON,不要解释,不要 ``` 围栏。\n"
                    f"JSON 的形状必须是:\n{shape}"
                ),
            },
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    timeout = float(os.environ.get("LOCAL_TIMEOUT", "180"))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url, headers={"Authorization": f"Bearer {api_key()}"}, json=payload
            )
    except httpx.RequestError as exc:
        raise LLMError(f"连不上 {url}:{exc}。检查 DGX_GATEWAY_URL / LOCAL_BASE_URL") from exc
    if response.status_code >= 300:
        raise LLMError(f"本地模型 {response.status_code}:{response.text[:300]}")
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"回包形状不对:{str(data)[:300]}") from exc
    if not content:
        raise LLMError("模型返回了空的 content(有的服务端把内容放进 reasoning 字段)")
    return content


def _call_claude(system: str, user: str, shape: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_name() or DEFAULT_CLAUDE_MODEL,
        max_tokens=16000,
        system=system,
        cache_control={"type": "ephemeral"},
        thinking={"type": "adaptive"},
        output_config={"effort": os.environ.get("EFFORT", "medium")},
        messages=[{"role": "user", "content": f"{user}\n\n只输出 JSON,形状:\n{shape}"}],
    )
    return next(block.text for block in response.content if block.type == "text")


def complete(system: str, user: str, model_cls: type[BaseModel]) -> BaseModel:
    """跑一次任务,拿回一个校验过的对象。校验不过给一次改正机会,再不过就报错。"""
    shape = _shape_hint(model_cls)
    call = _call_local if backend() == "local" else _call_claude
    raw = call(system, user, shape)
    try:
        return model_cls.model_validate_json(_extract_json(raw))
    except (ValidationError, LLMError) as first:
        repair = (
            f"{user}\n\n---\n你上一次的输出不符合要求:\n{raw[:1500]}\n\n"
            f"错误:{first}\n\n请只输出修正后的 JSON,不要任何其它文字。"
        )
        raw2 = call(system, repair, shape)
        try:
            return model_cls.model_validate_json(_extract_json(raw2))
        except (ValidationError, LLMError) as second:
            raise LLMError(f"两次都没给出合规 JSON。最后一次:{second}") from second
