# pydantic-ai as the LLM adapter

Snapshot 2026-09-17. Facts gathered for the D6 amendment (pydantic-ai adopted *under* the `LLM`
protocol) before the adapter is designed. Sources: the PyPI JSON API, the `pydantic/pydantic-ai`
repository at v2.44.0, the documentation site (`ai.pydantic.dev` now redirects to
`https://pydantic.dev/docs/ai/`), and a scratch install of `pydantic-ai-slim[openai]==2.44.0`
on which every signature below was executed. Items marked *(unverified)* were read from source
only.

## Package

| item | value | source |
|---|---|---|
| version | `pydantic-ai` and `pydantic-ai-slim` 2.44.0, released 2026-09-17; Python 3.10 to 3.14 | https://pypi.org/pypi/pydantic-ai-slim/json |
| cadence | 111 releases between v1.69.0 (2026-03-17) and v2.44.0; V2.0.0 on 2026-06-23 | GitHub releases |
| lean install | `pydantic-ai-slim[openai]` covers OpenAI, vLLM, Ollama, OpenRouter and every OpenAI-compatible endpoint; `[anthropic]` adds the native Anthropic model | https://pydantic.dev/docs/ai/overview/install/#slim-install |
| core deps of slim | anyio, genai-prices, griffelib, httpx, opentelemetry-api, pydantic-graph, pydantic >= 2.12 | PyPI metadata |
| version policy | no intended breaking changes in minors; *adding* message parts and optional fields is not breaking, so part matching needs a default branch | https://pydantic.dev/docs/ai/version-policy/ |

## Direct model request API

`pydantic_ai.direct`: `model_request`, `model_request_sync`, `model_request_stream`,
`model_request_stream_sync`, all with the signature

```python
model_request(model: Model | KnownModelName | str, messages: Sequence[ModelMessage], *,
              model_settings: ModelSettings | None = None,
              model_request_parameters: ModelRequestParameters | None = None,
              instrument: InstrumentationSettings | bool | None = None) -> ModelResponse
```

Internally `infer_model(model)`, then `model.request(messages, settings, params)`. The sync
form runs its own event loop and cannot be called from inside a running loop.
Docs: https://pydantic.dev/docs/ai/core-concepts/direct/

**Messages** (`pydantic_ai.messages`): `ModelMessage = ModelRequest | ModelResponse`,
discriminated on `kind`. `ModelRequest(parts, *, timestamp=None, instructions=None, ...)` with
parts `SystemPromptPart`, `UserPromptPart`, `ToolReturnPart`, `RetryPromptPart` and newer
kinds. `ModelResponse(parts, *, usage: RequestUsage, model_name, timestamp=now, provider_name,
provider_details, provider_response_id, finish_reason, ...)` with parts `TextPart`,
`ToolCallPart(tool_name, args, tool_call_id)`, `ThinkingPart` and newer kinds.

**Request parameters** (`pydantic_ai.models.ModelRequestParameters`, keyword-only dataclass):
`function_tools`, `output_mode` (`text | tool | native | prompted | tool_or_text | image |
auto`), `output_object: OutputObjectDefinition | None`, `output_tools`, `allow_text_output`,
`instruction_parts`, `thinking`, and more. `Model.prepare_request(settings, params)` is public
and returns the *effective* settings and parameters after the model's own defaults, the
prompted-output template and mode validation are applied. Every provider calls it first.

**Settings** (`pydantic_ai.settings.ModelSettings`, a `TypedDict`): `max_tokens`,
`temperature`, `top_p`, `seed`, `stop_sequences`, `timeout`, `parallel_tool_calls`,
`tool_choice`, `thinking`, `extra_headers`, `extra_body`, and provider-prefixed keys in the
provider subclasses. `merge_model_settings` is public.

**Usage** (`pydantic_ai.usage`): `RequestUsage(input_tokens, cache_write_tokens,
cache_read_tokens, output_tokens, input_audio_tokens, cache_audio_read_tokens,
output_audio_tokens, details, cost)`; `RunUsage` adds `requests` and `tool_calls`.
`UsageLimits` caps requests, tool calls, tokens and cost.

## Structured output without an agent

`OutputObjectDefinition(json_schema: dict, name, description, strict)` takes a plain JSON
schema; no Pydantic model is needed at the direct level. Modes:

- `tool`: `output_tools=[ToolDefinition(name, parameters_json_schema=...)]`,
  `output_mode="tool"`, `allow_text_output=False`; the answer arrives as a `ToolCallPart`.
- `native`: `output_mode="native"`, `output_object=...`; `prepare_request` raises unless the
  model profile has `supports_json_schema_output`.
- `prompted`: the schema is injected into the instructions from the profile's template.

