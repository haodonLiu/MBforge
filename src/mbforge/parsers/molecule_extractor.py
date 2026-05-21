"""分子数据提取器.

从文本中识别 SMILES、化学名、活性数据等。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

try:
    from rdkit import Chem
except ImportError:
    Chem = None  # type: ignore

from ..molecules.schema import Molecule


class MoleculeExtractor:
    """从非结构化文本中提取分子信息."""

    # 常见 SMILES 模式（简化）
    SMILES_PATTERN = re.compile(
        r'[A-Za-z0-9@\.\+\-\=\#\$\(\)\[\]\\\/\%]{4,}'
    )

    # 活性数据模式：如 IC50 = 5.2 nM, EC50: 10 µM 等
    ACTIVITY_PATTERN = re.compile(
        r'(IC50|EC50|Ki|Kd|pIC50|pEC50)\s*[=:~]\s*([0-9\.]+)\s*(nM|µM|uM|μM|mM|M|pM)',
        re.IGNORECASE,
    )

    def __init__(self):
        self._seen_smiles: set = set()

    def is_valid_smiles(self, smiles: str) -> bool:
        """验证 SMILES 是否有效."""
        if Chem is None:
            # fallback: basic syntax check
            return len(smiles) > 3 and any(c in smiles for c in "CcNnOoSsPp")
        try:
            mol = Chem.MolFromSmiles(smiles)
            return mol is not None and mol.GetNumAtoms() > 2
        except Exception:
            return False

    def extract_smiles_candidates(self, text: str) -> List[str]:
        """从文本中提取候选 SMILES."""
        candidates = []
        for match in self.SMILES_PATTERN.finditer(text):
            candidate = match.group(0)
            if candidate in self._seen_smiles:
                continue
            if self.is_valid_smiles(candidate):
                candidates.append(candidate)
                self._seen_smiles.add(candidate)
        return candidates

    def extract_activities(self, text: str) -> List[Dict[str, Any]]:
        """提取活性数据."""
        results = []
        for match in self.ACTIVITY_PATTERN.finditer(text):
            results.append({
                "type": match.group(1).upper(),
                "value": float(match.group(2)),
                "units": match.group(3).replace("uM", "µM"),
                "context": text[max(0, match.start() - 50):min(len(text), match.end() + 50)],
            })
        return results

    def extract_from_text(self, text: str, doc_id: str = "") -> List[Molecule]:
        """从文本提取分子记录."""
        smiles_list = self.extract_smiles_candidates(text)
        activities = self.extract_activities(text)

        # 预计算每个 SMILES 在文本中的位置
        smiles_positions = []
        for smi in smiles_list:
            pos = text.find(smi)
            if pos >= 0:
                smiles_positions.append((smi, pos))

        # 预计算每个活性数据在文本中的位置
        activity_positions = []
        for act in activities:
            pos = text.find(act["context"][:20])  # 用上下文片段定位
            if pos >= 0:
                activity_positions.append((act, pos))

        records = []
        used_activity_idx = set()
        for smi, smi_pos in smiles_positions:
            # 基于位置距离的精确匹配：找最近的未使用活性
            activity = None
            activity_unit = None
            if activity_positions:
                best_idx = None
                best_dist = float("inf")
                for idx, (act, act_pos) in enumerate(activity_positions):
                    if idx in used_activity_idx:
                        continue
                    dist = abs(smi_pos - act_pos)
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
                if best_idx is not None and best_dist < 200:
                    best = activity_positions[best_idx][0]
                    activity = best["value"]
                    activity_unit = best["units"]
                    used_activity_idx.add(best_idx)
            rec = Molecule(
                smiles=smi, source="pdf",
                activity=activity, activity_unit=activity_unit,
                metadata={"source_doc": doc_id},
            )
            records.append(rec)

        return records

    def extract_from_pdf_result(self, result_dict: Dict[str, Any], doc_id: str = "") -> List[Molecule]:
        """从 UniParser 解析结果提取分子."""
        records = []
        molecules = result_dict.get("molecules", [])
        for mol_data in molecules:
            smi = mol_data.get("smiles", "")
            if not smi or not self.is_valid_smiles(smi):
                continue
            rec = Molecule(
                smiles=smi,
                source="pdf",
                name=mol_data.get("name", ""),
                activity=mol_data.get("activity"),
                metadata={
                    "source_doc": doc_id,
                    "activity_type": mol_data.get("activity_type", ""),
                    "properties": mol_data.get("properties", {}),
                },
            )
            records.append(rec)
        return records
