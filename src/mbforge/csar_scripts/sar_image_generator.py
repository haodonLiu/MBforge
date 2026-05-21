"""SAR Image Generator - Generate Structure-Activity Relationship images.

This module creates professional SAR images with:
- Top: MCS scaffold with R-group labels (R1, R2, etc.)
- Bottom: Table with substituent structures (with attachment indicator ~) and activity data

Features:
- Wavy line (~) attachment indicator for substituents
- Support for additional property columns (MW, LogP, TPSA, etc.)
- High-resolution PNG output suitable for scientific reports
- Color-coded activity values
- Clustering before SAR analysis (each cluster <= 10 molecules)
"""
from __future__ import annotations

import io
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Draw, rdFMCS
from rdkit.Chem import DataStructs
from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
from rdkit.Chem.Draw import rdMolDraw2D

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SubstituentData:
    """Substituent data with molecular properties."""
    position_idx: int
    r_label: str
    smiles: str
    mol: Optional[Chem.Mol]
    activity: float
    mol_name: str
    full_mol: Optional[Chem.Mol] = None
    # Physicochemical properties
    mw: float = 0.0
    logp: float = 0.0
    tpsa: float = 0.0
    hbd: int = 0
    hba: int = 0


@dataclass
class ScaffoldData:
    """Scaffold (MCS) data with R-group positions."""
    mol: Optional[Chem.Mol] = None
    smiles: str = ""
    r_positions: Dict[int, List[SubstituentData]] = field(default_factory=dict)


# =============================================================================
# Core Functions
# =============================================================================

def calculate_properties(mol: Chem.Mol) -> Dict[str, float]:
    """Calculate molecular physicochemical properties.
    
    Args:
        mol: RDKit molecule object.
        
    Returns:
        Dictionary of calculated properties.
    """
    if mol is None:
        return {"MW": 0, "LogP": 0, "TPSA": 0, "HBD": 0, "HBA": 0}
    
    try:
        return {
            "MW": round(Descriptors.MolWt(mol), 1),
            "LogP": round(Descriptors.MolLogP(mol), 2),
            "TPSA": round(Descriptors.TPSA(mol), 1),
            "HBD": Descriptors.NumHDonors(mol),
            "HBA": Descriptors.NumHAcceptors(mol),
        }
    except Exception:
        return {"MW": 0, "LogP": 0, "TPSA": 0, "HBD": 0, "HBA": 0}


def extract_substituent(
    mol: Chem.Mol, attachment_idx: int, sub_idx: int
) -> Tuple[Optional[Chem.Mol], str]:
    """Extract substituent from molecule using BFS.
    
    Args:
        mol: Full molecule.
        attachment_idx: Index of attachment atom (on scaffold).
        sub_idx: Index of first substituent atom.
        
    Returns:
        Tuple of (substituent Mol, substituent SMILES).
    """
    sub_atoms = set()
    queue = [sub_idx]
    visited = {sub_idx}
    
    while queue:
        current = queue.pop(0)
        sub_atoms.add(current)
        for neighbor in mol.GetAtomWithIdx(current).GetNeighbors():
            if neighbor.GetIdx() not in visited and neighbor.GetIdx() != attachment_idx:
                visited.add(neighbor.GetIdx())
                queue.append(neighbor.GetIdx())
    
    if not sub_atoms:
        return None, ""
    
    try:
        sub_smiles = Chem.MolFragmentToSmiles(mol, atomsToUse=list(sub_atoms))
        if not sub_smiles:
            return None, ""
        sub_mol = Chem.MolFromSmiles(sub_smiles)
        return sub_mol, sub_smiles
    except Exception:
        return None, ""


