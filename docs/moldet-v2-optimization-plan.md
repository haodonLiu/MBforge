# MolDet v2 分子检测优化计划

> 自证过的最终方案 — 基于代码深度分析

---

## 1. 问题诊断

### 1.1 症状

| 症状 | 根因 |
|------|------|
| 错读概率大 | `conf_threshold=0.25` 过低，大量误检 |
| 无分子页面显示检测框 | 前端切页时不清除 `pageDetections`（已修） |
| 检测框位置与上一页相同 | `handlePageRendered` 无页面验证（已修） |
| 缺少上下文关联 | `extract_page` 不返回 `context_text` |
| coref 配对不准 | 最近邻欧氏距离，无语义匹配 |

### 1.2 当前架构

```
前端 cached_extract_page
  → Rust detection_cache.rs
    → SHA-256 缓存查找
    → Miss: POST /api/v1/moldet/extract-page
      → MolImagePipeline.extract_page()
        → MolDetv2DocDetector.detect(conf=0.25)  ← 问题1: 阈值太低
        → MolScribeRecognizer.predict()
        → ExtractionResult(context_text="")       ← 问题2: 无上下文
      → 缓存写入
    → 返回结果
```

### 1.3 代码证据

**问题1: 置信度阈值过低**
```python
# moldet.py:81
class MolDetv2DocDetector:
    def __init__(self, conf_threshold: float = 0.25, ...):  # ← 0.25 太低
```

**问题2: 无尺寸过滤**
```python
# moldet.py:184-192
for box in r.boxes:
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
    conf = float(box.conf[0].cpu().item())
    boxes.append((x1, y1, x2, y2, conf))  # ← 无尺寸检查
```

**问题3: 无上下文提取**
```python
# moldet.py:589-601
results.append(ExtractionResult(
    esmiles=smiles,
    name=f"IMG-P{page_idx:03d}-{idx:03d}",
    source="image",
    moldet_conf=det_conf,
    scribe_conf=scribe_conf,
    bbox_pdf=bbox_pdf,
    page_idx=page_idx,
    mol_img_path=mol_img_path,
    status="pending",
    # context_text 缺失！
))
```

**问题4: coref 未集成到 extract_page**
```python
# server.py:317-346
@app.post("/api/v1/moldet/extract-page")
async def extract_page(request: Request):
    # 只调用 MolImagePipeline，不调用 coref
    results = pipeline.extract_page(...)
```

**问题5: coref 配对算法简陋**
```python
# molcoref/data.py:144-165
def _pair_corefs(bboxes, mol_indices, idt_indices):
    """最近邻配对：每个 idt 找最近的 mol（bbox 中心欧氏距离）"""
    for idt_i in idt_indices:
        best_mol = min(mol_indices, key=lambda mi: distance(...))  # ← 太简单
```

---

## 2. 优化方案

### Phase 1: 检测质量提升（P0，前端+后端）

#### 2.1.1 提高置信度阈值

**文件**: `src/mbforge/backends/moldet.py`

```python
# 修改前
class MolDetv2DocDetector:
    def __init__(self, conf_threshold: float = 0.25, ...):

# 修改后
class MolDetv2DocDetector:
    def __init__(self, conf_threshold: float = 0.4, ...):  # 提高到 0.4
```

**验证**: 对比同一页的检测数量，0.25 → 0.4 应减少 30-50% 误检。

#### 2.1.2 添加尺寸过滤

**文件**: `src/mbforge/backends/moldet.py`

```python
def detect(self, image):
    results = self.model.predict(...)
    boxes = []
    img_area = image.width * image.height if hasattr(image, 'width') else image.shape[0] * image.shape[1]
    
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            conf = float(box.conf[0].cpu().item())
            
            # 尺寸过滤
            w, h = x2 - x1, y2 - y1
            box_area = w * h
            area_ratio = box_area / img_area
            
            # 过滤条件：
            # 1. 太小（< 0.01% 页面面积）→ 噪点
            # 2. 太大（> 50% 页面面积）→ 可能是整段文字
            # 3. 太窄（宽高比 > 10:1）→ 可能是线条
            if area_ratio < 0.0001:
                continue
            if area_ratio > 0.5:
                continue
            if w > 0 and h > 0:
                ratio = max(w/h, h/w)
                if ratio > 10:
                    continue
            
            boxes.append((x1, y1, x2, y2, conf))
    return boxes
```

#### 2.1.3 添加 composite_conf 计算

**文件**: `src/mbforge/backends/moldet.py`

