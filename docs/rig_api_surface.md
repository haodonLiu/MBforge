# rig-core 0.38.1 — API surface for MBForge M4

Source: `~/.cargo/registry/src/.../rig-core-0.38.1/` (verified directly from source).

## Section 1: Client construction

### OpenAI-compatible (sidecar = `OPENAI_BASE_URL`)

- `providers::openai::Client` = **type alias** for the Responses API client:
  ```rust
  pub type Client<H = reqwest::Client> = client::Client<OpenAIResponsesExt, H>;
  pub type ClientBuilder<H = Missing> = client::ClientBuilder<OpenAIResponsesExtBuilder, OpenAIApiKey, H>;
  ```
- `providers::openai::CompletionsClient` = type alias for the **Chat Completions** API:
  ```rust
  pub type CompletionsClient<H = reqwest::Client> = client::Client<OpenAICompletionsExt, H>;
  ```
  You can also convert: `client.completions_api() -> CompletionsClient<H>`.
- `Client::builder() -> ClientBuilder<Ext::Builder, Missing, Missing>` — type-state: `api_key` MUST be called before `build()` is reachable.
- Builder methods (from `src/client/mod.rs`):
  - `api_key<K>(self, k: impl Into<K>) -> ClientBuilder<Ext, K, H>` — consumes the `Missing` slot.
  - `base_url<S: AsRef<str>>(self, url: S) -> Self`
  - `http_client<U>(self, c: U) -> ClientBuilder<Ext, ApiKey, U>` — only for non-`reqwest` backends.
  - `build() -> http_client::Result<Client<...>>` where `http_client::Error` is `thiserror` enum (`Protocol`, `InvalidStatusCode`, `Instance`, `Io`, ...).
- **For the MBForge sidecar** (Chat Completions API) → use `providers::openai::CompletionsClient::builder().api_key("dummy").base_url("http://127.0.0.1:port/v1").build()?`. The `Client::from_env()` impl reads `OPENAI_API_KEY` and optionally `OPENAI_BASE_URL`. `internal::openai_chat_completions_compatible` is `pub(crate)` — not public.

### Anthropic

- `providers::anthropic::Client` is a type alias: `client::Client<AnthropicExt, H>` over `AnthropicExt` (zero-sized) and `AnthropicKey` (sends `x-api-key` header).
- `Client::builder().api_key(k).anthropic_version(v).anthropic_beta(name).build()` — **returns `http_client::Result<Client>`**, does NOT panic.
- `anthropic_version(self, &str) -> Self` sets the `anthropic-version` header (default `2023-06-01`).
- `anthropic_beta(self, &str) -> Self` and `anthropic_betas(self, &[&str]) -> Self` (append).
- `base_url` is set via the inherited `ClientBuilder::base_url(&str)`. `finish_anthropic_builder` normalises the URL (strips `/v1/messages`, `/messages`, `/v1`).
- `ProviderClient::from_env()` reads `ANTHROPIC_API_KEY` (no base URL env).

## Section 2: AgentBuilder chain

```rust
pub struct AgentBuilder<M, P = (), ToolState = NoToolConfig>
where M: CompletionModel, P: PromptHook<M>;
```

- `client.agent(model_name).preamble("...").default_max_turns(N).temperature(0.7).max_tokens(1024).tools(vec).build()`.
- `client.agent(model)` defined by `CompletionClient` trait: `fn agent(&self, model: impl Into<String>) -> AgentBuilder<Self::CompletionModel>`. Returns `AgentBuilder<_, (), NoToolConfig>`.
- Default `P = ()` (no hook). To attach a hook: `.hook(impl PromptHook<M>)` → `AgentBuilder<M, P2, ToolState>`.
- **Type-state for tools** (`NoToolConfig | WithToolServerHandle | WithBuilderTools`):
  - `NoToolConfig → WithBuilderTools`: `tool(impl Tool + 'static)`, `tools(Vec<Box<dyn ToolDyn>>)`, `dynamic_tools`, `rmcp_tool`, `rmcp_tools`.
  - `NoToolConfig → WithToolServerHandle`: `tool_server_handle(ToolServerHandle)`.
  - `WithBuilderTools` allows repeated `tool()`/`tools()` but **not** `tool_server_handle()`.
  - `WithToolServerHandle` allows **only** `.build()`.
