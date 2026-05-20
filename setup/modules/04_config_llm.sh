#!/usr/bin/env bash
# 模块 04: LLM 提供商选择与配置

LLM_PROVIDER="openai_compatible"
LLM_BASE_URL="https://api.siliconflow.cn/v1"
LLM_API_KEY=""
LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"

run_config_llm() {
    header "LLM 大语言模型配置"

    echo "选择 LLM 提供商:"
    echo "  1) OpenAI 兼容 API（硅基流动 / vLLM / 其他兼容服务）"
    echo "  2) Anthropic（Claude / MiniMax Anthropic 兼容）"
    if $OLLAMA_AVAILABLE; then
        echo "  3) Ollama（本地模型）"
    fi

    local choice
    read -rp "选择 [1]: " choice
    choice="${choice:-1}"

    case $choice in
        1)
            LLM_PROVIDER="openai_compatible"
            LLM_BASE_URL=$(ask "  API Base URL" "$LLM_BASE_URL")
            read -rp "  API Key: " LLM_API_KEY
            LLM_MODEL=$(ask "  模型名称" "$LLM_MODEL")
            ;;
        2)
            LLM_PROVIDER="anthropic"
            LLM_BASE_URL="https://api.minimaxi.com/anthropic"
            LLM_BASE_URL=$(ask "  API Base URL" "$LLM_BASE_URL")
            read -rp "  API Key: " LLM_API_KEY
            LLM_MODEL=$(ask "  模型名称" "MiniMax-M2.7")
            ;;
        3)
            if $OLLAMA_AVAILABLE; then
                LLM_PROVIDER="ollama"
                LLM_BASE_URL="$OLLAMA_HOST/v1"
                LLM_API_KEY="ollama"
                LLM_MODEL=$(ask "  模型名称" "qwen2.5:7b")
            fi
            ;;
    esac

    ok "LLM: $LLM_PROVIDER / $LLM_MODEL"
    export LLM_PROVIDER LLM_BASE_URL LLM_API_KEY LLM_MODEL
}
