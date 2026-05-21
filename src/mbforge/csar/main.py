"""CSAR工作流 - SAR分析流程的主入口点.

本模块提供了CSAR工具的命令行接口和完整工作流实现。
工作流包括: 读取分子 -> 聚类 -> 查找MCS -> SAR分析 -> 生成可视化.

使用方法:
    命令行: python -m src.main input.xlsx -o output/
    编程: from mbforge.main import run_workflow; run_workflow(...)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .io.reader import MoleculeReader
from ..clustering.fingerprinter import MolecularFingerprinter
from ..clustering.cluster import MolecularClusterer
from ..clustering.mcs_finder import MCSFinder
from .analyzer import SARAnalyzer
from .vis.renderer import SARRenderer, PlotSettings

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


def parse_args() -> argparse.Namespace:
    """解析命令行参数.

    定义并解析所有可用的命令行参数，包括输入输出路径、
    聚类参数、MCS参数和可视化选项等。

    Returns:
        解析后的参数命名空间对象.
    """
    parser = argparse.ArgumentParser(
        description="CSAR - Compound Structure-Activity Relationship Analysis"
    )
    parser.add_argument("input_file", type=Path, help="Input file (SDF, Excel, or CSV)")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--smiles-column",
        type=str,
        default="SMILES",
        help="Column name for SMILES (Excel/CSV)",
    )
    parser.add_argument(
        "--name-column",
        type=str,
        default="Name",
        help="Column name for molecule names (Excel/CSV)",
    )
    parser.add_argument(
        "--activity-column",
        type=str,
        default="Activity",
        help="Column name for activity values (Excel/CSV)",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=float,
        default=0.7,
        help="Similarity threshold for clustering (0.0 to 1.0)",
    )
    parser.add_argument(
        "--cluster-method",
        type=str,
        choices=["tanimoto", "butina"],
        default="tanimoto",
        help="Clustering method",
    )
    parser.add_argument(
        "--fp-type",
        type=str,
        choices=["Morgan", "MACCS", "RDKit"],
        default="Morgan",
        help="Fingerprint type",
    )
    parser.add_argument(
        "--mcs-timeout",
        type=int,
        default=30,
        help="MCS search timeout per cluster (seconds)",
    )
    parser.add_argument(
        "--skip-visualization",
        action="store_true",
        help="Skip visualization generation",
    )
    parser.add_argument(
        "--ic50-nm-column",
        type=str,
        default="IC50_nM",
        help="Column name for IC50 in nM",
    )
    parser.add_argument(
        "--ic50-um-column",
        type=str,
        default="IC50_uM",
        help="Column name for IC50 in uM",
    )
    return parser.parse_args()


def run_workflow(
    input_file: Path,
    output_dir: Path,
    smiles_column: str = "SMILES",
    name_column: str = "Name",
    activity_column: str = "Activity",
    cluster_threshold: float = 0.7,
    cluster_method: str = "tanimoto",
    fp_type: str = "Morgan",
    mcs_timeout: int = 30,
    skip_visualization: bool = False,
    ic50_nm_column: Optional[str] = None,
    ic50_um_column: Optional[str] = None,
) -> None:
    """运行完整的SAR分析工作流.

    执行完整的CSAR分析流程，包括:
    1. 读取分子数据
    2. 基于分子指纹进行聚类
    3. 对每个聚类查找最大公共子结构(MCS)
    4. 分析结构-活性关系
    5. 生成可视化图表
    6. 保存结果

    Args:
        input_file: 输入分子文件路径 (支持SDF, Excel, CSV格式).
        output_dir: 输出文件目录.
        smiles_column: SMILES列名 (用于Excel/CSV文件).
        name_column: 分子名称列名.
        activity_column: 活性值列名.
        cluster_threshold: 聚类相似度阈值 (0.0-1.0).
        cluster_method: 聚类方法 ("tanimoto" 或 "butina").
        fp_type: 指纹类型 ("Morgan", "MACCS", "RDKit").
        mcs_timeout: MCS搜索超时时间(秒).
        skip_visualization: 是否跳过可视化生成.
        ic50_nm_column: IC50(nM)列名.
        ic50_um_column: IC50(uM)列名.
    """
    logger.info(f"Starting CSAR workflow: {input_file} -> {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Reading molecules")
    reader = MoleculeReader(
        smiles_column=smiles_column,
        name_column=name_column,
        activity_column=activity_column,
    )

    if ic50_nm_column or ic50_um_column:
        batch = reader.read_batch(
            input_file,
            ic50_nm_column=ic50_nm_column,
            ic50_um_column=ic50_um_column,
        )
    else:
        batch = reader.read_batch(input_file)
    logger.info(f"Read {len(batch)} molecules")

    if len(batch) < 2:
        logger.error("Need at least 2 molecules for analysis")
        sys.exit(1)

    # 向下兼容：旧模块仍接受裸字典列表
    molecules = batch.to_dicts()

    logger.info("Clustering molecules")
    fingerprinter = MolecularFingerprinter(fp_type=fp_type)
    clusterer = MolecularClusterer(
        fingerprinter=fingerprinter, threshold=cluster_threshold, method=cluster_method
    )
    clusters, sim_matrix = clusterer.cluster(molecules)
    logger.info(f"Found {len(clusters)} clusters")

    logger.info("Finding MCS for each cluster")
    mcs_finder = MCSFinder(timeout=mcs_timeout)
    mcs_results = {}
    max_mcs_cluster_size = 30

    for cluster in clusters:
        if cluster.size >= 2:
            if cluster.size > max_mcs_cluster_size:
                logger.warning(
                    f"Cluster {cluster.cluster_id} has {cluster.size} molecules, "
                    f"skipping MCS (> {max_mcs_cluster_size})"
                )
                continue
            try:
                mcs = mcs_finder.find_mcs(cluster.molecules)
                mcs_results[cluster.cluster_id] = mcs
            except Exception as e:
                logger.warning(
                    f"MCS search failed for cluster {cluster.cluster_id}: {e}"
                )

    logger.info("Analyzing SAR")
    sar_analyzer = SARAnalyzer()
    sar_results = sar_analyzer.analyze_clusters(clusters, mcs_results)

    overall_stats = sar_analyzer.get_activity_stats(sar_results)
    logger.info(f"Overall statistics: {overall_stats}")

    if not skip_visualization:
        logger.info("Generating visualizations")
        renderer = SARRenderer(PlotSettings())

        logger.info("Rendering SAR summary")
        renderer.render_sar_summary(sar_results, output_dir / "sar_summary.png")

        logger.info("Rendering similarity matrix")
        renderer.render_similarity_matrix(
            sim_matrix,
            output_dir / "similarity_matrix.png",
            labels=[e.name for e in batch[:20]],
        )

        logger.info("Rendering SAR table images for each cluster")
        from mbforge.clustering.mcs_finder import find_substitution_positions

        for cluster in clusters:
            if cluster.size >= 2:
                mcs = mcs_results.get(cluster.cluster_id)
                if mcs is None:
                    continue

                scaffold_info = find_substitution_positions(
                    mcs.mcs_mol, cluster.molecules
                )
                if scaffold_info is None or scaffold_info.num_r_groups == 0:
                    logger.warning(
                        f"No R-group positions found for cluster {cluster.cluster_id}"
                    )
                    continue

                renderer.render_sar_path_image(
                    scaffold_info=scaffold_info,
                    molecules=cluster.molecules,
                    output_path=output_dir / f"cluster_{cluster.cluster_id}_sar.png",
                )

    logger.info("Saving results")
    batch.to_csv(output_dir / "molecules.csv")
    batch.to_sdf(output_dir / "molecules.sdf")

    logger.info(f"CSAR workflow complete. Results saved to {output_dir}")


def main() -> None:
    """主入口点 - 命令行执行入口."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()
    run_workflow(
        input_file=args.input_file,
        output_dir=args.output_dir,
        smiles_column=args.smiles_column,
        name_column=args.name_column,
        activity_column=args.activity_column,
        cluster_threshold=args.cluster_threshold,
        cluster_method=args.cluster_method,
        fp_type=args.fp_type,
        mcs_timeout=args.mcs_timeout,
        skip_visualization=args.skip_visualization,
        ic50_nm_column=args.ic50_nm_column if args.ic50_nm_column else None,
        ic50_um_column=args.ic50_um_column if args.ic50_um_column else None,
    )


# 程序入口点
if __name__ == "__main__":
    main()
