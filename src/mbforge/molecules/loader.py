"""molecules/loader.py — 从文件加载分子为统一 dict 格式.

各算法模块的 CLI 入口使用此工具加载 SDF/CSV/SMILES 文件。
输出 List[Dict[str, Any]]，key 包含 "mol" (RDKit Mol) 和 "smiles"。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rdkit import Chem

logger = logging.getLogger(__name__)


def load_molecules_from_file(
    path: Union[str, Path],
    smiles_column: str = "SMILES",
    activity_column: Optional[str] = None,
    name_column: str = "Name",
) -> List[Dict[str, Any]]:
    """从文件加载分子，返回算法模块所需的 dict 列表.

    支持格式:
        - .sdf: 从 SDF 读取分子结构和属性
        - .csv: 读取 CSV 中的 SMILES 列
        - .smi / .smiles: 一行一个 SMILES（可选 tab 分隔名称）

    Args:
        path: 分子文件路径.
        smiles_column: CSV 中 SMILES 所在列名.
        activity_column: CSV 中活性值列名（可选）.
        name_column: CSV 中名称列名.

    Returns:
        分子字典列表，每个字典包含:
            - mol: RDKit Mol 对象
            - smiles: SMILES 字符串
            - name: 分子名称（如果有）
            - activity: 活性值（如果指定且存在）
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".sdf":
        return _load_sdf(path)
    elif suffix == ".csv":
        return _load_csv(path, smiles_column, activity_column, name_column)
    elif suffix in (".smi", ".smiles"):
        return _load_smiles_file(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def _load_sdf(path: Path) -> List[Dict[str, Any]]:
    molecules = []
    with open(path, "rb") as f:
        supplier = Chem.ForwardSDMolSupplier(f)
        for idx, mol in enumerate(supplier):
            if mol is None:
                continue
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"mol_{idx}"
            smiles = Chem.MolToSmiles(mol)
            entry: Dict[str, Any] = {
                "mol": mol,
                "smiles": smiles,
                "name": name,
            }
            for prop in mol.GetPropNames():
                if prop == "_Name":
                    continue
                try:
                    val = mol.GetProp(prop)
                    entry[prop] = val
                except Exception:
                    pass
            molecules.append(entry)
    logger.info(f"Loaded {len(molecules)} molecules from {path}")
    return molecules


def _load_csv(
    path: Path,
    smiles_column: str,
    activity_column: Optional[str],
    name_column: str,
) -> List[Dict[str, Any]]:
    import pandas as pd

    df = pd.read_csv(path)
    if smiles_column not in df.columns:
        raise ValueError(
            f"Column '{smiles_column}' not found. Available: {list(df.columns)}"
        )

    molecules = []
    for idx, row in df.iterrows():
        smiles = str(row[smiles_column])
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning(f"Invalid SMILES at row {idx}: {smiles}")
            continue
        entry: Dict[str, Any] = {"mol": mol, "smiles": smiles}
        if name_column in df.columns:
            entry["name"] = str(row[name_column])
        if activity_column and activity_column in df.columns:
            try:
                entry["activity"] = float(row[activity_column])
            except (ValueError, TypeError):
                pass
        molecules.append(entry)
    logger.info(f"Loaded {len(molecules)} molecules from {path}")
    return molecules


def _load_smiles_file(path: Path) -> List[Dict[str, Any]]:
    molecules = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            smiles = parts[0]
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                logger.warning(f"Invalid SMILES: {smiles}")
                continue
            entry: Dict[str, Any] = {"mol": mol, "smiles": smiles}
            if len(parts) > 1:
                entry["name"] = parts[1]
            molecules.append(entry)
    logger.info(f"Loaded {len(molecules)} molecules from {path}")
    return molecules
