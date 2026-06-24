"""统一资源管理器 — 环境搭建 + 依赖下载 + 运行时检查.

所有外部资源（模型、Python包、二进制工具）的统一注册、检查、下载入口。
- 模型默认使用 ModelScope 下载
- Python 包默认使用清华源
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from platformdirs import user_config_dir

logger = logging.getLogger("mbforge.resource_manager")


# ---------------------------------------------------------------------------
# 读取 Rust 写入的 resolved_paths.json（单一真相源）
# ---------------------------------------------------------------------------

_RESOLVED_PATHS_CACHE: dict[str, str] | None = None
_RESOLVED_PATHS_MTIME: float = 0.0


def _read_resolved_paths() -> dict[str, str] | None:
    """读取 Rust 写入的 resolved_paths.json（按 mtime 失效的轻量缓存）.

    路径必须与 Rust 端 `ProjectDirs::from("", "", "MBForge").config_dir()` 一致，
    否则 Python 永远读不到 Rust 写入的内容（曾因 `.config/MBForge` vs `%APPDATA%/MBForge/config` 不匹配踩坑）。
    """
    global _RESOLVED_PATHS_CACHE, _RESOLVED_PATHS_MTIME

    # 与 Rust 端 `directories::ProjectDirs::from("", "", "MBForge")` 的 config_dir 对齐：
    #   Windows : %APPDATA%\MBForge\config
    #   Linux   : ~/.config/MBForge
    #   macOS   : ~/Library/Application Support/MBForge
    config_dir = Path(user_config_dir(appname="MBForge", appauthor=False, roaming=True)) / "config"
    path = config_dir / "resolved_paths.json"
    if not path.exists():
        return None

    try:
        mtime = path.stat().st_mtime
        if _RESOLVED_PATHS_CACHE is not None and mtime == _RESOLVED_PATHS_MTIME:
            return _RESOLVED_PATHS_CACHE
        with open(path) as f:
            data = json.load(f)
        _RESOLVED_PATHS_CACHE = data
        _RESOLVED_PATHS_MTIME = mtime
        logger.info(f"Loaded resolved paths from {path}: {list(data.keys())}")
        return data
    except Exception as e:
        logger.warning(f"Failed to read resolved_paths.json: {e}")
        return None


def _invalidate_resolved_paths_cache() -> None:
    """使 resolved_paths 缓存强制失效（Rust 刷新后调用）."""
    global _RESOLVED_PATHS_CACHE, _RESOLVED_PATHS_MTIME
    _RESOLVED_PATHS_CACHE = None
    _RESOLVED_PATHS_MTIME = 0.0
    logger.info("Invalidated resolved_paths cache")


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

class ResourceType(str, Enum):
    MODEL = "model"
    PYTHON_PACKAGE = "python_package"
    BINARY = "binary"
    NODE_PACKAGE = "node_package"


class ResourceStatus(str, Enum):
    READY = "ready"          # 已就绪
    NOT_FOUND = "not_found"  # 未下载/未安装
    PARTIAL = "partial"      # 部分就绪（如目录存在但缺文件）
    ERROR = "error"          # 检查出错
    DOWNLOADING = "downloading"  # 下载中


@dataclass
class ResourceInfo:
    """资源目录条目."""
    id: str
    name: str
    type: ResourceType
    description: str
    size_mb: float = 0
    license: str = ""
    license_url: str = ""
    # 模型专用
    ms_repo: str = ""          # ModelScope 仓库 ID
    hf_repo: str = ""          # HuggingFace 仓库 ID（备用/元数据）
    download_type: str = "snapshot"  # snapshot | file
    ms_file: str = ""          # 单文件下载时的远程文件名
    local_name: str = ""       # 本地文件名
    source_url: str = ""       # 项目主页
    allow_patterns: list[str] = field(default_factory=list)  # snapshot 下载时仅匹配的文件模式
    files: list[str] = field(default_factory=list)  # 资源包含的具体文件列表（与 Rust 端保持一致）
    # Python 包专用
    pip_name: str = ""         # pip 包名
    import_name: str = ""      # import 名（与 pip 名不同时）
    mirror: str = ""           # 镜像源 URL


@dataclass
class ResourceStatusResult:
    """单个资源的检查结果."""
    id: str
    name: str
    type: ResourceType
    status: ResourceStatus
    local_path: str = ""
    size_mb: float = 0
    version: str = ""
    error: str = ""


@dataclass
class EnvironmentReport:
    """全量环境检查报告."""
    python_version: str = ""
    gpu_available: bool = False
    gpu_name: str = ""
    cuda_version: str = ""
    resources: list[ResourceStatusResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        ready = sum(1 for r in self.resources if r.status == ResourceStatus.READY)
        total = len(self.resources)
        return f"{ready}/{total} resources ready"


# ---------------------------------------------------------------------------
# 资源目录（唯一真相源）
# ---------------------------------------------------------------------------

# 清华 PyPI 镜像
TSINGHUA_PIP = "https://pypi.tuna.tsinghua.edu.cn/simple"

RESOURCE_CATALOG: dict[str, ResourceInfo] = {
    # ──── 模型（ModelScope 下载）────
    "embedding": ResourceInfo(
        id="embedding",
        name="Qwen3-Embedding-0.6B",
        type=ResourceType.MODEL,
        description="通义千问3 嵌入模型 (0.6B) — 语义检索",
        size_mb=1152,
        license="Apache-2.0",
        license_url="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/main/LICENSE",
        ms_repo="Qwen/Qwen3-Embedding-0.6B",
        hf_repo="Qwen/Qwen3-Embedding-0.6B",
        download_type="snapshot",
        local_name="Qwen3-Embedding-0.6B",
        source_url="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
        allow_patterns=["*.safetensors", "*.json", "*.txt", "tokenizer*"],
    ),
    "reranker": ResourceInfo(
        id="reranker",
        name="Qwen3-Reranker-0.6B",
        type=ResourceType.MODEL,
        description="通义千问3 重排序模型 (0.6B) — 结果精排",
        size_mb=1152,
        license="Apache-2.0",
        license_url="https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/blob/main/LICENSE",
        ms_repo="Qwen/Qwen3-Reranker-0.6B",
        hf_repo="Qwen/Qwen3-Reranker-0.6B",
        download_type="snapshot",
        local_name="Qwen3-Reranker-0.6B",
        source_url="https://huggingface.co/Qwen/Qwen3-Reranker-0.6B",
        allow_patterns=["*.safetensors", "*.json", "*.txt", "tokenizer*"],
    ),
    "moldet": ResourceInfo(
        id="moldet",
        name="MolDetv2",
        type=ResourceType.MODEL,
        description="MolDetv2 分子结构检测 (YOLO, doc + general)",
        size_mb=11,
        license="Apache-2.0",
        ms_repo="UniParser/MolDetv2",
        download_type="snapshot",
        local_name="MolDetv2",
        allow_patterns=["*.pt", "*.onnx", "*.json"],
        files=["doc/moldet_v2_yolo11n_960_doc.pt", "general/moldet_v2_yolo11n_640_general.pt"],
    ),
    "molscribe": ResourceInfo(
        id="molscribe",
        name="MolScribe",
        type=ResourceType.MODEL,
        description="MolScribe 分子图像 → SMILES",
        size_mb=6186,
        license="MIT",
        license_url="https://github.com/thomas0809/MolScribe/blob/main/LICENSE",
        ms_repo="polyai/MolScribe",
        hf_repo="polyai/MolScribe",
        download_type="snapshot",
        local_name="MolScribe",
        source_url="https://github.com/thomas0809/MolScribe",
        allow_patterns=["*.pth", "*.safetensors", "*.json", "*.txt", "tokenizer*", "vocab*"],
        files=["swin_base_char_aux_1m680k.pth"],
    ),
    # ──── Python 包（清华源）────
    "rdkit": ResourceInfo(
        id="rdkit",
        name="RDKit",
        type=ResourceType.PYTHON_PACKAGE,
        description="分子信息学: SMILES 解析、分子属性计算",
        license="BSD-3",
        pip_name="rdkit",
        import_name="rdkit",
        mirror=TSINGHUA_PIP,
    ),
    "torch": ResourceInfo(
        id="torch",
        name="PyTorch",
        type=ResourceType.PYTHON_PACKAGE,
        description="深度学习框架 (CUDA 12.8)",
        license="BSD-3",
        pip_name="torch",
        import_name="torch",
        mirror=TSINGHUA_PIP,
    ),
    "sentence_transformers": ResourceInfo(
        id="sentence_transformers",
        name="Sentence Transformers",
        type=ResourceType.PYTHON_PACKAGE,
        description="文本嵌入 + CrossEncoder 框架",
        pip_name="sentence-transformers",
        import_name="sentence_transformers",
        mirror=TSINGHUA_PIP,
    ),
    "transformers": ResourceInfo(
        id="transformers",
        name="Transformers",
        type=ResourceType.PYTHON_PACKAGE,
        description="Hugging Face 模型加载框架",
        pip_name="transformers",
        import_name="transformers",
        mirror=TSINGHUA_PIP,
    ),
    "ultralytics": ResourceInfo(
        id="ultralytics",
        name="Ultralytics",
        type=ResourceType.PYTHON_PACKAGE,
        description="YOLO 目标检测框架 (MolDet 依赖)",
        license="AGPL-3.0",
        pip_name="ultralytics",
        import_name="ultralytics",
        mirror=TSINGHUA_PIP,
    ),
}


# ---------------------------------------------------------------------------
# 检查函数
# ---------------------------------------------------------------------------

def _get_model_cache_dir() -> Path:
    """获取模型缓存目录."""
    from mbforge.utils.constants import get_model_cache_dir
    return Path(get_model_cache_dir())


def _has_weights(path: Path) -> bool:
    """检查目录中是否包含模型权重文件."""
    if not path.exists():
        return False
    return (
        any(path.rglob("*.bin"))
        or any(path.rglob("*.safetensors"))
        or any(path.rglob("*.pt"))
        or any(path.rglob("*.pth"))
    )


def _dir_size(path: Path) -> float:
    """计算目录中所有文件的总大小（MB）."""
    return round(
        sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024, 1
    )


def _check_model_snapshot(info: ResourceInfo) -> ResourceStatusResult:
    """检查 snapshot 类型模型是否已下载.

    按 ENV 优先级顺序搜索:
    1. MBFORGE_MODEL_CACHE_DIR (通过 _get_model_cache_dir)
    2. HF_HOME
    3. MODELSCOPE_CACHE (env + 默认)
    4. TORCH_HOME
    """
    repo_name = info.ms_repo.split("/")[-1]
    ms_repo_name_encoded = repo_name.replace(".", "___")
    ms_org = info.ms_repo.split("/")[0]  # e.g. "Qwen"

    # 1. MBForge 缓存目录
    cache_dir = _get_model_cache_dir()
    local_dir = cache_dir / repo_name
    if _has_weights(local_dir):
        return ResourceStatusResult(
            id=info.id, name=info.name, type=info.type,
            status=ResourceStatus.READY,
            local_path=str(local_dir),
            size_mb=_dir_size(local_dir),
        )

    # 2. HuggingFace 缓存
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        hf_dir = Path(hf_home) / repo_name
        if _has_weights(hf_dir):
            return ResourceStatusResult(
                id=info.id, name=info.name, type=info.type,
                status=ResourceStatus.READY,
                local_path=str(hf_dir),
                size_mb=_dir_size(hf_dir),
            )

    # 3. ModelScope 缓存（env > 默认）
    ms_cache_candidates = []
    env_ms = os.environ.get("MODELSCOPE_CACHE", "")
    if env_ms:
        ms_cache_candidates.append(Path(env_ms))
    ms_cache_candidates.append(Path.home() / ".cache" / "modelscope")

    for ms_root in ms_cache_candidates:
        for subdir in ["", "models", "hub", "hub/models"]:
            for name in [repo_name, ms_repo_name_encoded]:
                ms_dir = ms_root / subdir / ms_org / name
                if _has_weights(ms_dir):
                    return ResourceStatusResult(
                        id=info.id, name=info.name, type=info.type,
                        status=ResourceStatus.READY,
                        local_path=str(ms_dir),
                        size_mb=_dir_size(ms_dir),
                    )

    # 4. TORCH_HOME
    torch_home = os.environ.get("TORCH_HOME", "")
    if torch_home:
        torch_dir = Path(torch_home) / repo_name
        if _has_weights(torch_dir):
            return ResourceStatusResult(
                id=info.id, name=info.name, type=info.type,
                status=ResourceStatus.READY,
                local_path=str(torch_dir),
                size_mb=_dir_size(torch_dir),
            )

    return ResourceStatusResult(
        id=info.id, name=info.name, type=info.type,
        status=ResourceStatus.NOT_FOUND,
    )


def _check_model_file(info: ResourceInfo) -> ResourceStatusResult:
    """检查单文件/snapshot 类型模型是否已下载.

    搜索顺序: MBForge cache → HF_HOME → MODELSCOPE_CACHE → TORCH_HOME
    每个目录下同时搜索直接文件、子目录和 ModelScope 新旧 SDK 布局。
    """
    repo_name = info.ms_repo.split("/")[-1]
    ms_org = info.ms_repo.split("/")[0]

    def _search_in(base: Path) -> ResourceStatusResult | None:
        if not base.exists():
            return None
        # 1. base/<local_name>（精确文件）
        local_name = info.local_name or f"{info.id}.pt"
        path = base / local_name
        if path.is_file() and path.stat().st_size > 0:
            return ResourceStatusResult(
                id=info.id, name=info.name, type=info.type,
                status=ResourceStatus.READY,
                local_path=str(path),
                size_mb=round(path.stat().st_size / 1024 / 1024, 1),
            )
        # 2. base/<repo_name>/（MBForge 子目录布局：moldetv2-doc/）
        for subdir_name in [repo_name, local_name, info.id]:
            subdir = base / subdir_name
            if subdir.is_dir():
                for f in subdir.iterdir():
                    if f.is_file() and f.suffix in (".pt", ".pth", ".bin", ".safetensors"):
                        return ResourceStatusResult(
                            id=info.id, name=info.name, type=info.type,
                            status=ResourceStatus.READY,
                            local_path=str(f),
                            size_mb=round(f.stat().st_size / 1024 / 1024, 1),
                        )
        # 3. base/ 下直接找权重文件（兜底，限定 1 层）
        for f in base.iterdir():
            if f.is_file() and f.suffix in (".pt", ".pth", ".bin", ".safetensors"):
                return ResourceStatusResult(
                    id=info.id, name=info.name, type=info.type,
                    status=ResourceStatus.READY,
                    local_path=str(f),
                    size_mb=round(f.stat().st_size / 1024 / 1024, 1),
                )
        return None

    def _search_modelscope(ms_root: Path) -> ResourceStatusResult | None:
        """搜索 ModelScope 缓存（新旧 SDK 布局）."""
        if not ms_root.exists():
            return None
        # 新 SDK: hub/models/{org}/{repo}/
        for subdir in ["models", "hub/models"]:
            d = ms_root / subdir / ms_org / repo_name
            result = _search_in(d)
            if result:
                return result
        # 旧 SDK: hub/{org}/{repo}/ （dots→___）
        encoded = repo_name.replace(".", "___")
        for name in [repo_name, encoded]:
            d = ms_root / "hub" / ms_org / name
            result = _search_in(d)
            if result:
                return result
        return None

    # 1. MBForge 缓存
    result = _search_in(_get_model_cache_dir())
    if result:
        return result

    # 2. HF_HOME
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        result = _search_in(Path(hf_home))
        if result:
            return result

    # 3. MODELSCOPE_CACHE
    env_ms = os.environ.get("MODELSCOPE_CACHE", "")
    if env_ms:
        result = _search_modelscope(Path(env_ms))
        if result:
            return result
    result = _search_modelscope(Path.home() / ".cache" / "modelscope")
    if result:
        return result

    # 4. TORCH_HOME
    torch_home = os.environ.get("TORCH_HOME", "")
    if torch_home:
        result = _search_in(Path(torch_home))
        if result:
            return result
            return result

    return ResourceStatusResult(
        id=info.id, name=info.name, type=info.type,
        status=ResourceStatus.NOT_FOUND,
    )


def _check_python_package(info: ResourceInfo) -> ResourceStatusResult:
    """检查 Python 包是否已安装."""
    import_name = info.import_name or info.pip_name
    try:
        mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", "")
        return ResourceStatusResult(
            id=info.id, name=info.name, type=info.type,
            status=ResourceStatus.READY,
            version=ver,
        )
    except ImportError:
        return ResourceStatusResult(
            id=info.id, name=info.name, type=info.type,
            status=ResourceStatus.NOT_FOUND,
        )


# ---------------------------------------------------------------------------
# 下载函数
# ---------------------------------------------------------------------------

def _download_model_from_modelscope(info: ResourceInfo, callback: Callable[[dict], None] | None = None) -> bool:
    """从 ModelScope 下载模型. 返回是否成功."""
    cache_dir = _get_model_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    ms_base = "https://modelscope.cn/api/v1/models"

    def _emit(event: dict):
        if callback:
            callback(event)
        logger.info("Download event: %s", event)

    _emit({"status": "connecting", "source": "modelscope", "repo": info.ms_repo})

    if info.download_type == "snapshot":
        dest = cache_dir / info.ms_repo.split("/")[-1]
        dest.mkdir(parents=True, exist_ok=True)

        # 尝试 modelscope SDK
        try:
            from modelscope import snapshot_download as ms_snapshot
            _emit({"status": "downloading", "progress": 0})
            try:
                ms_snapshot(info.ms_repo, local_dir=str(dest), local_dir_use_symlinks=False, allow_patterns=info.allow_patterns or None)
            except TypeError:
                # 新版 modelscope 不支持 local_dir_use_symlinks
                ms_snapshot(info.ms_repo, local_dir=str(dest), allow_patterns=info.allow_patterns or None)
            _emit({"status": "completed", "source": "modelscope"})
            return True
        except ImportError:
            pass
        except Exception as e:
            logger.warning("modelscope SDK 失败: %s", e)

        # 直接 HTTP 下载
        import fnmatch as _fnmatch

        import requests as _requests
        _emit({"status": "downloading", "progress": 0})
        try:
            r = _requests.get(f"{ms_base}/{info.ms_repo}/repo/tree?Revision=master", timeout=30)
            tree = r.json().get("Data", []) if r.ok else []
            files = [f["Path"] for f in tree if f.get("Type") == "blob"]
        except Exception:
            files = []

        if info.allow_patterns:
            files = [f for f in files if any(_fnmatch.fnmatch(f, p) for p in info.allow_patterns)]

        if not files:
            _emit({"status": "failed", "error": "无法获取 ModelScope 文件列表"})
            return False

        for i, fpath in enumerate(files):
            fdest = dest / fpath
            fdest.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = _requests.get(
                    f"{ms_base}/{info.ms_repo}/repo",
                    params={"Revision": "master", "FilePath": fpath},
                    timeout=300, stream=True,
                )
                r.raise_for_status()
                fsize = int(r.headers.get("Content-Length", 0))
                got = 0
                with open(fdest, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                        got += len(chunk)
                        if fsize > 0:
                            _emit({
                                "status": "downloading",
                                "file": fpath,
                                "file_progress": int(got * 100 / fsize),
                                "file_index": i + 1,
                                "total_files": len(files),
                            })
            except Exception as e:
                _emit({"status": "failed", "error": f"下载 {fpath} 失败: {e}"})
                return False

        _emit({"status": "completed", "source": "modelscope"})
        return True

    else:
        # 单文件下载
        dest = cache_dir / (info.local_name or f"{info.id}.pt")
        dest.parent.mkdir(parents=True, exist_ok=True)
        import requests as _requests
        try:
            r = _requests.get(
                f"{ms_base}/{info.ms_repo}/repo",
                params={"Revision": "master", "FilePath": info.ms_file},
                timeout=300, stream=True,
            )
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(262144):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        _emit({"status": "downloading", "progress": int(downloaded * 100 / total)})
            _emit({"status": "completed", "source": "modelscope"})
            return True
        except Exception as e:
            _emit({"status": "failed", "error": str(e)})
            return False


def _install_python_package(info: ResourceInfo, callback: Callable[[dict], None] | None = None) -> bool:
    """通过 pip 安装 Python 包. 返回是否成功."""
    def _emit(event: dict):
        if callback:
            callback(event)

    pip_name = info.pip_name
    mirror = info.mirror or TSINGHUA_PIP
    cmd = [sys.executable, "-m", "pip", "install", pip_name, "-i", mirror]

    _emit({"status": "downloading", "progress": 0})
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            _emit({"status": "completed"})
            return True
        else:
            _emit({"status": "failed", "error": result.stderr[-500:] if result.stderr else "Unknown error"})
            return False
    except subprocess.TimeoutExpired:
        _emit({"status": "failed", "error": "安装超时"})
        return False
    except Exception as e:
        _emit({"status": "failed", "error": str(e)})
        return False


# ---------------------------------------------------------------------------
# 检查分发
# ---------------------------------------------------------------------------

def _check_resource(resource_id: str) -> ResourceStatusResult:
    """检查单个资源的状态.

    优先读取 Rust 写入的 resolved_paths.json（单一真相源），
    未命中时回退到本地文件系统扫描。
    """
    info = RESOURCE_CATALOG.get(resource_id)
    if info is None:
        return ResourceStatusResult(
            id=resource_id, name=resource_id, type=ResourceType.MODEL,
            status=ResourceStatus.ERROR, error=f"未知资源: {resource_id}",
        )

    # 1. 优先读取 Rust 解析结果（snapshot/file 模型均适用）
    if info.type == ResourceType.MODEL:
        resolved = _read_resolved_paths()
        if resolved and resource_id in resolved:
            path = Path(resolved[resource_id])
            if path.exists():
                # 计算大小
                try:
                    if path.is_file():
                        size_mb = round(path.stat().st_size / 1024 / 1024, 1)
                    else:
                        size_mb = round(
                            sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024, 1
                        )
                except Exception:
                    size_mb = 0.0
                return ResourceStatusResult(
                    id=info.id, name=info.name, type=info.type,
                    status=ResourceStatus.READY,
                    local_path=str(path),
                    size_mb=size_mb,
                )
            # 路径已失效（文件被删除），继续扫描
            logger.warning(f"Resolved path for {resource_id} no longer exists: {path}")

    # 2. 回退到本地扫描
    try:
        if info.type == ResourceType.MODEL:
            if info.download_type == "file":
                return _check_model_file(info)
            else:
                return _check_model_snapshot(info)
        elif info.type == ResourceType.PYTHON_PACKAGE:
            return _check_python_package(info)
        elif info.type == ResourceType.BINARY:
            return ResourceStatusResult(
                id=resource_id, name=info.name, type=info.type,
                status=ResourceStatus.NOT_FOUND,
            )
        else:
            return ResourceStatusResult(
                id=resource_id, name=info.name, type=info.type,
                status=ResourceStatus.NOT_FOUND,
            )
    except Exception as e:
        return ResourceStatusResult(
            id=resource_id, name=info.name, type=info.type,
            status=ResourceStatus.ERROR, error=str(e),
        )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

class ResourceManager:
    """统一资源管理器."""

    catalog = RESOURCE_CATALOG

    @classmethod
    def check(cls, resource_id: str) -> ResourceStatusResult:
        """检查单个资源状态."""
        return _check_resource(resource_id)

    @classmethod
    def check_all(cls) -> EnvironmentReport:
        """全量环境检查."""
        report = EnvironmentReport()

        # Python 版本
        report.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # GPU
        try:
            import torch
            if torch.cuda.is_available():
                report.gpu_available = True
                report.gpu_name = torch.cuda.get_device_name(0)
                report.cuda_version = torch.version.cuda
        except ImportError:
            pass

        if not report.gpu_available:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    report.gpu_available = True
                    report.gpu_name = parts[0].strip() if parts else ""
                    if len(parts) > 1:
                        report.cuda_version = parts[1].strip()
            except (subprocess.SubprocessError, FileNotFoundError):
                pass

        # 逐个检查资源
        for resource_id in RESOURCE_CATALOG:
            report.resources.append(_check_resource(resource_id))

        return report

    @classmethod
    def ensure(cls, resource_id: str, callback: Callable[[dict], None] | None = None) -> ResourceStatusResult:
        """确保资源可用（缺失则下载/安装）."""
        status = cls.check(resource_id)
        if status.status == ResourceStatus.READY:
            return status

        info = RESOURCE_CATALOG.get(resource_id)
        if info is None:
            return status

        success = False
        if info.type == ResourceType.MODEL:
            success = _download_model_from_modelscope(info, callback)
        elif info.type == ResourceType.PYTHON_PACKAGE:
            success = _install_python_package(info, callback)
        elif info.type == ResourceType.BINARY:
            if callback:
                callback({"status": "failed", "error": f"二进制资源 {info.name} 需要手动安装，请参考项目文档"})
            return status

        if success:
            return cls.check(resource_id)
        return status

    @classmethod
    def get_model_path(cls, resource_id: str) -> Path | None:
        """获取已下载模型的本地路径（供模型加载使用）.

        优先读取 Rust 写入的 resolved_paths.json，未命中时回退到扫描。
        """
        resolved = _read_resolved_paths()
        if resolved and resource_id in resolved:
            path = Path(resolved[resource_id])
            if path.exists():
                return path
        # 回退
        status = cls.check(resource_id)
        if status.status == ResourceStatus.READY and status.local_path:
            return Path(status.local_path)
        return None

    @classmethod
    def get_molscribe_path(cls) -> Path | None:
        """获取 MolScribe 模型路径（兼容旧接口）."""
        resolved = _read_resolved_paths()
        if resolved and "molscribe" in resolved:
            path = Path(resolved["molscribe"])
            if path.exists():
                ckpt = path / "swin_base_char_aux_1m680k.pth"
                if ckpt.exists():
                    return ckpt
                if any(path.glob("*.safetensors")):
                    return path
        # 回退
        path = cls.get_model_path("molscribe")
        if path and path.exists():
            ckpt = path / "swin_base_char_aux_1m680k.pth"
            if ckpt.exists():
                return ckpt
            if any(path.glob("*.safetensors")):
                return path
        return None

    @classmethod
    def resolve_model_for_backend(cls, resource_id: str, subpath: str | None = None) -> Path | None:
        """后端统一入口：解析模型路径，找不到返回 None.

        所有 Python 后端（moldet、molscribe）应使用此方法
        而非自行实现路径搜索逻辑。
        返回值：
        - snapshot 类型：返回包含权重文件的目录
        - file 类型：返回具体权重文件路径
        - subpath 指定时：返回 `<resolved_dir>/<subpath>`（用于多文件资源的子文件定位）
        """
        # 1. Rust resolved_paths（最快）
        resolved = _read_resolved_paths()
        if resolved and resource_id in resolved:
            path = Path(resolved[resource_id])
            if path.exists():
                if subpath:
                    full = path / subpath
                    return full if full.exists() else None
                return path
        # 2. Python 侧扫描
        info = RESOURCE_CATALOG.get(resource_id)
        status = cls.check(resource_id)
        if status.status == ResourceStatus.READY and status.local_path:
            p = Path(status.local_path)
            if info and info.download_type == "snapshot":
                # snapshot 类型：返回目录（让调用方自己找具体文件）
                base = p.parent if p.is_file() else p
                if subpath:
                    full = base / subpath
                    return full if full.exists() else None
                return base
            return p
        return None