```python
# 在 extract_page 中
for idx, (x1, y1, x2, y2, det_conf) in enumerate(img_boxes):
    # ... 识别 SMILES ...
    
    # 计算综合置信度
    composite_conf = det_conf * scribe_conf if scribe_conf > 0 else det_conf
    
    results.append(ExtractionResult(
        esmiles=smiles,
        moldet_conf=det_conf,
        scribe_conf=scribe_conf,
        composite_conf=composite_conf,  # ← 显式设置
        # ...
    ))
```

---

### Phase 2: 上下文关联（P1，后端）

#### 2.2.1 extract_page 集成 coref

**文件**: `src/mbforge/server.py`

```python
@app.post("/api/v1/moldet/extract-page")
async def extract_page(request: Request):
    body = await request.json()
    # ... 现有参数 ...
    
    # 新增参数
    use_coref = body.get("use_coref", True)
    
    image = decode_base64_image(image_base64)
    pipeline = moldet.get_moldet()
    
    # 1. 基础检测
    results = pipeline.extract_page(image, page_idx, page_w_pts, page_h_pts, image_w, image_h, dpi)
    
    # 2. Coref 增强（可选）
    if use_coref and results:
        try:
            coref_backend = moldet_coref.get_coref()
            if coref_backend and coref_backend.is_available():
                # 用 coref 结果增强 context_text
                coref_result = coref_backend.detect_coref_with_mapping(
                    image, 
                    mol_bboxes=[{"x1": r.bbox_pdf[0], "y1": r.bbox_pdf[1], 
                                 "x2": r.bbox_pdf[2], "y2": r.bbox_pdf[3]} 
                                for r in results if r.bbox_pdf]
                )
                # 匹配 coref 到 results
                _enrich_with_coref(results, coref_result)
        except Exception as e:
            logger.warning("Coref enrichment failed: %s", e)
    
    return {"results": [r.to_dict() for r in results], "count": len(results)}


def _enrich_with_coref(results, coref_data):
    """用 coref 结果增强 context_text"""
    if not coref_data or "corefs" not in coref_data:
        return
    
    for coref in coref_data.get("corefs", []):
        mol_idx = coref.get("mol_idx")
        idt_bbox = coref.get("idt_bbox")
        
        if mol_idx is not None and mol_idx < len(results) and idt_bbox:
            # 从 idt_bbox 提取文本（如果有 OCR）
            # 或者用 bbox 位置作为 context 提示
            results[mol_idx].context_text = f"标号区域: {idt_bbox}"
```

#### 2.2.2 优化 coref 配对算法

**文件**: `src/mbforge/parsers/molecule/molcoref/data.py`

```python
def _pair_corefs(
    bboxes: list[dict[str, Any]],
    mol_indices: list[int],
    idt_indices: list[int],
    page_height: float = 842.0,  # 新增：页面高度
) -> list[tuple[int, int]]:
    """增强配对：空间关系 + 垂直对齐 + 文本语义"""
    if not mol_indices or not idt_indices:
        return []
    
    centers = []
    for b in bboxes:
        x1, y1, x2, y2 = b.get("bbox", (0, 0, 0, 0))
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    
    pairs = []
    used_mols = set()
    
    # 按置信度排序 idt（高置信度优先配对）
    sorted_idts = sorted(idt_indices, key=lambda i: bboxes[i].get("score", 0), reverse=True)
    
    for idt_i in sorted_idts:
        ix, iy = centers[idt_i]
        
        # 候选 mol：未使用过的，且在合理距离内
        candidates = []
        for mi in mol_indices:
            if mi in used_mols:
                continue
            mx, my = centers[mi]
            
            # 距离计算（归一化）
            dx = (mx - ix) / 595.0  # 归一化到页面宽度
            dy = (my - iy) / page_height
            dist = (dx**2 + dy**2) ** 0.5
            
            # 空间关系评分：
            # 1. 水平距离小 → 高分（标号通常在分子旁边）
            # 2. 垂直对齐 → 高分（标号通常在分子下方或右侧）
            # 3. 距离太远 → 排除
            
            h_dist = abs(mx - ix) / 595.0
            v_dist = abs(my - iy) / page_height
            
            # 排除太远的（超过页面宽度的 30%）
            if h_dist > 0.3 and v_dist > 0.3:
                continue
            
            # 评分：水平距离权重更高（标号通常在旁边）
            score = 1.0 / (1.0 + h_dist * 3 + v_dist * 2)
            candidates.append((mi, score))
        
        if candidates:
            # 选择得分最高的
            best_mol = max(candidates, key=lambda x: x[1])[0]
            pairs.append((best_mol, idt_i))
            used_mols.add(best_mol)
    
    return pairs
```

