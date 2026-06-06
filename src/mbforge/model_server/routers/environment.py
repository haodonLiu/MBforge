"""环境检测路由 - 检测可用的计算化学工具."""

from __future__ import annotations

import importlib
import subprocess
import sys
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class CapabilityStatus(BaseModel):
    name: str
    available: bool
    version: Optional[str] = None
    description: str
    category: str  # "core", "docking", "md", "admet", "ml"


class EnvironmentCheckResult(BaseModel):
    python_version: str
    gpu_available: bool
    gpu_name: Optional[str] = None
    gpu_memory_mb: Optional[int] = None
    cuda_version: Optional[str] = None
    capabilities: list[CapabilityStatus]


def check_package(pkg_name: str) -> tuple[bool, Optional[str]]:
    """检查 Python 包是否可用."""
    try:
        m = importlib.import_module(pkg_name)
        ver = getattr(m, '__version__', None)
        return True, ver
    except ImportError:
        return False, None


# 白名单：仅允许执行的系统命令（防止命令注入）
_ALLOWED_COMMANDS: frozenset[str] = frozenset([
    "vina",
    "nvidia-smi",
])


def check_command(cmd: str) -> bool:
    """检查系统命令是否在 PATH 中.

    Args:
        cmd: 要检查的命令名称。

    Returns:
        True 如果命令存在且可执行，否则 False。

    Raises:
        ValueError: 如果命令不在白名单中（安全防护）。
    """
    if cmd not in _ALLOWED_COMMANDS:
        raise ValueError(f"Command '{cmd}' is not in the allowed list: {_ALLOWED_COMMANDS}")
    try:
        subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@router.get("/check", response_model=EnvironmentCheckResult)
async def check_environment() -> EnvironmentCheckResult:
    """检测当前运行环境的能力.

    (no direct Rust caller; only invoked from the frontend via HTTP)
    """
    
    capabilities: list[CapabilityStatus] = []
    
    # === 核心依赖 ===
    for pkg, version, desc in [
        ("rdkit", None, "分子信息学: SMILES 解析、分子属性计算"),
        ("numpy", None, "数值计算: 数组运算、线性代数"),
        ("scipy", None, "科学计算: 优化、插值、统计"),
        ("pandas", None, "数据分析: 表格处理"),
    ]:
        available, ver = check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg,
            available=available,
            version=ver,
            description=desc,
            category="core"
        ))
    
    # === 分子动力学 ===
    for pkg, desc in [
        ("openmm", "分子动力学模拟 (GPU 加速)"),
    ]:
        available, ver = check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg,
            available=available,
            version=ver,
            description=desc,
            category="md"
        ))
    
    # === 对接工具 ===
    for cmd, pkg, desc in [
        ("vina", "autodock_vina", "分子对接 (命令行)"),
    ]:
        available = check_command(cmd)
        _, ver = check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=cmd,
            available=available,
            version=ver,
            description=desc,
            category="docking"
        ))
    
    # === ADMET ===
    for pkg, desc in [
        ("deepchem", "深度学习 ADMET 预测"),
    ]:
        available, ver = check_package(pkg)
        capabilities.append(CapabilityStatus(
            name=pkg,
            available=available,
            version=ver,
            description=desc,
            category="admet"
        ))
    
    # === GPU 检测 ===
    gpu_available = False
    gpu_name = None
    gpu_memory_mb = None
    cuda_version = None
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory_mb = int(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024)
            cuda_version = torch.version.cuda
    except ImportError:
        pass
    
    # 检查 nvidia-smi 获取更完整的 GPU 信息
    if not gpu_available:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if parts:
                    gpu_available = True
                    gpu_name = parts[0].strip()
                    if len(parts) > 1:
                        mem_str = parts[1].strip().replace(' MiB', '').replace('MiB', '').strip()
                        try:
                            gpu_memory_mb = int(mem_str)
                        except ValueError:
                            pass
                    if len(parts) > 2:
                        cuda_version = parts[2].strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    
    return EnvironmentCheckResult(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
        cuda_version=cuda_version,
        capabilities=capabilities
    )