def find_mcs_and_substituents(
    molecules: List[Dict[str, Any]],
    min_atoms: int = 3,
    timeout: int = 30,
    sample_size: int = 8,
    max_r_groups: int = 2,
) -> Optional[ScaffoldData]:
    """Find MCS and extract substituents for all molecules.

    Randomly samples molecules for MCS finding to improve performance.
    Filters to keep only MCS with at most max_r_groups substituents.

    Args:
        molecules: List of molecule dicts with 'mol', 'smiles', 'name', 'activity'.
        min_atoms: Minimum atoms for valid MCS.
        timeout: MCS search timeout in seconds.
        sample_size: Number of molecules to sample for MCS finding.
        max_r_groups: Maximum number of R-groups allowed (default 2, max 6).

    Returns:
        ScaffoldData object or None if no MCS found.
    """
    # 限制最大R基团数量为合理范围
    max_r_groups = min(max(1, max_r_groups), 6)

    if len(molecules) < 2:
        logger.warning("Need at least 2 molecules for MCS")
        return None
    
    if len(molecules) > sample_size:
        sample_mols = random.sample(molecules, sample_size)
        logger.info(f"Sampling {sample_size} molecules from {len(molecules)} total")
    else:
        sample_mols = molecules
    
    mols = [m["mol"] for m in sample_mols if m.get("mol") is not None]
    if len(mols) < 2:
        return None
    
    # Find MCS
    logger.info("Finding MCS...")
    mcs_result = rdFMCS.FindMCS(
        mols,
        ringMatchesRingOnly=False,  # Allow non-ring matches
        completeRingsOnly=False,
        timeout=timeout,
        threshold=0.5,  # Allow partial match
    )
    
    if mcs_result.numAtoms < min_atoms:
        logger.warning(f"MCS too small: {mcs_result.numAtoms} atoms")
        return None
    
    mcs_smarts = mcs_result.smartsString
    mcs_mol = Chem.MolFromSmarts(mcs_smarts)
    
    if mcs_mol is None:
        return None
    
    logger.info(f"MCS found: {mcs_result.numAtoms} atoms, SMARTS: {mcs_smarts[:50]}...")
    
    # Extract substituents
    r_positions: Dict[int, List[SubstituentData]] = {}
    r_counter: Dict[int, int] = {}
    
    for mol_data in molecules:
        mol = mol_data.get("mol")
        if mol is None:
            continue
        
        name = mol_data.get("name", "unknown")
        activity = mol_data.get("activity", 0.0)
        
        match = mol.GetSubstructMatch(mcs_mol)
        if not match:
            continue
        
        mcs_atom_set = set(match)
        mol_to_mcs = {mol_idx: mcs_idx for mcs_idx, mol_idx in enumerate(match)}
        
        # Find substituents at each scaffold atom
        for atom in mol.GetAtoms():
            if atom.GetIdx() not in mcs_atom_set:
                continue
            
            for neighbor in atom.GetNeighbors():
                if neighbor.GetIdx() not in mcs_atom_set:
                    # Found a substituent
                    sub_mol, sub_smiles = extract_substituent(
                        mol, atom.GetIdx(), neighbor.GetIdx()
                    )
                    
                    mcs_atom_idx = mol_to_mcs.get(atom.GetIdx())
                    if mcs_atom_idx is None:
                        continue
                    
                    if mcs_atom_idx not in r_positions:
                        r_positions[mcs_atom_idx] = []
                        r_counter[mcs_atom_idx] = len(r_positions)
                    
                    # Calculate properties
                    props = calculate_properties(sub_mol) if sub_mol else {}
                    
                    sub_data = SubstituentData(
                        position_idx=mcs_atom_idx,
                        r_label=f"R{r_counter[mcs_atom_idx] + 1}",
                        smiles=sub_smiles,
                        mol=sub_mol,
                        activity=activity,
                        mol_name=name,
                        full_mol=mol,
                        mw=props.get("MW", 0),
                        logp=props.get("LogP", 0),
                        tpsa=props.get("TPSA", 0),
                        hbd=props.get("HBD", 0),
                        hba=props.get("HBA", 0),
                    )
                    r_positions[mcs_atom_idx].append(sub_data)
    
    if not r_positions:
        return None
    
    # Filter to keep only MCS with at most max_r_groups
    if len(r_positions) > max_r_groups:
        # Sort by number of substituents and keep top max_r_groups
        sorted_r = sorted(r_positions.items(), key=lambda x: len(x[1]), reverse=True)
        r_positions = dict(sorted_r[:max_r_groups])
        logger.info(f"Filtered MCS from {len(r_positions)} to {max_r_groups} R-groups")
    
    scaffold_smiles = Chem.MolToSmiles(mcs_mol)
    
    return ScaffoldData(
        mol=mcs_mol,
        smiles=scaffold_smiles,
        r_positions=r_positions,
    )


# =============================================================================
# Rendering Functions
# =============================================================================

