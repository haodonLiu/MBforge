"""分子标准化模块.

提供化学结构的标准化处理，包括盐去除、互变异构标准化、电荷中性化、
立体化学清理等。标准化是化学信息学工作流的基础步骤。

核心类:
    MoleculeStandardizer: 分子标准化器

示例:
    >>> std = MoleculeStandardizer()
    >>> mol = Chem.MolFromSmiles("[Na+].O=C([O-])c1ccccc1")
    >>> clean = std.standardize(mol)
    >>> print(Chem.MolToSmiles(clean))
    O=C(O)c1ccccc1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rdkit import Chem
from rdkit.Chem import SaltRemover
from rdkit.Chem.MolStandardize import rdMolStandardize

logger = logging.getLogger(__name__)


@dataclass
class StandardizationResult:
    """标准化结果.

    属性:
        mol: 标准化后的分子对象.
        success: 是否成功.
        steps_applied: 应用的步骤列表.
        changes: 变更描述列表.
        errors: 错误信息列表.
    """

    mol: Chem.Mol | None = None
    success: bool = True
    steps_applied: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MoleculeStandardizer:
    """分子标准化器.

    提供可配置的分子标准化流水线，支持以下步骤：
    1. 去盐 (remove_salts)
    2. 去溶剂 (remove_solvents)
    3. 中性化 (neutralize)
    4. 互变异构标准化 (tautomerize)
    5. 立体化学清理 (clear_stereo)
    6. 芳香性规范化 (canonicalize_aromaticity)
    7. 原子映射号清理 (clear_atom_map_nums)
    8. 规范化 SMILES (canonicalize)

    属性:
        remove_salts: 是否去盐.
        remove_solvents: 是否去溶剂.
        neutralize: 是否中性化.
        tautomerize: 是否互变异构标准化.
        clear_stereo: 是否清除立体化学.
        canonicalize_aromaticity: 是否规范芳香性.
        clear_atom_map_nums: 是否清除原子映射号.
    """

    def __init__(
        self,
        remove_salts: bool = True,
        remove_solvents: bool = True,
        neutralize: bool = True,
        tautomerize: bool = True,
        clear_stereo: bool = False,
        canonicalize_aromaticity: bool = True,
        clear_atom_map_nums: bool = True,
    ) -> None:
        """初始化标准化器.

        Args:
            remove_salts: 是否去除盐离子，默认为 True.
            remove_solvents: 是否去除溶剂分子，默认为 True.
            neutralize: 是否电荷中性化，默认为 True.
            tautomerize: 是否互变异构标准化，默认为 True.
            clear_stereo: 是否清除立体化学信息，默认为 False.
            canonicalize_aromaticity: 是否规范芳香性，默认为 True.
            clear_atom_map_nums: 是否清除原子映射号，默认为 True.
        """
        self.remove_salts = remove_salts
        self.remove_solvents = remove_solvents
        self.neutralize = neutralize
        self.tautomerize = tautomerize
        self.clear_stereo = clear_stereo
        self.canonicalize_aromaticity = canonicalize_aromaticity
        self.clear_atom_map_nums = clear_atom_map_nums

        # 初始化 RDKit 的标准化工具
        self._salt_remover = SaltRemover.SaltRemover()
        self._salt_remover_defn = SaltRemover.SaltRemover()

        self._tautomer_enumerator = rdMolStandardize.TautomerEnumerator()
        self._uncharger = rdMolStandardize.Uncharger()
        self._normalizer = rdMolStandardize.Normalizer()

    def standardize(self, mol: Chem.Mol) -> StandardizationResult:
        """执行完整的分子标准化流水线.

        Args:
            mol: 输入分子.

        Returns:
            标准化结果.
        """
        if mol is None:
            return StandardizationResult(
                mol=None,
                success=False,
                errors=["Input mol is None"],
            )

        result = StandardizationResult(mol=Chem.Mol(mol))
        original_smiles = Chem.MolToSmiles(mol)

        try:
            # 1. 去盐
            if self.remove_salts:
                stripped = self._salt_remover.StripMol(result.mol)
                if stripped.GetNumAtoms() < result.mol.GetNumAtoms():
                    result.mol = stripped
                    result.steps_applied.append("remove_salts")
                    result.changes.append("Removed salt ions")

            # 2. 去溶剂
            if self.remove_solvents:
                result.mol = self._remove_solvents(result.mol)
                if Chem.MolToSmiles(result.mol) != original_smiles:
                    result.steps_applied.append("remove_solvents")
                    result.changes.append("Removed solvent molecules")

            # 3. 中性化
            if self.neutralize:
                new_mol = self._uncharger.uncharge(result.mol)
                if new_mol is not None:
                    result.mol = new_mol
                    result.steps_applied.append("neutralize")
                    result.changes.append("Neutralized charges")

            # 4. 互变异构标准化
            if self.tautomerize:
                new_mol = self._tautomer_enumerator.Canonicalize(result.mol)
                if new_mol is not None:
                    if Chem.MolToSmiles(new_mol) != Chem.MolToSmiles(result.mol):
                        result.changes.append("Standardized tautomer")
                    result.mol = new_mol
                    result.steps_applied.append("tautomerize")

            # 5. RDKit MolStandardize 规范化
            result.mol = self._normalizer.normalize(result.mol)
            result.steps_applied.append("normalize")

            # 6. 立体化学处理
            if self.clear_stereo:
                Chem.RemoveStereochemistry(result.mol)
                result.steps_applied.append("clear_stereo")

            # 7. 芳香性规范
            if self.canonicalize_aromaticity:
                Chem.SanitizeMol(result.mol)
                result.steps_applied.append("canonicalize_aromaticity")

            # 8. 清除原子映射号
            if self.clear_atom_map_nums:
                for atom in result.mol.GetAtoms():
                    atom.SetAtomMapNum(0)
                result.steps_applied.append("clear_atom_map_nums")

            # 最终校验
            if result.mol is None or result.mol.GetNumAtoms() == 0:
                return StandardizationResult(
                    mol=None,
                    success=False,
                    errors=["Standardization resulted in empty molecule"],
                )

            final_smiles = Chem.MolToSmiles(result.mol)
            if final_smiles != original_smiles:
                result.changes.append(
                    f"SMILES changed: {original_smiles} -> {final_smiles}"
                )

            result.success = True
            return result

        except Exception as e:
            logger.warning(f"Standardization failed: {e}")
            return StandardizationResult(
                mol=None,
                success=False,
                errors=[str(e)],
                steps_applied=result.steps_applied,
            )

    def standardize_smiles(self, smiles: str) -> str | None:
        """直接对 SMILES 字符串进行标准化.

        Args:
            smiles: 输入 SMILES.

        Returns:
            标准化后的 SMILES，失败返回 None.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        result = self.standardize(mol)
        if result.success and result.mol is not None:
            return Chem.MolToSmiles(result.mol)
        return None

    def standardize_batch(
        self,
        molecules: list[Chem.Mol],
        names: list[str] | None = None,
    ) -> list[StandardizationResult]:
        """批量标准化.

        Args:
            molecules: 分子列表.
            names: 可选名称列表.

        Returns:
            标准化结果列表.
        """
        results = []
        for i, mol in enumerate(molecules):
            result = self.standardize(mol)
            results.append(result)
            if not result.success and names:
                logger.warning(
                    f"Standardization failed for {names[i]}: {result.errors}"
                )
        return results

    @staticmethod
    def _remove_solvents(mol: Chem.Mol) -> Chem.Mol:
        """去除常见溶剂分子（内部方法）.

        简单实现：检测是否为单一小分子片段（< 5 个重原子）且常见溶剂.
        """
        frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
        if len(frags) <= 1:
            return mol

        # 保留最大的非溶剂片段
        non_solvent_frags = []
        for frag in frags:
            num_heavy = frag.GetNumHeavyAtoms()
            if num_heavy < 3:
                continue  # 跳过极小片段
            non_solvent_frags.append(frag)

        if not non_solvent_frags:
            return mol  # 全部都很小，返回原始分子

        # 选择重原子最多的片段
        largest = max(non_solvent_frags, key=lambda m: m.GetNumHeavyAtoms())
        return largest

    @staticmethod
    def strip_salts(smiles: str) -> str | None:
        """静态方法：快速去除 SMILES 中的盐.

        Args:
            smiles: 输入 SMILES.

        Returns:
            去盐后的 SMILES，失败返回 None.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        remover = SaltRemover.SaltRemover()
        mol = remover.StripMol(mol)
        return Chem.MolToSmiles(mol)

    @staticmethod
    def canonicalize_smiles(smiles: str) -> str | None:
        """静态方法：生成规范化的 Canonical SMILES.

        Args:
            smiles: 输入 SMILES.

        Returns:
            Canonical SMILES，失败返回 None.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        try:
            mol = rdMolStandardize.Normalizer().normalize(mol)
            mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
            return Chem.MolToSmiles(mol)
        except Exception:
            return Chem.MolToSmiles(mol)

    @staticmethod
    def neutralize_smiles(smiles: str) -> str | None:
        """静态方法：中性化 SMILES.

        Args:
            smiles: 输入 SMILES.

        Returns:
            中性化后的 SMILES，失败返回 None.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        try:
            mol = rdMolStandardize.Uncharger().uncharge(mol)
            return Chem.MolToSmiles(mol)
        except Exception:
            return Chem.MolToSmiles(mol)
