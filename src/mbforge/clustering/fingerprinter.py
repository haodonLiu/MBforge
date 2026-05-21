"""分子指纹计算模块 - 用于相似性计算.

本模块提供分子指纹生成和Tanimoto相似性计算功能。
分子指纹是将分子结构转换为固定长度位向量的方法，
用于快速比较分子相似性。

指纹类型说明:
    - Morgan (ECFP): 扩展连接指纹，基于原子的圆形环境，
      适用于相似性搜索和虚拟筛选。
    - MACCS: 分子访问系统键，包含167个预定义的结构键，
      适用于快速子结构搜索。
    - RDKit: 拓扑指纹，基于Daylight指纹算法，
      适用于一般相似性比较。

Tanimoto系数:
    计算两个指纹的相似度，范围为0.0(完全不同)到1.0(完全相同)。
    公式: Tc = (A ∩ B) / (A ∪ B)

示例:
    >>> fp = MolecularFingerprinter(fp_type="Morgan", radius=2, n_bits=2048)
    >>> result = fp.fingerprint(mol)
    >>> similarity = fp.similarity(mol1, mol2)
"""

from __future__ import annotations

from typing import Optional, Union
from dataclasses import dataclass

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, MACCSkeys
from rdkit import DataStructs


@dataclass
class FingerprintResult:
    """指纹生成结果数据类.
    
    存储分子指纹及其元数据信息。
    
    属性:
        fingerprint: 指纹位向量 (numpy数组)
        fp_type: 指纹类型 ("Morgan", "MACCS", "RDKit")
        n_bits: 指纹位数
    """

    fingerprint: np.ndarray  # 指纹位向量
    fp_type: str  # 指纹类型
    n_bits: int  # 指纹位数


class MolecularFingerprinter:
    """分子指纹计算器 - 支持多种指纹类型.
    
    该类提供分子指纹生成和Tanimoto相似性计算功能。
    支持Morgan (ECFP)、MACCS和RDKit三种指纹类型。
    
    属性:
        fp_type: 指纹类型
        radius: Morgan指纹的半径
        n_bits: 指纹位数
    
    示例:
        >>> fp = MolecularFingerprinter(fp_type="Morgan", radius=2)
        >>> result = fp.fingerprint(mol)
        >>> print(f"指纹类型: {result.fp_type}, 位数: {result.n_bits}")
    """

    def __init__(
        self, fp_type: str = "Morgan", radius: int = 2, n_bits: int = 2048
    ) -> None:
        """初始化分子指纹计算器.

        Args:
            fp_type: 指纹类型，可选"Morgan"(默认)、"MACCS"、"RDKit".
            radius: Morgan指纹的半径，默认为2(相当于ECFP4).
            n_bits: 指纹位数，默认为2048.
        """
        self.fp_type = fp_type
        self.radius = radius
        self.n_bits = n_bits

    def fingerprint(self, mol: Union[Chem.Mol, str]) -> FingerprintResult:
        """生成分子的指纹.

        Args:
            mol: RDKit分子对象或SMILES字符串.

        Returns:
            FingerprintResult对象，包含指纹数组和元数据.

        Raises:
            ValueError: 分子为None或无效时抛出.
        """
        # 如果输入是SMILES字符串，先转换为分子对象
        if isinstance(mol, str):
            mol = Chem.MolFromSmiles(mol)
            if mol is None:
                raise ValueError(f"Invalid SMILES: {mol}")

        # 验证分子有效性
        if mol is None:
            raise ValueError("Molecule cannot be None")

        if mol.GetNumAtoms() == 0:
            raise ValueError("Molecule has no atoms")

        # 根据指纹类型生成相应的指纹
        if self.fp_type == "Morgan":
            # Morgan指纹 (ECFP) - 基于圆形环境
            fp = AllChem.GetMorganFingerprintAsBitVect(
                mol, self.radius, nBits=self.n_bits
            )
        elif self.fp_type == "MACCS":
            # MACCS键指纹 - 167位结构键
            fp = MACCSkeys.GenMACCSKeys(mol)
        elif self.fp_type == "RDKit":
            # RDKit拓扑指纹
            fp = Chem.RDKFingerprint(mol)
        else:
            raise ValueError(f"Unknown fingerprint type: {self.fp_type}")

        # 将RDKit指纹转换为numpy数组
        arr = np.zeros((self.n_bits,), dtype=np.uint8)
        DataStructs.ConvertToNumpyArray(fp, arr)

        return FingerprintResult(
            fingerprint=arr, fp_type=self.fp_type, n_bits=self.n_bits
        )

    def similarity(
        self, mol1: Union[Chem.Mol, str], mol2: Union[Chem.Mol, str]
    ) -> float:
        """计算两个分子的Tanimoto相似度.
        
        Tanimoto系数衡量两个分子的相似程度，范围为0.0(完全不同)到1.0(完全相同)。

        Args:
            mol1: 第一个分子 (Mol对象或SMILES字符串).
            mol2: 第二个分子 (Mol对象或SMILES字符串).

        Returns:
            Tanimoto相似度分数 (0.0 到 1.0).
        """
        if isinstance(mol1, str):
            mol1 = Chem.MolFromSmiles(mol1)
        if isinstance(mol2, str):
            mol2 = Chem.MolFromSmiles(mol2)

        if mol1 is None or mol2 is None:
            raise ValueError("Invalid molecule(s)")

        fp1 = self.fingerprint(mol1).fingerprint
        fp2 = self.fingerprint(mol2).fingerprint

        return self._tanimoto(fp1, fp2)

    def _tanimoto(self, fp1: np.ndarray, fp2: np.ndarray) -> float:
        """计算两个指纹之间的Tanimoto系数.
        
        Tanimoto系数 = 交集大小 / 并集大小
        
        Args:
            fp1: 第一个指纹数组.
            fp2: 第二个指纹数组.
            
        Returns:
            Tanimoto相似度 (0.0 到 1.0).
        """
        intersection = np.sum(np.logical_and(fp1, fp2))  # 交集位数
        union = np.sum(np.logical_or(fp1, fp2))  # 并集位数
        if union == 0:
            return 0.0
        return intersection / union

    def pairwise_similarity(self, molecules: list[Chem.Mol]) -> np.ndarray:
        """计算成对Tanimoto相似度矩阵.
        
        计算所有分子之间的两两相似度，返回对称矩阵。
        对角线元素为1.0(分子与自身完全相同)。

        Args:
            molecules: RDKit分子对象列表.

        Returns:
            NxN相似度矩阵，N为分子数量.
        """
        n = len(molecules)
        sim_matrix = np.zeros((n, n), dtype=np.float64)  # 初始化相似度矩阵

        # 预计算所有分子的指纹
        fps = [self.fingerprint(mol).fingerprint for mol in molecules]

        # 计算成对相似度(利用对称性减少计算量)
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    sim_matrix[i, j] = 1.0  # 分子与自身的相似度为1
                else:
                    sim = self._tanimoto(fps[i], fps[j])
                    sim_matrix[i, j] = sim
                    sim_matrix[j, i] = sim  # 对称矩阵

        return sim_matrix
