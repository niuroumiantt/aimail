"""模型后端:一份合同,可切换的后端。

- local  —— Spark,走 LiteLLM 网关的 OpenAI 兼容接口
- claude —— Anthropic 官方 SDK
- codex_cli / claude_code_cli —— 已安装、已登录的研发 CLI，隔离的纯文本任务

合同(输入什么、输出什么、怎么核对)在 tasks/ 里,后端共用;同一套评测集跑出来的分数才可比。
知道"模型在哪"的只有这个目录(宪法第八条,tools/guard_hostnames.py 强制)。

小模型跟托管模型最大的差别不是聪明程度,是输出纪律:爱裹围栏、裹解释、写着写着截断。所以:
1. 按标准方式要 JSON(response_format,不支持的服务端会忽略)
2. 再给一份人类可读的字段模板——比原始 JSON Schema 对小模型更管用
3. 解析前剥围栏、取第一个括号平衡的 {...}
4. Pydantic 校验;不过就把错误原样丢回去让它改**一次**
5. 还不过就抛 LLMError——绝不编一个看起来像样的结果(宪法第六条)
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from . import routing

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_CLAUDE_MODEL = "claude-opus-5"


class LLMError(RuntimeError):
    """模型没有给出合规输出。不要把它当成「摘要为空」处理。"""


def backend() -> str:
    try:
        return routing.selected(os.environ.get("LLM_BACKEND", "local"))
    except routing.SelectionError as exc:
        raise LLMError(str(exc)) from None


@contextmanager
def use_backend(name: str, *, model: str | None = None) -> Iterator[str]:
    """Select a trusted provider id for this task and restore it on exit or failure."""
    try:
        routing.validate(name)
    except routing.SelectionError as exc:
        raise LLMError(str(exc)) from None
    if model is not None:
        resolved_model = model
    elif routing.selected_override() == name and routing.selected_model() is not None:
        resolved_model = routing.selected_model()
    else:
        with routing.use_backend(name):
            resolved_model = model_name()
    with routing.use_backend(name, model=resolved_model):
        yield name


def model_name(override: str | None = None) -> str:
    if override:
        return override.strip()
    scoped = routing.selected_model()
    if scoped is not None:
        return scoped
    if backend() == "local":
        return os.environ.get("LOCAL_MODEL", "").strip()
    if backend() in {"codex_cli", "claude_code_cli"}:
        from . import cli

        return cli.model_name(backend())
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


def describe(model: str | None = None) -> str:
    """一行字说明这次结果是谁算的；CLI 与 API 后端分别署名。"""
    name = model_name(model) or "(未设置)"
    if backend() in {"codex_cli", "claude_code_cli"}:
        from . import cli

        return f"{cli.label(backend())} · {name}"
    label = os.environ.get("LOCAL_PROVIDER_LABEL", "Spark")
    return f"{label} · {name}" if backend() == "local" else f"Claude · {name}"


def ready() -> tuple[bool, str]:
    if backend() in {"codex_cli", "claude_code_cli"}:
        from . import cli

        return cli.ready(backend(), model=model_name())
    if backend() == "local":
        if not model_name():
            return False, "没有设置 LOCAL_MODEL(网关路由名,例如 fast 或 brain)"
        return True, f"本地模型 {model_name()} @ {base_url()}"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "没有设置 ANTHROPIC_API_KEY"
    return True, f"Claude {model_name()}"


def provider_catalog() -> list[dict[str, str | bool]]:
    """Mailbox choices with public state only; no calls, commands, URLs or credentials.

    `available` means configured on this runtime, not a fresh paid inference/health
    check. CLI connection/login remains checked by the actual task call.
    """
    labels = {"local": "Spark", "codex_cli": "Codex CLI", "claude_code_cli": "Claude Code CLI"}
    choices: list[dict[str, str | bool]] = []
    for name in routing.MAILBOX_PROVIDERS:
        with routing.use_backend(name):
            model = model_name()
            with use_backend(name, model=model):
                configured, _ = ready()
        # Model ids are intended public attribution. Misconfigured URLs and control
        # characters must not turn this field into a route/credential disclosure.
        public_model = model if _public_model_id(model) else ""
        if model and not public_model:
            configured = False
        if not public_model:
            reason = "尚未指定模型"
        elif name == "local":
            reason = "使用已配置的本地模型服务" if configured else "本地模型服务尚未配置完成"
        else:
            from . import cli_bridge

            if cli_bridge.enabled():
                reason = (
                    "通过已连接的 CLI 工作站分析" if configured else "CLI 工作站未连接或型号未就绪"
                )
            else:
                reason = (
                    "CLI 已配置；登录及连接在任务运行时核验"
                    if configured
                    else "CLI 未安装或运行配置未完成"
                )
        choices.append(
            {
                "id": name,
                "label": labels[name],
                "available": configured,
                "model": public_model,
                "reason": reason,
            }
        )
    return choices


def _public_model_id(model: str) -> bool:
    return (
        bool(model)
        and len(model) <= 200
        and not any(ord(char) < 32 or char in "@?#" for char in model)
        and "://" not in model
    )


def _shape_hint(model_cls: type[BaseModel]) -> str:
    """把 Pydantic 模型渲染成人读得懂的字段模板;原始 JSON Schema 的 $defs、anyOf 对小模型是噪音。"""
    schema = model_cls.model_json_schema()
    if "$defs" in schema:
        # Nested result contracts must retain object fields, not become array<string>.
        return json.dumps(schema, ensure_ascii=False)
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


def _call_local(
    system: str,
    user: str,
    shape: str,
    *,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
) -> str:
    selected_model = model_name(model)
    if not selected_model:
        raise LLMError("没有设置 LOCAL_MODEL(网关路由名,例如 fast 或 brain)")
    url = f"{base_url()}/chat/completions"
    payload: dict[str, Any] = {
        "model": selected_model,
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
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
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
    if any(c.get("finish_reason") == "length" for c in data.get("choices", [])):
        raise LLMError("输出达到 token 上限，未作为完整结果保存")
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


def complete(
    system: str,
    user: str,
    model_cls: type[BaseModel],
    *,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
) -> BaseModel:
    """跑一次任务,拿回一个校验过的对象。校验不过给一次改正机会,再不过就报错。"""
    with use_backend(backend(), model=model_name(model)):
        return _complete_scoped(
            system,
            user,
            model_cls,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            model=model,
        )


def _complete_scoped(
    system: str,
    user: str,
    model_cls: type[BaseModel],
    *,
    max_tokens: int | None,
    reasoning_effort: str | None,
    model: str | None,
) -> BaseModel:
    shape = _shape_hint(model_cls)

    def call(system, user, shape):
        if backend() == "local":
            options = {}
            if max_tokens is not None:
                options["max_tokens"] = max_tokens
            if reasoning_effort is not None:
                options["reasoning_effort"] = reasoning_effort
            if model:
                options["model"] = model
            return _call_local(system, user, shape, **options)
        if backend() in {"codex_cli", "claude_code_cli"}:
            from . import cli

            try:
                return cli.complete(
                    backend(), system, user, model_cls.model_json_schema(), model=model_name(model)
                )
            except cli.CLIError as exc:
                raise LLMError(str(exc)) from None
        return _call_claude(system, user, shape)

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
            if backend() in {"codex_cli", "claude_code_cli"}:
                raise LLMError("CLI 两次都没给出合规 JSON；结果没有保存") from None
            raise LLMError(f"两次都没给出合规 JSON。最后一次:{second}") from second
