"""E-SMILES (Extended SMILES) 解析与序列化.

E-SMILES 格式: SMILES<sep><EXTENSION>
- <sep> 之前为标准 SMILES，RDKit 可直接解析
- <EXTENSION> 为 XML 标签: <a>原子索引:基团</a>, <r>环索引:基团</r>, <c>环索引:名称</c>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from rdkit import Chem
from rdkit.Chem import AllChem

# E-SMILES 分隔符
SEP = "<sep>"

# 标签正则: <a>0:R[1]</a> 或 <r>0:R[1]</r> 或 <c>0:B</c>
_TAG_PATTERN = re.compile(r"<([arc])>(\d+):(.+?)</\1>")


@dataclass
class ESmilesTag:
    """E-SMILES 扩展标签."""

    type: Literal["a", "r", "c"]
    index: int
    group: str


@dataclass
class ESmiles:
    """E-SMILES 结构."""

    smiles: str  # 标准 SMILES 部分
    tags: list[ESmilesTag] = field(default_factory=list)

    def to_string(self) -> str:
        """序列化为 E-SMILES 字符串."""
        if not self.tags:
            return self.smiles
        ext_parts = []
        for tag in self.tags:
            ext_parts.append(f"<{tag.type}>{tag.index}:{tag.group}</{tag.type}>")
        return f"{self.smiles}{SEP}{''.join(ext_parts)}"


def parse_esmiles(esmiles: str) -> ESmiles:
    """解析 E-SMILES 字符串，返回 ESmiles 结构."""
    if SEP not in esmiles:
        smiles_part = esmiles
        ext_part = ""
    else:
        smiles_part, ext_part = esmiles.split(SEP, 1)

    tags: list[ESmilesTag] = []
    for m in _TAG_PATTERN.finditer(ext_part):
        tag_type = m.group(1)  # "a", "r", or "c"
        idx = int(m.group(2))
        group = m.group(3).strip()
        tags.append(ESmilesTag(type=tag_type, index=idx, group=group))

    return ESmiles(smiles=smiles_part, tags=tags)


def get_rdkit_mol(esmiles: str) -> Chem.ROMol:
    """从 E-SMILES 获取 RDKit 分子对象（忽略扩展标签）."""
    smiles_part = esmiles.split(SEP)[0]
    mol = Chem.MolFromSmiles(smiles_part)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles_part}")
    return mol


def mol_to_smiles(mol: Chem.ROMol, rooted_at: int = 0) -> str:
    """将 RDKit 分子序列化为唯一 SMILES（从指定原子 rooted）。"""
    return Chem.MolToSmiles(mol, rootedAtAtom=rooted_at)


def esmiles_to_mol(esmiles: str) -> tuple[Chem.ROMol, list[ESmilesTag]]:
    """解析 E-SMILES，返回 (RDKit ROMol, 扩展标签列表)."""
    parsed = parse_esmiles(esmiles)
    mol = get_rdkit_mol(esmiles)
    return mol, parsed.tags


def mol_to_esmiles(
    mol: Chem.ROMol,
    tags: Optional[list[ESmilesTag]] = None,
    rooted_at: int = 0,
) -> str:
    """将 RDKit 分子序列化回 E-SMILES."""
    smiles = mol_to_smiles(mol, rooted_at)
    if not tags:
        return smiles
    ext_parts = []
    for tag in tags:
        ext_parts.append(f"<{tag.type}>{tag.index}:{tag.group}</{tag.type}>")
    return f"{smiles}{SEP}{''.join(ext_parts)}"


def is_markush(esmiles: str) -> bool:
    """判断是否为 Markush 结构（含扩展标签）。"""
    return SEP in esmiles