- `default_max_turns(usize)` sets the default recursion depth for multi-turn agent calls (tool-call round-trips). Override per-request with `.multi_turn(N)`. Default `None` (= 0) means only the initial response — no follow-up tool round-trips.
- `preamble(&str)` — stored as `Option<String>`. Other helpers: `append_preamble(&str)`, `without_preamble()`.
- `temperature(f64)`, `max_tokens(u64)` — direct setters.
- `build() -> Agent<M, P>` — does NOT return `Result`.

## Section 3: Agent<M, P> bounds

```rust
#[derive(Clone)]
#[non_exhaustive]
pub struct Agent<M, P = ()> where M: CompletionModel, P: PromptHook<M> {
    pub name: Option<String>,
    pub description: Option<String>,
    pub model: Arc<M>,
    pub preamble: Option<String>,
    pub static_context: Vec<Document>,
    pub temperature: Option<f64>,
    pub max_tokens: Option<u64>,
    pub additional_params: Option<serde_json::Value>,
    pub tool_server_handle: ToolServerHandle,
    pub dynamic_context: DynamicContextStore,  // Arc<...>
    pub tool_choice: Option<ToolChoice>,
    pub default_max_turns: Option<usize>,
    pub hook: Option<P>,
    pub output_schema: Option<schemars::Schema>,
    pub memory: Option<Arc<dyn ConversationMemory>>,
    pub default_conversation_id: Option<String>,
}
```

- `Clone`: all fields are `Clone` (model is `Arc<M>`, `DynamicContextStore` is `Arc<...>`, etc.), so `Agent<M, P>` is `Clone` when `M: Clone + CompletionModel` and `P: Clone`. (Both are required for the trait bounds anyway.)
- `prompt()` is via the `Prompt` trait:
  ```rust
  impl<M, P> Prompt for Agent<M, P>
  where M: CompletionModel + 'static, P: PromptHook<M> + 'static {
      fn prompt(&self, p: impl Into<Message> + WasmCompatSend)
          -> PromptRequest<Standard, M, P>;
  }
  ```
  `PromptRequest` is `IntoFuture`; `agent.prompt("...").await -> Result<PromptResponse, PromptError>`. `PromptError` is `thiserror` enum (`RequestError`, `MaxTurnsError`, `Cancelled`, `ProviderError`, ...). Requires `use rig_core::completion::Prompt;` (or prelude).
- `stream_prompt()` is via `StreamingPrompt`:
  ```rust
  impl<M, P> StreamingPrompt<M, M::StreamingResponse> for Agent<M, P>
  where M: CompletionModel + 'static, M::StreamingResponse: GetTokenUsage, P: PromptHook<M> + 'static {
      type Hook = P;
      fn stream_prompt(&self, p: impl Into<Message> + WasmCompatSend)
          -> StreamingPromptRequest<M, P>;
  }
  ```
  `StreamingPromptRequest` is `IntoFuture<Output = Result<StreamingResult<M::StreamingResponse>, StreamingError>>`. `StreamingResult<R> = Pin<Box<dyn Stream<Item = Result<MultiTurnStreamItem<R>, StreamingError>> + Send>>`. Requires `use rig_core::streaming::StreamingPrompt;` (or prelude).
- Streaming chain: `agent.stream_prompt("...").multi_turn(N).with_hook(MyHook).with_history(vec).await` → `Result<impl Stream<...>, StreamingError>`. Drain until `MultiTurnStreamItem::FinalResponse(_)` and call `.usage()` / `.response()` / `.completion_calls()`.

## Section 4: CompletionResponse for hooks

```rust
#[derive(Debug)]
pub struct CompletionResponse<T> {
    pub choice: OneOrMany<AssistantContent>,   // <-- OneOrMany
    pub usage: Usage,
    pub raw_response: T,                       // provider-specific raw body
    pub message_id: Option<String>,            // OpenAI Responses API msg_ id
}
```

```rust
pub struct Usage {
    pub input_tokens: u64,                     // NOT "prompt_tokens"
    pub output_tokens: u64,                    // NOT "completion_tokens"
    pub total_tokens: u64,
    pub cached_input_tokens: u64,
    pub cache_creation_input_tokens: u64,
    pub tool_use_prompt_tokens: u64,
    pub reasoning_tokens: u64,
}
```

