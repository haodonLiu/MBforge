# MBForge 模型服务化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有模型推理分离到独立 FastAPI 进程，主应用启动不等待模型加载，通过 HTTP 客户端调用模型服务，UI 状态指示灯实时反映模型状态。

**Architecture:** 单 FastAPI 进程管理所有模型（LLM/Embedder/Reranker/VLM），主应用通过 httpx 异步 HTTP 调用。进程由主应用 fork 管理，UI 轮询 /health 更新状态。

**Tech Stack:** FastAPI, uvicorn, httpx, sse-starlette, PyQt6

---

## 目录结构

```
src/mbforge/
├── model_server/                    # [新建]
│   ├── __init__.py
│   ├── main.py                     # FastAPI app 入口
│   ├── process_manager.py          # 子进程管理
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── llm.py                 # /api/v1/llm/*
│   │   ├── embed.py               # /api/v1/embed
│   │   ├── rerank.py              # /api/v1/rerank
│   │   ├── vlm.py                 # /api/v1/vlm/*
│   │   └── health.py              # /api/v1/health
│   └── models/
│       ├── __init__.py
│       ├── llm.py                 # LLM 模型加载/推理
│       ├── embedder.py            # Embedder 模型加载/推理
│       ├── reranker.py            # Reranker 模型加载/推理
│       └── vlm.py                 # VLM 模型加载/推理
├── models/
│   └── client.py                  # [新建] HTTP 客户端封装
└── utils/
    └── config.py                  # [修改] 新增 ModelServerConfig
```

---

## Batch 1: 项目骨架

### Task 1: 新建 model_server 目录结构和 `__init__.py`

**Files:**
- Create: `src/mbforge/model_server/__init__.py`

```python
"""MBForge 模型服务进程."""

__version__ = "1.0.0"
```

- [ ] **Step 1: Create directory and `__init__.py`**
- [ ] **Step 2: Commit**

```bash
mkdir -p src/mbforge/model_server/routers src/mbforge/model_server/models
touch src/mbforge/model_server/__init__.py
touch src/mbforge/model_server/routers/__init__.py
touch src/mbforge/model_server/models/__init__.py
git add src/mbforge/model_server/
git commit -m "feat(model_server): create model_server package skeleton"
```

---

### Task 2: 新增 `ModelServerConfig` 到 `config.py`

**Files:**
- Modify: `src/mbforge/utils/config.py`

在 `OcrConfig` 之后、`AppConfig` 之前添加：

```python
@dataclass
class ModelServerConfig:
    """模型服务进程配置."""

    host: str = "127.0.0.1"
    port: int = 18792
    auto_start: bool = True
    startup_timeout: int = 120
    health_check_interval: int = 5
```

在 `AppConfig` 中添加字段：

```python
@dataclass
class AppConfig:
    model_server: ModelServerConfig = field(default_factory=ModelServerConfig)
    # ... 现有字段保持不变 ...
```

在 `AppConfig.to_dict()` 和 `AppConfig.from_dict()` 中处理新字段：

在 `to_dict()` 的 `return asdict(self)` 前添加：
```python
# 手动处理以支持新增字段
result = {
    "llm": asdict(self.llm),
    "embed": asdict(self.embed),
    "rerank": asdict(self.rerank),
    "vlm": asdict(self.vlm),
    "ocr": asdict(self.ocr),
    "recent_projects": self.recent_projects,
    "theme": self.theme,
    "language": self.language,
    "model_server": asdict(self.model_server),
}
return result
```

在 `from_dict()` 中添加：
```python
model_server=ModelServerConfig(**data.get("model_server", {})),
```

- [ ] **Step 1: Read `config.py` to find exact line numbers**
- [ ] **Step 2: Add `ModelServerConfig` dataclass**
- [ ] **Step 3: Add `model_server` field to `AppConfig`**
- [ ] **Step 4: Update `to_dict()` and `from_dict()`**
- [ ] **Step 5: Commit**

```bash
git add src/mbforge/utils/config.py
git commit -m "feat(config): add ModelServerConfig"
```

---

### Task 3: 新建 `process_manager.py`

**Files:**
- Create: `src/mbforge/model_server/process_manager.py`