Validation of the response against the schema is **not** done by the direct API; it lives in the
private `_output` module driven by the agent graph. An adapter parses the tool arguments or the
text itself. At the agent level, `Agent(output_type=StructuredDict(schema))` gives a validated
`dict` from a JSON schema.
Docs: https://pydantic.dev/docs/ai/core-concepts/output/

## Serialisation and cache keys

- `ModelMessagesTypeAdapter` (a `TypeAdapter(list[ModelMessage])`) and
  `pydantic_core.to_jsonable_python` are the documented persistence route; round trip verified.
  https://pydantic.dev/docs/ai/core-concepts/message-history/
- The message classes are stdlib dataclasses with `eq=True` and no hash: **mutable and
  unhashable**.
- **No canonical-JSON or cache-key facility exists.** Fields that vary between two identical
  requests: `UserPromptPart.timestamp`, `SystemPromptPart.timestamp`, `ModelResponse.timestamp`
  (all default to now), `ModelRequest.timestamp`, `run_id`, `conversation_id`, generated
  `tool_call_id` values (`pyd_ai_<uuid>`), `provider_details`, `provider_response_id`. A
  content-addressed key must exclude them; `dump_python(mode="json", exclude=...)` followed by
  sorted-key JSON was verified to work.

## Where a cache sits

- **No built-in caching.** The only "cache" in the docs is provider-side prompt caching.
- **`pydantic_ai.models.wrapper.WrapperModel`** is the documented interception base
  (`InstrumentedModel` is the in-tree example). A subclass overriding `request` intercepts both
  `model_request_sync` and every request an `Agent` loop makes. Verified. Streaming goes through
  `request_stream` and is a separate path. https://pydantic.dev/docs/ai/api/models/wrapper/
- `FunctionModel(function: (messages, AgentInfo) -> ModelResponse)` and `TestModel()` are the
  deterministic test doubles; `ALLOW_MODEL_REQUESTS = False` blocks real providers in tests.
  https://pydantic.dev/docs/ai/guides/testing/
- Whole-loop caching (agent specification plus inputs) has no built-in support. `Agent` and
  `run_sync` accept a declarative `spec` *(unverified as a complete hashable description)*.
- `Agent.run_sync(...)` returns `AgentRunResult` with `output`, `all_messages()`,
  `new_messages()`, and `usage` and `timestamp` as **properties** in V2.

## Providers

- `OpenAIChatModel` (Chat Completions) and `OpenAIResponsesModel` (Responses API) in
  `pydantic_ai.models.openai`; `AnthropicModel` in `pydantic_ai.models.anthropic`;
  `OpenAIProvider(base_url=..., api_key=...)` and the `VLLMProvider`, `OllamaProvider`,
  `OpenRouterProvider` variants in `pydantic_ai.providers`.
- `infer_model("openai:gpt-5")` returns the **Responses** model; `openai-chat:` selects Chat
  Completions; `ollama:`, `vllm:`, `openrouter:` and a long list of compatible providers map to
  `OpenAIChatModel`. Provider construction reads the API key from the environment at
  `infer_model` time.
- **No subprocess or CLI-harness model exists.** `openai-codex:` and `github-copilot:` use OAuth
  over HTTP. A `claude -p` adapter stays ours: either a `Model` subclass or outside pydantic-ai
  under the `LLM` protocol.
- Running an `Agent` without observability configured prints a banner to stderr; set
  `PYDANTIC_AI_NO_BANNER=1`.

## Churn since 2026-03 that an adapter must know

`OpenAIModel` became `OpenAIChatModel`; bare `openai:` switched to the Responses API; `Usage`
split into `RequestUsage` and `RunUsage` with `input_tokens`/`output_tokens`; `result.usage()`
became a property; `vendor_details` became `provider_details`; model profiles became
`TypedDict`s; `end_strategy` defaults to `graceful`. Full lists:
https://pydantic.dev/docs/ai/changelog/ and https://pydantic.dev/docs/ai/migration/

## Consequences for the adapter design

Assessment, to be decided at the LLM layer of the stack walk:

1. The protocol's own frozen `Message`, `GenParams`, `Usage` and `Completion` stay the boundary
   types. They are hashable, tiny, and serve the CLI adapter, which pydantic-ai cannot host.
   pydantic-ai types are converted at the adapter edge. Its `RequestUsage` fields
   (`cache_read_tokens`, `cache_write_tokens`) should be reflected in `Usage`.
2. The request cache is a `WrapperModel` subclass keyed on the prepared request with the
   volatile fields stripped. Under it, a direct call and an agent loop are cached the same way,
   which is what makes the D6 "agent loop as one cacheable request" amendment implementable.
3. Structured output uses `tool` mode by default (universally supported) and `native` where the
   profile allows; validation is a `jsonschema`-style check in the adapter, with the retry
   count recorded, since the direct API does not validate.
4. Provider strings are explicit (`openai-chat:`, `ollama:`), never the bare `openai:` prefix,
   because its meaning changed once already.
