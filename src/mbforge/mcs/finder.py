"""最大公共子结构(MCS)查找模块 - 使用RDKit实现.

本模块提供查找分子间最大公共子结构(MCS)的功能。
MCS是多个分子共有的最大结构片段，在药物化学中用于:
- 识别共同的结构骨架
- 分析结构-活性关系(SAR)
- 发现药效团

算法说明:
    对于两个分子，使用RDKit的rdFMCS算法查找MCS。
    对于多个分子，采用两两比较策略，选择得分最高的MCS。
    支持超时控制，避免在大分子上花费过多时间。

主要组件:
    - MCSFinder: MCS查找器类
    - MCSResult: MCS结果数据类
    - ScaffoldInfo: 骨架信息(含R基团位置)
    - SubstituentInfo: 取代基信息

示例:
    >>> finder = MCSFinder(timeout=30)
    >>> result = finder.find_mcs(molecules)
    >>> print(f"MCS: {result.smiles}")
    >>> print(f"原子数: {result.num_atoms}, 得分: {result.score:.2f}")
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any, Union, Tuple
from dataclasses import dataclass
from datetime import datetime

from rdkit import Chem
from rdkit.Chem import rdFMCS
from rdkit.Chem.Draw import rdMolDraw2D

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class MCSError(Exception):
    """最大公共子结构查找失败异常.
    
    当MCS查找过程失败时抛出此异常，如分子数量不足或超时。
    """

    pass


@dataclass
class MCSResult:
    """MCS查找结果数据类.
    
    存储MCS查找的详细结果信息。
    
    属性:
        mcs_mol: MCS的RDKit分子对象
        smiles: MCS的SMARTS/SMILES表示
        num_atoms: MCS中的原子数
        num_bonds: MCS中的键数
        smiles_a: 第一个分子的SMILES(用于成对比较)
        smiles_b: 第二个分子的SMILES(用于成对比较)
        bond_matches: 匹配的键数
        atom_matches: 匹配的原子数
        score: MCS得分(0.0-1.0)，基于原子覆盖率
    """

    mcs_mol: Chem.Mol  # MCS分子对象
    smiles: str  # MCS的SMILES
    num_atoms: int  # 原子数
    num_bonds: int  # 键数
    smiles_a: str  # 分子A的SMILES
    smiles_b: str  # 分子B的SMILES
    bond_matches: int  # 匹配的键数
    atom_matches: int  # 匹配的原子数
    score: float  # MCS得分


class MCSFinder:
    """最大公共子结构查找器.
    
    该类用于在多个分子间查找最大公共子结构。
    支持两分子和多分子MCS查找，具有超时保护功能。
    
    属性:
        timeout: 每个聚类的最大搜索时间(秒)
        verbose: 是否输出详细日志
    
    示例:
        >>> finder = MCSFinder(timeout=30, verbose=True)
        >>> result = finder.find_mcs(molecules)
        >>> if result:
        ...     print(f"找到MCS: {result.smiles}")
    """

    def __init__(self, timeout: int = 30, verbose: bool = False) -> None:
        """初始化MCS查找器.

        Args:
            timeout: 每个聚类的最大搜索时间(秒)，默认为30秒.
            verbose: 是否输出详细日志，默认为False.
        """
        self.timeout = timeout
        self.verbose = verbose

    def find_mcs(
        self, molecules: List[Dict[str, Any]], threshold: float = 0.8
    ) -> Optional[MCSResult]:
        """在多个分子间查找最大公共子结构.
        
        对于两个分子，直接比较查找MCS。
        对于多个分子，采用两两比较策略，选择最优结果。

        Args:
            molecules: 分子字典列表，每个字典需包含'mol'和'smiles'键.
            threshold: 最小原子/键匹配阈值 (0.0-1.0)，默认为0.8.

        Returns:
            MCSResult对象，查找失败时返回None.

        Raises:
            MCSError: 提供的分子少于2个时抛出.
        """
        # 至少需要2个分子
        if len(molecules) < 2:
            raise MCSError("At least 2 molecules are required for MCS search")

        # 两个分子时直接比较
        if len(molecules) == 2:
            return self._find_mcs_pair(
                molecules[0]["mol"],
                molecules[0]["smiles"],
                molecules[1]["mol"],
                molecules[1]["smiles"],
            )

        # 提取分子对象和SMILES列表
        mols = [m["mol"] for m in molecules]
        smiles_list = [m["smiles"] for m in molecules]

        start_time = datetime.now()

        best_score = 0.0
        best_mcs = None
        n_mols = len(mols)

        for i in range(n_mols):
            # Check timeout once per outer iteration instead of every inner iteration
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > self.timeout:
                logger.warning(f"MCS search timeout after {elapsed:.1f}s")
                break

            for j in range(i + 1, n_mols):
                try:
                    result = self._find_mcs_pair(
                        mols[i], smiles_list[i], mols[j], smiles_list[j]
                    )
                    if result and result.score > best_score:
                        best_score = result.score
                        best_mcs = result
                except Exception as e:
                    logger.warning(f"MCS search failed for pair ({i}, {j}): {e}")
                    continue

        return best_mcs

    def _find_mcs_pair(
        self, mol_a: Chem.Mol, smiles_a: str, mol_b: Chem.Mol, smiles_b: str
    ) -> Optional[MCSResult]:
        """查找两个分子之间的MCS.
        
        使用RDKit的rdFMCS算法查找两个分子的最大公共子结构。
        
        Args:
            mol_a: 第一个分子对象.
            smiles_a: 第一个分子的SMILES.
            mol_b: 第二个分子对象.
            smiles_b: 第二个分子的SMILES.
            
        Returns:
            MCSResult对象，查找失败时返回None.
        """
        if self.verbose:
            logger.info(
                f"Finding MCS between: {smiles_a[:30]}... and {smiles_b[:30]}..."
            )

        # 使用RDKit的FMCS算法查找MCS
        mcs_result = rdFMCS.FindMCS(
            [mol_a, mol_b],
            threshold=0.8,  # 匹配阈值
            ringMatchesRingOnly=True,  # 只匹配环中的环
            completeRingsOnly=True,  # 只匹配完整环
            timeout=self.timeout,  # 超时限制
        )

        if mcs_result is None:
            return None

        mcs_smarts = mcs_result.smartsString
        if not mcs_smarts:
            return None

        mcs_mol = Chem.MolFromSmarts(mcs_smarts)
        if mcs_mol is None:
            return None

        num_atoms = mcs_result.numAtoms
        num_bonds = mcs_result.numBonds

        if num_atoms == 0:
            return None

        match_a = mol_a.GetSubstructMatches(mcs_mol)
        match_b = mol_b.GetSubstructMatches(mcs_mol)

        atom_matches = len(match_a[0]) if match_a else 0

        # Count bonds in MCS that exist in both molecules
        bond_matches = 0
        if match_a and match_b:
            for mcs_bond in mcs_mol.GetBonds():
                mcs_atom1 = mcs_bond.GetBeginAtomIdx()
                mcs_atom2 = mcs_bond.GetEndAtomIdx()
                # Map MCS atom indices to actual atoms in mol_a and mol_b
                atom1_a = match_a[0][mcs_atom1]
                atom2_a = match_a[0][mcs_atom2]
                atom1_b = match_b[0][mcs_atom1]
                atom2_b = match_b[0][mcs_atom2]
                # Check if bond exists in both molecules
                if mol_a.GetBondBetweenAtoms(atom1_a, atom2_a) is not None:
                    if mol_b.GetBondBetweenAtoms(atom1_b, atom2_b) is not None:
                        bond_matches += 1

        # 计算MCS得分: MCS原子数 / 最大分子原子数
        score = float(num_atoms) / max(mol_a.GetNumAtoms(), mol_b.GetNumAtoms())

        return MCSResult(
            mcs_mol=mcs_mol,
            smiles=mcs_smarts,
            num_atoms=num_atoms,
            num_bonds=num_bonds,
            smiles_a=smiles_a,
            smiles_b=smiles_b,
            bond_matches=bond_matches,
            atom_matches=atom_matches,
            score=score,
        )

    def find_mcs_for_clusters(
        self, clusters: List[Any]
    ) -> Dict[int, Optional[MCSResult]]:
        """为每个聚类查找MCS.
        
        批量处理多个聚类，为每个聚类查找最大公共子结构。

        Args:
            clusters: 聚类对象列表，每个对象需有'molecules'属性.

        Returns:
            字典，键为cluster_id，值为MCSResult或None.
        """
        results: Dict[int, Optional[MCSResult]] = {}

        for cluster in clusters:
            cluster_id = (
                cluster.cluster_id
                if hasattr(cluster, "cluster_id")
                else cluster.get("cluster_id", 0)
            )
            molecules = (
                cluster.molecules
                if hasattr(cluster, "molecules")
                else cluster.get("molecules", [])
            )

            logger.info(
                f"Finding MCS for cluster {cluster_id} with {len(molecules)} molecules"
            )

            try:
                mcs = self.find_mcs(molecules)
                results[cluster_id] = mcs
            except MCSError as e:
                logger.warning(f"Skipping cluster {cluster_id}: {e}")
                results[cluster_id] = None

        return results


@dataclass
class SubstituentInfo:
    """取代基信息数据类.
    
    存储特定位置上的取代基信息。
    
    属性:
        position_idx: 在MCS骨架上的位置索引
        substituent_smiles: 取代基的SMILES表示
        substituent_mol: 取代基的RDKit分子对象
        mol_name: 所属分子的名称
        activity: 分子的活性值
    """

    position_idx: int  # 位置索引
    substituent_smiles: str  # 取代基SMILES
    substituent_mol: Chem.Mol  # 取代基分子对象
    mol_name: str  # 分子名称
    activity: float  # 活性值


@dataclass
class ScaffoldInfo:
    """骨架信息数据类 - 包含R基团位置.
    
    存储MCS骨架及其上的R基团(取代位点)信息。
    
    属性:
        scaffold_mol: 骨架的RDKit分子对象(MCS)
        scaffold_smiles: 骨架的SMILES表示
        r_positions: R基团位置字典，键为位置索引，值为取代基列表
        num_r_groups: R基团数量(取代位点数量)
    """

    scaffold_mol: Chem.Mol  # 骨架分子对象
    scaffold_smiles: str  # 骨架SMILES
    r_positions: Dict[int, List[SubstituentInfo]]  # R基团位置字典
    num_r_groups: int  # R基团数量


def find_substitution_positions(
    mcs_mol: Chem.Mol,
    molecules: List[Dict[str, Any]],
) -> Optional[ScaffoldInfo]:
    """查找MCS骨架上的取代位点.
    
    分析分子与MCS的匹配关系，识别MCS骨架上的R基团位置。
    R基团是连接到MCS骨架但不属于MCS的原子或基团。

    Args:
        mcs_mol: MCS分子对象(骨架).
        molecules: 分子字典列表，需包含'mol', 'smiles', 'name', 'activity'.

    Returns:
        ScaffoldInfo对象，包含R基团位置信息，无取代位点时返回None.
    """
    if len(molecules) == 0:
        return None

    r_positions: Dict[int, List[SubstituentInfo]] = {}

    for mol_data in molecules:
        mol = mol_data["mol"]
        name = mol_data.get("name", "unknown")
        activity = mol_data.get("activity", 0.0)

        match = mol.GetSubstructMatch(mcs_mol)
        if not match:
            continue

        mcs_atom_set = set(match)
        mol_atom_to_mcs = {mol_idx: mcs_idx for mcs_idx, mol_idx in enumerate(match)}

        for atom in mol.GetAtoms():
            if atom.GetIdx() not in mcs_atom_set:
                continue

            neighbors = atom.GetNeighbors()
            for neighbor in neighbors:
                if neighbor.GetIdx() not in mcs_atom_set:
                    sub_mol, sub_smiles = _extract_substituent(
                        mol, atom.GetIdx(), neighbor.GetIdx()
                    )
                    if sub_mol is None:
                        continue

                    mcs_atom_idx = mol_atom_to_mcs.get(atom.GetIdx())
                    if mcs_atom_idx is None:
                        continue
                    if mcs_atom_idx not in r_positions:
                        r_positions[mcs_atom_idx] = []

                    r_positions[mcs_atom_idx].append(
                        SubstituentInfo(
                            position_idx=mcs_atom_idx,
                            substituent_smiles=sub_smiles,
                            substituent_mol=sub_mol,
                            mol_name=name,
                            activity=activity,
                        )
                    )

    if not r_positions:
        return None

    scaffold_smiles = Chem.MolToSmiles(mcs_mol)

    return ScaffoldInfo(
        scaffold_mol=mcs_mol,
        scaffold_smiles=scaffold_smiles,
        r_positions=r_positions,
        num_r_groups=len(r_positions),
    )


def _extract_substituent(
    mol: Chem.Mol, attachment_atom_idx: int, sub_atom_idx: int
) -> Tuple[Optional[Chem.Mol], str]:
    """从分子中提取取代基.
    
    使用BFS遍历从连接点开始提取取代基的原子集合。

    Args:
        mol: 完整分子对象.
        attachment_atom_idx: 骨架原子(连接点)的索引.
        sub_atom_idx: 取代基第一个原子的索引.

    Returns:
        元组 (取代基分子对象, 取代基SMILES)，提取失败时返回 (None, "").
    """
    sub_atoms = set()
    queue = [sub_atom_idx]
    visited = {sub_atom_idx}

    while queue:
        current = queue.pop(0)
        sub_atoms.add(current)
        for neighbor in mol.GetAtomWithIdx(current).GetNeighbors():
            if (
                neighbor.GetIdx() not in visited
                and neighbor.GetIdx() != attachment_atom_idx
            ):
                visited.add(neighbor.GetIdx())
                queue.append(neighbor.GetIdx())

    if not sub_atoms:
        return None, ""

    # 使用MolFragmentToSmiles从原子索引提取取代基SMILES，再转为分子对象
    # 注意: Chem.PathToSubmol需要键索引而非原子索引，此处不应使用
    try:
        sub_smiles = Chem.MolFragmentToSmiles(mol, atomsToUse=list(sub_atoms))
        if not sub_smiles:
            return None, ""
        sub_mol = Chem.MolFromSmiles(sub_smiles)
        if sub_mol is None:
            return None, ""
        return sub_mol, sub_smiles
    except Exception as e:
        logger.warning(f"Failed to extract substituent: {e}")
        return None, ""


def create_marked_scaffold(
    scaffold_info: ScaffoldInfo,
    size: Tuple[int, int] = (400, 300),
) -> bytes:
    """创建带R基团标签的骨架图像.
    
    生成MCS骨架的2D图像，并在R基团位置标记R1, R2等标签。

    Args:
        scaffold_info: 包含R基团位置的ScaffoldInfo对象.
        size: 图像尺寸 (宽, 高)，默认为(400, 300).

    Returns:
        PNG格式的图像字节数据.
    """
    from rdkit.Chem import AllChem

    scaffold_mol = Chem.Mol(scaffold_info.scaffold_mol)

    # 将SMARTS分子转换为普通分子对象以获得更好的渲染效果
    # SMARTS模式的查询原子/键会导致渲染异常
    try:
        scaffold_smiles = Chem.MolToSmiles(scaffold_mol)
        proper_mol = Chem.MolFromSmiles(scaffold_smiles)
        if proper_mol is not None and proper_mol.GetNumAtoms() > 0:
            # 重新映射R基团位置: 旧原子索引 -> 新原子索引
            match = proper_mol.GetSubstructMatch(scaffold_mol)
            if match:
                new_r_positions = {}
                for mcs_idx, r_info in scaffold_info.r_positions.items():
                    if mcs_idx < len(match):
                        new_r_positions[match[mcs_idx]] = r_info
                    else:
                        new_r_positions[mcs_idx] = r_info
                scaffold_mol = proper_mol
                r_positions = new_r_positions
            else:
                r_positions = scaffold_info.r_positions
        else:
            r_positions = scaffold_info.r_positions
    except Exception:
        r_positions = scaffold_info.r_positions

    AllChem.Compute2DCoords(scaffold_mol)
    sorted_positions = sorted(r_positions.keys())

    for i, mcs_atom_idx in enumerate(sorted_positions):
        r_label = f"R{i + 1}"
        scaffold_mol.GetAtomWithIdx(mcs_atom_idx).SetProp("_displayLabel", r_label)

    d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
    d.drawOptions().addStereoAnnotation = False
    d.drawOptions().addAtomIndices = False
    d.DrawMolecule(scaffold_mol)
    d.FinishDrawing()

    return d.GetDrawingText()
