# MBForge 参考资料索引

> 最后更新: 2026-06-04

本目录存放 MBForge 项目参考的外部项目、论文、文档和技术资料。

---

## 目录结构

```
ref/
├── INDEX.md              ← 本文件（总索引）
├── memvid.md             — 单文件 AI 记忆引擎（Smart Frames 架构）
├── harness-engineering.md — Agent Harness Engineering 综述（ETCLOVG 七层框架）
├── harness-systems.md    — Agent Systems with Harness Engineering（联合优化理论）
├── chematic.md           — 纯 Rust 化学信息学库（已在项目中集成）
└── wiki-app-notes.md     — 参考 Wiki 应用的提取管线设计笔记
```

---

## 参考资料清单

### 1. Memvid — 单文件 AI 记忆引擎
- **链接**: https://github.com/0xPlaygrounds/memvid
- **语言**: Rust (98.5%)
- **Stars**: 15.6K
- **核心创新**: 将 AI 记忆视为视频编码问题 — 追加写入、不可变 Smart Frames、单文件存储
- **与 MBForge 关系**: 单文件存储 + 追加写入 + HNSW 向量搜索的架构模式可参考
- **优先级**: P2（架构参考，非直接集成）
- **详情**: [memvid.md](memvid.md)

### 2. Agent Harness Engineering — 综述
- **链接**: https://openreview.net/forum?id=eONq7FdiHa
- **作者**: Junjie Li, Xi Xiao, et al.
- **类型**: 综述论文（170+ 开源项目映射）
- **核心创新**: ETCLOVG 七层分类法（执行环境、工具接口、上下文管理、生命周期/编排、可观测性、验证、治理）
- **与 MBForge 关系**: MBForge 的 Agent 架构可在 ETCLOVG 框架下审视和改进
- **优先级**: P1（架构评估框架）
- **详情**: [harness-engineering.md](harness-engineering.md)

### 3. Agent Systems with Harness Engineering
- **链接**: https://openreview.net/forum?id=nM5tDHrQsx
- **作者**: Xinyu Tang, Han Peng, et al.
- **类型**: 理论论文
- **核心创新**: Harness 与模型联合优化 — 记忆系统、技能库、多 Agent 编排
- **与 MBForge 关系**: MBForge 的 MemoryManager + SkillsManager + Agent 循环可对标此框架
- **优先级**: P1（理论指导）
- **详情**: [harness-systems.md](harness-systems.md)

### 4. Chematic — 纯 Rust 化学信息学库
- **链接**: https://github.com/kent-tokyo/chematic
- **语言**: Rust
- **许可**: Apache 2.0 + MIT
- **核心能力**: SMILES 解析、ECFP 指纹、VF2 子结构搜索、分子描述符、MCS、2D/3D
- **与 MBForge 关系**: 已集成（core/chem.rs），替代 Python RDKit sidecar
- **优先级**: P0（已集成，API 验证中）
- **详情**: [chematic.md](chematic.md)

### 5. 参考 Wiki 应用 — 提取管线设计
- **来源**: 用户提供的 Tauri v2 桌面 Wiki 应用
- **核心设计**: 多格式文件提取 → LLM 两阶段处理 → 文件变更监听 → 向量索引
- **与 MBForge 关系**: 文件缓存、提取队列、语义分块等模式已部分采纳
- **优先级**: 已参考实施
- **详情**: [wiki-app-notes.md](wiki-app-notes.md)

---

## 使用方式

每个 `.md` 文件包含：
- 资源概述和链接
- 核心技术要点
- 与 MBForge 的关联分析
- 可借鉴的具体设计模式
- 集成/参考的优先级和建议

---

## 引用格式

在代码注释或文档中引用时使用：
```
// 参考: ref/memvid.md — Smart Frames 追加写入模式
// 参考: ref/harness-engineering.md — ETCLOVG 七层框架
```
