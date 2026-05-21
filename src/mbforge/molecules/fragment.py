"""骨架与片段分析模块.

提供骨架提取（Bemis-Murcko、 scaffold tree）、片段分解（RECAP、BRICS）
和 R 基团分析等高级分子结构分析能力。

核心类:
    ScaffoldAnalyzer: 骨架分析器（Murcko 骨架、骨架层次等）
    RECAPFragmenter: RECAP 规则片段分解
    BRICSFragmenter: BRICS 规则片段分解

示例:
    >>> analyzer = ScaffoldAnalyzer()
    >>> scaffold = analyzer.get_murcko_scaffold(mol)
    >>> print(Chem.MolToSmiles(scaffold))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from rdkit import Chem
from rdkit.Chem import AllChem, BRICS, FragmentCatalog, Recap
from rdkit.Chem.Scaffolds import MurckoScaffold

logger = logging.getLogger(__name__)


@dataclass
class FragmentInfo:
    """片段信息.

    属性:
        smarts: 片段 SMARTS.
        smiles: 片段 SMILES.
        mol: RDKit 片段分子.
        atom_indices: 片段在原分子中的原子索引集合.
        bond_indices: 片段在原分子中的键索引集合.
    """

    smarts: str = ""
    smiles: str = ""
    mol: Optional[Chem.Mol] = None
    atom_indices: Set[int] = field(default_factory=set)
    bond_indices: Set[int] = field(default_factory=set)

    def __repr__(self) -> str:
        return f"FragmentInfo(smiles={self.smiles!r}, atoms={len(self.atom_indices)})"


@dataclass
class ScaffoldInfo:
    """骨架信息.

    属性:
        scaffold_mol: 骨架分子.
        scaffold_smiles: 骨架 SMILES.
        num_rings: 环数.
        num_atoms: 原子数.
        original_smiles: 原始分子 SMILES.
    """

    scaffold_mol: Optional[Chem.Mol] = None
    scaffold_smiles: str = ""
    num_rings: int = 0
    num_atoms: int = 0
    original_smiles: str = ""


class ScaffoldAnalyzer:
    """骨架分析器.

    提供多种骨架提取方法，包括 Bemis-Murcko 骨架、骨架层次分析等。
    """

    def get_murcko_scaffold(
        self,
        mol: Chem.Mol,
        include_chirality: bool = False,
    ) -> Optional[Chem.Mol]:
        """提取 Bemis-Murcko 骨架.

        移除所有侧链，仅保留环系统和连接它们的链。

        Args:
            mol: 输入分子.
            include_chirality: 是否保留手性信息，默认为 False.

        Returns:
            骨架分子，提取失败返回 None.
        """
        if mol is None:
            return None
        try:
            scaffold = MurckoScaffold.GetScaffoldForMol(mol)
            if include_chirality:
                return scaffold
            # 清除手性
            Chem.RemoveStereochemistry(scaffold)
            return scaffold
        except Exception as e:
            logger.warning(f"Murcko scaffold extraction failed: {e}")
            return None

    def get_murcko_scaffold_smiles(
        self,
        mol: Chem.Mol,
        include_chirality: bool = False,
    ) -> str:
        """提取 Murcko 骨架并返回 SMILES.

        Args:
            mol: 输入分子.
            include_chirality: 是否保留手性信息.

        Returns:
            骨架 SMILES，失败返回空字符串.
        """
        scaffold = self.get_murcko_scaffold(mol, include_chirality)
        if scaffold is None:
            return ""
        try:
            return Chem.MolToSmiles(scaffold)
        except Exception:
            return ""

    def get_generic_scaffold(self, mol: Chem.Mol) -> Optional[Chem.Mol]:
        """提取通用骨架（所有原子变为碳，所有键变为单键）.

        Args:
            mol: 输入分子.

        Returns:
            通用骨架分子，失败返回 None.
        """
        scaffold = self.get_murcko_scaffold(mol)
        if scaffold is None:
            return None
        try:
            generic = MurckoScaffold.MakeScaffoldGeneric(scaffold)
            return generic
        except Exception as e:
            logger.warning(f"Generic scaffold extraction failed: {e}")
            return None

    def get_scaffold_info(
        self,
        mol: Chem.Mol,
        include_chirality: bool = False,
    ) -> ScaffoldInfo:
        """获取骨架完整信息.

        Args:
            mol: 输入分子.
            include_chirality: 是否保留手性信息.

        Returns:
            ScaffoldInfo 数据对象.
        """
        from rdkit.Chem import rdMolDescriptors

        scaffold = self.get_murcko_scaffold(mol, include_chirality)
        if scaffold is None:
            return ScaffoldInfo(original_smiles=Chem.MolToSmiles(mol))

        smiles = Chem.MolToSmiles(scaffold)
        return ScaffoldInfo(
            scaffold_mol=scaffold,
            scaffold_smiles=smiles,
            num_rings=rdMolDescriptors.CalcNumRings(scaffold),
            num_atoms=scaffold.GetNumAtoms(),
            original_smiles=Chem.MolToSmiles(mol),
        )

    def group_by_scaffold(
        self,
        molecules: List[Chem.Mol],
        names: Optional[List[str]] = None,
        include_chirality: bool = False,
    ) -> Dict[str, List[Tuple[int, Optional[str], Chem.Mol]]]:
        """按 Murcko 骨架对分子分组.

        Args:
            molecules: 分子列表.
            names: 可选的分子名称列表.
            include_chirality: 是否包含手性信息.

        Returns:
            骨架 SMILES -> (索引, 名称, 分子) 列表 的字典.
        """
        groups: Dict[str, List[Tuple[int, Optional[str], Chem.Mol]]] = {}
        for i, mol in enumerate(molecules):
            scaffold_smiles = self.get_murcko_scaffold_smiles(mol, include_chirality)
            if not scaffold_smiles:
                scaffold_smiles = "_no_scaffold_"
            name = names[i] if names else None
            groups.setdefault(scaffold_smiles, []).append((i, name, mol))
        return groups

    def get_scaffold_hierarchy(
        self,
        mol: Chem.Mol,
    ) -> List[ScaffoldInfo]:
        """获取骨架层次结构（从完整分子逐步简化到骨架）.

        层次：
        1. 原始分子
        2. Murcko 骨架（保留杂原子）
        3. 通用骨架（所有原子为碳）

        Args:
            mol: 输入分子.

        Returns:
            从复杂到简单的 ScaffoldInfo 列表.
        """
        hierarchy = []
        original_smiles = Chem.MolToSmiles(mol)

        # Level 1: 原始分子
        hierarchy.append(
            ScaffoldInfo(
                scaffold_mol=Chem.Mol(mol),
                scaffold_smiles=original_smiles,
                num_rings=Chem.rdMolDescriptors.CalcNumRings(mol),
                num_atoms=mol.GetNumAtoms(),
                original_smiles=original_smiles,
            )
        )

        # Level 2: Murcko 骨架
        murcko = self.get_murcko_scaffold(mol)
        if murcko is not None:
            hierarchy.append(
                ScaffoldInfo(
                    scaffold_mol=murcko,
                    scaffold_smiles=Chem.MolToSmiles(murcko),
                    num_rings=Chem.rdMolDescriptors.CalcNumRings(murcko),
                    num_atoms=murcko.GetNumAtoms(),
                    original_smiles=original_smiles,
                )
            )

            # Level 3: 通用骨架
            generic = self.get_generic_scaffold(mol)
            if generic is not None:
                hierarchy.append(
                    ScaffoldInfo(
                        scaffold_mol=generic,
                        scaffold_smiles=Chem.MolToSmiles(generic),
                        num_rings=Chem.rdMolDescriptors.CalcNumRings(generic),
                        num_atoms=generic.GetNumAtoms(),
                        original_smiles=original_smiles,
                    )
                )

        return hierarchy


class RECAPFragmenter:
    """RECAP 片段分解器.

    使用 RECAP（Retrosynthetic Combinatorial Analysis Procedure）规则
    将分子分解为合成相关的片段。RECAP 定义了 11 种常见的合成反应键类型。
    """

    def fragment(self, mol: Chem.Mol) -> List[FragmentInfo]:
        """对分子进行 RECAP 片段分解.

        Args:
            mol: 输入分子.

        Returns:
            片段信息列表.
        """
        if mol is None:
            return []

        try:
            recap_decomp = Recap.RecapDecompose(mol)
            if recap_decomp is None:
                return []
            return self._extract_fragments_from_tree(recap_decomp)
        except Exception as e:
            logger.warning(f"RECAP fragmentation failed: {e}")
            return []

    def _extract_fragments_from_tree(
        self, node
    ) -> List[FragmentInfo]:
        """从 RECAP 分解树中提取片段（递归）."""
        fragments = []
        if hasattr(node, "mol") and node.mol is not None:
            try:
                smiles = Chem.MolToSmiles(node.mol)
                fragments.append(
                    FragmentInfo(
                        smiles=smiles,
                        mol=node.mol,
                    )
                )
            except Exception:
                pass
        if hasattr(node, "children"):
            for child in node.children.values():
                fragments.extend(self._extract_fragments_from_tree(child))
        return fragments

    def fragment_batch(
        self,
        molecules: List[Chem.Mol],
        names: Optional[List[str]] = None,
    ) -> Dict[str, List[FragmentInfo]]:
        """批量 RECAP 分解.

        Args:
            molecules: 分子列表.
            names: 可选名称列表.

        Returns:
            名称 -> 片段列表 的字典.
        """
        results = {}
        for i, mol in enumerate(molecules):
            name = names[i] if names else f"mol_{i}"
            results[name] = self.fragment(mol)
        return results


class BRICSFragmenter:
    """BRICS 片段分解器.

    使用 BRICS（Breaking of Retrosynthetically Interesting Chemical Substructures）
    规则将分子分解为合成相关的片段。BRICS 定义了 16 种断键规则。
    """

    def fragment(self, mol: Chem.Mol) -> List[FragmentInfo]:
        """对分子进行 BRICS 片段分解.

        Args:
            mol: 输入分子.

        Returns:
            片段信息列表.
        """
        if mol is None:
            return []

        try:
            bond_types = list(BRICS.FindBRICSBonds(mol))
            if not bond_types:
                # 无断键点，返回完整分子
                return [
                    FragmentInfo(
                        smiles=Chem.MolToSmiles(mol),
                        mol=mol,
                        atom_indices=set(range(mol.GetNumAtoms())),
                    )
                ]

            frags = BRICS.BreakBRICSBonds(mol, bonds=bond_types)
            if frags is None:
                return []

            mol_frags = Chem.GetMolFrags(frags, asMols=True, sanitizeFrags=True)
            fragments = []
            for frag in mol_frags:
                try:
                    smiles = Chem.MolToSmiles(frag)
                    fragments.append(
                        FragmentInfo(
                            smiles=smiles,
                            mol=frag,
                        )
                    )
                except Exception:
                    continue
            return fragments
        except Exception as e:
            logger.warning(f"BRICS fragmentation failed: {e}")
            return []

    def get_fragment_smiles(self, mol: Chem.Mol) -> List[str]:
        """获取 BRICS 片段的 SMILES 列表.

        Args:
            mol: 输入分子.

        Returns:
            片段 SMILES 列表.
        """
        return [f.smiles for f in self.fragment(mol) if f.smiles]

    def fragment_batch(
        self,
        molecules: List[Chem.Mol],
        names: Optional[List[str]] = None,
    ) -> Dict[str, List[FragmentInfo]]:
        """批量 BRICS 分解.

        Args:
            molecules: 分子列表.
            names: 可选名称列表.

        Returns:
            名称 -> 片段列表 的字典.
        """
        results = {}
        for i, mol in enumerate(molecules):
            name = names[i] if names else f"mol_{i}"
            results[name] = self.fragment(mol)
        return results


class RGroupAnalyzer:
    """R 基团分析器.

    基于最大公共子结构（MCS）识别分子间的 R 基团差异。
    """

    def __init__(self, timeout: int = 30) -> None:
        """初始化 R 基团分析器.

        Args:
            timeout: MCS 搜索超时时间（秒）.
        """
        self.timeout = timeout

    def find_r_groups(
        self,
        scaffold: Chem.Mol,
        mol: Chem.Mol,
    ) -> List[FragmentInfo]:
        """识别分子相对于骨架的 R 基团.

        Args:
            scaffold: 骨架分子.
            mol: 目标分子.

        Returns:
            R 基团片段列表.
        """
        if scaffold is None or mol is None:
            return []

        try:
            # 找到骨架在分子中的匹配
            match = mol.GetSubstructMatch(scaffold)
            if not match:
                return []

            scaffold_atoms = set(match)
            all_atoms = set(range(mol.GetNumAtoms()))
            r_group_atoms = all_atoms - scaffold_atoms

            if not r_group_atoms:
                return []

            # 提取 R 基团片段
            r_group_frags = []
            for atom_idx in r_group_atoms:
                atom = mol.GetAtomWithIdx(atom_idx)
                # 只提取与骨架直接相连的原子作为 R 基团起点
                neighbors_in_scaffold = [
                    n.GetIdx()
                    for n in atom.GetNeighbors()
                    if n.GetIdx() in scaffold_atoms
                ]
                if neighbors_in_scaffold:
                    # 这是一个连接点
                    frag = self._extract_r_group_fragment(mol, atom_idx, scaffold_atoms)
                    if frag is not None:
                        r_group_frags.append(frag)

            return r_group_frags
        except Exception as e:
            logger.warning(f"R-group analysis failed: {e}")
            return []

    def _extract_r_group_fragment(
        self,
        mol: Chem.Mol,
        start_atom: int,
        scaffold_atoms: Set[int],
    ) -> Optional[FragmentInfo]:
        """提取单个 R 基团片段."""
        from collections import deque

        visited = set(scaffold_atoms)
        queue = deque([start_atom])
        r_atoms = set()

        while queue:
            atom_idx = queue.popleft()
            if atom_idx in visited:
                continue
            visited.add(atom_idx)
            r_atoms.add(atom_idx)

            atom = mol.GetAtomWithIdx(atom_idx)
            for neighbor in atom.GetNeighbors():
                n_idx = neighbor.GetIdx()
                if n_idx not in visited:
                    queue.append(n_idx)

        if not r_atoms:
            return None

        # 创建子图
        emol = Chem.EditableMol(Chem.Mol())
        atom_map = {}
        for atom_idx in sorted(r_atoms):
            new_idx = emol.AddAtom(mol.GetAtomWithIdx(atom_idx))
            atom_map[atom_idx] = new_idx

        # 添加键
        for bond in mol.GetBonds():
            a1 = bond.GetBeginAtomIdx()
            a2 = bond.GetEndAtomIdx()
            if a1 in r_atoms and a2 in r_atoms:
                emol.AddBond(
                    atom_map[a1],
                    atom_map[a2],
                    bond.GetBondType(),
                )

        frag = emol.GetMol()
        try:
            Chem.SanitizeMol(frag)
            smiles = Chem.MolToSmiles(frag)
            return FragmentInfo(
                smiles=smiles,
                mol=frag,
                atom_indices=r_atoms,
            )
        except Exception:
            return None
