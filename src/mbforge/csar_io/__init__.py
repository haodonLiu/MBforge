"""分子文件的输入/输出处理模块.

本模块提供分子数据的读取和写入功能，支持多种文件格式:
- SDF (Structure Data File)
- Excel (.xlsx, .xls)
- CSV

主要类:
    MoleculeReader: 分子读取器，支持自动检测文件格式
    MoleculeWriter: 分子写入器，可导出为多种格式
    
异常类:
    MoleculeReadError: 读取错误
    MoleculeWriteError: 写入错误
"""

# 从子模块导入主要类和异常
from .api_client import (  # API 客户端
    APIClientError,
    ChemicalAPIClient,
    CompoundInfo,
    CompoundProperties,
    NCICIRClient,
    PubChemClient,
)
from .cas_resolver import CASResolver, CASResolverError  # CAS 号解析器和异常
from .reader import MoleculeReader, MoleculeReadError  # 分子读取器和读取异常
from .writer import MoleculeWriter, MoleculeWriteError  # 分子写入器和写入异常
from ..molecules.schema import Molecule, MoleculeBatch  # 统一数据契约

# 模块公开接口
__all__ = [
    # API 客户端
    "PubChemClient",
    "NCICIRClient",
    "ChemicalAPIClient",
    "CompoundProperties",
    "CompoundInfo",
    "APIClientError",
    # CAS 解析
    "CASResolver",
    "CASResolverError",
    # IO
    "MoleculeReader",
    "MoleculeReadError",
    "MoleculeWriter",
    "MoleculeWriteError",
    # 数据契约
    "Molecule",
    "MoleculeBatch",
]
