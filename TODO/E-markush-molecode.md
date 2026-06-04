# Task E: 基于 MoleCode 的 Markush 计算增强

> 优先级: P1 · 难度: ★★★☆☆ · 工作量: 2-3 天 · 依赖: 无

## 目标

将 MoleCode 的缩写展开、名称归一化、Kekule 等价逻辑移植到 `markush.rs`，
提升 Markush 结构匹配的准确性和鲁棒性。

## 当前问题

| 能力 | MoleCode (Python) | markush.rs (Rust) |
|------|-------------------|-------------------|
| 缩写展开 | `{Boc}` → 7 原子子图（60+ 条目） | 无 |
| 名称归一化 | `R[1]`/`R1`/`R^1` 统一 | 无，大小写敏感 |
| Kekule 等价 | 芳香环交替键视为等价 | 无 |
| 双向比较 | A ≅ B（图同构） | A ⊆ B（单向） |

## 实现步骤

### E1: 移植 abbreviation_map（Rust）

- 新建 `src-tauri/src/core/abbreviation_map.rs`
- 移植 `SINGLE_ATOM_MAP`（25 条）：`Me`→`CH3`，`Et`→`CH2`，`F`→`F`...
- 移植 `SUBGRAPH_MAP`（60+ 条）：`Boc`→`OC(=O)C(C)(C)C`...
- 移植 `NON_EXPANDABLE`（80+ 条）：`R`，`R1`...`R17`，`X`，`Y`，`Z`...
- 数据结构：`HashMap<&str, AbbrevDef>`，`AbbrevDef` 为 `SingleAtom(&str)` 或 `Subgraph { atoms, bonds, attach }`

### E2: 移植 normalize_abbrev_name

- 在 `abbreviation_map.rs` 中实现 `normalize(name: &str) -> &str`
- 处理：`R[1]`→`R1`，`R^1`→`R1`，`OCH3`→`OMe`，`MeO`→`OMe`，`CO2H`→`COOH`
- 处理大小写：`boc`→`Boc`，`cbz`→`Cbz`

### E3: 增强 check_overlap

- 修改 `markush.rs` 的 `check_overlap()`
- 匹配前先对 R-group 名称调用 `normalize()`
- 如果 pattern 含缩写节点，尝试展开后再匹配
- 如果直接匹配失败，展开双方重试

### E4: 添加 Kekule 感知

- 在 `has_substructure()` 中添加芳香环检测
- 检测 5/6/7 元环中 `===`/`---` 交替模式
- 芳香环内的键视为等价（不区分单/双）

## 参考文件

- `ref/MoleCode/molecode/markush/abbreviation_map.py` — 缩写展开定义
- `ref/MoleCode/molecode/markush/graph.py` — `normalize_abbrev_name()`、`molecode_isomorphic()`
- `src-tauri/src/core/markush.rs` — 当前实现（1100+ 行）

## 验证

```bash
cargo test --lib -- core::markush --nocapture
# 新增测试：
# - test_abbrev_expand_boc: {Boc} 展开后与完整结构匹配
# - test_normalize_rgroup: R[1] 和 R1 归一化后相等
# - test_kekule_equivalent: 芳香环 Kekule 写法等价
# - test_bidirectional_isomorphism: 双向图同构
```