```python
"""模型服务子进程管理."""

from __future__ import annotations

import asyncio
import sys
import subprocess
import time
from typing import Optional

import httpx


class ModelServerManager:
    """管理 FastAPI 模型服务子进程."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18792, startup_timeout: int = 120):
        self.host = host
        self.port = port
        self.startup_timeout = startup_timeout
        self._process: Optional[subprocess.Popen] = None
        self._base_url = f"http://{host}:{port}"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """启动 FastAPI 子进程并等待就绪."""
        if self.is_running:
            return

        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mbforge.model_server.main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
                "--workers",
                "1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待服务就绪
        self._wait_ready()

    def _wait_ready(self) -> None:
        """轮询 /health 直到服务就绪或超时."""
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._process is not None and self._process.poll() is not None:
                # 进程已退出
                return
            try:
                resp = httpx.get(f"{self._base_url}/api/v1/health", timeout=2.0)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(1.0)

    def stop(self) -> None:
        """停止 FastAPI 子进程."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None

    async def get_health_async(self) -> dict:
        """异步查询健康状态."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/v1/health")
                return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_health(self) -> dict:
        """同步查询健康状态."""
        try:
            resp = httpx.get(f"{self._base_url}/api/v1/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/process_manager.py
git commit -m "feat(model_server): add process manager for subprocess control"
```

---

### Task 4: 新建 FastAPI `main.py` 骨架

**Files:**
- Create: `src/mbforge/model_server/main.py`

```python
"""FastAPI 模型服务入口."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import llm, embed, rerank, vlm, health

app = FastAPI(title="MBForge Model Server", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(llm.router, prefix="/api/v1/llm", tags=["llm"])
app.include_router(embed.router, prefix="/api/v1", tags=["embed"])
app.include_router(rerank.router, prefix="/api/v1", tags=["rerank"])
app.include_router(vlm.router, prefix="/api/v1/vlm", tags=["vlm"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/main.py
git commit -m "feat(model_server): add FastAPI app skeleton with route registration"
```

---

### Task 5: 新建 health 路由（存根）

**Files:**
- Create: `src/mbforge/model_server/routers/health.py`

```python
"""健康检查路由."""

from fastapi import APIRouter

router = APIRouter()

_model_status = {
    "llm": "loading",
    "embedder": "loading",
    "reranker": "loading",
    "vlm": "loading",
}


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "loading",
        "models": _model_status,
        "error": None,
    }


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/routers/health.py
git commit -m "feat(model_server): add health check route stub"
```

---

## Batch 2: LLM 路由 + 客户端封装

### Task 6: LLM 模型加载器（服务进程内）

**Files:**
- Create: `src/mbforge/model_server/models/llm.py`

```python
"""LLM 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from ....models.base import Message, StreamChunk
from ....models.llm import create_llm_from_config
from ....utils.config import ModelConfig

_llm_instance: Any = None


def get_llm(config: ModelConfig) -> Any:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = create_llm_from_config(config)
    return _llm_instance


def reset_llm() -> None:
    global _llm_instance
    _llm_instance = None
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/models/llm.py
git commit -m "feat(model_server): add LLM model loader for server process"
```

---

### Task 7: LLM 路由

**Files:**
- Create: `src/mbforge/model_server/routers/llm.py`

```python
"""LLM 推理路由."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ....models.base import Message
from ..models.llm import get_llm
from .health import set_model_status

router = APIRouter()


@router.post("/chat")
async def chat(request: Request) -> dict:
    try:
        body = await request.json()
        messages = [Message(**m) for m in body.get("messages", [])]
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)

        llm = get_llm(None)  # 使用默认配置
        result = llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
        set_model_status("llm", "ready")
        return {"content": result, "finish_reason": "stop"}
    except Exception as e:
        set_model_status("llm", "error")
        return {"content": "", "finish_reason": "error", "error": str(e)}


@router.post("/chat-stream")
async def chat_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            body = await request.json()
            messages = [Message(**m) for m in body.get("messages", [])]
            temperature = body.get("temperature", 0.7)
            max_tokens = body.get("max_tokens", 4096)

            llm = get_llm(None)
            for chunk in llm.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield f"data: {json.dumps({'delta': chunk.delta, 'finish_reason': chunk.finish_reason})}\n\n"
            set_model_status("llm", "ready")
        except Exception as e:
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/routers/llm.py
git commit -m "feat(model_server): add LLM chat and chat-stream routes"
```

---

### Task 8: LLM HTTP 客户端

**Files:**
- Create: `src/mbforge/models/client.py`

