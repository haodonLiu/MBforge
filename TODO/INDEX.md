# MBForge 任务看板

## P0 — 进行中 / 阻塞

## P1 — 近期计划

## P2 — 中期计划

## P2 — 中期计划

## P3 — 远期 / 想法

### 🔴 长期方案：MolDetect ONNX + 纯 Rust 推理

**目标**：消除 Python 依赖，将 MolDetect/MolDetv2/MolScribe 全部迁移到 Rust

**背景**：
- 当前架构：Rust → HTTP → Python sidecar → PyTorch 推理
- 问题：需要 Python 环境 + PyTorch (~2GB)，启动慢，内存占用高

**方案**：
1. **导出 ONNX 模型**（Python，一次性）
   - `coref_best.ckpt` → `moldetect_coref.onnx`
   - `moldetv2-doc.pt` → `moldetv2_doc.onnx`
   - `swin_base_char_aux_1m.pth` → `molscribe.onnx`

2. **Rust ONNX 推理**（使用 ort crate）
   ```toml
   [dependencies]
   ort = { version = "2.0", features = ["download-binaries", "cuda"] }
   ```

3. **需要迁移的组件**：
   - 预处理：图像缩放、归一化（OpenCV/image crate）⭐⭐
   - Tokenizer：CorefTokenizer（~2000 行）⭐⭐⭐⭐⭐
   - 后处理：BBox 操作、坐标转换 ⭐⭐⭐

**预期收益**：
- 启动时间：5-10s → <1s
- 内存占用：~2GB → ~500MB
- 推理速度：快 20-50%
- 部署：单一二进制，无 Python 依赖

**工作量**：~2500 行 Rust 代码

**许可证**：MIT（Copyright (c) 2023 Yujie Qian），可自由修改和分发，需保留版权声明

**优先级**：P3（长期，待核心功能稳定后实施）

## 已完成（本次会话）

- [x] 前端 API 彻底统一到单层（`api/tauri/*`）
- [x] Environment 页面添加"刷新模型环境"按钮（调用 `refresh_resolved_paths` + 自动重载模型列表）
- [x] 删除遗留顶层 API 文件（`http.ts`、`download.ts`、`moldet.ts`、`settings.ts`）
- [x] Rust/Python 模型路径扫描统一为 ENV 优先级顺序（MBFORGE → HF_HOME → MODELSCOPE → TORCH_HOME）
- [x] Python 侧改为优先读取 Rust 写入的 `resolved_paths.json`（单一真相源）
- [x] Rust 添加 `refresh_resolved_paths` Tauri command 供前端刷新调用
- [x] `resolved_paths.json` 缓存改为 mtime 感知，Rust 刷新后 Python 自动重读
