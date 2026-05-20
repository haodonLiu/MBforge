#!/usr/bin/env bash
# 模块 06: ModelScope 安装与模型下载

run_install_modelscope() {
    header "模型下载（可选）"

    if has_cmd modelscope || has_module modelscope; then
        ok "ModelScope 已安装"

        if confirm "是否下载推荐的 Embedding/Rerank 模型到本地？" "Y"; then
            info "下载 $EMBED_MODEL ..."
            $PYTHON -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('$EMBED_MODEL')
print('Downloaded: $EMBED_MODEL')
" 2>/dev/null && ok "$EMBED_MODEL 下载完成" || warn "$EMBED_MODEL 下载失败"

            info "下载 $RERANK_MODEL ..."
            $PYTHON -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('$RERANK_MODEL')
print('Downloaded: $RERANK_MODEL')
" 2>/dev/null && ok "$RERANK_MODEL 下载完成" || warn "$RERANK_MODEL 下载失败"
        fi
    else
        echo "ModelScope 未安装。安装后可离线下载模型，加速首次加载。"
        if confirm "安装 ModelScope？" "y"; then
            info "安装 ModelScope ..."
            uv pip install modelscope --python "$PYTHON"
            ok "ModelScope 已安装"
        fi
    fi
}
