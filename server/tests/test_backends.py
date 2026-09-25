"""攻击后端层。它唯一的承诺是:模型不合规时报错,不编结果(宪法第六条)。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from pydantic import BaseModel

from aimail import backends
from aimail.tasks.summarize import InquirySummary


class Tiny(BaseModel):
    name: str
    count: int


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("DGX_GATEWAY_URL", raising=False)


# ── 抠 JSON ──


def test_fenced_json_is_unwrapped():
    assert json.loads(backends._extract_json('```json\n{"a": 1}\n```')) == {"a": 1}


def test_prose_around_json_is_stripped():
    assert json.loads(backends._extract_json('好的,以下是结果:\n{"a": 1}\n希望有帮助!')) == {"a": 1}


def test_truncated_json_is_rejected_rather_than_guessed():
    with pytest.raises(backends.LLMError, match="没有闭合"):
        backends._extract_json('{"a": 1, "b": {"c": 2}')


def test_unmatched_brace_inside_a_string_does_not_end_the_object():
    assert json.loads(backends._extract_json('{"s": "型号 A}B", "n": 1}'))["n"] == 1


def test_escaped_quote_does_not_reopen_brace_counting():
    assert json.loads(backends._extract_json(r'{"s": "他说 \"}\" 无所谓", "n": 1}'))["n"] == 1


def test_empty_output_is_rejected():
    with pytest.raises(backends.LLMError):
        backends._extract_json("   ")


# ── 后端选择与地址 ──


def test_unknown_backend_name_is_rejected_loudly(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "spark")
    with pytest.raises(backends.LLMError, match="只能是"):
        backends.backend()


def test_local_backend_without_model_name_is_not_ready(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    ready, why = backends.ready()
    assert ready is False and "LOCAL_MODEL" in why


def test_describe_names_the_backend_that_answered():
    assert backends.describe() == "Spark · fast"


def test_gateway_url_gets_the_v1_suffix(monkeypatch):
    monkeypatch.setenv("DGX_GATEWAY_URL", "https://gateway.example:4000/")
    assert backends.base_url() == "https://gateway.example:4000/v1"


def test_explicit_base_url_overrides_the_gateway(monkeypatch):
    monkeypatch.setenv("DGX_GATEWAY_URL", "https://gateway.example:4000")
    monkeypatch.setenv("LOCAL_BASE_URL", "http://ollama.example:11434/v1")
    assert backends.base_url() == "http://ollama.example:11434/v1"


# ── 重试与放弃 ──


def test_bad_output_gets_exactly_one_repair_attempt(monkeypatch):
    calls: list[str] = []

    def fake(system, user, shape):
        calls.append(user)
        return "我不想输出 JSON。"

    monkeypatch.setattr(backends, "_call_local", fake)
    with pytest.raises(backends.LLMError, match="两次都没给出合规 JSON"):
        backends.complete("sys", "邮件正文", Tiny)
    assert len(calls) == 2, "只重试一次——无限重试会把本地机器跑死"
    assert "邮件正文" in calls[1] and "不符合要求" in calls[1]


def test_repair_attempt_can_succeed(monkeypatch):
    answers = iter(["不是 JSON", '{"name": "a", "count": 2}'])
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: next(answers))
    assert backends.complete("sys", "x", Tiny).count == 2


def test_wrong_types_are_rejected_not_coerced(monkeypatch):
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: '{"name": "a", "count": "很多"}')
    with pytest.raises(backends.LLMError):
        backends.complete("sys", "x", Tiny)


# ── 真 HTTP:发出去的字节 ──

seen: dict = {}
ANSWER = {
    "is_inquiry": True,
    "detected_language": "en",
    "summary_zh": "客户要 48 台。",
    "summary_en": "Customer needs 48 units.",
    "facts": ["48 台"],
    "quoted_numbers": ["48"],
}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        seen["path"] = self.path
        seen["auth"] = self.headers.get("Authorization")
        seen["body"] = json.loads(self.rfile.read(length))
        content = "好的:\n```json\n" + json.dumps(ANSWER, ensure_ascii=False) + "\n```"
        raw = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def fake_gateway(monkeypatch):
    seen.clear()
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    monkeypatch.setenv("DGX_GATEWAY_URL", f"http://{host}:{port}")
    monkeypatch.setenv("DGX_API_KEY", "tok")
    yield
    server.shutdown()


def test_request_lands_on_the_openai_chat_completions_path(fake_gateway):
    backends.complete("你是助手", "We need 48 servers.", InquirySummary)
    assert seen["path"] == "/v1/chat/completions"


def test_task_can_bound_its_output_budget(fake_gateway):
    backends.complete("sys", "mail", InquirySummary, max_tokens=3072, reasoning_effort="none")
    assert seen["body"]["max_tokens"] == 3072
    assert seen["body"]["reasoning_effort"] == "none"


def test_api_key_is_sent_as_a_bearer_token(fake_gateway):
    backends.complete("你是助手", "x", InquirySummary)
    assert seen["auth"] == "Bearer tok"


def test_payload_carries_model_zero_temperature_and_shape(fake_gateway):
    backends.complete("你是助手", "x", InquirySummary)
    assert seen["body"]["model"] == "fast"
    assert seen["body"]["temperature"] == 0
    assert "quoted_numbers" in seen["body"]["messages"][0]["content"]


def test_fenced_answer_from_a_real_socket_is_parsed(fake_gateway):
    result = backends.complete("你是助手", "We need 48 servers.", InquirySummary)
    assert isinstance(result, InquirySummary) and result.quoted_numbers == ["48"]


def test_unreachable_gateway_says_where_to_look(monkeypatch):
    monkeypatch.setenv("LOCAL_BASE_URL", "http://127.0.0.1:1/v1")
    with pytest.raises(backends.LLMError, match="LOCAL_BASE_URL"):
        backends.complete("s", "u", InquirySummary)
