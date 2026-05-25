"""分子文件写入器 - 支持多种文件格式.

本模块提供将分子数据写入不同格式文件的功能。
支持导出分子结构、属性和计算描述符。

支持的格式:
    - SDF: 标准分子结构文件格式
    - CSV: 逗号分隔值文件
    - Excel: .xlsx 格式

示例:
    >>> writer = MoleculeWriter()
    >>> writer.write_csv(molecules, "output.csv")
    >>> writer.write_sdf(molecules, "output.sdf")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Union

import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors

from ...molecules.schema import Molecule, MoleculeBatch

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class MoleculeWriteError(Exception):
    """分子文件写入失败异常.

    当写入分子文件失败时抛出此异常，包含原始错误信息。
    """

    pass


class MoleculeWriter:
    """分子写入器 - 支持多种文件格式.

    该类提供将分子数据写入SDF、CSV和Excel文件的功能。
    自动计算分子描述符(分子量、LogP等)并包含在输出中。
    """

    def write_sdf(
        self, molecules: list[dict[str, Any]], path: Union[str, Path]
    ) -> None:
        """将分子写入SDF文件.

        将分子列表写入SDF格式文件，保留分子结构和属性。

        Args:
            molecules: 分子字典列表，每个字典包含'mol'和可选的'props'.
            path: 输出SDF文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        path = Path(path)
        logger.info(f"Writing {len(molecules)} molecules to SDF: {path}")

        try:
            with open(path, "wb") as f:
                writer = Chem.SDWriter(f)
                for mol_data in molecules:
                    mol = mol_data["mol"]
                    for prop, value in mol_data.get("props", {}).items():
                        mol.SetProp(prop, str(value))
                    writer.write(mol)
                writer.close()
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write SDF file {path}: {e}") from e

        logger.info(f"Successfully wrote {len(molecules)} molecules")

    def write_csv(
        self, molecules: list[dict[str, Any]], path: Union[str, Path]
    ) -> None:
        """将分子写入CSV文件.

        将分子数据导出为CSV格式，包含以下列:
        - Name: 分子名称
        - SMILES: SMILES字符串
        - NumAtoms: 原子数
        - NumBonds: 键数
        - MolecularWeight: 分子量
        - LogP: 脂水分配系数
        - Activity: 活性值(如果有)

        Args:
            molecules: 分子字典列表.
            path: 输出CSV文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        path = Path(path)
        logger.info(f"Writing {len(molecules)} molecules to CSV: {path}")

        try:
            records = []
            for mol_data in molecules:
                mol = mol_data["mol"]
                record: dict[str, Any] = {
                    "Name": mol_data.get("name", ""),
                    "SMILES": mol_data.get("smiles", Chem.MolToSmiles(mol)),
                    "NumAtoms": mol.GetNumAtoms(),
                    "NumBonds": mol.GetNumBonds(),
                    "MolecularWeight": Descriptors.MolWt(mol),
                    "LogP": Descriptors.MolLogP(mol),
                }
                if "activity" in mol_data:
                    record["Activity"] = mol_data["activity"]
                if "cas" in mol_data:
                    record["CAS"] = mol_data["cas"]
                records.append(record)

            df = pd.DataFrame(records)
            df.to_csv(path, index=False)
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write CSV file {path}: {e}") from e

        logger.info(f"Successfully wrote {len(molecules)} molecules")

    def write_excel(
        self, molecules: list[dict[str, Any]], path: Union[str, Path]
    ) -> None:
        """将分子写入Excel文件.

        将分子数据导出为Excel格式(.xlsx)，包含与CSV相同的列。

        Args:
            molecules: 分子字典列表.
            path: 输出Excel文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        path = Path(path)
        logger.info(f"Writing {len(molecules)} molecules to Excel: {path}")

        try:
            records = []
            for mol_data in molecules:
                mol = mol_data["mol"]
                record: dict[str, Any] = {
                    "Name": mol_data.get("name", ""),
                    "SMILES": mol_data.get("smiles", Chem.MolToSmiles(mol)),
                    "NumAtoms": mol.GetNumAtoms(),
                    "NumBonds": mol.GetNumBonds(),
                    "MolecularWeight": Descriptors.MolWt(mol),
                    "LogP": Descriptors.MolLogP(mol),
                }
                if "activity" in mol_data:
                    record["Activity"] = mol_data["activity"]
                if "cas" in mol_data:
                    record["CAS"] = mol_data["cas"]
                records.append(record)

            df = pd.DataFrame(records)
            df.to_excel(path, index=False)
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write Excel file {path}: {e}") from e

        logger.info(f"Successfully wrote {len(molecules)} molecules")

    # ------------------------------------------------------------------
    # Molecule / MoleculeBatch 支持（schema 契约）
    # ------------------------------------------------------------------

    def write_molecules_csv(
        self, molecules: list[Molecule], path: Union[str, Path]
    ) -> None:
        """将 Molecule 列表写入 CSV 文件.

        Args:
            molecules: Molecule 列表.
            path: 输出 CSV 文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        batch = MoleculeBatch(molecules)
        try:
            batch.to_csv(path)
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write CSV file {path}: {e}") from e

    def write_molecules_sdf(
        self, molecules: list[Molecule], path: Union[str, Path]
    ) -> None:
        """将 Molecule 列表写入 SDF 文件.

        Args:
            molecules: Molecule 列表.
            path: 输出 SDF 文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        batch = MoleculeBatch(molecules)
        try:
            batch.to_sdf(path)
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write SDF file {path}: {e}") from e

    def write_molecules_excel(
        self, molecules: list[Molecule], path: Union[str, Path]
    ) -> None:
        """将 Molecule 列表写入 Excel 文件.

        Args:
            molecules: Molecule 列表.
            path: 输出 Excel 文件路径.

        Raises:
            MoleculeWriteError: 写入失败时抛出.
        """
        batch = MoleculeBatch(molecules)
        try:
            batch.to_excel(path)
        except Exception as e:
            raise MoleculeWriteError(f"Failed to write Excel file {path}: {e}") from e
