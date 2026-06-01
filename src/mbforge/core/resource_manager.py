"""统一资源管理器 — 环境搭建 + 依赖下载 + 运行时检查.

所有外部资源（模型、Python包、二进制工具）的统一注册、检查、下载入口。
- 模型默认使用 ModelScope 下载
- Python 包默认使用清华源
"""

from __future__ import annotations

import importlib
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("mbforge.resource_manager")


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
        source_url="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
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
        source_url="https://huggingface.co/Qwen/Qwen3-Reranker-0.6B",
    ),
    "moldet": ResourceInfo(
        id="moldet",
        name="MolDetv2",
        type=ResourceType.MODEL,
        description="MolDetv2 分子结构检测 (YOLO)",
        size_mb=25,
        license="Apache-2.0",
        license_url="https://huggingface.co/yujieq/MolDetect/blob/main/LICENSE",
        ms_repo="yujieq/MolDetect",
        hf_repo="yujieq/MolDetect",
        download_type="file",
        ms_file="best.pt",
        local_name="moldetv2-doc.pt",
        source_url="https://huggingface.co/yujieq/MolDetect",
    ),
    "molscribe": ResourceInfo(
        id="molscribe",
        name="MolScribe",
        type=ResourceType.MODEL,
        description="MolScribe 分子图像 → SMILES",
        size_mb=6186,
        license="MIT",
        license_url="https://github.com/thomas0809/MolScribe/blob/main/LICENSE",
        ms_repo="yujieq/MolScribe",
        hf_repo="yujieq/MolScribe",
        download_type="snapshot",
        source_url="https://github.com/thomas0809/MolScribe",
    ),
    # ──── Python 包（清华源）────
    "rdkit": ResourceInfo(
        id="rdkit",
        name="RDKit",
        type=ResourceType.PYTHON_PACKAGE,
        description="分子信息学: SMILES 解析、分子属性计算",
        pip_name="rdkit",
        import_name="rdkit",
        mirror=TSINGHUA_PIP,
    ),
    "torch": ResourceInfo(
        id="torch",
        name="PyTorch",
        type=ResourceType.PYTHON_PACKAGE,
        description="深度学习框架 (CUDA 12.8)",
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
        pip_name="ultralytics",
        import_name="ultralytics",
        mirror=TSINGHUA_PIP,
    ),
    "chromadb": ResourceInfo(
        id="chromadb",
        name="ChromaDB",
        type=ResourceType.PYTHON_PACKAGE,
        description="向量数据库 (知识库)",
        pip_name="chromadb",
        import_name="chromadb",
        mirror=TSINGHUA_PIP,
    ),
    # ──── 二进制工具 ────
    "pdfium": ResourceInfo(
        id="pdfium",
        name="PDFium",
        type=ResourceType.BINARY,
        description="PDF 渲染引擎 (Rust 侧编译依赖)",
    ),
}


# ---------------------------------------------------------------------------
# 检查函数
# ---------------------------------------------------------------------------

def _get_model_cache_dir() -> Path:
    """获取模型缓存目录."""
    from mbforge.utils.constants import get_model_cache_dir
    return Path(get_model_cache_dir())


def _check_model_snapshot(info: ResourceInfo) -> ResourceStatusResult:
    """检查 snapshot 类型模型是否已下载."""
    cache_dir = _get_model_cache_dir()
    repo_name = info.ms_repo.split("/")[-1]

    # 1. MBForge 缓存目录
    local_dir = cache_dir / repo_name
    if local_dir.exists():
        has_weights = (
            any(local_dir.rglob("*.bin"))
            or any(local_dir.rglob("*.safetensors"))
            or any(local_dir.rglob("*.pt"))
            or any(local_dir.rglob("*.pth"))
        )
        if has_weights:
            size = sum(f.stat().st_size for f in local_dir.rglob("*") if f.is_file())
            return ResourceStatusResult(
                id=info.id, name=info.name, type=info.type,
                status=ResourceStatus.READY,
                local_path=str(local_dir),
                size_mb=round(size / 1024 / 1024, 1),
            )

    # 2. HuggingFace 缓存
    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        hf_dir = Path(hf_home) / repo_name
        if hf_dir.exists() and (any(hf_dir.rglob("*.bin")) or any(hf_dir.rglob("*.safetensors"))):
            size = sum(f.stat().st_size for f in hf_dir.rglob("*") if f.is_file())
            return ResourceStatusResult(
                id=info.id, name=info.name, type=info.type,
                status=ResourceStatus.READY,
                local_path=str(hf_dir),
                size_mb=round(size / 1024 / 1024, 1),
            )

    # 3. ModelScope 缓存（目录名中 . 被替换为 ___，且在 models/ 子目录下）
    ms_repo_name_encoded = repo_name.replace(".", "___")
    ms_org = info.ms_repo.split("/")[0]  # e.g. "Qwen"
    ms_cache_candidates = []
    # 用户配置的 MODELSCOPE_CACHE
    env_ms = os.environ.get("MODELSCOPE_CACHE", "")
    if env_ms:
        ms_cache_candidates.append(Path(env_ms))
    # 默认 ModelScope 缓存路径
    ms_cache_candidates.append(Path.home() / ".cache" / "modelscope")

    for ms_root in ms_cache_candidates:
        for subdir in ["", "models", "hub/models"]:
            for name in [repo_name, ms_repo_name_encoded]:
                ms_dir = ms_root / subdir / ms_org / name
                if ms_dir.exists() and (any(ms_dir.rglob("*.bin")) or any(ms_dir.rglob("*.safetensors"))):
                    size = sum(f.stat().st_size for f in ms_dir.rglob("*") if f.is_file())
                    return ResourceStatusResult(
                        id=info.id, name=info.name, type=info.type,
                        status=ResourceStatus.READY,
                        local_path=str(ms_dir),
                        size_mb=round(size / 1024 / 1024, 1),
                    )

    return ResourceStatusResult(
        id=info.id, name=info.name, type=info.type,
        status=ResourceStatus.NOT_FOUND,
    )