def render_scaffold_with_r_labels(
    scaffold_mol: Chem.Mol,
    r_positions: Dict[int, List],
    size: Tuple[int, int] = (600, 400),
) -> Optional[Image.Image]:
    """Render scaffold with R-group labels.
    
    Args:
        scaffold_mol: MCS scaffold molecule.
        r_positions: Dictionary mapping atom indices to substituent lists.
        size: Image size (width, height).
        
    Returns:
        PIL Image of scaffold with R labels.
    """
    if scaffold_mol is None:
        return None
    
    # Convert SMARTS to proper molecule for better rendering
    scaffold_copy = None
    try:
        scaffold_smiles = Chem.MolToSmiles(scaffold_mol)
        proper_mol = Chem.MolFromSmiles(scaffold_smiles)
        if proper_mol is not None and proper_mol.GetNumAtoms() > 0:
            # Map old R positions to new indices
            match = proper_mol.GetSubstructMatch(scaffold_mol)
            if match:
                new_r_positions = {}
                for old_idx, r_list in r_positions.items():
                    if old_idx < len(match):
                        new_r_positions[match[old_idx]] = r_list
                    else:
                        new_r_positions[old_idx] = r_list
                r_positions = new_r_positions
            scaffold_copy = proper_mol
        else:
            scaffold_copy = Chem.Mol(scaffold_mol)
    except Exception:
        scaffold_copy = Chem.Mol(scaffold_mol)
    
    # Set R labels
    sorted_positions = sorted(r_positions.keys())
    
    for i, atom_idx in enumerate(sorted_positions):
        r_label = f"R{i + 1}"
        try:
            scaffold_copy.GetAtomWithIdx(atom_idx).SetProp("_displayLabel", r_label)
        except Exception:
            pass
    
    AllChem.Compute2DCoords(scaffold_copy)
    
    # Render
    d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
    d.drawOptions().addStereoAnnotation = True
    d.drawOptions().addAtomIndices = False
    d.drawOptions().fixedBondLength = 20
    d.DrawMolecule(scaffold_copy)
    d.FinishDrawing()
    
    png_bytes = d.GetDrawingText()
    return Image.open(io.BytesIO(png_bytes))


