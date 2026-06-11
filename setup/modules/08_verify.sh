#!/usr/bin/env bash
# 模块 08: 验证安装

run_verify() {
    header "验证安装"

    local FAIL=0

    $PYTHON -c "import torch; print(f'PyTorch {torch.__version__}, CUDA={torch.cuda.is_available()}')" 2>/dev/null \
        && ok "PyTorch OK" || { warn "PyTorch 异常"; FAIL=1; }

    $PYTHON -c "import lxml.etree; print(f'lxml {lxml.etree.__version__}')" 2>/dev/null \
        && ok "lxml OK" || { warn "lxml 异常"; FAIL=1; }

    $PYTHON -c "from mbforge.sar.analyzer import SARAnalyzer; print('csar SARAnalyzer OK')" 2>/dev/null \
        && ok "csar OK" || { warn "csar 异常"; FAIL=1; }

    $PYTHON -c "import mbforge; print(f'mbforge {mbforge.__version__}')" 2>/dev/null \
        && ok "mbforge OK" || { warn "mbforge 异常"; FAIL=1; }

    echo ""
    if [ "$FAIL" -eq 0 ]; then
        echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  配置完成! 运行 uv run mbforge 启动应用  ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
    else
        echo -e "${YELLOW}╔══════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║  配置完成，部分组件有警告请检查上方      ║${NC}"
        echo -e "${YELLOW}╚══════════════════════════════════════════╝${NC}"
    fi

    # ── 可选功能提示 ──
    echo ""
    echo -e "${DIM}───────────────── 可选功能提示 ─────────────────${NC}"

    # LiteParse / PDFium
    if [ -f "vendor/pdfium/release/pdfium.dll" ] || [ -f "vendor/pdfium/release/libpdfium.so" ]; then
        ok "LiteParse (PDFium) — 就绪"
    else
        warn "LiteParse (PDFium) — 未安装（离线扫描 PDF 解析回退）"
        echo -e "  ${DIM}需要时手动下载 PDFium 到 vendor/pdfium/release/${NC}"
        echo -e "  ${DIM}https://github.com/run-llama/pdfium-binaries/releases/latest${NC}"
    fi

    # MolDet GPU
    if $PYTHON -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
        ok "MolDet (GPU) — 就绪"
    else
        warn "MolDet (GPU) — 无 GPU，分子检测功能不可用"
        echo -e "  ${DIM}需 NVIDIA GPU + CUDA 12.8 才能使用分子检测功能${NC}"
    fi

    echo -e "${DIM}────────────────────────────────────────────────${NC}"
}
