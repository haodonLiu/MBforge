# PDF 查看器前端 API 接口文档

> 完整的前端 PDF 功能所需 API 及后端实现需求

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript)                                  │
│  ├── PdfViewer.tsx          主容器                              │
│  ├── PdfToolbar.tsx         顶部工具栏（模式切换 + 工具）       │
│  ├── PdfFloatingControls.tsx 底部浮动控件（翻页 + 缩放）        │
│  ├── PdfResultPane.tsx      右侧识别结果面板（虚拟滚动）        │
│  ├── PdfContinuousViewer.tsx 连续滚动 PDF 查看器               │
│  ├── MoleculeOverlay.tsx    分子检测框叠加层                    │
│  └── usePdfViewer.ts        状态管理 Hook                       │
├─────────────────────────────────────────────────────────────────┤
│  Tauri IPC (Rust)                                               │
│  ├── detection_cache.rs     分子检测缓存                        │
│  ├── pdf.rs                 PDF 解析命令                        │
│  └── sidecar.rs             Sidecar 管理                       │
├─────────────────────────────────────────────────────────────────┤
│  Python Sidecar (FastAPI)                                       │
│  ├── /api/v1/moldet/extract-page  分子检测                     │
│  ├── /api/v1/moldet/coref         分子-标号共指消解             │
│  ├── /api/v1/molscribe            SMILES 识别                  │
│  └── /api/v1/health               健康检查                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Tauri IPC 命令（Rust）

### 2.1 分子检测缓存

| 命令名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `cached_extract_page` | projectRoot, docId, page, imageBase64, pageWPts, pageHPts, imageW, imageH, force | CachedExtractPageResponse | 缓存感知的单页分子检测 |
| `get_cached_page_detections` | projectRoot, docId, page | CachedExtractPageResponse | 仅读取缓存，不触发检测 |
| `get_detection_cache_stats` | projectRoot | DetectionCacheStats | 缓存统计信息 |
| `clear_detection_cache` | projectRoot | void | 清除所有检测缓存 |
| `clear_detection_cache_doc` | projectRoot, docId | void | 清除单文档检测缓存 |
| `batch_quick_moldet_scan` | request: {project_root, doc_ids} | BatchQuickMoldetResponse | 批量快速扫描 |

**CachedExtractPageResponse 结构**:
```typescript
interface CachedExtractPageResponse {
  results: ExtractionResult[]
  count: number
  source: 'cache' | 'sidecar' | 'sidecar_error' | 'cache_miss'
  cache_path?: string | null
  error?: string | null
}
```

**ExtractionResult 结构**:
```typescript
interface ExtractionResult {
  esmiles: string           // E-SMILES 字符串
  smiles?: string           // 标准 SMILES
  name: string              // 分子名称
  source: 'image' | 'text' | 'manual'
  moldet_conf: number       // MolDet 置信度 (0-1)
  scribe_conf: number       // MolScribe 置信度 (0-1)
  composite_conf: number    // 综合置信度
  bbox_pdf: [number, number, number, number] | null  // PDF 坐标 [x1, y1, x2, y2]
  page_idx: number | null   // 页码（0-based）
  context_text: string      // 上下文文本（coref）
  mol_img_path: string | null
  status: 'pending' | 'confirmed' | 'rejected' | 'done'
  is_quick_scan?: boolean
  properties: Record<string, unknown>
}
```

### 2.2 PDF 解析

| 命令名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `classify_pdf` | path | PdfClassification | 快速分类 PDF 类型 |
| `inspect_pdf` | projectRoot, docId | PdfClassification | 检查 PDF 并写入项目状态 |
| `confirm_ocr` | projectRoot, docId, confirm | ConfirmOcrResult | 确认/跳过 OCR |
| `extract_text` | path | PdfExtraction | 提取文本 |
| `parse_pdf` | path, chunkSize, overlap, parser | PdfParseResult | 完整解析 |
| `process_document` | path, userRequest, projectRoot | void | 完整文档处理管线 |
| `get_document_ocr_layout` | path, docId | OcrLayoutResult | 获取 OCR 布局 |

