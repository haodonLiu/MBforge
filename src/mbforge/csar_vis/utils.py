"""Shared visualization utilities for SAR analysis."""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple, List, Any

from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

logger = logging.getLogger(__name__)

# Constants
SUBSTITUENT_SIZE = (80, 60)
BORDER_COLOR = (0, 0, 0)
TEXT_COLOR = (0, 0, 0)


def render_substituent_image(
    mol: Chem.Mol,
    size: Tuple[int, int] = SUBSTITUENT_SIZE,
) -> Optional[Image.Image]:
    """Render a substituent molecule as an image.

    Args:
        mol: Substituent molecule object.
        size: Image size (width, height).

    Returns:
        PIL Image object, or None if rendering fails.
    """
    if mol is None or mol.GetNumAtoms() == 0:
        return None

    try:
        AllChem.Compute2DCoords(mol)
        d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
        d.drawOptions().addStereoAnnotation = False
        d.drawOptions().addAtomIndices = False
        d.drawOptions().fixedBondLength = 15
        d.DrawMolecule(mol)
        d.FinishDrawing()

        png_bytes = d.GetDrawingText()
        img = Image.open(io.BytesIO(png_bytes))
        return img
    except Exception as e:
        logger.warning(f"Failed to render substituent: {e}")
        return None


def combine_scaffold_and_table(
    scaffold_img: bytes,
    table_img: Image.Image,
    title: str = "",
    fontsize: int = 14,
) -> Image.Image:
    """Combine scaffold and table into a single image.

    Args:
        scaffold_img: Scaffold PNG bytes.
        table_img: Table PIL image.
        title: Optional title text.
        fontsize: Title font size.

    Returns:
        Combined PIL image.
    """
    scaffold_pil = Image.open(io.BytesIO(scaffold_img))

    scaffold_width, scaffold_height = scaffold_pil.size
    table_width, table_height = table_img.size

    total_width = max(scaffold_width, table_width)
    title_height = 40 if title else 0
    total_height = scaffold_height + title_height + table_height + 10

    combined = Image.new("RGB", (total_width, total_height), "white")
    draw = ImageDraw.Draw(combined)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fontsize
        )
    except Exception:
        font = ImageFont.load_default()

    if title:
        title_bbox = draw.textbbox((0, 0), title, font=font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (total_width - title_width) // 2
        draw.text((title_x, 10), title, fill=TEXT_COLOR, font=font)

    scaffold_x = (total_width - scaffold_width) // 2
    combined.paste(scaffold_pil, (scaffold_x, title_height))

    table_x = (total_width - table_width) // 2
    combined.paste(table_img, (table_x, title_height + scaffold_height + 10))

    return combined


def get_activity_color(activity: Optional[float]) -> Tuple[int, int, int]:
    """Get color based on activity value.

    Low IC50 (high activity) = green, high IC50 (low activity) = red.

    Color gradient:
        - IC50 <= 10 nM: pure green
        - 10 < IC50 <= 100 nM: green to yellow
        - 100 < IC50 <= 1000 nM: yellow to orange
        - IC50 > 1000 nM: pure red

    Args:
        activity: IC50 value in nM.

    Returns:
        RGB color tuple.
    """
    if activity is None:
        return (255, 255, 255)

    if activity <= 10:
        return (0, 255, 0)
    elif activity <= 100:
        t = (activity - 10) / 90
        return (int(255 * t), int(255 * (1 - t)), 0)
    elif activity <= 1000:
        t = (activity - 100) / 900
        return (255, int(128 * t), 0)
    else:
        return (255, 0, 0)


def extract_substituent(
    mol: Chem.Mol, attachment_atom_idx: int, sub_atom_idx: int
) -> Tuple[Optional[Chem.Mol], str]:
    """Extract substituent from molecule using BFS.

    Args:
        mol: Full molecule object.
        attachment_atom_idx: Index of attachment atom (connects to scaffold).
        sub_atom_idx: Index of first substituent atom.

    Returns:
        Tuple of (substituent molecule, substituent SMILES), or (None, "") on failure.
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


def create_sar_table_image(
    rows: List[List[Any]],
    col_labels: List[str],
    sub_size: Tuple[int, int] = SUBSTITUENT_SIZE,
    activity_col_index: Optional[int] = None,
    use_activity_colors: bool = False,
) -> Image.Image:
    """统一 SAR 表格图像创建 (消除 sar_table.py + renderer.py 重复).

    生成包含取代基图像或文本的 SAR 表格图像。
    支持可选的活性值颜色编码背景。

    Args:
        rows: 行列表，每行是单元格列表 (PIL Image 或 str).
        col_labels: 列标签列表.
        sub_size: 每个单元格尺寸 (宽, 高).
        activity_col_index: 活性值列索引 (用于颜色编码).
        use_activity_colors: 是否启用活性颜色编码.

    Returns:
        PIL Image 对象.
    """
    num_cols = len(col_labels)
    num_rows = len(rows)
    if num_rows == 0 or num_cols == 0:
        return Image.new("RGB", (100, 100), "white")

    cell_width = sub_size[0] + 10
    cell_height = sub_size[1] + 10
    label_height = 30
    padding = 5

    table_width = num_cols * cell_width + padding * 2
    table_height = label_height + num_rows * cell_height + padding * 2

    table = Image.new("RGB", (table_width, table_height), "white")
    draw = ImageDraw.Draw(table)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12
        )
    except Exception:
        font = ImageFont.load_default()

    HEADER_BG_COLOR = (200, 200, 200)
    draw.rectangle(
        [0, 0, table_width - 1, table_height - 1],
        outline=(0, 0, 0), width=2,
    )

    # 表头
    for col_idx, label in enumerate(col_labels):
        x = padding + col_idx * cell_width
        draw.rectangle(
            [x, padding, x + cell_width, padding + label_height],
            fill=HEADER_BG_COLOR, outline=(0, 0, 0),
        )
        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        draw.text((
            x + (cell_width - text_w) // 2,
            padding + (label_height - text_h) // 2,
        ), label, fill=(0, 0, 0), font=font)

    # 数据行
    for row_idx, row in enumerate(rows):
        y = padding + label_height + row_idx * cell_height

        # 确定该行的基础颜色
        row_bg = (255, 255, 255)
        if use_activity_colors and activity_col_index is not None and activity_col_index < len(row):
            cell_val = row[activity_col_index]
            if isinstance(cell_val, (int, float)):
                row_bg = get_activity_color(cell_val)

        for col_idx, cell in enumerate(row):
            x = padding + col_idx * cell_width

            # 斑马纹效果
            bg_color = (
                tuple(max(0, c - 15) for c in row_bg)
                if (row_idx + col_idx) % 2 == 0 else row_bg
            )

            draw.rectangle(
                [x + 1, y + 1, x + cell_width - 1, y + cell_height - 1],
                fill=bg_color,
            )

            if isinstance(cell, Image.Image):
                img_resized = cell.resize(sub_size, Image.Resampling.LANCZOS)
                table.paste(img_resized, (
                    x + (cell_width - sub_size[0]) // 2,
                    y + (cell_height - sub_size[1]) // 2,
                ))
            elif isinstance(cell, str):
                text_bbox = draw.textbbox((0, 0), cell, font=font)
                text_w = text_bbox[2] - text_bbox[0]
                text_h = text_bbox[3] - text_bbox[1]
                draw.text((
                    x + (cell_width - text_w) // 2,
                    y + (cell_height - text_h) // 2,
                ), cell, fill=(0, 0, 0), font=font)

            draw.rectangle([x, y, x + cell_width, y + cell_height], outline=(0, 0, 0))

    return table