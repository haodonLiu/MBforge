"""模型下载路由 — 基于 ResourceManager 统一管理.

所有模型目录和状态检查委托给 ResourceManager。
下载逻辑保留 ModelScope SSE 流式实现。
错误通过全局异常处理器统一返回。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...core.resource_manager import (
    RESOURCE_CATALOG, ResourceManager, ResourceType, ResourceStatus,
)
from ...utils.constants import get_model_cache_dir
from ...utils.exceptions import ResourceNotAvailableError, ValidationError
from ...utils.logger import get_logger
from ...utils.config import load_global_config, save_global_config

logger = get_logger(__name__)
router = APIRouter()

_download_tasks: dict[str, bool] = {}
MS_BASE = "https://modelscope.cn/api/v1/models"


def _get_model_cache_dir() -> Path:
    return Path(get_model_cache_dir())


# ---------------------------------------------------------------------------
# 内部工具（保持 SSE 下载流实现）
# ---------------------------------------------------------------------------

def _filter_essential_files(all_files: list[str], model_id: str) -> list[str]:
    """从仓库文件列表中筛选必要文件（只下载权重 + 配置，不下载完整仓库）."""
    def _name(p: str) -> str:
        return p.rsplit("/", 1)[-1] if "/" in p else p

    if model_id == "molscribe":
        return [f for f in all_files if _name(f).endswith((".pth", ".json", ".txt", ".model"))]

    has_safetensors = any(_name(f).endswith(".safetensors") for f in all_files)

    def _is_essential(path: str) -> bool:
        name = _name(path)
        ext = name.rsplit(".", 1)[-1] if "." in name else ""

        weight_patterns = [
            ext == "safetensors",
            name.endswith(".pt") and not name.startswith("."),
            name.endswith(".pth"),
        ]
        if not has_safetensors:
            weight_patterns.append(name.endswith(".bin"))

        config_patterns = [
            name == "config.json",
            name == "generation_config.json",
            name == "preprocessor_config.json",
            name == "tokenizer.json",
            name == "tokenizer_config.json",
            name == "vocab.json",
            name == "merges.txt",
            name == "special_tokens_map.json",
            name == "added_tokens.json",
            name == "model.safetensors.index.json",
        ]
        return any(weight_patterns) or any(config_patterns)

    return [f for f in all_files if _is_essential(f)]


def _download_from_modelscope(model_id: str, *, timeout: int = 300):
    """纯 ModelScope 下载，yield SSE 事件（只下载必要文件）."""
    import requests as _requests

    info = RESOURCE_CATALOG[model_id]
    dest = _get_model_cache_dir()
    repo = info.ms_repo

    yield {"status": "connecting", "source": "modelscope", "repo": repo}

    if info.download_type == "snapshot":
        local_dir = dest / repo.split("/")[-1]
        local_dir.mkdir(parents=True, exist_ok=True)

        yield {"status": "downloading", "progress": 0}
        try:
            r = _requests.get(f"{MS_BASE}/{repo}/repo/tree?Revision=master", timeout=30)
            tree = r.json().get("Data", []) if r.ok else []
            all_files = [f["Path"] for f in tree if f.get("Type") == "blob"]
            files = _filter_essential_files(all_files, model_id)
        except Exception:
            files = []

        if not files:
            yield {"status": "failed", "error": "无法获取 ModelScope 文件列表，请检查网络或手动下载"}
            return

        logger.info(f"Downloading {len(files)}/{len(all_files)} essential files for {model_id}")
        for i, fpath in enumerate(files):
            fdest = local_dir / fpath
            fdest.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = _requests.get(
                    f"{MS_BASE}/{repo}/repo",
                    params={"Revision": "master", "FilePath": fpath},
                    timeout=timeout, stream=True,
                )
                r.raise_for_status()
                fsize = int(r.headers.get("Content-Length", 0))
                got = 0
                with open(fdest, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                        got += len(chunk)
                        if fsize > 0:
                            yield {
                                "status": "downloading",
                                "file": fpath,
                                "file_progress": int(got * 100 / fsize),
                                "file_index": i + 1,
                                "total_files": len(files),
                            }
            except Exception as e:
                yield {"status": "failed", "error": f"下载 {fpath} 失败: {e}"}
                return

        yield {"status": "completed", "source": "modelscope"}

    else:
        local_name = info.local_name or f"{model_id}.pt"
        file_dest = dest / local_name
        file_dest.parent.mkdir(parents=True, exist_ok=True)
        ms_file = info.ms_file
        try:
            r = _requests.get(
                f"{MS_BASE}/{repo}/repo",
                params={"Revision": "master", "FilePath": ms_file},
                timeout=timeout, stream=True,
            )
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            if "text/html" in ct:
                yield {"status": "failed", "error": "ModelScope 返回 HTML，可能需要登录"}
                return

            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            with open(file_dest, "wb") as f:
                for chunk in r.iter_content(262144):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        yield {"status": "downloading", "progress": int(downloaded * 100 / total)}

            yield {"status": "completed", "source": "modelscope"}
        except Exception as e:
            yield {"status": "failed", "error": f"下载失败: {e}"}


def _get_dir_size(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(size_bytes / 1024 / 1024, 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Endpoints — 错误通过全局异常处理器统一返回
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models() -> dict[str, Any]:
    """列出所有模型及其状态."""
    result = []
    for mid, info in RESOURCE_CATALOG.items():
        if info.type != ResourceType.MODEL:
            continue
        status = ResourceManager.check(mid)
        result.append({
            "id": mid,
            "name": info.name,
            "type": info.type.value,
            "description": info.description,
            "ms_repo": info.ms_repo,
            "hf_repo": info.hf_repo,
            "downloaded": status.status == ResourceStatus.READY,
            "downloading": _download_tasks.get(mid, False),
            "local_path": status.local_path or str(_get_model_cache_dir() / info.ms_repo.split("/")[-1]),
            "license": info.license,
            "license_url": info.license_url,
            "size_mb": info.size_mb,
            "actual_size_mb": status.size_mb if status.status == ResourceStatus.READY else 0,
            "source_url": info.source_url,
            "location": {
                "found": status.status == ResourceStatus.READY,
                "primary": "modelscope" if status.status == ResourceStatus.READY else None,
                "locations": (
                    [{"source": "modelscope", "path": status.local_path, "size_mb": status.size_mb}]
                    if status.status == ResourceStatus.READY else []
                ),
            },
        })
    return {"success": True, "models": result}


@router.get("/model-paths")
async def get_model_paths() -> dict[str, Any]:
    """返回所有模型相关的缓存路径."""
    return {
        "success": True,
        "paths": {
            "mbforge": {
                "path": str(_get_model_cache_dir()),
                "exists": _get_model_cache_dir().exists(),
                "size_mb": _get_dir_size(_get_model_cache_dir()),
            },
            "huggingface": {
                "path": str(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))),
                "env_var": "HF_HOME",
                "exists": Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))).exists(),
                "size_mb": _get_dir_size(Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))),
            },
            "modelscope": {
                "path": str(os.environ.get("MODELSCOPE_CACHE", str(Path.home() / ".cache" / "modelscope"))),
                "env_var": "MODELSCOPE_CACHE",
                "exists": Path(os.environ.get("MODELSCOPE_CACHE", str(Path.home() / ".cache" / "modelscope"))).exists(),
                "size_mb": _get_dir_size(Path(os.environ.get("MODELSCOPE_CACHE", str(Path.home() / ".cache" / "modelscope")))),
            },
        },
    }


@router.post("/model-dir")
async def set_model_dir(path: str) -> dict[str, Any]:
    """设置 MBForge 模型缓存目录."""
    new_path = Path(path).expanduser().absolute()
    if not new_path.parent.exists():
        raise ValidationError("父目录不存在")
    cfg = load_global_config()
    cfg.model_cache_dir = str(new_path)
    save_global_config(cfg)
    return {"success": True, "model_dir": str(new_path), "message": "模型目录已更新，重启后生效"}


@router.get("/model-dir")
async def get_model_dir() -> dict[str, Any]:
    """返回当前模型下载目录路径."""
    cfg = load_global_config()
    return {"success": True, "model_dir": str(_get_model_cache_dir()), "config_dir": cfg.model_cache_dir or "(default)"}


@router.get("/list-downloaded")
async def list_downloaded() -> dict[str, Any]:
    """扫描模型目录，返回所有已下载模型的信息."""
    cache_dir = _get_model_cache_dir()
    downloaded = []
    if cache_dir.exists():
        for entry in cache_dir.iterdir():
            if not entry.is_dir():
                if entry.suffix in (".pt", ".pth", ".onnx"):
                    size_bytes = entry.stat().st_size
                    matched_id = None
                    for mid, info in RESOURCE_CATALOG.items():
                        if info.type == ResourceType.MODEL and info.local_name == entry.name:
                            matched_id = mid
                            break
                    downloaded.append({
                        "id": matched_id or entry.stem,
                        "name": entry.stem,
                        "path": str(entry),
                        "size_mb": round(size_bytes / 1024 / 1024, 1),
                        "type": "file",
                        "in_catalog": matched_id is not None,
                    })
                continue
            has_weights = any(entry.rglob("*.bin")) or any(entry.rglob("*.safetensors"))
            if has_weights:
                size_bytes = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                matched_id = None
                for mid, info in RESOURCE_CATALOG.items():
                    if info.type == ResourceType.MODEL:
                        repo_name = info.ms_repo.split("/")[-1]
                        if entry.name == repo_name:
                            matched_id = mid
                            break
                downloaded.append({
                    "id": matched_id or entry.name,
                    "name": entry.name,
                    "path": str(entry),
                    "size_mb": round(size_bytes / 1024 / 1024, 1),
                    "type": "directory",
                    "in_catalog": matched_id is not None,
                })
    return {"success": True, "models": downloaded, "model_dir": str(cache_dir)}


@router.delete("/delete/{model_id}")
async def delete_model(model_id: str) -> dict[str, Any]:
    """删除已下载的模型."""
    cache_dir = _get_model_cache_dir()

    if model_id in RESOURCE_CATALOG:
        info = RESOURCE_CATALOG[model_id]
        if info.type != ResourceType.MODEL:
            raise ValidationError(f"非模型资源: {model_id}")
        if info.download_type == "file":
            target = cache_dir / (info.local_name or f"{model_id}.pt")
        else:
            target = cache_dir / info.ms_repo.split("/")[-1]
    else:
        target = cache_dir / model_id
        if not target.exists():
            target = cache_dir / f"{model_id}.pt"
        if not target.exists():
            raise ResourceNotAvailableError(f"未找到模型: {model_id}")

    if not target.exists():
        raise ResourceNotAvailableError(f"模型路径不存在: {target}")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"success": True, "deleted": str(target)}


@router.post("/download/{model_id}")
async def download_model(model_id: str):
    """下载模型（SSE 流式进度）."""
    if model_id not in RESOURCE_CATALOG:
        raise ValidationError(f"未知模型: {model_id}")
    info = RESOURCE_CATALOG[model_id]
    if info.type != ResourceType.MODEL:
        raise ValidationError(f"非模型资源: {model_id}")
    if _download_tasks.get(model_id):
        raise ValidationError("该模型正在下载中")

    _download_tasks[model_id] = True

    def event_stream():
        try:
            for event in _download_from_modelscope(model_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Download stream failed for model={model_id}: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            _download_tasks.pop(model_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/status/{model_id}")
async def model_status(model_id: str) -> dict[str, Any]:
    """查询单个模型状态."""
    if model_id not in RESOURCE_CATALOG:
        raise ValidationError(f"未知模型: {model_id}")
    status = ResourceManager.check(model_id)
    info = RESOURCE_CATALOG[model_id]
    return {
        "success": True,
        "model_id": model_id,
        "downloaded": status.status == ResourceStatus.READY,
        "downloading": _download_tasks.get(model_id, False),
        "local_path": status.local_path or str(_get_model_cache_dir() / info.ms_repo.split("/")[-1]),
        "location": {
            "found": status.status == ResourceStatus.READY,
            "primary": "modelscope" if status.status == ResourceStatus.READY else None,
        },
    }