**PdfClassification 结构**:
```typescript
interface PdfClassification {
  pdf_type: string          // "TextBased" | "Scanned" | "Mixed" | "ImageBased"
  confidence: number
  page_count: number
  pages_needing_ocr: number[]
  text_density_avg: number
  has_complex_layout: boolean
  has_encoding_issues: boolean
  title: string | null
}
```

**OcrBlock 结构**:
```typescript
interface OcrBlock {
  page: number
  block_type: string
  bbox: [number, number, number, number]
  content: string | null
  index: number
  angle: number
}
```

### 2.3 Sidecar 管理

| 命令名 | 参数 | 返回值 | 说明 |
|--------|------|--------|------|
| `start_sidecar` | projectRoot | void | 启动 Python sidecar |
| `stop_sidecar` | | void | 停止 Python sidecar |
| `get_sidecar_status` | | SidecarStatus | 获取 sidecar 状态 |

---

## 3. Python Sidecar HTTP API

### 3.1 分子检测

**POST** `/api/v1/moldet/extract-page`

请求体:
```json
{
  "image_base64": "base64编码的页面图像",
  "page_idx": 0,
  "page_w_pts": 595.0,
  "page_h_pts": 842.0,
  "image_w": 1200,
  "image_h": 1694,
  "use_coref": true
}
```

响应:
```json
{
  "results": [ExtractionResult...],
  "count": 3
}
```

### 3.2 分子-标号共指消解

**POST** `/api/v1/moldet/coref`

请求体:
```json
{
  "image_base64": "base64编码的页面图像",
  "use_molscribe": true,
  "use_ocr": true
}
```

响应:
```json
{
  "corefs": [{"mol_idx": 0, "idt_bbox": [x1, y1, x2, y2]}],
  "idt_bboxes": [[x1, y1, x2, y2], ...]
}
```

### 3.3 SMILES 识别

**POST** `/api/v1/molscribe`

请求体:
```json
{
  "image_base64": "base64编码的分子图像"
}
```

响应:
```json
{
  "smiles": "c1ccccc1",
  "confidence": 0.95
}
```

### 3.4 健康检查

**GET** `/api/v1/health`

响应:
```json
{
  "status": "ok",
  "models": {
    "moldet": "ready",
    "molscribe": "ready",
    "embedder": "ready"
  }
}
```

---

## 4. Tauri 事件

| 事件名 | 载荷 | 触发时机 |
|--------|------|----------|
| `sidecar-status` | {status, uptimeSecs, lastError} | sidecar 状态变化 |
| `sidecar-log` | {stream, line, timestamp} | sidecar 日志输出 |
| `task-progress` | {doc_id, status, progress, current_page, total_pages, error} | 任务进度更新 |
| `doc-result` | DocumentReport | 文档解析完成 |

---

## 5. 前端组件接口

### 5.1 usePdfViewer Hook

```typescript
function usePdfViewer(doc: DocumentEntry, projectRoot: string, initialMode?: 'read' | 'detect' | 'ocr') {
  return {
    // 视图模式
    pdfViewMode: 'read' | 'detect' | 'ocr'
    setPdfViewMode: (mode) => void
    isDetectMode: boolean
    isOcrMode: boolean
    isSinglePageMode: boolean

    // 置信度
    confidenceThreshold: number
    setConfidenceThreshold: (threshold: number) => void

    // 页面状态
    currentPage: number
    setCurrentPage: (page) => void
    pdfPageCount: number
    pdfScale: number

    // 检测结果
    pageDetections: Map<number, ExtractionResult[]>
    currentDetections: ExtractionResult[]
    selectedDetection: number | null
    setSelectedDetection: (index: number | null) => void
    isDetecting: boolean
    canDetect: boolean

    // 文本
    currentTextItems: TextItem[]
    currentTextTotal: number
    hasTextLayer: boolean

    // 操作
    handleDetectPage: (force?: boolean) => Promise<void>
    handleClearDetectionCache: () => Promise<void>
    handleJumpToPage: () => void
    scrollToDetection: (detection: ExtractionResult) => void
  }
}
```