```python
"""模型服务 HTTP 客户端（替代直接模型调用）."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from .base import Message, StreamChunk


class LLMClient:
    """LLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def chat(self, messages: list[Message], **kwargs) -> str:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        resp = await self._client.post(f"{self.base_url}/api/v1/llm/chat", json=payload)
        data = resp.json()
        return data.get("content", "")

    async def chat_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[StreamChunk]:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        async with self._client.stream("POST", f"{self.base_url}/api/v1/llm/chat-stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    d = json.loads(line[6:])
                    yield StreamChunk(delta=d.get("delta", ""), finish_reason=d.get("finish_reason"))

    async def aclose(self) -> None:
        await self._client.aclose()


class EmbedClient:
    """Embedder HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        payload = {"texts": texts, "model": kwargs.get("model", "sentence_transformers")}
        resp = await self._client.post(f"{self.base_url}/api/v1/embed", json=payload)
        return resp.json().get("embeddings", [])

    async def aclose(self) -> None:
        await self._client.aclose()


class RerankClient:
    """Reranker HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def rerank(self, query: str, passages: list[str], top_n: int = 5, **kwargs) -> list[tuple[int, float]]:
        payload = {
            "query": query,
            "passages": passages,
            "top_n": top_n,
            "model": kwargs.get("model", "sentence_transformers"),
        }
        resp = await self._client.post(f"{self.base_url}/api/v1/rerank", json=payload)
        results = resp.json().get("results", [])
        return [(r["index"], r["score"]) for r in results]

    async def aclose(self) -> None:
        await self._client.aclose()


class VLMClient:
    """VLM HTTP 客户端."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def describe(self, image_base64: str, prompt: str = "", **kwargs) -> str:
        payload = {"image_base64": image_base64, "prompt": prompt}
        resp = await self._client.post(f"{self.base_url}/api/v1/vlm/describe", json=payload)
        return resp.json().get("description", "")

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 1: Write the file**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/models/client.py
git commit -m "feat(models): add HTTP client wrappers for model server"
```

---

## Batch 3: Embedder / Reranker 路由

### Task 9: Embedder 模型加载器 + 路由

**Files:**
- Create: `src/mbforge/model_server/models/embedder.py`
- Create: `src/mbforge/model_server/routers/embed.py`

embedder.py:
```python
"""Embedder 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from ....models.embedding import create_embedder_from_config
from ....utils.config import EmbedConfig

_embedder_instance: Any = None


def get_embedder(config: EmbedConfig | None = None) -> Any:
    global _embedder_instance
    if _embedder_instance is None:
        from ....utils.config import load_global_config
        cfg = config or load_global_config().embed
        _embedder_instance = create_embedder_from_config(cfg)
    return _embedder_instance


def reset_embedder() -> None:
    global _embedder_instance
    _embedder_instance = None
```

embed.py:
```python
"""Embedder 推理路由."""

from fastapi import APIRouter, Request

from ..models.embedder import get_embedder
from .health import set_model_status

router = APIRouter()


@router.post("/embed")
async def embed(request: Request) -> dict:
    try:
        body = await request.json()
        texts = body.get("texts", [])
        if isinstance(texts, str):
            texts = [texts]

        embedder = get_embedder()
        embeddings = embedder.embed(texts)
        set_model_status("embedder", "ready")
        return {"embeddings": embeddings}
    except Exception as e:
        set_model_status("embedder", "error")
        return {"embeddings": [], "error": str(e)}
```

- [ ] **Step 1: Write both files**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/models/embedder.py src/mbforge/model_server/routers/embed.py
git commit -m "feat(model_server): add embedder model loader and route"
```

---

### Task 10: Reranker 模型加载器 + 路由

**Files:**
- Create: `src/mbforge/model_server/models/reranker.py`
- Create: `src/mbforge/model_server/routers/rerank.py`

reranker.py:
```python
"""Reranker 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from ....models.rerank import create_reranker_from_config
from ....utils.config import RerankConfig

_reranker_instance: Any = None


def get_reranker(config: RerankConfig | None = None) -> Any:
    global _reranker_instance
    if _reranker_instance is None:
        from ....utils.config import load_global_config
        cfg = config or load_global_config().rerank
        _reranker_instance = create_reranker_from_config(cfg)
    return _reranker_instance


def reset_reranker() -> None:
    global _reranker_instance
    _reranker_instance = None
```

rerank.py:
```python
"""Reranker 推理路由."""

from fastapi import APIRouter, Request

from ..models.reranker import get_reranker
from .health import set_model_status

router = APIRouter()


@router.post("/rerank")
async def rerank(request: Request) -> dict:
    try:
        body = await request.json()
        query = body.get("query", "")
        passages = body.get("passages", [])
        top_n = body.get("top_n", 5)

        reranker = get_reranker()
        results = reranker.rerank(query, passages)
        # results: list of (index, score), take top N
        top_results = sorted(results, key=lambda x: x[1], reverse=True)[:top_n]
        set_model_status("reranker", "ready")
        return {"results": [{"index": idx, "score": score} for idx, score in top_results]}
    except Exception as e:
        set_model_status("reranker", "error")
        return {"results": [], "error": str(e)}
```

- [ ] **Step 1: Write both files**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/models/reranker.py src/mbforge/model_server/routers/rerank.py
git commit -m "feat(model_server): add reranker model loader and route"
```

---

## Batch 4: VLM 路由 + 健康检查完善

### Task 11: VLM 模型加载器 + 路由

**Files:**
- Create: `src/mbforge/model_server/models/vlm.py`
- Create: `src/mbforge/model_server/routers/vlm.py`

vlm.py:
```python
"""VLM 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from ....models.vlm import create_vlm_from_config