- Extract assistant text: iterate `response.choice` (a `OneOrMany<AssistantContent>`), match `AssistantContent::Text(Text { text, .. })` and use `text.text: String`.
- `AssistantContent` is `#[serde(untagged)]` with variants for text, tool calls, reasoning. Use the `Text` variant for plain text.

## Section 5: MultiTurnStreamItem variants

```rust
#[serde(tag = "type", rename_all = "camelCase")]
#[non_exhaustive]
pub enum MultiTurnStreamItem<R> {
    StreamAssistantItem(StreamedAssistantContent<R>),
    StreamUserItem(StreamedUserContent),        // tool results
    CompletionCall(CompletionCall),             // one finished provider call (with optional Usage)
    FinalResponse(FinalResponse),               // terminal item
}
```

`StreamedAssistantContent<R>` variants (from `streaming.rs`):
- `Text(Text)` — text delta
- `ToolCall { tool_call, internal_call_id }` — complete tool call
- `ToolCallDelta { id, internal_call_id, content: ToolCallDeltaContent }` — partial
- `Reasoning(Reasoning)`
- `ReasoningDelta { reasoning, id }`
- `Final(R)` — terminal provider `StreamingCompletionResponse`

```rust
pub struct FinalResponse {
    content: OneOrMany<AssistantContent>,
    response: String,                          // concatenated assistant text
    aggregated_usage: crate::completion::Usage,
    completion_calls: Vec<CompletionCall>,      // skipped if empty
    history: Option<Vec<Message>>,
}
impl FinalResponse {
    pub fn response(&self) -> &str;
    pub fn content(&self) -> &OneOrMany<AssistantContent>;
    pub fn assistant_content(&self) -> &OneOrMany<AssistantContent>;
    pub fn usage(&self) -> crate::completion::Usage;     // BY VALUE (Usage is Copy)
    pub fn completion_calls(&self) -> &[CompletionCall];
    pub fn history(&self) -> Option<&[Message]>;
}
```

`CompletionCall` = `struct { call_index: usize, usage: Option<Usage> }` (one finished provider call with optional `Usage`).

## Section 6: Features

- `default = ["reqwest", "derive", "rustls"]`.
- Available: `audio`, `derive`, `discord-bot`, `epub`, `experimental`, `image`, `native-tls`, `pdf`, `rayon`, `reqwest` (`charset`/`http2`/`system-proxy`), `reqwest-middleware`, `reqwest-middleware-native-tls`, `reqwest-middleware-rustls`, `rmcp`, `rustls` (`reqwest/rustls` + `tokio-tungstenite?/rustls-tls-webpki-roots`), `socks`, `test-utils`, `wasm`, `websocket`, `websocket-native-tls`, `websocket-rustls`.
- `test-utils` is a feature flag (lib.rs: `#[cfg(any(test, feature = "test-utils"))] pub mod test_utils;`). Re-exports `MockCompletionModel`, `MockTurn`, `MockError`, `MockResponse`, `MockStreamEvent`, `MockAddTool`, `MockSubtractTool`, `MockHttpResponse`, `MockStreamingClient`, `RecordingHttpClient`, etc.
- **To enable MockCompletionModel**: `rig-core = { version = "0.38.1", features = ["test-utils"] }`. Exact flag string: `"test-utils"` (with hyphen, not underscore).
- `derive` (on by default) enables the `#[derive(Embed)]` and `#[rig_tool]` proc-macros.

## Caveats

- The type-state `ToolState` is a third generic; `client.agent(model).build()` infers `NoToolConfig` for you.
- `PromptHook<M>` has no required methods, so the simplest custom hook is:
  ```rust
  struct AuditLogHook;
  impl<M: CompletionModel> PromptHook<M> for AuditLogHook {}
  ```
- `build()` does not return `Result` — it always returns `Agent<M, P>`. Tool-server spawn is infallible.
- `ProviderClient::from_env()` returns `Result<_, ProviderClientError>`; `Client::builder().build()` returns `http_client::Result`. Both `?` into `Box<dyn Error>`.
- For streaming, `M::StreamingResponse: GetTokenUsage` is required. Anthropic's and OpenAI's `StreamingCompletionResponse` both implement it.
- `multi_turn(0)` (default) means no follow-up LLM turn after the first response — so tool calls will not trigger round-trips. For tool-using agents, set `.multi_turn(N)` per request or `.default_max_turns(N)` on the builder.
