"""Activity data extraction from reorganized markdown.

Extracts IC50/Ki/EC50/Kd values from tables and text using LLM-based parsing.
Phase 0 baseline: ~70% accuracy (requires human validation).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.extract_activities")


@dataclass
class ActivityRecord:
    """Single activity measurement extracted from text."""

    activity_type: str  # IC50, Ki, EC50, Kd, ED50
    value: float  # Normalized to nM
    value_original: float
    unit: str  # Original unit
    operator: str  # =, <, >, ~, >=, <=
    target: str | None
    assay_type: str | None
    raw_text: str
    confidence: float
    page_num: int | None
    evidence_kind: str  # table, text, figure_caption
    evidence_bbox: dict[str, float] | None


def extract_activities_from_document(
    reorganized_md_path: str,
    doc_id: str,
    llm_model: str = "gpt-4o-mini",
) -> list[ActivityRecord]:
    """Extract activity data from reorganized markdown.

    Args:
        reorganized_md_path: Path to reorganized.md
        doc_id: Document ID
        llm_model: LLM model name for extraction

    Returns:
        List of ActivityRecord objects (may be empty if no activities found)
    """
    from pathlib import Path

    md_text = Path(reorganized_md_path).read_text(encoding="utf-8")

    # Phase 0: 简化实现 — 只做表格抽取，不做 figure caption
    # Phase 1 可扩展到 caption/正文段落
    tables = _extract_tables_from_markdown(md_text)
    if not tables:
        logger.info("No tables found in %s, skipping activity extraction", doc_id)
        return []

    # 使用 LLM 批量解析表格
    records: list[ActivityRecord] = []
    for table_idx, table_md in enumerate(tables):
        try:
            activities = _parse_table_with_llm(table_md, table_idx, llm_model)
            records.extend(activities)
        except Exception as exc:
            logger.warning(
                "Failed to parse table %d in %s: %s", table_idx, doc_id, exc
            )

    logger.info("Extracted %d activity records from %s", len(records), doc_id)
    return records


def _extract_tables_from_markdown(md_text: str) -> list[str]:
    """Extract Markdown tables from text.

    Returns:
        List of table blocks (including header/separator/rows)
    """
    # Markdown table pattern: lines starting with '|'
    lines = md_text.split("\n")
    tables: list[str] = []
    current_table: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current_table.append(line)
        else:
            if current_table:
                tables.append("\n".join(current_table))
                current_table = []

    if current_table:
        tables.append("\n".join(current_table))

    return tables


def _parse_table_with_llm(
    table_md: str, table_idx: int, model: str
) -> list[ActivityRecord]:
    """Parse a Markdown table using LLM.

    Prompt strategy:
    - Few-shot examples from ChEMBL-like SAR tables
    - Structured JSON output (activity_type, value, unit, target, confidence)
    - Confidence scoring based on text clarity

    Args:
        table_md: Markdown table text
        table_idx: Table index in document
        model: LLM model name

    Returns:
        List of ActivityRecord objects
    """
    from ..utils.config import load_global_config

    cfg = load_global_config()

    # Lazy import to avoid circular dependencies
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("LangChain not available, skipping activity extraction")
        return []

    llm = ChatOpenAI(
        model=model,
        api_key=cfg.llm.api_key or "dummy",
        base_url=cfg.llm.base_url or None,
        temperature=0.0,  # Deterministic extraction
    )

    prompt = _build_extraction_prompt(table_md)

    try:
        response = llm.invoke(prompt)
        result_text = response.content if hasattr(response, "content") else str(response)
        activities_json = _extract_json_from_response(result_text)

        records: list[ActivityRecord] = []
        for item in activities_json:
            # Normalize unit to nM
            value_nm = _normalize_to_nm(
                item.get("value", 0), item.get("unit", "nM")
            )
            records.append(
                ActivityRecord(
                    activity_type=item.get("activity_type", "IC50"),
                    value=value_nm,
                    value_original=item.get("value", 0),
                    unit=item.get("unit", "nM"),
                    operator=item.get("operator", "="),
                    target=item.get("target"),
                    assay_type=item.get("assay_type"),
                    raw_text=item.get("raw_text", ""),
                    confidence=item.get("confidence", 0.5),
                    page_num=None,  # TODO: 从 markdown 提取页码
                    evidence_kind="table",
                    evidence_bbox=None,  # TODO: 表格 bbox 需要从 PDF 解析
                )
            )
        return records
    except Exception as exc:
        logger.warning("LLM parsing failed for table %d: %s", table_idx, exc)
        return []


def _build_extraction_prompt(table_md: str) -> str:
    """Build few-shot prompt for activity extraction."""
    return f"""Extract bioactivity data from the following SAR table.

Output a JSON array where each element has:
- activity_type: IC50 | Ki | EC50 | Kd | ED50
- value: numeric value (float)
- unit: nM | μM | mM | pM | M
- operator: = | < | > | ~ | >= | <=
- target: protein/enzyme name (e.g. "EGFR", "HER2", "CDK4/6")
- assay_type: enzymatic | cellular | binding (if mentioned)
- raw_text: exact text from the table
- confidence: 0.0-1.0 (your confidence in this extraction)

Example input:
| Compound | IC50 (nM) EGFR | IC50 (nM) HER2 |
|----------|----------------|----------------|
| 1a       | 10.2           | >1000          |
| 1b       | 5.3            | 450            |

Example output:
```json
[
  {{"activity_type": "IC50", "value": 10.2, "unit": "nM", "operator": "=", "target": "EGFR", "assay_type": "enzymatic", "raw_text": "IC50 (nM) EGFR: 10.2", "confidence": 0.9}},
  {{"activity_type": "IC50", "value": 1000, "unit": "nM", "operator": ">", "target": "HER2", "assay_type": "enzymatic", "raw_text": "IC50 (nM) HER2: >1000", "confidence": 0.8}},
  {{"activity_type": "IC50", "value": 5.3, "unit": "nM", "operator": "=", "target": "EGFR", "assay_type": "enzymatic", "raw_text": "IC50 (nM) EGFR: 5.3", "confidence": 0.95}},
  {{"activity_type": "IC50", "value": 450, "unit": "nM", "operator": "=", "target": "HER2", "assay_type": "enzymatic", "raw_text": "IC50 (nM) HER2: 450", "confidence": 0.9}}
]
```

Now extract from this table:

{table_md}

Output only the JSON array, no explanations."""


def _extract_json_from_response(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from LLM response (handles markdown code blocks)."""
    # Remove markdown code fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode failed: %s", exc)
        return []


def _normalize_to_nm(value: float, unit: str) -> float:
    """Convert activity value to nM."""
    unit_lower = unit.lower()
    if unit_lower in ("nm", "nanomolar"):
        return value
    if unit_lower in ("um", "μm", "micromolar"):
        return value * 1000
    if unit_lower in ("mm", "millimolar"):
        return value * 1_000_000
    if unit_lower in ("pm", "picomolar"):
        return value / 1000
    if unit_lower in ("m", "molar"):
        return value * 1_000_000_000
    logger.warning("Unknown unit %s, assuming nM", unit)
    return value
