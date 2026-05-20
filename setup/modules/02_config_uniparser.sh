#!/usr/bin/env bash
# 模块 02: UniParser 交互配置

run_config_uniparser() {
    header "UniParser 配置"

    UNIPARSER_HOST=""
    UNIPARSER_KEY=""

    if confirm "是否配置 UniParser 远程解析服务？" "Y"; then
        UNIPARSER_HOST=$(ask "  服务地址" "https://your-server.com")
        read -rp "  API Key: " UNIPARSER_KEY
        if [ -n "$UNIPARSER_KEY" ]; then
            ok "UniParser: $UNIPARSER_HOST"
        else
            warn "未填写 API Key，UniParser 将不可用"
        fi
    else
        info "跳过 UniParser 配置"
    fi

    export UNIPARSER_HOST UNIPARSER_KEY
}