_vlm_instance: Any = None


def get_vlm() -> Any:
    global _vlm_instance
    if _vlm_instance is None:
        from ....utils.config import load_global_config
        cfg = load_global_config().vlm
        _vlm_instance = create_vlm_from_config(cfg)
    return _vlm_instance


def reset_vlm() -> None:
    global _vlm_instance
    _vlm_instance = None
```

vlm.py (router):
```python
"""VLM 推理路由."""

from fastapi import APIRouter, Request

from ..models.vlm import get_vlm
from .health import set_model_status

router = APIRouter()


@router.post("/describe")
async def describe(request: Request) -> dict:
    try:
        body = await request.json()
        image_base64 = body.get("image_base64", "")
        prompt = body.get("prompt", "")

        vlm = get_vlm()
        description = vlm.describe_image(image_base64, prompt=prompt)
        set_model_status("vlm", "ready")
        return {"description": description}
    except Exception as e:
        set_model_status("vlm", "error")
        return {"description": "", "error": str(e)}
```

- [ ] **Step 1: Write both files**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/models/vlm.py src/mbforge/model_server/routers/vlm.py
git commit -m "feat(model_server): add VLM model loader and route"
```

---

### Task 12: 完善健康检查路由

**Files:**
- Modify: `src/mbforge/model_server/routers/health.py`

将存根替换为完整的健康检查实现：

```python
"""健康检查路由."""

from fastapi import APIRouter

from ..models.llm import get_llm, reset_llm
from ..models.embedder import get_embedder, reset_embedder
from ..models.reranker import get_reranker, reset_reranker
from ..models.vlm import get_vlm, reset_vlm

router = APIRouter()

_model_status = {
    "llm": "loading",
    "embedder": "loading",
    "reranker": "loading",
    "vlm": "loading",
}


@router.get("/health")
async def health_check() -> dict:
    # 尝试初始化各模型（触发懒加载）
    try:
        get_llm()
        _model_status["llm"] = "ready"
    except Exception:
        _model_status["llm"] = "error"

    try:
        get_embedder()
        _model_status["embedder"] = "ready"
    except Exception:
        _model_status["embedder"] = "error"

    try:
        get_reranker()
        _model_status["reranker"] = "ready"
    except Exception:
        _model_status["reranker"] = "error"

    try:
        get_vlm()
        _model_status["vlm"] = "ready"
    except Exception:
        _model_status["vlm"] = "error"

    statuses = list(_model_status.values())
    if all(s == "ready" for s in statuses):
        overall = "online"
    elif any(s == "ready" for s in statuses):
        overall = "partial"
    elif any(s == "error" for s in statuses):
        overall = "error"
    else:
        overall = "loading"

    return {
        "status": overall,
        "models": dict(_model_status),
        "error": None,
    }


def set_model_status(name: str, status: str) -> None:
    _model_status[name] = status
```

- [ ] **Step 1: Replace health.py with complete implementation**
- [ ] **Step 2: Commit**

```bash
git add src/mbforge/model_server/routers/health.py
git commit -m "feat(model_server): implement full health check with lazy model initialization"
```

---

## Batch 5: 主应用集成

### Task 13: 集成 `ModelServerManager` 到 `MainWindow`

**Files:**
- Modify: `src/mbforge/ui/main_window.py`

在 `MainWindow.__init__` 中：
1. 导入 `ModelServerManager`
2. 创建 `self._server_manager`
3. 如果 `config.model_server.auto_start` 为 True，启动服务
4. 更新 `ServiceStatusIndicator` 使用 manager

在 `MainWindow.closeEvent` 中：
1. 调用 `self._server_manager.stop()`

在 `MainWindow._start_model_worker` 中：
1. 改为调用 `self._server_manager.start()` 并等待就绪
2. 而不是直接加载模型

