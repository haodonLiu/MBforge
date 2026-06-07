"""Empty placeholder router — kept so main.py's include_router doesn't break.

所有真实工具执行都已迁移到 Rust native（`src-tauri/src/core/agent/executor_rig.rs`
+ `arxiv_rig.rs`，通过 `rig_adapter.rs::assemble_rig_tool_vec` 注入到 rig agent）。
Python 端不再注册 Agent 工具。需要走网络的（如深度模型推理）由调用方在
自己的 router 里直接 HTTP 调用，不经过 Agent tool 接口。

如果未来要加新工具，建议：
- 能用 Rust 写的 → 加到 `executor_rig.rs` / `arxiv_rig.rs` 里再 rig-tool
- 必须用 Python 写（如深度模型）→ 在对应模块的 router 里直接暴露端点
  （如 `moldet.py` / `vlm.py`），调用方显式 import，不混进 Agent tool 接口
"""

from fastapi import APIRouter

router = APIRouter()
