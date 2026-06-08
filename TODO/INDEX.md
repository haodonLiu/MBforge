# MBForge 任务看板

## P0 — 进行中 / 阻塞

## P1 — 近期计划

## P2 — 中期计划

## P2 — 中期计划

## P3 — 远期 / 想法

## 已完成（本次会话）

- [x] 前端 API 彻底统一到单层（`api/tauri/*`）
- [x] Environment 页面添加"刷新模型环境"按钮（调用 `refresh_resolved_paths` + 自动重载模型列表）
- [x] 删除遗留顶层 API 文件（`http.ts`、`download.ts`、`moldet.ts`、`settings.ts`）
- [x] Rust/Python 模型路径扫描统一为 ENV 优先级顺序（MBFORGE → HF_HOME → MODELSCOPE → TORCH_HOME）
- [x] Python 侧改为优先读取 Rust 写入的 `resolved_paths.json`（单一真相源）
- [x] Rust 添加 `refresh_resolved_paths` Tauri command 供前端刷新调用
- [x] `resolved_paths.json` 缓存改为 mtime 感知，Rust 刷新后 Python 自动重读
