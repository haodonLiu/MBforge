"""模型下载路由 — 仅 ModelScope，4 个确认模型."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...utils.constants import get_model_cache_dir
from ...utils.logger import get_logger
from ...utils.config import load_global_config, save_global_config

logger = get_logger(__name__)
router = APIRouter()

# 只维护我们确认可用的 4 个模型（含许可证和预估大小信息）
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "qwen3-embedding-0.6b": {
        "name": "Qwen3-Embedding-0.6B",
        "type": "embedding",
        "description": "通义千问3 嵌入模型 (0.6B)",
        "ms_repo": "Qwen/Qwen3-Embedding-0.6B",
        "hf_repo": "Qwen/Qwen3-Embedding-0.6B",
        "download_type": "snapshot",
        "license": "Apache-2.0",
        "license_url": "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/main/LICENSE",
        "size_mb": 1152,  # 实际大小: ~1151.55 MB
        "source_url": "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
    },
    "qwen3-reranker-0.6b": {
        "name": "Qwen3-Reranker-0.6B",
        "type": "reranker",
        "description": "通义千问3 重排序模型 (0.6B)",
        "ms_repo": "Qwen/Qwen3-Reranker-0.6B",
        "hf_repo": "Qwen/Qwen3-Reranker-0.6B",
        "download_type": "snapshot",
        "license": "Apache-2.0",
        "license_url": "https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/blob/main/LICENSE",
        "size_mb": 1152,  # 实际大小: ~1151.55 MB
        "source_url": "https://huggingface.co/Qwen/Qwen3-Reranker-0.6B",
    },
    "moldetv2": {
        "name": "MolDetv2",
        "type": "detection",
        "description": "MolDetv2 分子检测模型",
        "ms_repo": "yujieq/MolDetect",
        "hf_repo": "yujieq/MolDetect",
        "ms_file": "best.pt",
        "download_type": "file",
        "local_name": "moldetv2-doc.pt",
        "license": "Apache-2.0",
        "license_url": "https://huggingface.co/yujieq/MolDetect/blob/main/LICENSE",
        "size_mb": 25,  # 预估大小 (实际需要从本地文件获取)
        "source_url": "https://huggingface.co/yujieq/MolDetect",
    },
    "molscribe": {
        "name": "MolScribe",
        "type": "detection",
        "description": "MolScribe 分子图像转 SMILES",
        "ms_repo": "yujieq/MolScribe",
        "hf_repo": "yujieq/MolScribe",
        "download_type": "snapshot",
        "license": "MIT",
        "license_url": "https://github.com/thomas0809/MolScribe/blob/main/LICENSE",
        "size_mb": 6186,  # 实际大小: ~6185.65 MB
        "source_url": "https://github.com/thomas0809/MolScribe",
    },
}

_download_tasks: dict[str, bool] = {}
MS_BASE = "https://modelscope.cn/api/v1/models"


def _get_model_cache_dir() -> Path:
    return Path(get_model_cache_dir())


def _get_hf_cache_dir() -> Path:
    """获取 HuggingFace 缓存目录."""
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        return Path(hf_home)
    return Path.home() / ".cache" / "huggingface"


def _get_modelscope_cache_dir() -> Path:
    """获取 ModelScope 缓存目录."""
    ms_cache = os.environ.get("MODELSCOPE_CACHE", "")
    if ms_cache:
        return Path(ms_cache)
    return Path.home() / ".cache" / "modelscope"


def _check_model_in_cache(model_id: str, cache_dir: Path) -> dict | None:
    """检查模型是否在指定的缓存目录中."""
    if not cache_dir.exists():
        return None
    
    info = MODEL_CATALOG.get(model_id, {})
    if not info:
        return None
    
    if info.get("download_type") == "file":
        local_name = info.get("local_name", f"{model_id}.pt")
        path = cache_dir / local_name
        if path.exists() and path.stat().st_size > 0:
            return {
                "path": str(path),
                "size_mb": round(path.stat().st_size / 1024 / 1024, 1),
            }
    else:
        repo_name = info.get("ms_repo", "").split("/")[-1]
        path = cache_dir / repo_name
        if path.exists():
            # 检查是否有模型文件
            has_weights = any(path.rglob("*.bin")) or any(path.rglob("*.safetensors")) or any(path.rglob("*.pt"))
            if has_weights:
                size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                return {
                    "path": str(path),
                    "size_mb": round(size_bytes / 1024 / 1024, 1),
                }
    return None


def _model_local_path(model_id: str) -> Path:
    cache_dir = _get_model_cache_dir()
    info = MODEL_CATALOG[model_id]
    if info["download_type"] == "file":
        return cache_dir / info.get("local_name", f"{model_id}.pt")
    name = info["ms_repo"].split("/")[-1]
    return cache_dir / name


def _is_downloaded(model_id: str) -> bool:
    # 首先检查 MBForge 缓存目录
    path = _model_local_path(model_id)
    info = MODEL_CATALOG[model_id]
    if info["download_type"] == "file":
        if path.exists() and path.stat().st_size > 0:
            return True
    else:
        if path.exists() and (any(path.rglob("*.bin")) or any(path.rglob("*.safetensors"))):
            return True
    
    # 检查 HuggingFace 缓存目录
    if _check_model_in_cache(model_id, _get_hf_cache_dir()):
        return True
    
    # 检查 ModelScope 缓存目录
    if _check_model_in_cache(model_id, _get_modelscope_cache_dir()):
        return True
    
    return False


def _get_model_location(model_id: str) -> dict:
    """获取模型的存储位置信息."""
    info = MODEL_CATALOG.get(model_id, {})
    locations = []
    primary_location = None
    
    # 检查 MBForge 缓存目录
    mbforge_path = _model_local_path(model_id)
    if mbforge_path.exists():
        locations.append({
            "source": "mbforge",
            "path": str(mbforge_path),
            "size_mb": round(sum(f.stat().st_size for f in mbforge_path.rglob("*") if f.is_file()) / 1024 / 1024, 1) if mbforge_path.is_dir() else round(mbforge_path.stat().st_size / 1024 / 1024, 1),
        })
        primary_location = "mbforge"
    
    # 检查 HuggingFace 缓存目录
    hf_cache = _get_hf_cache_dir()
    hf_result = _check_model_in_cache(model_id, hf_cache)
    if hf_result:
        locations.append({
            "source": "huggingface",
            "path": hf_result["path"],
            "size_mb": hf_result["size_mb"],
        })
        if primary_location is None:
            primary_location = "huggingface"
    
    # 检查 ModelScope 缓存目录
    ms_cache = _get_modelscope_cache_dir()
    ms_result = _check_model_in_cache(model_id, ms_cache)
    if ms_result:
        locations.append({
            "source": "modelscope",
            "path": ms_result["path"],
            "size_mb": ms_result["size_mb"],
        })
        if primary_location is None:
            primary_location = "modelscope"
    
    return {
        "found": len(locations) > 0,
        "locations": locations,
        "primary": primary_location,
    }


def _download_from_modelscope(model_id: str, *, timeout: int = 300):
    """纯 ModelScope 下载，yield SSE 事件."""
    import requests as _requests

    info = MODEL_CATALOG[model_id]
    dest = _model_local_path(model_id)
    repo = info["ms_repo"]

    yield {"status": "connecting", "source": "modelscope", "repo": repo}

    if info["download_type"] == "snapshot":
        dest.mkdir(parents=True, exist_ok=True)

        # 尝试 modelscope SDK
        try:
            from modelscope import snapshot_download as ms_snapshot
            yield {"status": "downloading", "progress": 0}
            ms_snapshot(repo, local_dir=str(dest), local_dir_use_symlinks=False)
            yield {"status": "completed", "source": "modelscope"}
            return
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"modelscope SDK 失败: {e}")

        # 直接 HTTP: 先拿文件列表
        yield {"status": "downloading", "progress": 0}
        try:
            r = _requests.get(f"{MS_BASE}/{repo}/repo/tree?Revision=master", timeout=30)
            tree = r.json().get("Data", []) if r.ok else []
            files = [f["Path"] for f in tree if f.get("Type") == "blob"]
        except Exception:
            files = []

        if not files:
            yield {"status": "failed", "error": "无法获取 ModelScope 文件列表，请检查网络或手动下载"}
            return

        for i, fpath in enumerate(files):
            fdest = dest / fpath
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
        # 单文件下载（MolDetv2 等）
        dest.parent.mkdir(parents=True, exist_ok=True)
        ms_file = info.get("ms_file", "")
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
            with open(dest, "wb") as f:
                for chunk in r.iter_content(262144):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        yield {"status": "downloading", "progress": int(downloaded * 100 / total)}

            yield {"status": "completed", "source": "modelscope"}
        except Exception as e:
            yield {"status": "failed", "error": f"下载失败: {e}"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models() -> dict:
    """列出所有模型及其状态."""
    try:
        result = []
        for mid, info in MODEL_CATALOG.items():
            location = _get_model_location(mid)
            
            # 计算实际下载的大小（如果已下载）
            actual_size_mb = info.get("size_mb", 0)
            if location["found"] and location["locations"]:
                # 使用主位置的大小
                for loc in location["locations"]:
                    if loc["source"] == location["primary"]:
                        actual_size_mb = loc["size_mb"]
                        break
            
            result.append({
                "id": mid,
                "name": info["name"],
                "type": info["type"],
                "description": info.get("description", ""),
                "ms_repo": info.get("ms_repo", ""),
                "hf_repo": info.get("hf_repo", ""),
                "downloaded": location["found"],
                "downloading": _download_tasks.get(mid, False),
                "local_path": str(_model_local_path(mid)),
                "license": info.get("license", "Unknown"),
                "license_url": info.get("license_url", ""),
                "size_mb": info.get("size_mb", 0),  # 预估/官方大小
                "actual_size_mb": actual_size_mb,  # 实际下载大小
                "source_url": info.get("source_url", ""),
                "location": location,
            })
        return {"success": True, "models": result}
    except Exception as e:
        logger.error(f"List models failed: {e}", exc_info=True)
        return {"success": False, "error": f"获取模型列表失败: {e}"}


@router.get("/model-paths")
async def get_model_paths() -> dict:
    """返回所有模型相关的缓存路径."""
    try:
        return {
            "success": True,
            "paths": {
                "mbforge": {
                    "path": str(_get_model_cache_dir()),
                    "exists": _get_model_cache_dir().exists(),
                    "size_mb": _get_dir_size(_get_model_cache_dir()),
                },
                "huggingface": {
                    "path": str(_get_hf_cache_dir()),
                    "env_var": "HF_HOME",
                    "exists": _get_hf_cache_dir().exists(),
                    "size_mb": _get_dir_size(_get_hf_cache_dir()),
                },
                "modelscope": {
                    "path": str(_get_modelscope_cache_dir()),
                    "env_var": "MODELSCOPE_CACHE",
                    "exists": _get_modelscope_cache_dir().exists(),
                    "size_mb": _get_dir_size(_get_modelscope_cache_dir()),
                },
            }
        }
    except Exception as e:
        logger.error(f"Get model paths failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _get_dir_size(path: Path) -> float:
    """计算目录大小（MB）."""
    if not path.exists():
        return 0.0
    try:
        size_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(size_bytes / 1024 / 1024, 1)
    except Exception:
        return 0.0


@router.post("/model-dir")
async def set_model_dir(path: str) -> dict:
    """设置 MBForge 模型缓存目录."""
    try:
        new_path = Path(path).expanduser().absolute()
        
        # 验证路径是否有效
        if not new_path.parent.exists():
            return {"success": False, "error": "父目录不存在"}
        
        # 保存到配置
        cfg = load_global_config()
        cfg.model_cache_dir = str(new_path)
        save_global_config(cfg)
        
        return {
            "success": True,
            "model_dir": str(new_path),
            "message": "模型目录已更新，重启后生效"
        }
    except Exception as e:
        logger.error(f"Set model dir failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/model-dir")
async def get_model_dir() -> dict:
    """返回当前模型下载目录路径."""
    try:
        cfg = load_global_config()
        return {
            "success": True, 
            "model_dir": str(_get_model_cache_dir()),
            "config_dir": cfg.model_cache_dir or "(default)",
        }
    except Exception as e:
        logger.error(f"Get model dir failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/list-downloaded")
async def list_downloaded() -> dict:
    """扫描模型目录，返回所有已下载模型的信息."""
    try:
        cache_dir = _get_model_cache_dir()
        downloaded = []
        if cache_dir.exists():
            for entry in cache_dir.iterdir():
                if not entry.is_dir():
                    # 单文件模型（如 moldetv2-doc.pt）
                    if entry.suffix in (".pt", ".pth", ".onnx"):
                        size_bytes = entry.stat().st_size
                        # 尝试匹配 catalog
                        matched_id = None
                        for mid, info in MODEL_CATALOG.items():
                            if info.get("local_name") == entry.name:
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
                # 目录模型（如 Qwen3-Embedding-0.6B）
                has_weights = any(entry.rglob("*.bin")) or any(entry.rglob("*.safetensors"))
                if has_weights:
                    size_bytes = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    # 尝试匹配 catalog
                    matched_id = None
                    for mid, info in MODEL_CATALOG.items():
                        repo_name = info["ms_repo"].split("/")[-1]
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
    except Exception as e:
        logger.error(f"List downloaded models failed: {e}", exc_info=True)
        return {"success": False, "error": f"扫描已下载模型失败: {e}"}


@router.delete("/delete/{model_id}")
async def delete_model(model_id: str) -> dict:
    """删除已下载的模型."""
    cache_dir = _get_model_cache_dir()

    # 先在 catalog 中查找
    if model_id in MODEL_CATALOG:
        info = MODEL_CATALOG[model_id]
        if info["download_type"] == "file":
            target = cache_dir / info.get("local_name", f"{model_id}.pt")
        else:
            repo_name = info["ms_repo"].split("/")[-1]
            target = cache_dir / repo_name
    else:
        # 尝试作为目录名或文件名
        target = cache_dir / model_id
        if not target.exists():
            target = cache_dir / f"{model_id}.pt"
        if not target.exists():
            return {"success": False, "error": f"未找到模型: {model_id}"}

    if not target.exists():
        return {"success": False, "error": f"模型路径不存在: {target}"}

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"success": True, "deleted": str(target)}
    except Exception as e:
        logger.error(f"删除模型失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/download/{model_id}")
async def download_model(model_id: str):
    if model_id not in MODEL_CATALOG:
        return {"success": False, "error": f"未知模型: {model_id}"}
    if _download_tasks.get(model_id):
        return {"success": False, "error": "该模型正在下载中"}

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
async def model_status(model_id: str) -> dict:
    try:
        if model_id not in MODEL_CATALOG:
            return {"success": False, "error": f"未知模型: {model_id}"}
        location = _get_model_location(model_id)
        return {
            "success": True,
            "model_id": model_id,
            "downloaded": location["found"],
            "downloading": _download_tasks.get(model_id, False),
            "local_path": str(_model_local_path(model_id)),
            "location": location,
        }
    except Exception as e:
        logger.error(f"Model status failed for model_id={model_id}: {e}", exc_info=True)
        return {"success": False, "error": f"查询模型状态失败: {e}"}
