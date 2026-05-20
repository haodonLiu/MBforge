#!/usr/bin/env bash
# 模块 05: Embedding / Rerank 模型选择

EMBED_PROVIDER="sentence_transformers"
EMBED_MODEL="BAAI/bge-small-zh-v1.5"
EMBED_DEVICE="cpu"
EMBED_BASE_URL=""
EMBED_API_KEY=""
RERANK_MODEL="BAAI/bge-reranker-base"
RERANK_DEVICE="cpu"

run_config_models() {
    header "Embedding / Rerank 模型配置"

    local HAS_CUDA=false
    local GPU_NAME=""
    if detect_cuda; then
        HAS_CUDA=true
        GPU_NAME=$(get_gpu_name)
        ok "检测到 GPU: $GPU_NAME"
    fi

    # ---- Embedding ----
    echo "Embedding 模型选择:"
    echo "  1) BAAI/bge-small-zh-v1.5（轻量，推荐 CPU）"
    echo "  2) BAAI/bge-large-zh-v1.5（高精度）"
    echo "  3) Qwen/Qwen3-Embedding-0.6B（通义千问，推荐）"
    echo "  4) 使用 API（OpenAI / 兼容接口）"

    local choice
    read -rp "选择 [1]: " choice
    choice="${choice:-1}"

    case $choice in
        1) EMBED_MODEL="BAAI/bge-small-zh-v1.5" ;;
        2) EMBED_MODEL="BAAI/bge-large-zh-v1.5" ;;
        3) EMBED_MODEL="Qwen/Qwen3-Embedding-0.6B" ;;
        4)
            EMBED_PROVIDER="api"
            EMBED_BASE_URL=$(ask "  Embedding API Base URL" "")
            read -rp "  Embedding API Key: " EMBED_API_KEY
            EMBED_MODEL=$(ask "  模型名称" "$EMBED_MODEL")
            ;;
    esac

    if $HAS_CUDA && confirm "使用 GPU 加速 Embedding？" "Y"; then
        EMBED_DEVICE="cuda"
    fi

    # ---- Rerank ----
    echo ""
    echo "Rerank 模型选择:"
    echo "  1) BAAI/bge-reranker-base（默认）"
    echo "  2) BAAI/bge-reranker-v2-m3（多语言）"
    echo "  3) Qwen/Qwen3-Reranker-0.6B（通义千问，推荐）"

    read -rp "选择 [1]: " choice
    choice="${choice:-1}"

    case $choice in
        1) RERANK_MODEL="BAAI/bge-reranker-base" ;;
        2) RERANK_MODEL="BAAI/bge-reranker-v2-m3" ;;
        3) RERANK_MODEL="Qwen/Qwen3-Reranker-0.6B" ;;
    esac

    if $HAS_CUDA; then
        RERANK_DEVICE="$EMBED_DEVICE"
    fi

    ok "Embedding: $EMBED_MODEL ($EMBED_DEVICE)"
    ok "Rerank: $RERANK_MODEL ($RERANK_DEVICE)"

    export EMBED_PROVIDER EMBED_MODEL EMBED_DEVICE EMBED_BASE_URL EMBED_API_KEY
    export RERANK_MODEL RERANK_DEVICE
}