def _check_model_file(info: ResourceInfo) -> ResourceStatusResult:
    """检查单文件类型模型是否已下载."""
    cache_dir = _get_model_cache_dir()
    local_name = info.local_name or f"{info.id}.pt"
    path = cache_dir / local_name
    if path.exists() and path.stat().st_size > 0:
        return ResourceStatusResult(
            id=info.id, name=info.name, type=info.type,
            status=ResourceStatus.READY,
            local_path=str(path),
            size_mb=round(path.stat().st_size / 1024 / 1024, 1),
        )
    # 也检查子目录
    subdir = cache_dir / info.ms_repo.split("/")[-1]
    if subdir.exists():
        for f in subdir.iterdir():
            if f.is_file() and f.suffix in (".pt", ".pth", ".onnx"):
                return ResourceStatusResult(
                    id=info.id, name=info.name, type=info.type,
                    status=ResourceStatus.READY,
                    local_path=str(f),
                    size_mb=round(f.stat().st_size / 1024 / 1024, 1),
                )
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


def _check_pdfium() -> ResourceStatusResult:
    """检查 PDFium 是否已设置."""
    # 检查 Rust vendor 目录
    project_root = Path(__file__).resolve().parent.parent.parent
    pdfium_lib = project_root / "src-tauri" / "vendor" / "pdfium" / "release" / "lib"
    if pdfium_lib.exists():
        libs = list(pdfium_lib.glob("*"))
        if libs:
            return ResourceStatusResult(
                id="pdfium", name="PDFium", type=ResourceType.BINARY,
                status=ResourceStatus.READY,
                local_path=str(pdfium_lib),
            )
    # 检查环境变量
    env_path = os.environ.get("PDFIUM_LIB_PATH", "")
    if env_path and Path(env_path).exists():
        return ResourceStatusResult(
            id="pdfium", name="PDFium", type=ResourceType.BINARY,
            status=ResourceStatus.READY,
            local_path=env_path,
        )
    return ResourceStatusResult(
        id="pdfium", name="PDFium", type=ResourceType.BINARY,
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
            ms_snapshot(info.ms_repo, local_dir=str(dest), local_dir_use_symlinks=False)
            _emit({"status": "completed", "source": "modelscope"})
            return True
        except ImportError:
            pass
        except Exception as e:
            logger.warning("modelscope SDK 失败: %s", e)

        # 直接 HTTP 下载
        import requests as _requests
        _emit({"status": "downloading", "progress": 0})
        try:
            r = _requests.get(f"{ms_base}/{info.ms_repo}/repo/tree?Revision=master", timeout=30)
            tree = r.json().get("Data", []) if r.ok else []
            files = [f["Path"] for f in tree if f.get("Type") == "blob"]
        except Exception:
            files = []

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
    """检查单个资源的状态."""
    info = RESOURCE_CATALOG.get(resource_id)
    if info is None:
        return ResourceStatusResult(
            id=resource_id, name=resource_id, type=ResourceType.MODEL,
            status=ResourceStatus.ERROR, error=f"未知资源: {resource_id}",
        )

    try:
        if info.type == ResourceType.MODEL:
            if info.download_type == "file":
                return _check_model_file(info)
            else:
                return _check_model_snapshot(info)
        elif info.type == ResourceType.PYTHON_PACKAGE:
            return _check_python_package(info)
        elif info.type == ResourceType.BINARY:
            if resource_id == "pdfium":
                return _check_pdfium()
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

        if success:
            return cls.check(resource_id)
        return status

    @classmethod
    def get_model_path(cls, resource_id: str) -> Path | None:
        """获取已下载模型的本地路径（供模型加载使用）."""
        status = cls.check(resource_id)
        if status.status == ResourceStatus.READY and status.local_path:
            return Path(status.local_path)
        return None

    @classmethod
    def get_molscribe_path(cls) -> Path | None:
        """获取 MolScribe 模型路径（兼容旧接口）."""
        path = cls.get_model_path("molscribe")
        if path and path.exists():
            # 检查是否包含 checkpoint 文件
            ckpt = path / "swin_base_char_aux_1m680k.pth"
            if ckpt.exists():
                return ckpt
            # 检查是否包含 safetensors
            if any(path.glob("*.safetensors")):
                return path
        return None
