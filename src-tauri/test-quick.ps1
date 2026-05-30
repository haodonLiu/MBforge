# 快速测试 — 只运行本次修改相关的模块
# 用法: .\test-quick.ps1

$modules = @(
    "embedding::",
    "vector_store::",
    "knowledge_base::",
    "document_tree::",
    "executor::",
    "headings::",
    "sections::",
    "pipeline::"
)

Write-Host "Running targeted tests..." -ForegroundColor Cyan
$total = 0

foreach ($mod in $modules) {
    Write-Host "  → testing $mod" -NoNewline -ForegroundColor DarkGray
    $output = cargo test --lib $mod 2>&1
    $result = $output | Select-String "test result:"
    if ($result) {
        Write-Host "  $result" -ForegroundColor Green
        if ($result -match '(\d+) passed') {
            $total += [int]$matches[1]
        }
    } else {
        Write-Host "  (no tests)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Total: $total targeted tests passed" -ForegroundColor Cyan