具体修改：

在 `__init__` 中添加（在 `self._models_ready = False` 后）：
```python
from ..model_server.process_manager import ModelServerManager

config = load_global_config()
self._server_manager = ModelServerManager(
    host=config.model_server.host,
    port=config.model_server.port,
    startup_timeout=config.model_server.startup_timeout,
)
if config.model_server.auto_start:
    self._server_manager.start()
```

在 `closeEvent` 中添加：
```python
if hasattr(self, "_server_manager"):
    self._server_manager.stop()
```

- [ ] **Step 1: Read main_window.py to find exact insertion points**
- [ ] **Step 2: Add imports and server manager initialization**
- [ ] **Step 3: Add stop() call in closeEvent**
- [ ] **Step 4: Commit**

```bash
git add src/mbforge/ui/main_window.py
git commit -m "feat(main_window): integrate ModelServerManager for subprocess control"
```

---

### Task 14: 改造 `ServiceStatusIndicator` 轮询健康状态

**Files:**
- Modify: `src/mbforge/ui/panels/status_indicator.py`

将现有的 `ServiceStatusIndicator` 改为接受 `ModelServerManager` 并定期轮询 `/health`：

```python
class ServiceStatusIndicator(QWidget):
    """服务状态指示器，轮询模型服务健康状态."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(8)

        self._indicators: dict[str, QLabel] = {}
        labels = ["LLM", "Embedding", "Reranker", "VLM"]
        for label in labels:
            lbl = QLabel(label)
            dot = QLabel("●")
            dot.setStyleSheet("color: gray; font-size: 10px;")
            self._layout.addWidget(dot)
            self._layout.addWidget(lbl)
            self._indicators[label.lower()] = dot

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_health)
        self._timer.start(5000)
        self._check_health()

    def _check_health(self):
        if self._manager is None:
            return
        health = self._manager.get_health()
        status = health.get("status", "error")
        color = {"online": "green", "partial": "yellow", "loading": "gray", "error": "red"}.get(status, "gray")
        for name, dot in self._indicators.items():
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
```

- [ ] **Step 1: Read status_indicator.py**
- [ ] **Step 2: Replace the class with health-polling version**
- [ ] **Step 3: Commit**

```bash
git add src/mbforge/ui/panels/status_indicator.py
git commit -m "feat(ui): ServiceStatusIndicator polls /health for model server status"
```

---

## Batch 6: 向后兼容降级

### Task 15: 客户端降级逻辑

**Files:**
- Modify: `src/mbforge/models/client.py`

添加连接失败时自动降级到直接模型调用的逻辑：

```python
class ModelClientFactory:
    """工厂类：根据连接状态返回 HTTP 客户端或直接模型实例."""

    def __init__(self, base_url: str = "http://127.0.0.1:18792"):
        self.base_url = base_url
        self._http_available: bool | None = None
        self._llm_client = LLMClient(base_url)
        self._embed_client = EmbedClient(base_url)
        self._rerank_client = RerankClient(base_url)
        self._vlm_client = VLMClient(base_url)

    def _check_http(self) -> bool:
        if self._http_available is not None:
            return self._http_available
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/health", timeout=2.0)
            self._http_available = resp.status_code == 200
        except Exception:
            self._http_available = False
        return self._http_available

    def get_llm(self):
        if self._check_http():
            return self._llm_client
        # 降级到直接实例
        from .llm import create_llm_from_config
        from ..utils.config import load_global_config
        return create_llm_from_config(load_global_config().llm)
```

- [ ] **Step 1: Read the existing client.py**
- [ ] **Step 2: Add ModelClientFactory class**
- [ ] **Step 3: Commit**

```bash
git add src/mbforge/models/client.py
git commit -m "feat(models): add ModelClientFactory with fallback to direct model calls"
```

---

## 最终验收

- [ ] FastAPI 服务独立启动：`python -m uvicorn mbforge.model_server.main:app --port 18792`
- [ ] `GET /api/v1/health` 返回正确的 JSON 格式
- [ ] `POST /api/v1/llm/chat` 返回 LLM 推理结果
- [ ] `POST /api/v1/embed` 返回嵌入向量
- [ ] `POST /api/v1/rerank` 返回重排结果
- [ ] `mbforge gui` 启动不等待模型，主应用立即就绪
- [ ] 状态指示灯轮询 `/health` 并更新颜色
- [ ] 关闭 MBForge 时 FastAPI 子进程被正确终止
- [ ] `ruff check` 通过
