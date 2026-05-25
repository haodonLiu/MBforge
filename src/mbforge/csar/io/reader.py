"""分子文件读取器 - 支持多种文件格式.

本模块提供从不同格式文件中读取分子数据的功能。
支持自动检测文件格式并调用相应的读取方法。

支持的格式:
    - SDF: 标准分子结构文件格式
    - Excel: .xlsx, .xls 格式，包含SMILES列
    - CSV: 逗号分隔值文件，包含SMILES列

示例:
    >>> reader = MoleculeReader(smiles_column="SMILES", activity_column="IC50")
    >>> molecules = reader.read("data.xlsx")
    >>> print(f"读取了 {len(molecules)} 个分子")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Union

import pandas as pd
from rdkit import Chem

from ...clustering.fingerprinter import MolecularFingerprinter
from ...molecules.schema import Molecule, MoleculeBatch

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class MoleculeReadError(Exception):
    """分子文件读取失败异常.

    当读取分子文件失败时抛出此异常，包含原始错误信息。
    """

    pass


class MoleculeReader:
    """分子读取器 - 支持多种文件格式.

    该类提供从SDF、Excel和CSV文件中读取分子数据的功能。
    支持自动检测文件格式，并根据文件扩展名调用相应的读取方法。

    属性:
        smiles_column: SMILES字符串所在的列名
        name_column: 分子名称所在的列名
        activity_column: 活性值所在的列名(可选)
    """

    def __init__(
        self,
        smiles_column: str = "SMILES",
        name_column: str = "Name",
        activity_column: str | None = None,
        cas_column: str | None = None,
    ) -> None:
        """初始化分子读取器.

        Args:
            smiles_column: 包含SMILES字符串的列名，默认为"SMILES".
            name_column: 包含分子名称的列名，默认为"Name".
            activity_column: 包含活性值的可选列名.
            cas_column: 包含CAS号的可选列名.
        """
        self.smiles_column = smiles_column
        self.name_column = name_column
        self.activity_column = activity_column
        self.cas_column = cas_column
        self._fingerprinter = MolecularFingerprinter()

    def read_sdf(self, path: Union[str, Path]) -> list[dict[str, Any]]:
        """从SDF文件读取分子.

        SDF (Structure Data File) 是化学信息学中常用的分子结构文件格式。
        该方法读取SDF文件中的所有分子，并提取分子结构、名称和属性。

        Args:
            path: SDF文件路径.

        Returns:
            分子字典列表，每个字典包含:
                - 'mol': RDKit分子对象
                - 'name': 分子名称
                - 'smiles': SMILES字符串
                - 'props': 分子属性字典(可选)

        Raises:
            MoleculeReadError: 文件读取失败时抛出.
        """
        path = Path(path)
        logger.info(f"Reading molecules from SDF: {path}")

        molecules = []
        try:
            with open(path, "rb") as f:
                supplier = Chem.ForwardSDMolSupplier(f)
                for idx, mol in enumerate(supplier):
                    if mol is not None:
                        name = (
                            mol.GetProp("_Name")
                            if mol.HasProp("_Name")
                            else f"mol_{idx}"
                        )
                        entry: dict[str, Any] = {
                            "mol": mol,
                            "name": name,
                            "smiles": Chem.MolToSmiles(mol),
                            "props": {
                                prop: mol.GetProp(prop) for prop in mol.GetPropNames()
                            },
                        }
                        # 如果 SDF 中包含 CAS 属性也一并读取
                        if mol.HasProp("CAS"):
                            entry["cas"] = mol.GetProp("CAS")
                        elif mol.HasProp("CAS_NO"):
                            entry["cas"] = mol.GetProp("CAS_NO")
                        molecules.append(entry)
        except Exception as e:
            raise MoleculeReadError(f"Failed to read SDF file {path}: {e}") from e

        logger.info(f"Successfully read {len(molecules)} molecules")
        return molecules

    def read_excel(
        self,
        path: Union[str, Path],
        sheet_name: Union[str, int] = 0,
        ic50_nm_column: str | None = None,
        ic50_um_column: str | None = None,
        deduplicate: bool = True,
    ) -> list[dict[str, Any]]:
        """从Excel文件读取分子.

        读取Excel文件中的分子数据，支持IC50活性值处理。
        可以自动合并nM和uM单位的IC50值，并进行SMILES去重。

        Args:
            path: Excel文件路径.
            sheet_name: 工作表名称或索引，默认为第一个工作表.
            ic50_nm_column: IC50(nM)列名.
            ic50_um_column: IC50(uM)列名.
            deduplicate: 是否按SMILES去重并平均活性值.

        Returns:
            分子字典列表，每个字典包含:
                - 'mol': RDKit分子对象
                - 'name': 分子名称
                - 'smiles': SMILES字符串
                - 'activity': 活性值(如果有)
                - 'activity_raw': 原始活性值字符串

        Raises:
            MoleculeReadError: 文件读取或SMILES解析失败时抛出.
        """
        path = Path(path)
        logger.info(f"Reading molecules from Excel: {path}")

        try:
            df = pd.read_excel(path, sheet_name=sheet_name)
        except Exception as e:
            raise MoleculeReadError(f"Failed to read Excel file {path}: {e}") from e

        if ic50_nm_column and ic50_nm_column in df.columns:
            df["IC50_nM_numeric"] = pd.to_numeric(df[ic50_nm_column], errors="coerce")

        if ic50_um_column and ic50_um_column in df.columns:
            df["IC50_uM_numeric"] = pd.to_numeric(df[ic50_um_column], errors="coerce")
            df["IC50_uM_nM"] = df["IC50_uM_numeric"] * 1000

        if "IC50_nM_numeric" in df.columns and "IC50_uM_nM" in df.columns:
            df["activity"] = df["IC50_nM_numeric"].combine_first(df["IC50_uM_nM"])
        elif "IC50_nM_numeric" in df.columns:
            df["activity"] = df["IC50_nM_numeric"]
        elif "IC50_uM_nM" in df.columns:
            df["activity"] = df["IC50_uM_nM"]
        elif self.activity_column and self.activity_column in df.columns:
            df["activity"] = pd.to_numeric(df[self.activity_column], errors="coerce")
        else:
            df["activity"] = None

        if ic50_nm_column and ic50_nm_column in df.columns:
            df["activity_raw"] = df[ic50_nm_column].astype(str)
        elif ic50_um_column and ic50_um_column in df.columns:
            df["activity_raw"] = df[ic50_um_column].astype(str)
        elif self.activity_column and self.activity_column in df.columns:
            df["activity_raw"] = df[self.activity_column].astype(str)
        else:
            df["activity_raw"] = ""

        if deduplicate and self.smiles_column in df.columns:
            df = df.dropna(subset=[self.smiles_column])
            agg_dict = {
                self.name_column: "first",
                "activity": "mean",
                "activity_raw": "first",
            }
            if self.cas_column and self.cas_column in df.columns:
                agg_dict[self.cas_column] = "first"
            df = df.groupby(self.smiles_column, as_index=False).agg(agg_dict)
            logger.info(f"Deduplicated to {len(df)} unique molecules by SMILES")

        molecules = []
        for idx, row in df.iterrows():
            try:
                smiles = str(row[self.smiles_column])
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    logger.warning(f"Invalid SMILES at row {idx}: {smiles}")
                    continue

                name = str(row.get(self.name_column, f"mol_{idx}"))
                mol.SetProp("_Name", name)

                activity_raw = str(row.get("activity_raw", ""))
                activity_value = row.get("activity")
                if activity_value is not None:
                    try:
                        activity_value = float(activity_value)
                    except (ValueError, TypeError):
                        activity_value = None

                entry: dict[str, Any] = {
                    "mol": mol,
                    "name": name,
                    "smiles": smiles,
                    "activity": activity_value,
                    "activity_raw": activity_raw,
                }

                if self.cas_column and self.cas_column in row:
                    cas_value = row[self.cas_column]
                    if pd.notna(cas_value):
                        entry["cas"] = str(cas_value).strip()

                molecules.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse row {idx}: {e}")
                continue

        logger.info(f"Successfully read {len(molecules)} molecules")
        return molecules

    def read_csv(self, path: Union[str, Path]) -> list[dict[str, Any]]:
        """从CSV文件读取分子.

        读取CSV文件中的分子数据，解析SMILES字符串为分子对象。

        Args:
            path: CSV文件路径.

        Returns:
            分子字典列表，每个字典包含:
                - 'mol': RDKit分子对象
                - 'name': 分子名称
                - 'smiles': SMILES字符串
                - 'activity': 活性值(如果有)

        Raises:
            MoleculeReadError: 文件读取或SMILES解析失败时抛出.
        """
        path = Path(path)
        logger.info(f"Reading molecules from CSV: {path}")

        try:
            df = pd.read_csv(path)
        except Exception as e:
            raise MoleculeReadError(f"Failed to read CSV file {path}: {e}") from e

        molecules = []
        for idx, row in df.iterrows():
            try:
                smiles = str(row[self.smiles_column])
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    logger.warning(f"Invalid SMILES at row {idx}: {smiles}")
                    continue

                name = str(row.get(self.name_column, f"mol_{idx}"))
                mol.SetProp("_Name", name)

                entry: dict[str, Any] = {
                    "mol": mol,
                    "name": name,
                    "smiles": smiles,
                }

                if self.activity_column and self.activity_column in row:
                    entry["activity"] = float(row[self.activity_column])

                if self.cas_column and self.cas_column in row:
                    cas_value = row[self.cas_column]
                    if pd.notna(cas_value):
                        entry["cas"] = str(cas_value).strip()

                molecules.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse row {idx}: {e}")
                continue

        logger.info(f"Successfully read {len(molecules)} molecules")
        return molecules

    def read_entries(
        self,
        path: Union[str, Path],
        **kwargs: Any,
    ) -> list[Molecule]:
        """读取分子并返回类型安全的 Molecule 列表.

        这是 read() 的类型安全版本，将字典列表转换为 Molecule 对象。
        支持自动检测文件格式。

        Args:
            path: 分子文件路径.
            **kwargs: 传递给具体读取方法的额外参数.

        Returns:
            Molecule 对象列表.

        Raises:
            MoleculeReadError: 格式不支持或读取失败时抛出.

        示例:
            >>> reader = MoleculeReader()
            >>> entries = reader.read_entries("data.csv")
            >>> batch = MoleculeBatch(entries)
            >>> print(batch.filter_has_activity())
        """
        dicts = self.read(path, **kwargs)
        entries: list[Molecule] = []
        for d in dicts:
            try:
                entries.append(Molecule.from_dict(d))
            except Exception as e:
                logger.warning(f"Skipping invalid molecule: {e}")
                continue
        logger.info(f"Converted {len(entries)} molecules to Molecule")
        return entries

    def read_batch(
        self,
        path: Union[str, Path],
        **kwargs: Any,
    ) -> MoleculeBatch:
        """读取分子并直接返回 MoleculeBatch 容器.

        Args:
            path: 分子文件路径.
            **kwargs: 传递给具体读取方法的额外参数.

        Returns:
            MoleculeBatch 对象，可直接进行批量操作.

        示例:
            >>> reader = MoleculeReader()
            >>> batch = reader.read_batch("data.xlsx")
            >>> active = batch.filter_has_activity()
            >>> active.to_csv("active.csv")
        """
        entries = self.read_entries(path, **kwargs)
        return MoleculeBatch(entries)

    def read(self, path: Union[str, Path], **kwargs: Any) -> list[dict[str, Any]]:
        """自动检测格式并读取分子.

        根据文件扩展名自动选择合适的读取方法。
        支持的格式: .sdf, .xlsx, .xls, .csv

        Args:
            path: 分子文件路径.
            **kwargs: 传递给具体读取方法的额外参数.

        Returns:
            包含分子数据的字典列表.

        Raises:
            MoleculeReadError: 格式不支持或读取失败时抛出.
        """
        path = Path(path)  # 转换为Path对象
        suffix = path.suffix.lower()  # 获取小写文件扩展名

        # 根据扩展名选择读取方法
        if suffix == ".sdf":
            return self.read_sdf(path)
        elif suffix in (".xlsx", ".xls"):
            return self.read_excel(path, **kwargs)
        elif suffix == ".csv":
            return self.read_csv(path)
        else:
            raise MoleculeReadError(f"Unsupported file format: {suffix}")
