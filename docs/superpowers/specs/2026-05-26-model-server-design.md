# MBForge 模型服务化设计文档

## 1. 概述

**目标**：将所有模型推理（LLM、Embedder、Reranker、VLM）从主应用中分离到独立 FastAPI 进程，解除 MBForge 启动对模型加载的依赖，实现进程级隔离。

**核心变化**：
- 主应用启动不再等待模型加载，立即就绪
- 模型在独立 FastAPI 进程中加载，通过 HTTP 与主应用通信
- UI 通过状态指示灯实时反映模型服务状态

---

## 2. 架构

### 进程模型

```
┌─────────────────────────────────────────────────────────┐
│  MBForge 主进程 (PyQt6)                                │
│  ├── UI 层                                             │
│  ├── 业务逻辑（KnowledgeBase, Agent, Pipeline）         │
│  └── HTTP 客户端（httpx）调用模型服务                   │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP (localhost:18792)
┌─────────────────────────▼───────────────────────────────┐
│  模型服务进程 (FastAPI / uvicorn)                      │
│  ├── /api/v1/llm/chat        → LLM 推理                │
│  ├── /api/v1/llm/chat-stream → LLM 流式推理            │
│  ├── /api/v1/embed           → Embedder 推理            │
│  ├── /api/v1/rerank          → Reranker 推理           │
│  ├── /api/v1/vlm/describe    → VLM 推理                │
│  └── /api/v1/health          → 服务+模型状态            │
└─────────────────────────────────────────────────────────┘
```

### 启动时序

1. MBForge 主应用启动，UI 立即就绪
2. 后台启动 FastAPI 子进程（`subprocess.Popen`）
3. 轮询 `/api/v1/health`，直到所有模型就绪或超时
4. UI 状态指示灯反映实时状态

### 退出时序

1. MBForge 主应用退出
2. `Popen.terminate()` 终止 FastAPI 子进程
3. 等待子进程退出（`wait(timeout=5)`），超时则 `kill()`

---

## 3. 配置

### 新增配置项（`AppConfig`）

```python
ModelServerConfig:
    host: str = "127.0.0.1"
    port: int = 18792
    auto_start: bool = True      # 是否自动启动子进程
    startup_timeout: int = 120   # 等待服务就绪的超时（秒）
    health_check_interval: int = 5  # 健康检查间隔（秒）
```

### 向后兼容

- `auto_start=False` 时，MBForge 作为 HTTP 代理，连接外部已运行的服务
- 连接失败时降级为直接 import 模式（当前行为兼容）

---

## 4. API 设计

### 4.1 健康检查

```
GET /api/v1/health
```

Response:
```json
{
  "status": "online|loading|error",
  "models": {
    "llm": "ready|loading|error|unavailable",
    "embedder": "ready|loading|error|unavailable",
    "reranker": "ready|loading|error|unavailable",
    "vlm": "ready|loading|error|unavailable"
  },
  "error": "optional error message"
}
```

### 4.2 LLM Chat

```
POST /api/v1/llm/chat
Content-Type: application/json

{
  "messages": [
    { "role": "user", "content": "..." }
  ],
  "temperature": 0.7,
  "max_tokens": 2048,
  "tools": [...]
}
```

Response:
```json
{
  "content": "...",
  "finish_reason": "stop"
}
```

### 4.3 LLM Chat Stream

```
POST /api/v1/llm/chat-stream
Content-Type: application/json

{
  "messages": [...],
  "temperature": 0.7,
  "max_tokens": 2048
}
```

Response: SSE stream
```
data: {"delta": "Hello", "finish_reason": null}
data: {"delta": " world", "finish_reason": null}
data: {"delta": "", "finish_reason": "stop"}
```

### 4.4 Embedder

```
POST /api/v1/embed
Content-Type: application/json

{
  "texts": ["string or array of strings"],
  "model": "sentence_transformers" | "qwen3" | "openai"
}
```

Response:
```json
{
  "embeddings": [[0.123, -0.456, ...]]
}
```

### 4.5 Reranker

```
POST /api/v1/rerank
Content-Type: application/json

{
  "query": "string",
  "passages": ["string", "string", ...],
  "top_n": 5,
  "model": "sentence_transformers" | "qwen3"
}
```

Response:
```json
{
  "results": [
    { "index": 0, "score": 0.92 },
    { "index": 3, "score": 0.85 }
  ]
}
```

