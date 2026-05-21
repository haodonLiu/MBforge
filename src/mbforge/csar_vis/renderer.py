"""SAR可视化渲染模块 - 使用matplotlib和RDKit.

本模块提供SAR分析结果的多种可视化功能:
    - MCS结构渲染: 显示最大公共子结构
    - 活性分布图: 柱状图显示聚类内活性分布
    - SAR汇总图: 聚类平均活性和大小关系
    - 相似度矩阵: 热图显示分子间相似度
    - 分子网格: 显示多个分子的2D结构
    - SAR表格: 显示骨架和R基团的对应关系

技术栈:
    - matplotlib: 用于统计图表
    - RDKit: 用于分子结构绘制
    - PIL: 用于图像处理和SAR表格生成

示例:
    >>> renderer = SARRenderer()
    >>> renderer.render_sar_summary(sar_results, "summary.png")
    >>> renderer.render_similarity_matrix(sim_matrix, "similarity.png")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Union, Tuple
from dataclasses import dataclass

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from rdkit import Chem
from rdkit.Chem import Draw

from ..mcs.finder import (
    create_marked_scaffold,
    MCSScaffoldInfo,
)
from .utils import (
    render_substituent_image,
    combine_scaffold_and_table,
    extract_substituent,
    create_sar_table_image,
)

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class RenderError(Exception):
    """渲染失败异常.

    当图像渲染过程失败时抛出此异常。
    """

    pass


@dataclass
class PlotSettings:
    """SAR绘图设置数据类.

    存储绘图的各种参数设置。

    属性:
        figure_size: 图像尺寸 (宽, 高)，默认(12, 8)
        dpi: 图像分辨率，默认300
        title_fontsize: 标题字体大小，默认14
        label_fontsize: 标签字体大小，默认12
        tick_fontsize: 刻度字体大小，默认10
        color_scheme: 颜色方案，默认"RdYlGn"(红-黄-绿)
        show_labels: 是否显示标签，默认True
        save_format: 保存格式，默认"png"
    """

    figure_size: tuple[int, int] = (12, 8)  # 图像尺寸
    dpi: int = 300  # 分辨率
    title_fontsize: int = 14  # 标题字体大小
    label_fontsize: int = 12  # 标签字体大小
    tick_fontsize: int = 10  # 刻度字体大小
    color_scheme: str = "RdYlGn"  # 颜色方案
    show_labels: bool = True  # 显示标签
    save_format: str = "png"  # 保存格式


class SARRenderer:
    """SAR渲染器 - 生成各种SAR分析可视化.

    该类提供多种方法来渲染SAR分析结果，包括:
    - MCS结构图
    - 活性分布图
    - SAR汇总图
    - 相似度矩阵热图
    - 分子网格图
    - SAR表格图

    属性:
        settings: PlotSettings对象，控制绘图参数

    示例:
        >>> renderer = SARRenderer()
        >>> renderer.render_sar_summary(results, "summary.png")
        >>> renderer.render_mcs(mcs_mol, "mcs.png", title="MCS Structure")
    """

    def __init__(self, settings: Optional[PlotSettings] = None) -> None:
        """初始化SAR渲染器.

        Args:
            settings: 绘图设置对象，使用默认值时为None.
        """
        self.settings = settings or PlotSettings()

    def render_mcs(
        self,
        mcs_mol: Chem.Mol,
        output_path: Union[str, Path],
        title: str = "MCS Structure",
    ) -> None:
        """渲染MCS结构为图像.

        Args:
            mcs_mol: MCS分子对象.
            output_path: 输出文件路径.
            title: 图像标题.
        """
        output_path = Path(output_path)
        logger.info(f"Rendering MCS to {output_path}")

        try:
            # 将SMARTS分子转换为普通分子对象以获得更好的渲染效果
            render_mol = mcs_mol
            try:
                smiles = Chem.MolToSmiles(mcs_mol)
                proper_mol = Chem.MolFromSmiles(smiles)
                if proper_mol is not None and proper_mol.GetNumAtoms() > 0:
                    render_mol = proper_mol
            except Exception:
                pass

            Draw.MolToMPL(render_mol, size=self.settings.figure_size)
            plt.title(title, fontsize=self.settings.title_fontsize)
            plt.savefig(output_path, dpi=self.settings.dpi, bbox_inches="tight")
            plt.close()
        except Exception as e:
            raise RenderError(f"Failed to render MCS: {e}") from e

    def render_cluster_activity(
        self,
        cluster_id: int,
        molecules: List[Dict[str, Any]],
        output_path: Union[str, Path],
        mcs_mol: Optional[Chem.Mol] = None,
    ) -> None:
        """渲染聚类的活性分布图.

        生成包含活性分布直方图和MCS结构的组合图。

        Args:
            cluster_id: 聚类ID.
            molecules: 分子字典列表，需包含'mol'和'activity'.
            output_path: 输出文件路径.
            mcs_mol: 可选的MCS分子，作为背景显示.
        """
        output_path = Path(output_path)
        activities = [m["activity"] for m in molecules if "activity" in m]

        if not activities:
            logger.warning(f"No activities for cluster {cluster_id}")
            return

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        axes[0].hist(activities, bins=20, edgecolor="black", alpha=0.7)
        axes[0].set_xlabel("Activity", fontsize=self.settings.label_fontsize)
        axes[0].set_ylabel("Count", fontsize=self.settings.label_fontsize)
        axes[0].set_title(
            f"Cluster {cluster_id} Activity Distribution",
            fontsize=self.settings.title_fontsize,
        )
        axes[0].grid(True, alpha=0.3)

        axes[1].axis("off")
        if mcs_mol:
            try:
                img = Draw.MolToImage(mcs_mol, size=(400, 300))
                axes[1].imshow(img)
                axes[1].set_title("MCS Scaffold", fontsize=self.settings.title_fontsize)
            except Exception as e:
                logger.warning(f"Failed to render MCS: {e}")

        plt.tight_layout()
        plt.savefig(output_path, dpi=self.settings.dpi, bbox_inches="tight")
        plt.close()

    def render_sar_summary(
        self, sar_results: Dict[int, Any], output_path: Union[str, Path]
    ) -> None:
        """渲染跨所有聚类的SAR汇总图.

        生成包含两个子图的汇总:
        - 左图: 各聚类的平均活性柱状图
        - 右图: 聚类大小与平均活性的散点图

        Args:
            sar_results: SAR结果字典，键为cluster_id.
            output_path: 输出文件路径.
        """
        output_path = Path(output_path)

        cluster_ids = sorted(sar_results.keys())
        mean_activities = [sar_results[cid].mean_activity for cid in cluster_ids]
        std_activities = [sar_results[cid].std_activity for cid in cluster_ids]
        sizes = [sar_results[cid].num_compounds for cid in cluster_ids]

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        x_pos = np.arange(len(cluster_ids))
        axes[0].bar(x_pos, mean_activities, yerr=std_activities, capsize=3, alpha=0.7)
        axes[0].set_xlabel("Cluster ID", fontsize=self.settings.label_fontsize)
        axes[0].set_ylabel("Mean Activity", fontsize=self.settings.label_fontsize)
        axes[0].set_title(
            "Mean Activity by Cluster", fontsize=self.settings.title_fontsize
        )
        axes[0].set_xticks(x_pos)
        axes[0].set_xticklabels(cluster_ids)
        axes[0].grid(True, alpha=0.3, axis="y")

        axes[1].scatter(sizes, mean_activities, s=100, alpha=0.6)
        for i, cid in enumerate(cluster_ids):
            axes[1].annotate(str(cid), (sizes[i], mean_activities[i]), fontsize=8)
        axes[1].set_xlabel(
            "Cluster Size (# compounds)", fontsize=self.settings.label_fontsize
        )
        axes[1].set_ylabel("Mean Activity", fontsize=self.settings.label_fontsize)
        axes[1].set_title(
            "Activity vs Cluster Size", fontsize=self.settings.title_fontsize
        )
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=self.settings.dpi, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved SAR summary to {output_path}")

    def render_similarity_matrix(
        self,
        sim_matrix: np.ndarray,
        output_path: Union[str, Path],
        labels: Optional[List[str]] = None,
    ) -> None:
        """渲染相似度矩阵热图.

        使用颜色编码显示分子间的相似度关系。

        Args:
            sim_matrix: NxN相似度矩阵.
            output_path: 输出文件路径.
            labels: 每个分子的可选标签.
        """
        output_path = Path(output_path)

        fig, ax = plt.subplots(figsize=(10, 8))

        im = ax.imshow(sim_matrix, cmap=self.settings.color_scheme, vmin=0, vmax=1)

        ax.set_title(
            "Tanimoto Similarity Matrix", fontsize=self.settings.title_fontsize
        )
        plt.colorbar(im, ax=ax, label="Similarity")

        if labels and len(labels) <= 20:
            ax.set_xticks(np.arange(len(labels)))
            ax.set_yticks(np.arange(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.set_yticklabels(labels)

        plt.tight_layout()
        plt.savefig(output_path, dpi=self.settings.dpi, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved similarity matrix to {output_path}")

    def render_mols_with_activities(
        self,
        molecules: List[Dict[str, Any]],
        output_path: Union[str, Path],
        mols_per_row: int = 4,
        legends: Optional[List[str]] = None,
    ) -> None:
        """渲染带活性标注的分子网格图.

        以网格形式显示多个分子的2D结构，并标注活性值。

        Args:
            molecules: 分子字典列表，需包含'mol'和'activity'.
            output_path: 输出文件路径.
            mols_per_row: 每行显示的分子数，默认4.
            legends: 可选的自定义图例.
        """
        output_path = Path(output_path)

        mols = [m["mol"] for m in molecules]

        legends_out = []
        for i, m in enumerate(molecules):
            act = m.get("activity", 0)
            name = m.get("name", f"mol_{i}")
            legends_out.append(f"{name}\nAct: {act:.2f}")

        try:
            img = Draw.MolsToGridImage(
                mols,
                molsPerRow=mols_per_row,
                legends=legends_out if legends is None else legends,
                returnPNG=False,
            )
            img.save(output_path)
        except Exception as e:
            raise RenderError(f"Failed to render molecules: {e}") from e

        logger.info(f"Saved molecule grid to {output_path}")

    def render_sar_table_image(
        self,
        scaffold_info: MCSScaffoldInfo,
        molecules: List[Dict[str, Any]],
        output_path: Union[str, Path],
        scaffold_size: Tuple[int, int] = (400, 300),
        sub_size: Tuple[int, int] = (80, 60),
    ) -> None:
        """渲染SAR表格图像.

        生成包含骨架和取代基的SAR表格图像。
        如果R基团超过2个，会生成多个图像(每2个R基团一个)。

        Args:
            scaffold_info: 包含R基团位置的MCSScaffoldInfo对象.
            molecules: 分子数据字典列表.
            output_path: 输出文件路径.
            scaffold_size: 骨架图像尺寸 (宽, 高).
            sub_size: 取代基图像尺寸 (宽, 高).
        """
        output_path = Path(output_path)
        logger.info(f"Rendering SAR table to {output_path}")

        r_atom_indices = sorted(scaffold_info.r_positions.keys())
        num_r = len(r_atom_indices)

        if num_r <= 2:
            self._render_single_table(
                scaffold_info,
                molecules,
                output_path,
                r_atom_indices,
                scaffold_size,
                sub_size,
            )
        else:
            pairs = []
            for i in range(0, num_r, 2):
                pair = r_atom_indices[i : i + 2]
                if len(pair) == 1:
                    pair = (
                        r_atom_indices[i - 1 : i + 1] if i > 0 else r_atom_indices[:2]
                    )
                pairs.append(pair)

            seen = []
            unique_pairs = []
            for p in pairs:
                key = tuple(sorted(p))
                if key not in seen:
                    seen.append(key)
                    unique_pairs.append(p)

            for idx, pair_indices in enumerate(unique_pairs):
                pair_scaffold = MCSScaffoldInfo(
                    scaffold_mol=scaffold_info.scaffold_mol,
                    scaffold_smiles=scaffold_info.scaffold_smiles,
                    r_positions={k: scaffold_info.r_positions[k] for k in pair_indices},
                    num_r_groups=len(pair_indices),
                )
                if idx == 0:
                    pair_output = output_path
                else:
                    stem = output_path.stem
                    suffix = output_path.suffix
                    pair_output = output_path.parent / f"{stem}_R{idx + 1}{suffix}"

                self._render_single_table(
                    pair_scaffold,
                    molecules,
                    pair_output,
                    pair_indices,
                    scaffold_size,
                    sub_size,
                )

    def _render_single_table(
        self,
        scaffold_info: MCSScaffoldInfo,
        molecules: List[Dict[str, Any]],
        output_path: Path,
        r_atom_indices: List[int],
        scaffold_size: Tuple[int, int],
        sub_size: Tuple[int, int],
    ) -> None:
        """Render a single SAR table image."""
        scaffold_img = create_marked_scaffold(scaffold_info, scaffold_size)

        rows = []
        col_labels = [f"R{i + 1}" for i in range(scaffold_info.num_r_groups)]
        col_labels.append("IC50 (nM)")

        r_to_idx = {idx: i for i, idx in enumerate(r_atom_indices)}

        sorted_mols = sorted(molecules, key=lambda m: m.get("activity", float("inf")))

        for mol_data in sorted_mols:
            mol = mol_data["mol"]
            activity = mol_data.get("activity")
            activity_raw = mol_data.get("activity_raw", "")

            match = mol.GetSubstructMatch(scaffold_info.scaffold_mol)
            if not match:
                continue

            mcs_atom_set = set(match)
            mol_to_mcs = {mol_idx: mcs_idx for mcs_idx, mol_idx in enumerate(match)}

            subs_at_r = {i: [] for i in range(scaffold_info.num_r_groups)}

            for atom in mol.GetAtoms():
                if atom.GetIdx() not in mcs_atom_set:
                    continue

                for neighbor in atom.GetNeighbors():
                    if neighbor.GetIdx() not in mcs_atom_set:
                        sub_mol, sub_smiles = extract_substituent(
                            mol, atom.GetIdx(), neighbor.GetIdx()
                        )
                        if sub_mol is None:
                            continue

                        mcs_atom_idx = mol_to_mcs.get(atom.GetIdx())
                        if mcs_atom_idx in r_to_idx:
                            r_idx = r_to_idx[mcs_atom_idx]
                            img = render_substituent_image(sub_mol, sub_size)
                            subs_at_r[r_idx].append((activity, img, sub_smiles))

            row = []
            for i in range(scaffold_info.num_r_groups):
                if subs_at_r[i]:
                    _, img, _ = subs_at_r[i][0]
                    row.append(img if img else "H")
                else:
                    row.append("H")

            if activity is not None:
                activity_text = f"{activity:.1f} nM"
            else:
                raw_str = str(activity_raw).strip() if activity_raw else ""
                if raw_str.upper() == "INACTIVATE":
                    activity_text = "INACTIVATE"
                else:
                    activity_text = "N/A"
            row.append(activity_text)
            rows.append(row)

        table_img = self._create_table_image(
            rows, col_labels, scaffold_info.num_r_groups, sub_size
        )

        combined_img = combine_scaffold_and_table(
            scaffold_img, table_img, "Cluster SAR"
        )

        combined_img.save(output_path)
        logger.info(f"Saved SAR table to {output_path}")

    def render_sar_path_image(
        self,
        scaffold_info: MCSScaffoldInfo,
        molecules: List[Dict[str, Any]],
        output_path: Union[str, Path],
        scaffold_size: Tuple[int, int] = (400, 300),
        sub_size: Tuple[int, int] = (80, 60),
    ) -> None:
        """渲染SAR修饰路径图像.

        显示带R标签的骨架，然后按修饰路径分组的表格。
        每个表格显示具有相同R1但不同R2的化合物(或反之)。

        Args:
            scaffold_info: 包含R基团位置的MCSScaffoldInfo对象.
            molecules: 分子数据字典列表.
            output_path: 输出文件路径.
            scaffold_size: 骨架图像尺寸.
            sub_size: 取代基图像尺寸.
        """
        output_path = Path(output_path)
        logger.info(f"Rendering SAR path to {output_path}")

        r_atom_indices = sorted(scaffold_info.r_positions.keys())
        num_r = len(r_atom_indices)

        if num_r == 0:
            logger.warning("No R-group positions found")
            return

        if num_r == 1:
            self._render_single_table(
                scaffold_info,
                molecules,
                output_path,
                r_atom_indices,
                scaffold_size,
                sub_size,
            )
            return

        scaffold_img = create_marked_scaffold(scaffold_info, scaffold_size)

        r_to_idx = {idx: i for i, idx in enumerate(r_atom_indices)}

        mol_data_list = []
        for mol_data in molecules:
            mol = mol_data["mol"]
            activity = mol_data.get("activity")
            activity_raw = mol_data.get("activity_raw", "")

            match = mol.GetSubstructMatch(scaffold_info.scaffold_mol)
            if not match:
                continue

            mcs_atom_set = set(match)
            mol_to_mcs = {mol_idx: mcs_idx for mcs_idx, mol_idx in enumerate(match)}

            r_values = {}
            for atom in mol.GetAtoms():
                if atom.GetIdx() not in mcs_atom_set:
                    continue
                for neighbor in atom.GetNeighbors():
                    if neighbor.GetIdx() not in mcs_atom_set:
                        sub_mol, sub_smiles = extract_substituent(
                            mol, atom.GetIdx(), neighbor.GetIdx()
                        )
                        if sub_mol is None:
                            continue
                        mcs_atom_idx = mol_to_mcs.get(atom.GetIdx())
                        if mcs_atom_idx in r_to_idx:
                            r_idx = r_to_idx[mcs_atom_idx]
                            r_values[r_idx] = sub_smiles

            if len(r_values) < num_r:
                for i in range(num_r):
                    if i not in r_values:
                        r_values[i] = "H"

            if activity is not None:
                activity_text = f"{activity:.1f} nM"
            else:
                raw_str = str(activity_raw).strip() if activity_raw else ""
                if raw_str.upper() == "INACTIVATE":
                    activity_text = "INACTIVATE"
                else:
                    activity_text = "N/A"

            mol_data_list.append(
                {
                    "r_values": r_values,
                    "activity": activity_text,
                    "activity_num": activity,
                    "mol": mol_data["mol"],
                    "name": mol_data.get("name", ""),
                }
            )

        mol_data_list.sort(
            key=lambda x: (
                x["activity_num"] if x["activity_num"] is not None else float("inf")
            )
        )

        path_tables = self._group_by_path(mol_data_list, num_r)

        for table_idx, (title, table_rows, table_labels) in enumerate(path_tables):
            table_img = self._create_table_image(
                table_rows, table_labels, num_r, sub_size
            )
            combined = combine_scaffold_and_table(scaffold_img, table_img, title)
            if table_idx == 0:
                combined.save(output_path)
            else:
                stem = output_path.stem
                suffix = output_path.suffix
                path_output = output_path.parent / f"{stem}_path{table_idx + 1}{suffix}"
                combined.save(path_output)
            logger.info(f"Saved SAR path table {table_idx + 1}")

    def _group_by_path(
        self,
        mol_data_list: List[Dict[str, Any]],
        num_r: int,
    ) -> List[Tuple[str, List[List[Any]], List[str]]]:
        """Group molecules by modification path.

        For 2 R-groups: group by R1 value, show R2 variation.

        Returns:
            List of (title, rows, col_labels) for each path table.
        """
        if num_r == 1:
            rows = []
            for md in mol_data_list:
                r0_img = self._render_substituent_image(
                    Chem.MolFromSmiles(md["r_values"].get(0, "H")),
                    (80, 60),
                )
                rows.append([r0_img if r0_img else "H", md["activity"]])
            return [("SAR Table", rows, ["R1", "IC50 (nM)"])]

        groups = {}
        for md in mol_data_list:
            key = md["r_values"].get(0, "H")
            if key not in groups:
                groups[key] = []
            groups[key].append(md)

        path_tables = []
        for i, (r1_val, group_mols) in enumerate(groups.items()):
            col_labels = ["R1", "R2", "IC50 (nM)"]
            rows = []

            r1_img = self._render_substituent_image(
                Chem.MolFromSmiles(r1_val) if r1_val != "H" else None,
                (80, 60),
            )

            for md in group_mols:
                r2_val = md["r_values"].get(1, "H")
                r2_img = self._render_substituent_image(
                    Chem.MolFromSmiles(r2_val) if r2_val != "H" else None,
                    (80, 60),
                )
                rows.append(
                    [
                        r1_img if r1_img else "H",
                        r2_img if r2_img else "H",
                        md["activity"],
                    ]
                )

            title = f"Path {i + 1}: R1 = {r1_val}"
            path_tables.append((title, rows, col_labels))

        return path_tables

    def _create_table_image(
        self,
        rows: List[List[Any]],
        col_labels: List[str],
        num_r_groups: int,
        sub_size: Tuple[int, int],
    ) -> Image.Image:
        """创建表格图像 (委托给统一实现).

        Args:
            rows: 行数据.
            col_labels: 列标签.
            num_r_groups: R基团数量.
            sub_size: 取代基尺寸.

        Returns:
            PIL 图像.
        """
        return create_sar_table_image(
            rows=rows,
            col_labels=col_labels,
            sub_size=sub_size,
        )