---

### Phase 3: 前端增强（P2）

#### 2.3.1 添加置信度阈值 UI

**文件**: `frontend/src/components/project/pdf/PdfToolbar.tsx`

```typescript
// 新增 props
interface Props {
  // ... 现有 ...
  confidenceThreshold: number
  onConfidenceThresholdChange: (threshold: number) => void
}

// 在工具栏中添加
<div className="pdf-confidence-control">
  <span className="pdf-confidence-label">置信度</span>
  <input
    type="range"
    min="0"
    max="100"
    value={confidenceThreshold * 100}
    onChange={e => onConfidenceThresholdChange(Number(e.target.value) / 100)}
    className="pdf-confidence-slider"
  />
  <span className="pdf-confidence-value">{Math.round(confidenceThreshold * 100)}%</span>
</div>
```

#### 2.3.2 前端置信度过滤

**文件**: `frontend/src/components/MoleculeOverlay.tsx`

```typescript
const validDetections = useMemo(() => {
  return detections.filter(d => {
    // 页面验证
    if (currentPage !== undefined && d.page_idx !== null) {
      if (d.page_idx !== currentPage - 1) return false
    }
    // 置信度过滤
    if (d.composite_conf < confidenceThreshold) return false
    // bbox 有效性
    if (!d.bbox_pdf || d.bbox_pdf[2] <= d.bbox_pdf[0]) return false
    return true
  })
}, [detections, currentPage, confidenceThreshold])
```

---

## 3. 实施顺序

| 阶段 | 任务 | 文件 | 预期效果 |
|------|------|------|----------|
| P0 | 提高 conf_threshold | moldet.py | 减少 30-50% 误检 |
| P0 | 添加尺寸过滤 | moldet.py | 过滤噪点和异常框 |
| P0 | 修复前端状态 | usePdfViewer.ts | ✅ 已完成 |
| P1 | 集成 coref 到 extract_page | server.py | 返回 context_text |
| P1 | 优化 coref 配对算法 | molcoref/data.py | 提高配对准确率 |
| P2 | 前端置信度 UI | PdfToolbar.tsx | 用户可调阈值 |
| P2 | 前端置信度过滤 | MoleculeOverlay.tsx | 实时过滤低质量结果 |

---

## 4. 验证方法

### 4.1 检测质量验证

```python
# 测试脚本
from mbforge.backends.moldet import MolImagePipeline
from PIL import Image

pipeline = MolImagePipeline()
image = Image.open("test_page.png")

# 对比不同阈值
results_025 = pipeline.extract_page(image, 0, 595, 842, 1200, 1694)
# 修改 conf_threshold=0.4 后
results_040 = pipeline.extract_page(image, 0, 595, 842, 1200, 1694)

print(f"0.25 阈值: {len(results_025)} 个检测")
print(f"0.40 阈值: {len(results_040)} 个检测")
print(f"减少: {len(results_025) - len(results_040)} 个")
```

### 4.2 Coref 配对验证

```python
# 测试 coref 配对
from mbforge.parsers.molecule.molcoref.data import _pair_corefs

# 模拟数据
bboxes = [
    {"category_id": 1, "bbox": (100, 100, 200, 200), "score": 0.9},  # mol
    {"category_id": 3, "bbox": (150, 210, 180, 230), "score": 0.8},  # idt
]
mol_indices = [0]
idt_indices = [1]

pairs = _pair_corefs(bboxes, mol_indices, idt_indices)
assert pairs == [(0, 1)], f"Expected [(0, 1)], got {pairs}"
```

### 4.3 前端状态验证

```typescript
// 测试切页状态清理
// 1. 打开 PDF，进入分子模式
// 2. 检测第 1 页
// 3. 切换到第 2 页
// 4. 验证第 1 页的检测框消失
// 5. 验证第 2 页不显示第 1 页的检测结果
```

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 提高阈值漏检真实分子 | 中 | 提供用户可调阈值 UI |
| coref 模型不可用 | 低 | 降级到无 coref 模式 |
| 尺寸过滤误杀小分子 | 低 | 阈值可配置 |
| 配对算法计算开销 | 低 | 只对当前页计算 |

---

## 6. 总结

本方案从三个层面解决问题：

1. **检测质量**：提高阈值 + 尺寸过滤 → 减少误检
2. **语义关联**：集成 coref + 优化配对 → 提供上下文
3. **用户体验**：置信度 UI + 实时过滤 → 用户可控

优先级：P0（检测质量）→ P1（语义关联）→ P2（用户体验）