### 5.2 PdfToolbar Props

```typescript
interface PdfToolbarProps {
  doc: DocumentEntry
  onClose: () => void
  pdfViewMode: 'read' | 'detect' | 'ocr'
  onViewModeChange: (mode) => void
  isDetectMode: boolean
  isDetecting: boolean
  canDetect: boolean
  onDetect: () => void
  onClearDetectionCache: () => void
  currentDetectionsCount: number
  confidenceThreshold: number
  onConfidenceThresholdChange: (threshold: number) => void
  // ... 其他工具按钮 props
}
```

### 5.3 PdfResultPane Props

```typescript
interface PdfResultPaneProps {
  currentPage: number
  currentTextItems: TextItem[]
  currentTextTotal: number
  detections: ExtractionResult[]
  selectedDetection: number | null
  onSelectDetection: (index: number | null) => void
  onScrollToDetection?: (detection: ExtractionResult) => void
  confidenceThreshold?: number
}
```

### 5.4 MoleculeOverlay Props

```typescript
interface MoleculeOverlayProps {
  detections: ExtractionResult[]
  renderWidth: number
  renderHeight: number
  originalHeight: number
  scale: number
  currentPage?: number
  selectedIndex?: number
  onSelect?: (index: number) => void
  onRecognize?: () => void
  isRecognizing?: boolean
}
```

---

## 6. 后端实现需求

### 6.1 P0: 已实现

| 需求 | 状态 | 说明 |
|------|------|------|
| 缓存感知检测 | ✅ | `cached_extract_page` 支持缓存查找 |
| 页面验证 | ✅ | `page_idx` 验证防止跨页污染 |
| 尺寸过滤 | ✅ | 面积比/宽高比过滤噪点 |
| 置信度阈值 | ✅ | 前端可调，后端返回 composite_conf |
| Coref 集成 | ✅ | `extract_page` 支持 `use_coref` 参数 |
| ScrollRef 转发 | ✅ | `PdfContinuousViewer` 支持 ref |

### 6.2 P1: 待实现

| 需求 | 优先级 | 说明 |
|------|--------|------|
| Coref 上下文提取 | 高 | 从 bbox 周围提取文本作为 context_text |
| 空页面检测 | 高 | 返回空结果而非缓存 miss |
| 检测结果持久化 | 中 | 支持跨会话保留检测结果 |
| 批量检测进度 | 中 | 大文档分页检测进度报告 |

### 6.3 P2: 待实现

| 需求 | 优先级 | 说明 |
|------|--------|------|
| 检测结果导出 | 低 | 支持导出为 CSV/JSON |
| 检测结果标注 | 低 | 支持用户手动修正检测框 |
| 多文档对比 | 低 | 跨文档分子对比分析 |

---

## 7. 数据流

```
用户打开 PDF
  → PdfViewer 初始化
  → usePdfViewer 加载文档
  → PdfContinuousViewer 渲染页面

用户进入分子模式
  → isDetectMode = true
  → 自动检测当前页
  → cached_extract_page
    → 检查缓存
    → 缓存 miss → 调用 sidecar /api/v1/moldet/extract-page
    → 返回 ExtractionResult[]
  → pageDetections.set(page, results)
  → MoleculeOverlay 渲染检测框

用户点击分子卡片
  → onSelectDetection(index)
  → scrollToDetection(detection)
  → 滚动 PDF 到检测框位置

用户调整置信度阈值
  → confidenceThreshold 更新
  → PdfResultPane 过滤低置信度结果
  → MoleculeOverlay 过滤低置信度检测框
```

---

## 8. 缓存策略

| 缓存类型 | 位置 | 过期策略 |
|----------|------|----------|
| PDF 哈希 | 内存 LRU | mtime 变化时重算 |
| 检测结果 | `index/detections/{doc_slug}/page_{N}.json` | PDF 哈希变化时失效 |
| 文档文本 | `vectors.db` file_cache | 永久，手动清除 |
| 语义缓存 | `semantic_cache.json` | TTL 1 小时 |
