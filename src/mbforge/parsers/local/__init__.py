"""parsers/local — 本地 PDF 处理轨道.

与 parsers/uniparser/（UniParser API）形成双轨，均输出标准 Molecule 对象。

轨道：
- PyMuPDF 文本/图片提取
- regex + LLM 分子识别
- 输出 Molecule 对象（schema.py 契约）

示例:
    >>> from mbforge.parsers.local import LocalMoleculeExtractor
    >>> from mbforge.molecules.schema import Molecule
    >>> extractor = LocalMoleculeExtractor()
    >>> mols = extractor.extract_from_text("CCO is ethanol. C=C is ethene.")
    >>> [m.smiles for m in mols]
    ['CCO', 'C=C']
"""

from __future__ import annotations

from ..molecule import MoleculeExtractor

__all__ = [
    "MoleculeExtractor",
]
