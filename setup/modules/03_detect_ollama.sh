#!/usr/bin/env bash
# 模块 03: Ollama 自动检测

OLLAMA_AVAILABLE=false
OLLAMA_HOST="http://localhost:11434"

run_detect_ollama() {
    header "Ollama 本地模型检测"

    if has_cmd ollama; then
        OLLAMA_AVAILABLE=true
        ok "检测到 Ollama"

        if curl -s "$OLLAMA_HOST/api/tags" &>/dev/null; then
            ok "Ollama 服务运行中"
            local models
            models=$($PYTHON -c "
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen('$OLLAMA_HOST/api/tags').read())
    for m in data.get('models', []):
        print(f'  - {m[\"name\"]}')
except: pass
" 2>/dev/null || true)
            if [ -n "$models" ]; then
                info "已安装模型:"
                echo "$models"
            fi
        else
            warn "Ollama 已安装但服务未运行，请执行: ollama serve"
        fi
    else
        info "未检测到 Ollama，跳过本地模型配置"
        info "后续可安装: https://ollama.com/download"
    fi

    export OLLAMA_AVAILABLE OLLAMA_HOST
}
