#!/usr/bin/env bash
# 模块 07: 基于 .env.template 生成 .env 配置文件

run_write_env() {
    header "写入配置文件"

    local TEMPLATE=".env.template"
    if [ ! -f "$TEMPLATE" ]; then
        warn ".env.template 不存在，使用内置模板"
        _write_env_fallback
        return
    fi

    if [ -f ".env" ]; then
        if confirm ".env 已存在，是否覆盖？" "y"; then
            cp .env .env.bak 2>/dev/null && ok "已备份旧 .env → .env.bak"
        else
            info "保留现有 .env"
            return
        fi
    fi

    # 基于模板生成：用 sed 替换占位值
    cp "$TEMPLATE" .env

    # UniParser
    _env_set "UNIPARSER_HOST" "${UNIPARSER_HOST:-}"
    _env_set "UNIPARSER_API_KEY" "${UNIPARSER_KEY:-}"

    # LLM
    _env_set "MBFORGE_LLM_PROVIDER" "${LLM_PROVIDER}"
    _env_set "MBFORGE_LLM_BASE_URL" "${LLM_BASE_URL}"
    _env_set "MBFORGE_LLM_API_KEY" "${LLM_API_KEY}"
    _env_set "MBFORGE_LLM_MODEL" "${LLM_MODEL}"

    # Embedding
    _env_set "MBFORGE_EMBED_PROVIDER" "${EMBED_PROVIDER}"
    _env_set "MBFORGE_EMBED_MODEL" "${EMBED_MODEL}"
    _env_set "MBFORGE_EMBED_DEVICE" "${EMBED_DEVICE}"
    if [ -n "${EMBED_BASE_URL:-}" ]; then
        _env_set "MBFORGE_EMBED_BASE_URL" "${EMBED_BASE_URL}"
    fi
    if [ -n "${EMBED_API_KEY:-}" ]; then
        _env_set "MBFORGE_EMBED_API_KEY" "${EMBED_API_KEY}"
    fi

    # Rerank
    _env_set "MBFORGE_RERANK_MODEL" "${RERANK_MODEL}"
    _env_set "MBFORGE_RERANK_DEVICE" "${RERANK_DEVICE}"

    ok ".env 已从模板生成"
}

# 模板不存在时的回退方案
_write_env_fallback() {
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

# ---------- Rerank ----------
MBFORGE_RERANK_MODEL=${RERANK_MODEL}
MBFORGE_RERANK_DEVICE=${RERANK_DEVICE}

# ---------- UV Mirror ----------
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
UV_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
UV_PYTHON_MIRRORS=https://mirror.sjtu.edu.cn/python-request
ENVEOF
    ok ".env 已写入（内置模板）"
}

# 设置 .env 中 KEY=VALUE 的值（保留注释和格式）
_env_set() {
    local key="$1" value="$2"
    # 转义 value 中的特殊字符
    local escaped
    escaped=$(printf '%s\n' "$value" | sed 's/[&/\]/\\&/g')
    # 替换 KEY=... 或 # KEY=... 行
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env
    # 也处理被注释掉的行（# MBFORGE_XXX=）
    sed -i "s|^# *${key}=.*|${key}=${escaped}|" .env
}
