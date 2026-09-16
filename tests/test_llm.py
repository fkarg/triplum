import json

from triplum.cache import Cache
from triplum.llm.cached import CachedLLM
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import GenParams, Message, request_payload


def test_request_payload_includes_schema_and_params():
    msgs = [Message("user", "hi")]
    p1 = request_payload("fake", "m", msgs, None, GenParams())
    p2 = request_payload("fake", "m", msgs, {"type": "object"}, GenParams())
    p3 = request_payload("fake", "m", msgs, None, GenParams(temperature=0.5))
    assert p1 != p2 and p1 != p3


def test_fake_llm_is_deterministic_and_reports_usage():
    llm = FakeLLM()
    a = llm.complete([Message("user", "What is 2+2?")])
    b = llm.complete([Message("user", "What is 2+2?")])
    assert a.text == b.text and a.usage.output_tokens > 0 and a.cached is False


def test_fake_llm_structured_output_parses():
    llm = FakeLLM(responder=lambda msgs, schema: json.dumps({"answer": "4"}))
    c = llm.complete([Message("user", "q")], schema={"type": "object"})
    assert c.parsed == {"answer": "4"}


def test_cached_llm_hits_on_second_call(tmp_path):
    calls = []

    def responder(msgs, schema):
        calls.append(1)
        return "x"

    llm = CachedLLM(FakeLLM(responder=responder), Cache(tmp_path))
    c1 = llm.complete([Message("user", "q")])
    c2 = llm.complete([Message("user", "q")])
    assert len(calls) == 1 and c1.cached is False and c2.cached is True
    assert c1.text == c2.text and c1.request_hash == c2.request_hash


import sys

from triplum.llm.cli import CliLLM
from triplum.llm.openai_compat import OpenAICompatLLM


def test_openai_compat_builds_request_and_parses():
    sent = {}

    class _Msg:
        content = '{"answer": "4"}'

    class _Choice:
        message = _Msg()

    class _Usage:
        prompt_tokens = 7
        completion_tokens = 3
        prompt_tokens_details = None

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()
        model = "test-model"

        def model_dump(self):
            return {"id": "r1"}

    class _Completions:
        def create(self, **kw):
            sent.update(kw)
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    llm = OpenAICompatLLM(model="test-model", client=_Client())
    c = llm.complete([Message("user", "q")], schema={"type": "object"})
    assert sent["model"] == "test-model"
    assert sent["response_format"]["type"] == "json_schema"
    assert c.parsed == {"answer": "4"} and c.usage.input_tokens == 7 and c.usage.output_tokens == 3


def test_cli_llm_runs_command_and_reads_stdout():
    llm = CliLLM(
        model="echo", argv=[sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"]
    )
    c = llm.complete([Message("user", "hello")])
    assert "HELLO" in c.text and c.usage.output_tokens >= 1


def test_cli_llm_json_output_field():
    argv = [
        sys.executable,
        "-c",
        "import json,sys; sys.stdin.read(); print(json.dumps({'result': 'ok'}))",
    ]
    llm = CliLLM(model="x", argv=argv, json_field="result")
    assert llm.complete([Message("user", "q")]).text == "ok"