### 4.6 VLM Describe

```
POST /api/v1/vlm/describe
Content-Type: application/json

{
  "image_base64": "...",
  "prompt": "optional prompt"
}
```

Response:
```json
{
  "description": "..."
}
```

---

## 5. 目录结构

```
src/mbforge/
├── model_server/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口，uvicorn 启动点
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── llm.py          # /api/v1/llm/*
│   │   ├── embed.py        # /api/v1/embed
│   │   ├── rerank.py       # /api/v1/rerank
│   │   ├── vlm.py          # /api/v1/vlm/*
│   │   └── health.py        # /api/v1/health
│   ├── models/             # 模型实例化管理
│   │   ├── __init__.py
│   │   ├── llm.py          # LLM 模型加载和推理
│   │   ├── embedder.py     # Embedder 模型加载和推理
│   │   ├── reranker.py     # Reranker 模型加载和推理
│   │   └── vlm.py          # VLM 模型加载和推理
│   └── process_manager.py   # 子进程管理（启动/停止/健康检查）
├── models/
│   └── client.py            # HTTP 客户端封装，替代直接模型调用
└── utils/
    └── config.py            # 新增 ModelServerConfig
```

---

## 6. 实现要点

### 6.1 模型客户端（`models/client.py`）

将现有的直接模型调用（`create_llm_from_config` 等）替换为 HTTP 调用：

```python
class LLMClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def chat(self, messages, **kwargs) -> str:
        resp = await self._client.post(f"{self.base_url}/api/v1/llm/chat", json={...})
        return resp.json()["content"]

    async def chat_stream(self, messages, **kwargs) -> AsyncIterator[str]:
        async with self._client.stream(...) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])["delta"]
```

### 6.2 进程管理（`model_server/process_manager.py`）

```python
class ModelServerManager:
    def __init__(self, config: ModelServerConfig):
        self.config = config
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        """启动 FastAPI 子进程"""
        self._process = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "mbforge.model_server.main:app",
            "--host", self.config.host,
            "--port", str(self.config.port),
            "--workers", "1",
        ])
        self._wait_ready()

    def stop(self) -> None:
        """停止 FastAPI 子进程"""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

    async def get_health(self) -> dict:
        """查询健康状态"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{self.host}:{self.port}/api/v1/health")
            return resp.json()
```

### 6.3 状态指示灯（`ServiceStatusIndicator` 改造）

现有 `ServiceStatusIndicator` 改造为轮询 `/api/v1/health`：

```python
class ServiceStatusIndicator(QWidget):
    # status: offline | loading | online | partial | error

    def __init__(self, manager: ModelServerManager):
        super().__init__()
        self._manager = manager
        self._timer = QTimer()
        self._timer.timeout.connect(self._check_health)
        self._timer.start(5000)  # 每5秒检查一次
        self._check_health()

    def _check_health(self):
        health = self._manager.get_health()
        self.set_status(health["status"])
```

### 6.4 向后兼容降级

如果 FastAPI 服务连接失败（`auto_start=False` 或服务未运行），检测到连接失败后：

1. 尝试直接 import 模型（兼容模式）
2. 对用户提示"模型服务未连接，使用兼容模式"

---

## 7. 依赖变更

新增依赖：
- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `sse-starlette`（流式响应）

---

## 8. 向后兼容性

- 所有现有 API 接口不变（`knowledge_base.search()`, `agent.chat()` 等）
- 内部实现从直接调用改为 HTTP 调用
- 配置项有默认值，现有用户无需修改配置即可运行
- `auto_start=False` 时完全兼容手动启动的模型服务

---

## 9. 实施批次

| Batch | 内容 | 涉及文件 |
|---|---|---|
| 1 | 项目骨架：FastAPI 应用、进程管理、路由注册 | `model_server/` 新建 |
| 2 | LLM 路由实现 + 客户端封装 | `model_server/routers/llm.py`, `models/client.py` |
| 3 | Embedder/Reranker 路由 + 客户端 | `model_server/routers/embed.py`, `rerank.py` |
| 4 | VLM 路由 + 健康检查端点 | `model_server/routers/vlm.py`, `health.py` |
| 5 | 主应用集成：进程启动/停止、状态指示灯 | `main_window.py`, `components.py` |
| 6 | 向后兼容降级逻辑 | `models/client.py` |
