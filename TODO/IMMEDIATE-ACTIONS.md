# MBForge 立即行动清单（本周开始）

> **创建日期**: 2026-07-10  
> **适用对象**: 核心开发者、贡献者  
> **目标**: Phase 0 第一周（2026-07-10 ~ 07-17）立即启动的任务

---

## 优先级说明

本文档只包含 **本周必须启动** 的任务。完整 6 周计划见 `TODO/PHASE0-ROADMAP.md`。

---

## Week 1 任务列表（2026-07-10 ~ 07-17）

### 🔴 P0-1: Pipeline 集成测试（3 天，最高优先级）

**负责人**: TBD  
**截止日期**: 2026-07-13  

#### 任务描述
编写完整的 9-stage pipeline 集成测试，确保每个阶段输出符合预期。

#### 具体工作
```python
# tests/integration/test_pipeline_flow.py
def test_full_pipeline_with_5page_pdf(tmp_path):
    """
    完整 9-stage 流程测试（extract → density → rough_md → detect 
    → insert_molecode → reorganize → pageindex → wiki → persist_mols 
    → register_links → persist）
    """
    # 1. 准备 fixture PDF（5 页，包含 2-3 个分子结构图）
    fixture_pdf = "tests/fixtures/sample_5pg.pdf"
    library_root = tmp_path / "library"
    library_root.mkdir()
    
    # 2. 运行 pipeline
    result = run_pipeline(
        fixture_pdf, 
        str(library_root), 
        doc_id="test_doc"
    )
    
    # 3. 验证基础输出
    assert result.page_count == 5
    assert result.indexed_count == 1
    assert result.duration_ms > 0
    
    # 4. 验证数据库写入
    db = DatabaseManager.get(str(library_root))
    docs = db.execute("SELECT * FROM documents WHERE doc_id=?", ["test_doc"])
    assert len(docs) == 1
    
    mols = db.execute("SELECT * FROM molecules WHERE doc_id=?", ["test_doc"])
    assert len(mols) >= 2  # 至少检出 2 个分子
    
    # 5. 验证文件生成
    assert (library_root / "storage" / "test_doc" / "reorganized.md").exists()
    assert (library_root / "storage" / "test_doc" / "source.pdf").exists()
    
    # 6. 验证 OpenKB 索引
    adapter = OpenKBAdapter(library_root)
    search_result = adapter.search("test query", top_k=1)
    assert len(search_result) > 0
```

#### 验收标准
- [ ] 测试通过（`pytest tests/integration/test_pipeline_flow.py -v`）
- [ ] 执行时间 <3 分钟（首次模型下载除外）
- [ ] 数据库、文件系统、OpenKB 三层验证都通过

---

### 🔴 P0-2: Pipeline 单元测试（extract_molecules + normalize）（2 天）

**负责人**: TBD  
**截止日期**: 2026-07-15

#### 任务 A: extract_molecules 单元测试
```python
# tests/unit/pipeline/test_extract_molecules.py

def test_extract_molecules_from_pdf_mock_backends(tmp_path, monkeypatch):
    """Mock MolDet/MolScribe 后端，验证输出结构"""
    # Mock 实现省略，见完整版
    pass
```

#### 任务 B: normalize 单元测试
```python
# tests/unit/pipeline/test_normalize.py

def test_normalize_molecules_dedup():
    """测试 RDKit 规范化 + 去重逻辑"""
    candidates = [
        ExtractionResult(esmiles="CCO", source="text", status="pending"),
        ExtractionResult(esmiles="OCC", source="text", status="pending"),
        # ... 更多测试用例
    ]
    
    normalized = normalize_molecules(candidates)
    unique_valid = [m for m in normalized if m.status == "accepted"]
    assert len(unique_valid) == 2
```

#### 验收标准
- [ ] 两个测试文件都通过
- [ ] Mock 不依赖真实模型加载（执行时间 <10 秒）

---

### 🟡 P0-3: Core 模块测试（database.py）（2 天）

**负责人**: TBD  
**截止日期**: 2026-07-16

#### 任务描述
测试数据库 CRUD + 事务一致性。

```python
# tests/unit/core/test_database.py

def test_transaction_rollback(tmp_path):
    """事务回滚测试（关键！）"""
    db = DatabaseManager.get(str(tmp_path))
    
    with pytest.raises(Exception):
        with db.transaction():
            db.execute("INSERT INTO documents ...")
            raise Exception("Simulated failure")
    
    # 验证：回滚后数据库无脏数据
    docs = db.execute("SELECT * FROM documents WHERE doc_id=?", ["test_doc"])
    assert len(docs) == 0
```

#### 注意事项
- 当前 `core/database.py` **可能没有** `transaction()` context manager，需要先实现

#### 验收标准
- [ ] CRUD 测试通过
- [ ] 事务回滚测试通过（这是 C-8 的核心）

---

### 🟡 P0-4: Router Smoke Tests 生成脚本（1 天）

**负责人**: TBD  
**截止日期**: 2026-07-14

#### 实现方案
```python
# tests/unit/test_routers_smoke.py

ROUTES = [
    ("/api/v1/health", "GET", 200),
    ("/api/v1/documents/list", "GET", 200),
    ("/api/v1/kb/search", "POST", 422),
    # ... 自动生成其余 16 个
]

@pytest.mark.parametrize("endpoint,method,expected_status", ROUTES)
def test_router_responds(endpoint, method, expected_status):
    if method == "GET":
        response = client.get(endpoint)
    else:
        response = client.post(endpoint, json={})
    assert response.status_code == expected_status
```

#### 验收标准
- [ ] `pytest tests/unit/test_routers_smoke.py -v` 通过
- [ ] 执行时间 <30 秒

---

## Week 1 验收检查表

### 代码质量
- [ ] 测试覆盖率从 ~5% 提升到 ≥15%
- [ ] CI 通过（GitHub Actions: tests + lint）

### 可交付物
- [ ] `tests/integration/test_pipeline_flow.py`
- [ ] `tests/unit/pipeline/test_extract_molecules.py`
- [ ] `tests/unit/pipeline/test_normalize.py`
- [ ] `tests/unit/core/test_database.py`
- [ ] `tests/unit/test_routers_smoke.py`

---

## 并行任务建议

| 任务 | 依赖 | 优先级 | 预计工时 |
|------|------|--------|---------|
| P0-4: Router smoke tests | 独立 | 最高 | 1 天 |
| P0-3: database 测试 | 需实现 transaction() | 高 | 2 天 |
| P0-2: pipeline 单元测试 | 需 Mock 技巧 | 高 | 2 天 |
| P0-1: pipeline 集成测试 | 依赖 fixture PDF | 中 | 3 天 |

**建议顺序**（如果单人）：P0-4 → P0-3 → P0-2 → P0-1

---

## Week 2 预告（2026-07-17 ~ 07-24）

Week 1 完成后，立即启动：

1. **错误处理改进**（C-7）
   - StageResult 标准化
   - SSE error events
   - 前端错误展示

2. **数据一致性**（C-8）
   - Pipeline 使用 `transaction()`
   - doc_id 冲突处理

详见 `TODO/PHASE0-ROADMAP.md` Week 2 章节。

---

## 总结

**本周目标**：启动测试覆盖 + 为 Week 2 错误处理做准备。

**关键产出**：
- 5 个测试文件
- 测试覆盖率 ≥15%
- `transaction()` context manager 实现

开始行动！🚀