def render_substituent_with_wavy_line(
    sub_mol: Chem.Mol,
    size: Tuple[int, int] = (100, 70),
    attachment_char: str = "~",
) -> Optional[Image.Image]:
    """Render substituent with wavy line attachment indicator.
    
    Args:
        sub_mol: Substituent molecule.
        size: Image size.
        attachment_char: Character for attachment (~ or -).
        
    Returns:
        PIL Image with attachment indicator.
    """
    if sub_mol is None or sub_mol.GetNumAtoms() == 0:
        # Return placeholder for H (no substituent)
        img = Image.new("RGB", (size[0] + 30, size[1]), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            font = ImageFont.load_default()
        draw.text((15, size[1]//2 - 7), "H", fill=(0, 0, 0), font=font)
        return img
    
    try:
        AllChem.Compute2DCoords(sub_mol)
        d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
        d.drawOptions().addStereoAnnotation = False
        d.drawOptions().addAtomIndices = False
        d.drawOptions().fixedBondLength = 12
        d.DrawMolecule(sub_mol)
        d.FinishDrawing()
        
        png_bytes = d.GetDrawingText()
        mol_img = Image.open(io.BytesIO(png_bytes))
        
        # Create image with wavy line attachment indicator
        attachment_width = 25
        total_width = attachment_width + size[0]
        combined = Image.new("RGB", (total_width, size[1]), "white")
        draw = ImageDraw.Draw(combined)
        
        # Draw wavy line
        y_center = size[1] // 2
        wave_points = []
        for i in range(4):
            x = 2 + i * 6
            y = y_center + (4 if i % 2 == 0 else -4)
            wave_points.append((x, y))
        
        if len(wave_points) >= 2:
            draw.line(wave_points, fill=(0, 0, 0), width=2)
        
        # Paste molecule image
        combined.paste(mol_img, (attachment_width, 0))
        
        return combined
        
    except Exception as e:
        logger.warning(f"Failed to render substituent: {e}")
        return None


def get_activity_color(activity: Optional[float]) -> Tuple[int, int, int]:
    """Get color based on activity value (IC50).
    
    Green = high activity (low IC50)
    Red = low activity (high IC50)
    """
    if activity is None:
        return (255, 255, 255)
    
    if activity <= 10:
        return (144, 238, 144)  # Light green
    elif activity <= 100:
        t = (activity - 10) / 90
        return (144 + int(111 * t), 238 - int(38 * t), 144 - int(144 * t))
    elif activity <= 1000:
        t = (activity - 100) / 900
        return (255, 200 - int(100 * t), 0)
    else:
        return (255, 99, 71)  # Tomato red


def create_sar_table(
    scaffold_data: ScaffoldData,
    include_properties: List[str] = None,
    sub_size: Tuple[int, int] = (100, 70),
    font_size: int = 11,
) -> Optional[Image.Image]:
    """Create SAR table with substituents and activity data.
    
    Args:
        scaffold_data: ScaffoldData with R positions and substituents.
        include_properties: List of property columns to include.
        sub_size: Substituent image size.
        font_size: Font size for text.
        
    Returns:
        PIL Image of the table.
    """
    if include_properties is None:
        include_properties = ["MW", "LogP"]
    
    # Collect unique substituent combinations
    r_keys = sorted(scaffold_data.r_positions.keys())
    num_r_groups = len(r_keys)
    
    if num_r_groups == 0:
        return None
    
    # Build rows: each row is a unique molecule with its substituents
    molecule_data: Dict[str, Dict] = {}  # mol_name -> data
    
    for r_idx, sub_list in scaffold_data.r_positions.items():
        for sub in sub_list:
            if sub.mol_name not in molecule_data:
                molecule_data[sub.mol_name] = {
                    "activity": sub.activity,
                    "substituents": {},
                    "full_mol": sub.full_mol,
                }
            molecule_data[sub.mol_name]["substituents"][r_idx] = sub
    
    if not molecule_data:
        return None
    
    # Sort by activity
    sorted_mols = sorted(molecule_data.items(), key=lambda x: x[1]["activity"])
    
    # Build table rows
    rows = []
    for mol_name, data in sorted_mols:
        row = []
        for r_idx in r_keys:
            sub = data["substituents"].get(r_idx)
            if sub and sub.mol:
                img = render_substituent_with_wavy_line(sub.mol, sub_size)
                row.append(img if img else "H")
            else:
                row.append("H")
        
        # Add activity
        activity = data["activity"]
        if activity and activity > 0:
            row.append(f"{activity:.1f}")
        else:
            row.append("N/A")
        
        # Add properties (use first substituent's properties as representative)
        first_sub = list(data["substituents"].values())[0] if data["substituents"] else None
        for prop in include_properties:
            if first_sub:
                val = getattr(first_sub, prop.lower(), 0)
                if isinstance(val, float):
                    row.append(f"{val:.1f}" if prop == "MW" else f"{val:.2f}")
                else:
                    row.append(str(val))
            else:
                row.append("-")
        
        rows.append((activity, row))
    
    # Build column labels
    col_labels = [f"R{i+1}" for i in range(num_r_groups)]
    col_labels.append("IC50(nM)")
    col_labels.extend(include_properties)
    
    # Create table image
    return _render_table(rows, col_labels, sub_size, font_size)


def _render_table(
    rows: List[Tuple[float, List[Any]]],
    col_labels: List[str],
    sub_size: Tuple[int, int],
    font_size: int,
) -> Image.Image:
    """Render the actual table image."""
    # Calculate dimensions
    img_col_width = sub_size[0] + 35  # Extra space for wavy line
    text_col_width = 70
    row_height = sub_size[1] + 15
    header_height = 35
    padding = 10
    
    num_cols = len(col_labels)
    num_rows = len(rows)
    
    # Determine column widths
    col_widths = []
    for i, label in enumerate(col_labels):
        if i < len(col_labels) - len(["IC50(nM)"]):  # Image columns
            col_widths.append(img_col_width)
        else:  # Text columns
            col_widths.append(text_col_width)
    
    total_width = sum(col_widths) + padding * 2
    total_height = header_height + num_rows * row_height + padding * 2
    
    # Create image
    table = Image.new("RGB", (total_width, total_height), "white")
    draw = ImageDraw.Draw(table)
    
    # Load font
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        header_font = ImageFont.truetype("arialbd.ttf", font_size + 1)
    except Exception:
        font = ImageFont.load_default()
        header_font = font
    
    # Draw header
    y = padding
    x = padding
    for i, (label, width) in enumerate(zip(col_labels, col_widths)):
        draw.rectangle([x, y, x + width, y + header_height], 
                      fill=(220, 220, 220), outline=(0, 0, 0), width=1)
        
        bbox = draw.textbbox((0, 0), label, font=header_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text((x + (width - text_w) // 2, y + (header_height - text_h) // 2),
                 label, fill=(0, 0, 0), font=header_font)
        x += width
    
    # Draw rows
    for row_idx, (activity, row) in enumerate(rows):
        y = padding + header_height + row_idx * row_height
        
        # Row background color based on activity
        bg_color = get_activity_color(activity)
        draw.rectangle([padding, y, total_width - padding, y + row_height],
                      fill=bg_color, outline=(0, 0, 0), width=1)
        
        x = padding
        for col_idx, (cell, width) in enumerate(zip(row, col_widths)):
            if isinstance(cell, Image.Image):
                # Center image in cell
                img_x = x + (width - cell.width) // 2
                img_y = y + (row_height - cell.height) // 2
                table.paste(cell, (img_x, img_y))
            else:
                # Draw text
                text = str(cell)
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                draw.text((x + (width - text_w) // 2, y + (row_height - text_h) // 2),
                         text, fill=(0, 0, 0), font=font)
            
            # Cell border
            draw.rectangle([x, y, x + width, y + row_height], outline=(0, 0, 0), width=1)
            x += width
    
    return table


def create_sar_image(
    scaffold_data: ScaffoldData,
    output_path: Union[str, Path],
    title: str = "SAR Analysis",
    scaffold_size: Tuple[int, int] = (500, 350),
    sub_size: Tuple[int, int] = (90, 65),
    include_properties: List[str] = None,
) -> bool:
    """Create complete SAR image with scaffold and table.
    
    Args:
        scaffold_data: ScaffoldData from find_mcs_and_substituents().
        output_path: Output PNG file path.
        title: Image title.
        scaffold_size: Scaffold image size.
        sub_size: Substituent image size.
        include_properties: Property columns to include.
        
    Returns:
        True if successful, False otherwise.
    """
    if scaffold_data.mol is None:
        logger.error("No scaffold molecule")
        return False
    
    if include_properties is None:
        include_properties = ["MW", "LogP"]
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Render scaffold
    logger.info("Rendering scaffold...")
    scaffold_img = render_scaffold_with_r_labels(
        scaffold_data.mol, scaffold_data.r_positions, scaffold_size
    )
    
    if scaffold_img is None:
        logger.error("Failed to render scaffold")
        return False
    
    # Create table
    logger.info("Creating SAR table...")
    table_img = create_sar_table(
        scaffold_data, include_properties, sub_size
    )
    
    if table_img is None:
        logger.error("Failed to create table")
        return False
    
    # Combine images
    scaffold_w, scaffold_h = scaffold_img.size
    table_w, table_h = table_img.size
    
    total_width = max(scaffold_w, table_w) + 40
    title_height = 50 if title else 0
    total_height = title_height + scaffold_h + table_h + 40
    
    combined = Image.new("RGB", (total_width, total_height), "white")
    draw = ImageDraw.Draw(combined)
    
    # Load font
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 16)
    except Exception:
        title_font = ImageFont.load_default()
    
    # Draw title
    if title:
        bbox = draw.textbbox((0, 0), title, font=title_font)
        text_w = bbox[2] - bbox[0]
        draw.text(((total_width - text_w) // 2, 15), title, fill=(0, 0, 0), font=title_font)
    
    # Paste scaffold
    scaffold_x = (total_width - scaffold_w) // 2
    combined.paste(scaffold_img, (scaffold_x, title_height + 10))
    
    # Paste table
    table_x = (total_width - table_w) // 2
    combined.paste(table_img, (table_x, title_height + scaffold_h + 25))
    
    # Save
    combined.save(output_path, dpi=(300, 300))
    logger.info(f"SAR image saved to {output_path}")
    
    return True


# =============================================================================
# Clustering Functions
# =============================================================================

def generate_morgan_fingerprint(mol: Chem.Mol, radius: int = 2, nBits: int = 2048) -> Any:
    """Generate Morgan fingerprint for a molecule.
    
    Args:
        mol: RDKit molecule object.
        radius: Morgan fingerprint radius.
        nBits: Number of bits.
        
    Returns:
        Fingerprint array.
    """
    if mol is None:
        return None
    try:
        # Use new GetMorganGenerator API (RDKit 2023.09+)
        generator = GetMorganGenerator(radius=radius, fpSize=nBits)
        fp = generator.GetFingerprint(mol)
        arr = np.zeros((nBits,), dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        return arr
    except Exception:
        return None


def calculate_tanimoto(fp1: np.ndarray, fp2: np.ndarray) -> float:
    """Calculate Tanimoto similarity between two fingerprints.
    
    Args:
        fp1: First fingerprint array.
        fp2: Second fingerprint array.
        
    Returns:
        Tanimoto similarity (0-1).
    """
    if fp1 is None or fp2 is None:
        return 0.0
    try:
        bits1 = set(np.where(fp1 == 1)[0])
        bits2 = set(np.where(fp2 == 1)[0])
        if len(bits1) == 0 and len(bits2) == 0:
            return 1.0
        if len(bits1) == 0 or len(bits2) == 0:
            return 0.0
        intersection = len(bits1 & bits2)
        union = len(bits1 | bits2)
        return intersection / union if union > 0 else 0.0
    except Exception:
        return 0.0


def cluster_molecules(
    molecules: List[Dict[str, Any]],
    threshold: float = 0.7,
    max_cluster_size: int = 10,
    hierarchical: bool = True,
    min_substituents: int = 6,
) -> List[List[Dict[str, Any]]]:
    """Cluster molecules based on Tanimoto similarity with hierarchical clustering.
    
    Two-level hierarchical clustering:
    1. First level: coarse clustering (lower threshold)
    2. Second level: fine clustering within each coarse cluster
    
    Args:
        molecules: List of molecule dicts.
        threshold: Similarity threshold (0-1) for first level.
        max_cluster_size: Maximum molecules per final cluster.
        hierarchical: Use hierarchical clustering (default True).
        min_substituents: Minimum substituents required per cluster (default 6).
        
    Returns:
        List of clusters, each cluster is a list of molecule dicts.
    """
    if len(molecules) <= max_cluster_size:
        return [molecules]
    
    logger.info(f"Clustering {len(molecules)} molecules (threshold={threshold}, max={max_cluster_size})...")
    
    if not hierarchical or len(molecules) <= 20:
        # Simple single-level clustering for small datasets
        return _single_level_clustering(molecules, threshold, max_cluster_size)
    
    # Hierarchical clustering: two levels
    # First level: coarse clustering (threshold - 0.15)
    coarse_threshold = max(0.3, threshold - 0.15)
    logger.info(f"Level 1: Coarse clustering (threshold={coarse_threshold})...")
    
    coarse_clusters = _single_level_clustering(molecules, coarse_threshold, max_cluster_size * 3)
    logger.info(f"Created {len(coarse_clusters)} coarse clusters")
    
    # Second level: fine clustering within each coarse cluster
    final_clusters = []
    for i, coarse_cluster in enumerate(coarse_clusters):
        if len(coarse_cluster) <= max_cluster_size:
            # Already small enough
            final_clusters.append(coarse_cluster)
        else:
            logger.info(f"  Level 2: Fine clustering coarse cluster {i+1} ({len(coarse_cluster)} molecules)...")
            fine_clusters = _single_level_clustering(coarse_cluster, threshold, max_cluster_size)
            final_clusters.extend(fine_clusters)
    
    logger.info(f"Final: {len(final_clusters)} clusters")
    for i, c in enumerate(final_clusters):
        logger.info(f"  Cluster {i+1}: {len(c)} molecules")
    
    # Filter clusters to ensure minimum substituents
    if min_substituents > 0:
        logger.info(f"Filtering clusters to ensure >= {min_substituents} substituents...")
        valid_clusters = []
        for i, cluster in enumerate(final_clusters):
            if len(cluster) < 2:
                logger.debug(f"  Cluster {i+1}: Skipped (only {len(cluster)} molecules)")
                continue
            
            # Quick MCS check to count substituents
            scaffold_data = find_mcs_and_substituents(cluster, max_r_groups=10)
            if scaffold_data is None:
                logger.debug(f"  Cluster {i+1}: Skipped (no MCS found)")
                continue
            
            # Count total unique substituents
            total_subs = sum(len(subs) for subs in scaffold_data.r_positions.values())
            
            if total_subs >= min_substituents:
                valid_clusters.append(cluster)
                logger.info(f"  Cluster {i+1}: OK ({len(cluster)} molecules, {total_subs} substituents)")
            else:
                logger.debug(f"  Cluster {i+1}: Skipped (only {total_subs} substituents, need {min_substituents})")
        
        logger.info(f"Filtered: {len(valid_clusters)}/{len(final_clusters)} clusters meet minimum substituent requirement")
        return valid_clusters
    
    return final_clusters


def _single_level_clustering(
    molecules: List[Dict[str, Any]],
    threshold: float,
    max_cluster_size: int,
) -> List[List[Dict[str, Any]]]:
    """Perform single-level clustering based on Tanimoto similarity."""
    # Generate fingerprints
    fps = []
    valid_indices = []
    for i, mol_data in enumerate(molecules):
        mol = mol_data.get("mol")
        fp = generate_morgan_fingerprint(mol)
        if fp is not None:
            fps.append(fp)
            valid_indices.append(i)
    
    if len(fps) < 2:
        return [molecules]
    
    n = len(fps)
    
    # Calculate distance matrix (1 - similarity)
    dist_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            sim = calculate_tanimoto(fps[i], fps[j])
            dist = 1.0 - sim
            dist_matrix[i, j] = dist
            dist_matrix[j, i] = dist
    
    # Single-linkage clustering
    clusters = [[i] for i in range(n)]
    
    # Keep merging until minimum distance > (1 - threshold) or cluster too large
    while len(clusters) > 1:
        # Find closest pair of clusters
        min_dist = float('inf')
        merge_pair = (0, 1)
        
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # Complete linkage (maximum distance)
                max_dist = 0
                for idx1 in clusters[i]:
                    for idx2 in clusters[j]:
                        d = dist_matrix[idx1, idx2]
                        if d > max_dist:
                            max_dist = d
                
                if max_dist < min_dist:
                    min_dist = max_dist
                    merge_pair = (i, j)
        
        # Stop if clusters are too dissimilar
        if min_dist > (1 - threshold):
            break
        
        # Check if merged cluster would exceed size limit
        new_size = len(clusters[merge_pair[0]]) + len(clusters[merge_pair[1]])
        if new_size > max_cluster_size:
            break
        
        # Merge clusters
        i, j = merge_pair
        clusters[i].extend(clusters[j])
        clusters.pop(j)
    
    # Convert indices back to molecule dicts
    result_clusters = []
    for cluster_indices in clusters:
        cluster_mols = [molecules[valid_indices[i]] for i in cluster_indices]
        result_clusters.append(cluster_mols)
    
    return result_clusters


# =============================================================================
# Main Function for Testing
# =============================================================================

def generate_sar_images_from_clusters(
    csv_path: Union[str, Path],
    output_dir: Union[str, Path],
    smiles_column: str = "SMILES",
    name_column: str = "Compound_ID",
    activity_column: str = "IC50_nM",
    include_properties: List[str] = None,
    cluster_threshold: float = 0.7,
    max_cluster_size: int = 10,
    cluster_id: Optional[int] = None,
    min_substituents: int = 6,
    max_r_groups: int = 2,
) -> List[Path]:
    """Generate SAR images from clustered molecules.

    Args:
        csv_path: Path to CSV file.
        output_dir: Output directory for SAR images.
        smiles_column: SMILES column name.
        name_column: Compound name column.
        activity_column: Activity column name.
        include_properties: Property columns to include.
        cluster_threshold: Tanimoto similarity threshold for clustering.
        max_cluster_size: Maximum molecules per cluster.
        cluster_id: If specified, only generate SAR for this cluster (1-based).
        min_substituents: Minimum substituents per cluster (default 6).
        max_r_groups: Max R-groups per MCS (default 2, range 1-6).

    Returns:
        List of output image paths.
    """
    logger.info(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Validate columns
    if smiles_column not in df.columns:
        logger.error(f"SMILES column '{smiles_column}' not found")
        return []
    
    # Parse molecules
    molecules = []
    for _, row in df.iterrows():
        smi = row.get(smiles_column, "")
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        
        activity = row.get(activity_column)
        if pd.isna(activity):
            activity = 0.0
        elif isinstance(activity, str):
            try:
                activity = float(activity)
            except ValueError:
                activity = 0.0
        
        molecules.append({
            "mol": mol,
            "smiles": smi,
            "name": str(row.get(name_column, "unknown")),
            "activity": float(activity),
        })
    
    logger.info(f"Parsed {len(molecules)} valid molecules")
    
    if len(molecules) < 2:
        logger.error("Need at least 2 valid molecules")
        return []
    
    # Cluster molecules
    clusters = cluster_molecules(
        molecules, 
        cluster_threshold, 
        max_cluster_size,
        min_substituents=min_substituents,
    )
    
    # Create output directory
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate SAR image for each cluster
    output_paths = []
    
    for i, cluster_mols in enumerate(clusters):
        if cluster_id is not None and (i + 1) != cluster_id:
            continue
        
        logger.info(f"\n=== Processing Cluster {i+1}/{len(clusters)} ({len(cluster_mols)} molecules) ===")
        
        # Find MCS and substituents for this cluster
        scaffold_data = find_mcs_and_substituents(
            cluster_mols,
            max_r_groups=max_r_groups,
        )
        
        if scaffold_data is None:
            logger.warning(f"Failed to find MCS for cluster {i+1}")
            continue
        
        # Check if this cluster has valid R-groups
        if len(scaffold_data.r_positions) == 0:
            logger.warning(f"No R-groups found for cluster {i+1}")
            continue
        
        logger.info(f"  MCS has {len(scaffold_data.r_positions)} R-group(s)")
        
        # Generate SAR image
        output_path = output_dir / f"sar_cluster_{i+1}.png"
        
        success = create_sar_image(
            scaffold_data,
            output_path,
            title=f"SAR Analysis - Cluster {i+1} ({len(cluster_mols)} compounds)",
            include_properties=include_properties,
        )
        
        if success:
            output_paths.append(output_path)
            logger.info(f"Saved: {output_path}")
    
    return output_paths


def generate_sar_from_csv(
    csv_path: Union[str, Path],
    output_path: Union[str, Path],
    smiles_column: str = "SMILES",
    name_column: str = "Compound_ID",
    activity_column: str = "IC50_nM",
    include_properties: List[str] = None,
) -> bool:
    """Generate SAR image from CSV file.
    
    DEPRECATED: Use generate_sar_images_from_clusters instead.
    
    Args:
        csv_path: Path to CSV file.
        output_path: Output PNG path.
        smiles_column: SMILES column name.
        name_column: Compound name column.
        activity_column: Activity column name.
        include_properties: Property columns to include.
        
    Returns:
        True if successful.
    """
    logger.info(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Validate columns
    if smiles_column not in df.columns:
        logger.error(f"SMILES column '{smiles_column}' not found")
        return False
    
    # Parse molecules
    molecules = []
    for _, row in df.iterrows():
        smi = row.get(smiles_column, "")
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        
        activity = row.get(activity_column)
        if pd.isna(activity):
            activity = 0.0
        elif isinstance(activity, str):
            try:
                activity = float(activity)
            except ValueError:
                activity = 0.0
        
        molecules.append({
            "mol": mol,
            "smiles": smi,
            "name": str(row.get(name_column, "unknown")),
            "activity": float(activity),
        })
    
    logger.info(f"Parsed {len(molecules)} valid molecules")
    
    if len(molecules) < 2:
        logger.error("Need at least 2 valid molecules")
        return False
    
    # Find MCS and substituents
    scaffold_data = find_mcs_and_substituents(molecules)
    
    if scaffold_data is None:
        logger.error("Failed to find MCS")
        return False
    
    # Generate SAR image
    return create_sar_image(
        scaffold_data,
        output_path,
        include_properties=include_properties,
    )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python sar_image_generator.py <input.csv> [output_dir] [options]")
        print("  input.csv      - Input CSV file")
        print("  output_dir     - Output directory (default: output/sar/)")
        print("  --cluster ID   - Generate SAR only for cluster ID (1-based)")
        print("  --threshold N  - Clustering threshold (default: 0.7)")
        print("  --max N        - Max molecules per cluster (default: 10)")
        print("  --min-subs N   - Min substituents per cluster (default: 6)")
        print("  --r-groups N   - Max R-groups per MCS (default: 2, range 1-6)")
        print("")
        print("Example:")
        print("  python sar_image_generator.py data.csv output/sar/")
        print("  python sar_image_generator.py data.csv output/sar/ --cluster 1")
        print("  python sar_image_generator.py data.csv output/sar/ --threshold 0.6 --max 8 --min-subs 6")
        print("  python sar_image_generator.py data.csv output/sar/ --r-groups 4")
        sys.exit(1)
    
    csv_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/sar")
    
    # Parse optional arguments
    cluster_id = None
    threshold = 0.7
    max_size = 10
    min_subs = 6
    max_r_groups = 2

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--cluster" and i + 1 < len(sys.argv):
            cluster_id = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--threshold" and i + 1 < len(sys.argv):
            threshold = float(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--max" and i + 1 < len(sys.argv):
            max_size = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--min-subs" and i + 1 < len(sys.argv):
            min_subs = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--r-groups" and i + 1 < len(sys.argv):
            max_r_groups = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    print(f"\nSAR Image Generation")
    print(f"  Input: {csv_file}")
    print(f"  Output: {output_dir}")
    print(f"  Clustering threshold: {threshold}")
    print(f"  Max molecules per cluster: {max_size}")
    print(f"  Min substituents per cluster: {min_subs}")
    print(f"  Max R-groups per MCS: {max_r_groups}")
    if cluster_id:
        print(f"  Target cluster: {cluster_id}")
    print()

    output_paths = generate_sar_images_from_clusters(
        csv_file,
        output_dir,
        cluster_threshold=threshold,
        max_cluster_size=max_size,
        cluster_id=cluster_id,
        min_substituents=min_subs,
        max_r_groups=max_r_groups,
    )
    
    if output_paths:
        print(f"\nGenerated {len(output_paths)} SAR image(s):")
        for p in output_paths:
            print(f"  - {p}")
        sys.exit(0)
    else:
        print("\nFailed to generate SAR images")
        sys.exit(1)
