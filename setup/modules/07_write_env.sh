#!/usr/bin/env bash
# 模块 07: 写入 .env 配置文件

run_write_env() {
    header "写入配置文件"

    if [ -f ".env" ]; then
        if confirm ".env 已存在，是否覆盖？" "y"; then
            cp .env .env.bak 2>/dev/null && ok "已备份旧 .env → .env.bak"
        else
            info "保留现有 .env"
            return
        fi
    fi

    cat > .env << ENVEOF
# UniParser Configuration
UNIPARSER_HOST=${UNIPARSER_HOST:-}
UNIPARSER_API_KEY=${UNIPARSER_KEY:-}

# ---------- LLM ----------
MBFORGE_LLM_PROVIDER=${LLM_PROVIDER}
MBFORGE_LLM_BASE_URL=${LLM_BASE_URL}
MBFORGE_LLM_API_KEY=${LLM_API_KEY}
MBFORGE_LLM_MODEL=${LLM_MODEL}
MBFORGE_LLM_MAX_TOKENS=4096
MBFORGE_LLM_TEMPERATURE=0.7
MBFORGE_LLM_TOP_P=0.9

# ---------- Embedding ----------
MBFORGE_EMBED_PROVIDER=${EMBED_PROVIDER}
MBFORGE_EMBED_MODEL=${EMBED_MODEL}
MBFORGE_EMBED_DEVICE=${EMBED_DEVICE}
MBED_BASE_URL=${EMBED_BASE_URL:-}
MBED_API_KEY=${EMBED_API_KEY:-}

# ---------- Rerank ----------
MBFORGE_RERANK_MODEL=${RERANK_MODEL}
MBFORGE_RERANK_DEVICE=${RERANK_DEVICE}

# ---------- UV Mirror ----------
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
UV_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
UV_PYTHON_MIRRORS=https://mirror.sjtu.edu.cn/python-request
ENVEOF

    ok ".env 已写入"
}
