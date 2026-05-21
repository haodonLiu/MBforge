#!/usr/env bash
# 模块 07b: 本地模型缓存目录配置

run_config_cache() {
    header "本地模型缓存目录"

    local DEFAULT_CACHE="$HOME/Models"

    if confirm "是否自定义模型缓存目录？" "n"; then
        HF_HOME=$(ask "  HuggingFace 模型目录" "${HF_HOME:-$DEFAULT_CACHE/HuggingFace}")
        MODELSCOPE_CACHE=$(ask "  ModelScope 缓存目录" "${MODELSCOPE_CACHE:-$DEFAULT_CACHE/ModelScope}")
        TORCH_HOME=$(ask "  PyTorch 模型/权重缓存目录" "${TORCH_HOME:-$DEFAULT_CACHE/Torch}")
        OLLAMA_MODELS=$(ask "  Ollama 本地模型存放目录" "${OLLAMA_MODELS:-$DEFAULT_CACHE/Ollama}")
        info "已配置缓存目录"
    else
        HF_HOME=""
        MODELSCOPE_CACHE=""
        TORCH_HOME=""
        OLLAMA_MODELS=""
        info "使用系统默认缓存目录"
    fi

    export HF_HOME MODELSCOPE_CACHE TORCH_HOME OLLAMA_MODELS
}
