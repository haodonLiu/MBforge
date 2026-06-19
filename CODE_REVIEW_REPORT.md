# 代码审查报告 — 前后端链接链路

> 审查范围：`services/pdfService.ts` → `usePdfViewer.ts` → Rust commands → Python sidecar

---

## 发现的问题

### 🔴 严重问题

#### 1. Sidecar 状态字段命名不匹配

**文件**: `src-tauri/src/commands/sidecar.rs:21-27` vs `services/pdfService.ts:422-427`

Rust 返回 **camelCase**：
```rust
serde_json::json!({
    "healthy": healthy,
    "restartCount": restarts,    // camelCase
    "uptimeSecs": uptime,       // camelCase
    "lastError": ...,           // camelCase
})
```

前端期望 **snake_case**：
```typescript
const resp = await invoke<{
  restart_count: number   // snake_case ← 不匹配!
  uptime_secs: number     // snake_case ← 不匹配!
  last_error: string | null  // snake_case ← 不匹配!
}>('sidecar_status')
```

**后果**: `resp.restart_count` 等字段永远是 `undefined`，前端获取不到正确的 sidecar 状态。

**修复方案**: 统一使用 camelCase（Tauri 默认序列化风格）：
```typescript
// pdfService.ts
const resp = await invoke<{
  healthy: boolean
  restartCount: number
  state: string
  uptimeSecs: number
  lastError: string | null
}>('sidecar_status')
```

---

### 🟡 中等问题

#### 2. `result.data!` 非空断言风险

**文件**: `usePdfViewer.ts:181, 222`

```typescript
const results = result.data!.results  // 非空断言
```

虽然有 `result.success` 检查，但 TypeScript 不保证 `success=true` 时 `data` 一定非空。如果 `detectPageMolecules` 返回 `{ success: true }` 而不带 `data`，这里会崩溃。

**修复方案**: 添加防御性检查：
```typescript
if (!result.success || !result.data) {
  throw new Error(result.error || '检测失败')
}
const results = result.data.results
```

#### 3. `sidecar_status` 返回类型是 `serde_json::Value`

**文件**: `src-tauri/src/commands/sidecar.rs:9`

```rust
pub fn sidecar_status(state: State<Arc<SidecarInner>>) -> serde_json::Value {
```

返回非类型化的 JSON，无法在编译期保证字段名正确。

**修复方案**: 定义结构体：
```rust
#[derive(Serialize)]
struct SidecarStatusResponse {
    healthy: bool,
    restart_count: u32,
    state: String,
    uptime_secs: u64,
    last_error: Option<String>,
}
```

#### 4. `handleLoadImages` 直接调用 `parsePdf` 绕过 service 层

**文件**: `usePdfViewer.ts:350`

```typescript
const result = await parsePdf(absDocPath, 512, 128, 'pdf_inspector')
```

其他 API 都走 `pdfService.ts`，但这个直接调用了 `api/tauri/pdf`。不一致。

**修复方案**: 在 `pdfService.ts` 中添加 `extractPdfImages()` 封装。

---

### 🟢 轻微问题

#### 5. `pdfOcrSummary` 累加逻辑有 bug

**文件**: `usePdfViewer.ts:335-338`

```typescript
setPdfOcrSummary(prev => ({
  totalChars: (prev?.totalChars ?? 0) + totalChars,
  textDensity: totalChars > 500 ? 'rich' : ...,
}))
```

`textDensity` 使用当前页的 `totalChars` 而非累计值，导致每页都覆盖密度判断。

#### 6. `handleKeyDown` 缺少上下文菜单阻止

**文件**: `usePdfViewer.ts:395-405`

空格键翻页可能与浏览器默认行为冲突（如滚动到页面底部）。

---

## 验证清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 命令名匹配 | ✅ | `cached_extract_page`, `get_cached_page_detections` 等 |
| 参数命名 | ✅ | Tauri 自动处理 camelCase → snake_case |
| 返回值字段名 | ❌ | `sidecar_status` 返回 camelCase，前端期望 snake_case |
| 类型安全 | ⚠️ | 使用 `as` 类型断言，无运行时验证 |
| 错误处理 | ✅ | 统一 `ServiceResult<T>` 格式 |
| 空值处理 | ⚠️ | 存在 `!` 非空断言风险 |

---

## 建议修复优先级

1. **P0**: 修复 `sidecar_status` 字段命名不匹配
2. **P1**: 移除 `result.data!` 非空断言
3. **P1**: `sidecar_status` 改为返回类型化结构体
4. **P2**: 统一 `handleLoadImages` 走 service 层
5. **P2**: 修复 `pdfOcrSummary` 密度判断逻辑
