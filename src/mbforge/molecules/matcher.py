"""子结构匹配与 SMARTS 查询模块.

提供子结构匹配、SMARTS 查询、分子相似性计算等高级分子匹配能力。

核心类:
    SubstructureMatcher: 子结构匹配器
    SMARTSQuery: SMARTS 查询工具

示例:
    >>> matcher = SubstructureMatcher()
    >>> matches = matcher.find_substructure_matches(mol, "c1ccccc1")
    >>> print(len(matches))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdFMCS, rdMolDescriptors

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """匹配结果.

    属性:
        matched: 是否匹配成功.
        query: 查询模式.
        target: 目标分子.
        atom_matches: 匹配的原子索引列表（每个匹配一组）.
        bond_matches: 匹配的键索引列表.
        match_count: 匹配次数.
    """

    matched: bool = False
    query: str = ""
    target: str = ""
    atom_matches: List[Tuple[int, ...]] = field(default_factory=list)
    bond_matches: List[Tuple[int, ...]] = field(default_factory=list)
    match_count: int = 0

    def __bool__(self) -> bool:
        return self.matched


class SubstructureMatcher:
    """子结构匹配器.

    提供基于 SMARTS 和 SMILES 的子结构搜索功能，支持
    子结构匹配、最大公共子结构（MCS）和分子相似性计算。
    """

    def __init__(self, use_chirality: bool = False) -> None:
        """初始化子结构匹配器.

        Args:
            use_chirality: 是否考虑手性，默认为 False.
        """
        self.use_chirality = use_chirality

    def has_substruct(
        self,
        mol: Chem.Mol,
        pattern: Union[str, Chem.Mol],
    ) -> bool:
        """检查分子是否包含指定子结构.

        Args:
            mol: 目标分子.
            pattern: SMARTS/SMILES 字符串或 RDKit Mol 模式.

        Returns:
            包含返回 True，否则 False.
        """
        query = self._to_mol(pattern)
        if query is None:
            return False
        return mol.HasSubstructMatch(query, useChirality=self.use_chirality)

    def count_substruct_matches(
        self,
        mol: Chem.Mol,
        pattern: Union[str, Chem.Mol],
        uniquify: bool = True,
    ) -> int:
        """计算子结构匹配次数.

        Args:
            mol: 目标分子.
            pattern: SMARTS/SMILES 模式.
            uniquify: 是否去重.

        Returns:
            匹配次数.
        """
        query = self._to_mol(pattern)
        if query is None:
            return 0
        return len(
            mol.GetSubstructMatches(
                query,
                useChirality=self.use_chirality,
                uniquify=uniquify,
            )
        )

    def find_substructure_matches(
        self,
        mol: Chem.Mol,
        pattern: Union[str, Chem.Mol],
        uniquify: bool = True,
    ) -> MatchResult:
        """查找所有子结构匹配.

        Args:
            mol: 目标分子.
            pattern: SMARTS/SMILES 模式.
            uniquify: 是否去重.

        Returns:
            匹配结果.
        """
        query = self._to_mol(pattern)
        if query is None:
            return MatchResult(query=str(pattern), target=Chem.MolToSmiles(mol))

        atom_matches = mol.GetSubstructMatches(
            query,
            useChirality=self.use_chirality,
            uniquify=uniquify,
        )

        return MatchResult(
            matched=len(atom_matches) > 0,
            query=str(pattern),
            target=Chem.MolToSmiles(mol),
            atom_matches=list(atom_matches),
            match_count=len(atom_matches),
        )

    def find_largest_common_substructure(
        self,
        mol1: Chem.Mol,
        mol2: Chem.Mol,
        timeout: int = 30,
    ) -> Optional[Chem.Mol]:
        """查找两个分子的最大公共子结构（MCS）.

        Args:
            mol1: 第一个分子.
            mol2: 第二个分子.
            timeout: 搜索超时时间（秒）.

        Returns:
            MCS 分子，失败返回 None.
        """
        if mol1 is None or mol2 is None:
            return None

        try:
            mcs_result = rdFMCS.FindMCS(
                [mol1, mol2],
                timeout=timeout,
                atomCompare=rdFMCS.AtomCompare.CompareAny,
                bondCompare=rdFMCS.BondCompare.CompareAny,
                matchValences=False,
                ringMatchesRingOnly=False,
                completeRingsOnly=False,
            )
            if mcs_result.smartsString:
                return Chem.MolFromSmarts(mcs_result.smartsString)
            return None
        except Exception as e:
            logger.warning(f"MCS search failed: {e}")
            return None

    def tanimoto_similarity(
        self,
        mol1: Chem.Mol,
        mol2: Chem.Mol,
        radius: int = 2,
        n_bits: int = 2048,
    ) -> float:
        """计算两个分子的 Tanimoto 相似度（Morgan 指纹）.

        Args:
            mol1: 第一个分子.
            mol2: 第二个分子.
            radius: Morgan 指纹半径，默认为 2.
            n_bits: 指纹位数，默认为 2048.

        Returns:
            Tanimoto 相似度（0.0 ~ 1.0）.
        """
        if mol1 is None or mol2 is None:
            return 0.0

        fp1 = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol1, radius, nBits=n_bits)
        fp2 = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol2, radius, nBits=n_bits)
        return float(np.bitwise_and(fp1, fp2).sum()) / float(np.bitwise_or(fp1, fp2).sum())

    def dice_similarity(
        self,
        mol1: Chem.Mol,
        mol2: Chem.Mol,
        radius: int = 2,
        n_bits: int = 2048,
    ) -> float:
        """计算两个分子的 Dice 相似度.

        Args:
            mol1: 第一个分子.
            mol2: 第二个分子.
            radius: Morgan 指纹半径.
            n_bits: 指纹位数.

        Returns:
            Dice 相似度（0.0 ~ 1.0）.
        """
        if mol1 is None or mol2 is None:
            return 0.0

        fp1 = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol1, radius, nBits=n_bits)
        fp2 = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol2, radius, nBits=n_bits)
        intersection = float(np.bitwise_and(fp1, fp2).sum())
        return 2.0 * intersection / (float(fp1.sum()) + float(fp2.sum()))

    def pairwise_similarity_matrix(
        self,
        molecules: List[Chem.Mol],
        radius: int = 2,
        n_bits: int = 2048,
    ) -> np.ndarray:
        """计算分子列表的成对相似度矩阵.

        Args:
            molecules: 分子列表.
            radius: Morgan 指纹半径.
            n_bits: 指纹位数.

        Returns:
            N x N 相似度矩阵.
        """
        n = len(molecules)
        matrix = np.zeros((n, n))

        # 预计算指纹
        fps = []
        for mol in molecules:
            if mol is None:
                fps.append(None)
            else:
                fps.append(
                    rdMolDescriptors.GetMorganFingerprintAsBitVect(
                        mol, radius, nBits=n_bits
                    )
                )

        for i in range(n):
            for j in range(i, n):
                if fps[i] is None or fps[j] is None:
                    sim = 0.0
                else:
                    intersection = float(np.bitwise_and(fps[i], fps[j]).sum())
                    union = float(np.bitwise_or(fps[i], fps[j]).sum())
                    sim = intersection / union if union > 0 else 0.0
                matrix[i, j] = sim
                matrix[j, i] = sim

        return matrix

    def find_similar_molecules(
        self,
        query: Chem.Mol,
        molecules: List[Chem.Mol],
        threshold: float = 0.7,
        top_n: Optional[int] = None,
    ) -> List[Tuple[int, float, Chem.Mol]]:
        """从分子库中查找与查询分子相似的分子.

        Args:
            query: 查询分子.
            molecules: 分子库列表.
            threshold: 相似度阈值.
            top_n: 返回前 N 个最相似的，默认全部.

        Returns:
            (索引, 相似度, 分子) 元组列表，按相似度降序.
        """
        results = []
        for i, mol in enumerate(molecules):
            sim = self.tanimoto_similarity(query, mol)
            if sim >= threshold:
                results.append((i, sim, mol))

        results.sort(key=lambda x: x[1], reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    def _to_mol(self, pattern: Union[str, Chem.Mol]) -> Optional[Chem.Mol]:
        """将字符串模式转换为 RDKit Mol 对象."""
        if isinstance(pattern, Chem.Mol):
            return pattern
        if isinstance(pattern, str):
            # 先尝试 SMARTS，再尝试 SMILES
            mol = Chem.MolFromSmarts(pattern)
            if mol is not None:
                return mol
            mol = Chem.MolFromSmiles(pattern)
            if mol is not None:
                return mol
        logger.warning(f"Failed to parse pattern: {pattern}")
        return None


class SMARTSQuery:
    """SMARTS 查询工具.

    提供基于 SMARTS 的批量查询、分子筛选和统计功能。
    """

    def __init__(self) -> None:
        """初始化 SMARTS 查询工具."""
        self._queries: Dict[str, Chem.Mol] = {}

    def add_query(self, name: str, smarts: str) -> bool:
        """添加 SMARTS 查询模式.

        Args:
            name: 查询名称.
            smarts: SMARTS 字符串.

        Returns:
            成功添加返回 True，失败返回 False.
        """
        mol = Chem.MolFromSmarts(smarts)
        if mol is None:
            logger.warning(f"Invalid SMARTS: {smarts}")
            return False
        self._queries[name] = mol
        return True

    def remove_query(self, name: str) -> bool:
        """移除 SMARTS 查询模式.

        Args:
            name: 查询名称.

        Returns:
            成功移除返回 True.
        """
        if name in self._queries:
            del self._queries[name]
            return True
        return False

    def query(self, mol: Chem.Mol, name: str) -> MatchResult:
        """执行单个查询.

        Args:
            mol: 目标分子.
            name: 查询名称.

        Returns:
            匹配结果.

        Raises:
            KeyError: 查询名称不存在时抛出.
        """
        if name not in self._queries:
            raise KeyError(f"Query '{name}' not found. Available: {list(self._queries.keys())}")

        query = self._queries[name]
        atom_matches = mol.GetSubstructMatches(query)

        return MatchResult(
            matched=len(atom_matches) > 0,
            query=name,
            target=Chem.MolToSmiles(mol),
            atom_matches=list(atom_matches),
            match_count=len(atom_matches),
        )

    def query_all(self, mol: Chem.Mol) -> Dict[str, MatchResult]:
        """对所有注册的查询进行匹配.

        Args:
            mol: 目标分子.

        Returns:
            查询名称 -> 匹配结果 的字典.
        """
        return {name: self.query(mol, name) for name in self._queries}

    def filter_molecules(
        self,
        molecules: List[Chem.Mol],
        query_name: str,
        mode: str = "include",  # "include" or "exclude"
    ) -> List[Tuple[int, Chem.Mol]]:
        """根据 SMARTS 查询筛选分子.

        Args:
            molecules: 分子列表.
            query_name: 查询名称.
            mode: "include" 保留匹配的，"exclude" 排除匹配的.

        Returns:
            (索引, 分子) 列表.
        """
        results = []
        for i, mol in enumerate(molecules):
            match = self.query(mol, query_name)
            if mode == "include" and match.matched:
                results.append((i, mol))
            elif mode == "exclude" and not match.matched:
                results.append((i, mol))
        return results

    @classmethod
    def from_query_dict(cls, queries: Dict[str, str]) -> SMARTSQuery:
        """从字典批量创建查询工具.

        Args:
            queries: 名称 -> SMARTS 的字典.

        Returns:
            初始化后的 SMARTSQuery 对象.
        """
        sq = cls()
        for name, smarts in queries.items():
            if not sq.add_query(name, smarts):
                logger.warning(f"Skipped invalid SMARTS for '{name}': {smarts}")
        return sq

    def get_query_names(self) -> List[str]:
        """获取所有已注册查询的名称.

        Returns:
            查询名称列表.
        """
        return list(self._queries.keys())

    def __repr__(self) -> str:
        return f"SMARTSQuery(queries={len(self._queries)})"


# 便捷工厂函数

def query_functional_groups(mol: Chem.Mol) -> Dict[str, bool]:
    """查询常见官能团.

    Args:
        mol: 目标分子.

    Returns:
        官能团名称 -> 是否存在的字典.
    """
    functional_groups = {
        "hydroxyl": "[OX2H]",
        "amine": "[NX3;H2,H1;!$(NC=O)]",
        "amide": "[NX3][CX3](=[OX1])",
        "carboxylic_acid": "[CX3](=O)[OX2H1]",
        "ester": "[#6][CX3](=O)[OX2H0][#6]",
        "ketone": "[#6][CX3](=O)[#6]",
        "aldehyde": "[CX3H1](=O)[#6]",
        "ether": "[#6][OX2][#6]",
        "nitro": "[NX3](=[OX1])(=[OX1])",
        "sulfonamide": "[SX4](=[OX1])(=[OX1])[NX3]",
        "halogen": "[F,Cl,Br,I]",
        "aromatic_ring": "c1ccccc1",
        "heterocycle": "[#7,#8,#16]1~*~*~*~*~1",
        "alkene": "[CX3]=[CX3]",
        "alkyne": "[CX2]#[CX2]",
    }

    sq = SMARTSQuery.from_query_dict(functional_groups)
    results = sq.query_all(mol)
    return {name: result.matched for name, result in results.items()}
