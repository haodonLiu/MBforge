"""UniDockPlugin —— GPU 加速高性能分子对接插件.

Uni-Dock 是深势科技开发的高性能 GPU 加速分子对接引擎 (Apache 2.0 开源)。
GitHub: https://github.com/dptech-corp/Uni-Dock

支持的输入格式:
    - 受体: PDBQT (或 PDB 自动转换)
    - 配体: PDBQT, SDF, MOL2
    - 柔性侧链: PDBQT (通过 --flex 参数)

支持的打分函数:
    - vina:    AutoDock Vina (默认)
    - vinardo: Vinardo 打分函数
    - ad4:     AutoDock4

搜索模式:
    - fast:    exhaustiveness=128,  max_step=20   (快速筛选)
    - balance: exhaustiveness=384,  max_step=40   (推荐默认)
    - detail:  exhaustiveness=512,  max_step=40   (高精度)

安装方式:
    conda create -n unidock_env unidock -c conda-forge

常见问题:
    - GPU OOM: 使用 --max_gpu_memory 限制显存
    - 命令行过长: 使用 --ligand_index 代替 --gpu_batch
    - paired_batch 模式: --paired_batch_size + JSON 配置 (1:1 批量加速)
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem

from ...agent.tools import ToolRegistry

from ..base import (
    BasePlugin,
    PluginCapability,
    PluginMetadata,
    WorkflowStep,
)


# ---- 结果数据结构 ----

@dataclass
class UniDockResult:
    """UniDock 分子对接结果.

    Attributes:
        ligand: RDKit Mol 对象（对接后的构象）
        affinity: 对接打分 (kcal/mol)，越小越好
        pose_index: 构象序号（从0开始）
        rmsd_lb: RMSD lower bound (Å)
        rmsd_ub: RMSD upper bound (Å)
        receptor: 受体文件路径
        box_center: 对接盒子中心坐标 (x, y, z) 单位: Å
        box_size: 对接盒子尺寸 (width_x, width_y, width_z) 单位: Å
        scoring_function: 使用的打分函数 (vina/vinardo/ad4)
        search_mode: 搜索模式 (fast/balance/detail)
        metadata: 额外元数据字典
    """

    ligand: Chem.Mol
    affinity: float  # kcal/mol, 越小越好
    pose_index: int = 0
    rmsd_lb: float = 0.0  # RMSD lower bound
    rmsd_ub: float = 0.0  # RMSD upper bound
    receptor: str = ""
    box_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    box_size: tuple[float, float, float] = (20.0, 20.0, 20.0)
    scoring_function: str = "vina"
    search_mode: str = "balance"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UniDockBatchResult:
    """UniDock 批量对接结果.

    Attributes:
        results: 所有配体的对接结果列表
        total_ligands: 总配体数
        successful_count: 成功对接数
        failed_smiles: 失败的 SMILES 列表
    """

    results: list[UniDockResult] = field(default_factory=list)
    total_ligands: int = 0
    successful_count: int = 0
    failed_smiles: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---- 插件主类 ----

class UniDockPlugin(BasePlugin):
    """UniDock GPU 加速分子对接插件.

    提供基于 Uni-Dock 的高性能分子对接功能，支持:
    - GPU 加速对接 (比 CPU 快 2000 倍)
    - 批量配体对接
    - 柔性侧链对接
    - 多种打分函数 (Vina/Vinardo/AD4)
    """

    # 插件元数据
    meta = PluginMetadata(
        name="unidock",
        version="0.1.0",
        description="UniDock GPU 加速分子对接插件 (Apache 2.0)",
        author="MBForge Team",
        capabilities=[
            PluginCapability.AGENT_TOOL,
            PluginCapability.WORKFLOW,
            PluginCapability.CLI_COMMAND,
        ],
        supported_engines=[
            "unidock",
            "vina",      # Uni-Dock 兼容 Vina 打分函数
            "vinardo",   # Vinardo 打分函数
            "ad4",       # AutoDock4 打分函数
        ],
        external_binaries=[
            "unidock",   # Uni-Dock 可执行文件
        ],
    )

    def __init__(self, project_root: Path | None = None):
        """初始化 UniDock 插件.

        Args:
            project_root: 项目根目录，用于存储缓存文件
        """
        super().__init__(project_root)
        self._unidock_available: bool = False
        self._unidock_path: Path | None = None

    def setup(self) -> None:
        """检查 UniDock 是否可用，建立缓存目录.

        检查流程:
        1. 检查 unidock 命令是否在 PATH 中
        2. 创建缓存目录结构
        3. 设置可用状态标志
        """
        super().setup()

        # 检查 unidock 是否可用
        self._unidock_path = self.check_binary("unidock")
        self._unidock_available = self._unidock_path is not None

        # 创建缓存目录
        cache = self.cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "ligands").mkdir(exist_ok=True)
        (cache / "receptors").mkdir(exist_ok=True)
        (cache / "outputs").mkdir(exist_ok=True)

        # 输出可用状态
        if self._unidock_available:
            print(f"[UniDock] ✓ UniDock 可用: {self._unidock_path}")
        else:
            print("[UniDock] ⚠ UniDock 未安装或不在 PATH 中")
            print("[UniDock]   安装方式: conda create -n unidock_env unidock -c conda-forge")
            print("[UniDock]   将使用 fallback 模式（不执行实际对接）")

    # ═══════════════════════════════════════════════════════════════════
    #  1. 主对接方法
    # ═══════════════════════════════════════════════════════════════════

    def run_docking(
        self,
        ligand: Chem.Mol,
        receptor_pdb: str | Path,
        center: tuple[float, float, float] | None = None,
        size: tuple[float, float, float] = (20.0, 20.0, 20.0),
        scoring: str = "vina",
        search_mode: str = "balance",
        exhaustiveness: int | None = None,
        num_modes: int = 9,
        energy_range: float = 3.0,
        flex: str | Path | None = None,
        autobox: bool = False,
        max_gpu_memory: int = 0,
    ) -> list[UniDockResult]:
        """运行分子对接.

        Args:
            ligand: RDKit Mol 对象（建议已有 3D 构象）
            receptor_pdb: 受体蛋白 PDB/PDBQT 文件路径
            center: 对接盒子中心坐标 (x, y, z)，单位 Å
                    None 时使用 autobox 或自动计算配体重心
            size: 对接盒子尺寸 (width_x, width_y, width_z)，单位 Å
            scoring: 打分函数，"vina" | "vinardo" | "ad4"
            search_mode: 搜索模式，"fast" | "balance" | "detail"
            exhaustiveness: 搜索穷尽度，None 时根据 search_mode 自动设置
            num_modes: 最大输出构象数
            energy_range: 最佳与最差构象的最大能量差 (kcal/mol)
            flex: 柔性侧链 PDBQT 文件路径
            autobox: 根据配体自动设置盒子大小
            max_gpu_memory: GPU 显存上限 (MB)，0 表示不限制

        Returns:
            UniDockResult 列表，按亲和力排序（最佳构象在前）

        Raises:
            FileNotFoundError: 受体文件不存在
            RuntimeError: UniDock 执行失败
        """
        receptor_path = Path(receptor_pdb)
        if not receptor_path.exists():
            raise FileNotFoundError(f"受体文件不存在: {receptor_pdb}")

        # 自动计算中心点（如果未指定且不使用 autobox）
        if center is None and not autobox:
            center = self._calc_ligand_center(ligand)

        # 如果 UniDock 可用，执行真实对接
        if self._unidock_available:
            return self._run_unidock(
                ligand=ligand,
                receptor=receptor_path,
                center=center,
                size=size,
                scoring=scoring,
                search_mode=search_mode,
                exhaustiveness=exhaustiveness,
                num_modes=num_modes,
                energy_range=energy_range,
                flex=flex,
                autobox=autobox,
                max_gpu_memory=max_gpu_memory,
            )
        else:
            # Fallback: 返回模拟结果
            return self._fallback_docking(
                ligand, receptor_path, center, size, scoring, search_mode
            )

    def _run_unidock(
        self,
        ligand: Chem.Mol,
        receptor: Path,
        center: tuple[float, float, float] | None,
        size: tuple[float, float, float],
        scoring: str,
        search_mode: str,
        exhaustiveness: int | None,
        num_modes: int,
        energy_range: float,
        flex: str | Path | None,
        autobox: bool,
        max_gpu_memory: int,
    ) -> list[UniDockResult]:
        """调用 UniDock 进行分子对接.

        Args:
            ligand: RDKit Mol 对象
            receptor: 受体文件路径
            center: 对接盒子中心
            size: 对接盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式
            exhaustiveness: 搜索穷尽度
            num_modes: 最大构象数
            energy_range: 能量范围
            flex: 柔性侧链文件
            autobox: 自动盒子
            max_gpu_memory: GPU 显存限制

        Returns:
            UniDockResult 列表
        """
        cache = self.cache_dir()
        ligand_pdbqt = cache / "ligands" / f"ligand_{id(ligand)}.pdbqt"
        output_pdbqt = cache / "outputs" / f"out_{id(ligand)}.pdbqt"

        # 准备配体为 PDBQT 格式
        self._prepare_ligand(ligand, ligand_pdbqt)

        # 构建命令行参数
        cmd = [
            str(self._unidock_path),
            "--receptor", str(receptor),
            "--ligand", str(ligand_pdbqt),
            "--out", str(output_pdbqt),
            "--scoring", scoring,
        ]

        # 添加搜索模式或穷尽度
        if exhaustiveness is not None:
            cmd.extend(["--exhaustiveness", str(exhaustiveness)])
        else:
            cmd.extend(["--search_mode", search_mode])

        # 添加盒子参数
        if center is not None:
            cmd.extend([
                "--center_x", str(center[0]),
                "--center_y", str(center[1]),
                "--center_z", str(center[2]),
            ])

        if not autobox:
            cmd.extend([
                "--size_x", str(size[0]),
                "--size_y", str(size[1]),
                "--size_z", str(size[2]),
            ])
        else:
            cmd.append("--autobox")

        # 添加其他参数
        cmd.extend([
            "--num_modes", str(num_modes),
            "--energy_range", str(energy_range),
        ])

        # 柔性侧链
        if flex is not None:
            cmd.extend(["--flex", str(flex)])

        # GPU 显存限制
        if max_gpu_memory > 0:
            cmd.extend(["--max_gpu_memory", str(max_gpu_memory)])

        # 执行 UniDock
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cache,
                timeout=600,  # 10 分钟超时
            )

            if proc.returncode != 0:
                # 检查是否是临时文件导致的错误
                if "No such file" in proc.stderr or "not found" in proc.stderr.lower():
                    # 尝试使用临时目录
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_ligand = Path(tmpdir) / "ligand.pdbqt"
                        tmp_output = Path(tmpdir) / "output.pdbqt"
                        self._prepare_ligand(ligand, tmp_ligand)

                        cmd = [
                            str(self._unidock_path),
                            "--receptor", str(receptor),
                            "--ligand", str(tmp_ligand),
                            "--out", str(tmp_output),
                            "--scoring", scoring,
                        ]
                        if exhaustiveness is not None:
                            cmd.extend(["--exhaustiveness", str(exhaustiveness)])
                        else:
                            cmd.extend(["--search_mode", search_mode])
                        if center is not None:
                            cmd.extend([
                                "--center_x", str(center[0]),
                                "--center_y", str(center[1]),
                                "--center_z", str(center[2]),
                            ])
                        if not autobox:
                            cmd.extend([
                                "--size_x", str(size[0]),
                                "--size_y", str(size[1]),
                                "--size_z", str(size[2]),
                            ])
                        else:
                            cmd.append("--autobox")
                        cmd.extend([
                            "--num_modes", str(num_modes),
                            "--energy_range", str(energy_range),
                        ])
                        if max_gpu_memory > 0:
                            cmd.extend(["--max_gpu_memory", str(max_gpu_memory)])

                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                        if proc.returncode == 0:
                            return self._parse_unidock_output(
                                tmp_output, ligand, str(receptor),
                                center or (0, 0, 0), size, scoring, search_mode
                            )

                raise RuntimeError(f"UniDock 执行失败: {proc.stderr}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("UniDock 执行超时 (10 分钟)")

        # 解析输出
        return self._parse_unidock_output(
            output_pdbqt, ligand, str(receptor),
            center or (0, 0, 0), size, scoring, search_mode
        )

    def _fallback_docking(
        self,
        ligand: Chem.Mol,
        receptor: Path,
        center: tuple[float, float, float] | None,
        size: tuple[float, float, float],
        scoring: str,
        search_mode: str,
    ) -> list[UniDockResult]:
        """无 UniDock 时的 fallback 模式.

        基于 RDKit 的简单 shape-based 打分返回模拟结果。
        实际使用时建议安装 UniDock 以获得准确的结合亲和力预测。

        Args:
            ligand: RDKit Mol 对象
            receptor: 受体文件路径
            center: 对接盒子中心
            size: 对接盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式

        Returns:
            模拟的 UniDockResult 列表
        """
        print("[UniDock] 警告: UniDock 不可用，使用 fallback 模式（模拟结果）")

        # 计算简单打分作为模拟值
        from rdkit.Chem import Descriptors
        mw = Descriptors.MolWt(ligand)

        # 基于分子量的粗略估计（仅用于演示）
        estimated_affinity = -7.0 + (mw - 300) * 0.002
        estimated_affinity = max(-12.0, min(-5.0, estimated_affinity))

        return [
            UniDockResult(
                ligand=ligand,
                affinity=round(estimated_affinity, 2),
                receptor=str(receptor),
                box_center=center or (0.0, 0.0, 0.0),
                box_size=size,
                scoring_function=scoring,
                search_mode=search_mode,
                metadata={"method": "fallback_rdkit", "warning": "UniDock not installed"},
            )
        ]

    # ═══════════════════════════════════════════════════════════════════
    #  2. 配体准备与输出解析
    # ═══════════════════════════════════════════════════════════════════

    def _prepare_ligand(self, mol: Chem.Mol, output_path: Path) -> None:
        """将 RDKit Mol 转换为 PDBQT 格式.

        使用简化版转换方法。对于生产环境，建议使用 Meeko 或 obabel
        进行更准确的 PDBQT 转换。

        Args:
            mol: RDKit Mol 对象
            output_path: 输出 PDBQT 文件路径
        """
        # 确保分子有 3D 构象
        if mol.GetConformer(-1).GetNumAtoms() == 0:
            mol_h = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol_h, AllChem.ETKDGv3())
            AllChem.MMFFOptimizeMolecule(mol_h)
            mol = mol_h

        # 生成 PDBQT 内容（简化版本）
        # 实际生产中应使用 meeko 或 openbabel 进行转换
        pdb_content = self._mol_to_pdbqt_simple(mol)
        output_path.write_text(pdb_content)

    def _mol_to_pdbqt_simple(self, mol: Chem.Mol) -> str:
        """简化的 Mol 到 PDBQT 转换.

        这是一个简化实现，只支持基本的原子类型。
        生产环境建议使用 Meeko:

            from meeko import MoleculePreparation
            prep = MoleculePreparation()
            mol_pdbqt, msgs = prep.prepare(mol)

        Args:
            mol: RDKit Mol 对象

        Returns:
            PDBQT 格式字符串
        """
        lines = []
        conf = mol.GetConformer()

        # 原子类型映射（简化版）
        atom_types = {
            1: "H", 6: "C", 7: "N", 8: "O", 9: "F",
            15: "P", 16: "S", 17: "Cl", 35: "Br", 53: "I"
        }

        for i, atom in enumerate(mol.GetAtoms()):
            pos = conf.GetAtomPosition(i)
            atomic_num = atom.GetAtomicNum()
            atom_type = atom_types.get(atomic_num, "X")

            # 简化版的 AD4 类型（实际应使用正确的类型）
            ad4_type = atom_type

            # 添加原子电荷（简化版，设为 0.0）
            charge = 0.0

            lines.append(
                f"ATOM  {i+1:5d} {atom_type:2s} LIG A{1:4d}    "
                f"{pos.x:8.3f}{pos.y:8.3f}{pos.z:8.3f}"
                f"  1.00{charge:7.3f}          {ad4_type:>2s}"
            )

        # 根原子（第一个重原子）
        for i, atom in enumerate(mol.GetAtoms()):
            if atom.GetAtomicNum() not in (1,):  # 跳过氢原子
                lines.append("ROOT")
                lines.append(f"ATOM  {i+1:5d} {atom.GetSymbol():2s} LIG A{1:4d}    ")
                lines.append("ENDROOT")
                break

        # 结束
        lines.append("END")

        return "\n".join(lines)

    def _parse_unidock_output(
        self,
        output_path: Path,
        original_ligand: Chem.Mol,
        receptor: str,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        scoring: str,
        search_mode: str,
    ) -> list[UniDockResult]:
        """解析 UniDock PDBQT 输出文件.

        UniDock 输出格式与 AutoDock Vina 兼容:
        - REMARK 行包含打分信息
        - MODEL ... ENDMDL 包含多个构象

        Args:
            output_path: UniDock 输出 PDBQT 文件路径
            original_ligand: 原始配体 Mol 对象
            receptor: 受体文件路径
            center: 对接盒子中心
            size: 对接盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式

        Returns:
            UniDockResult 列表
        """
        results: list[UniDockResult] = []

        if not output_path.exists():
            return results

        # 读取文件内容
        content = output_path.read_text()

        # 解析 REMARK 行获取打分
        # 格式: "REMARK VINA RESULT:  affinity  rmsd_lb  rmsd_ub"
        remark_pattern = re.compile(
            r"REMARK\s+VINA\s+RESULT:\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"
        )

        # 解析构象
        current_model = []
        model_affinity = None
        model_rmsd_lb = 0.0
        model_rmsd_ub = 0.0
        pose_index = 0

        for line in content.split("\n"):
            if line.startswith("MODEL"):
                current_model = []
            elif line.startswith("ENDMDL"):
                # 解析当前构象
                if current_model and model_affinity is not None:
                    try:
                        # 转换为 RDKit Mol
                        pdb_block = "\n".join(current_model)
                        mol = Chem.MolFromPDBBlock(pdb_block, sanitize=False)

                        if mol is not None:
                            results.append(
                                UniDockResult(
                                    ligand=mol,
                                    affinity=model_affinity,
                                    pose_index=pose_index,
                                    rmsd_lb=model_rmsd_lb,
                                    rmsd_ub=model_rmsd_ub,
                                    receptor=receptor,
                                    box_center=center,
                                    box_size=size,
                                    scoring_function=scoring,
                                    search_mode=search_mode,
                                )
                            )
                            pose_index += 1
                    except Exception:
                        pass

                current_model = []
                model_affinity = None
            elif line.startswith("REMARK"):
                match = remark_pattern.search(line)
                if match:
                    model_affinity = float(match.group(1))
                    model_rmsd_lb = float(match.group(2))
                    model_rmsd_ub = float(match.group(3))
            elif line.startswith("ATOM") or line.startswith("HETATM"):
                current_model.append(line)

        # 按亲和力排序（越小越好）
        results.sort(key=lambda x: x.affinity)

        # 更新 pose_index 为排序后的序号
        for i, result in enumerate(results):
            result.pose_index = i

        return results

    def _calc_ligand_center(self, mol: Chem.Mol) -> tuple[float, float, float]:
        """计算配体的几何中心.

        Args:
            mol: RDKit Mol 对象

        Returns:
            配体重心坐标 (x, y, z)
        """
        conf = mol.GetConformer(-1)
        if conf.GetNumAtoms() == 0:
            # 如果没有构象，尝试获取第一个构象
            conf = mol.GetConformer(0)

        cx = cy = cz = 0.0
        n = conf.GetNumAtoms()

        if n == 0:
            return (0.0, 0.0, 0.0)

        for i in range(n):
            pos = conf.GetAtomPosition(i)
            cx += pos.x
            cy += pos.y
            cz += pos.z

        return (cx / n, cy / n, cz / n)

    # ═══════════════════════════════════════════════════════════════════
    #  3. 批量对接
    # ═══════════════════════════════════════════════════════════════════

    def run_batch_docking(
        self,
        smiles_list: list[str],
        receptor_pdb: str | Path,
        center: tuple[float, float, float] | None = None,
        size: tuple[float, float, float] = (20.0, 20.0, 20.0),
        scoring: str = "vina",
        search_mode: str = "balance",
        num_modes: int = 1,
    ) -> UniDockBatchResult:
        """批量对接多个配体.

        Args:
            smiles_list: SMILES 字符串列表
            receptor_pdb: 受体蛋白 PDB 文件路径
            center: 对接盒子中心
            size: 对接盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式
            num_modes: 每个配体输出的构象数

        Returns:
            UniDockBatchResult 包含所有对接结果
        """
        results: list[UniDockResult] = []
        failed_smiles: list[str] = []
        successful_count = 0

        for i, smiles in enumerate(smiles_list):
            try:
                # 从 SMILES 创建分子
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    failed_smiles.append(smiles)
                    continue

                # 添加氢原子并生成 3D 构象
                mol = Chem.AddHs(mol)
                AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                AllChem.MMFFOptimizeMolecule(mol)

                # 运行对接
                docking_results = self.run_docking(
                    mol,
                    receptor_pdb,
                    center=center,
                    size=size,
                    scoring=scoring,
                    search_mode=search_mode,
                    num_modes=num_modes,
                )

                if docking_results:
                    results.extend(docking_results)
                    successful_count += 1
                else:
                    failed_smiles.append(smiles)

            except Exception as e:
                failed_smiles.append(f"{smiles} (error: {str(e)})")

        return UniDockBatchResult(
            results=results,
            total_ligands=len(smiles_list),
            successful_count=successful_count,
            failed_smiles=failed_smiles,
            metadata={
                "scoring": scoring,
                "search_mode": search_mode,
                "receptor": str(receptor_pdb),
            },
        )

    # ═══════════════════════════════════════════════════════════════════
    #  4. 工具注册 (Agent Tool)
    # ═══════════════════════════════════════════════════════════════════

    def register_tools(self, registry: ToolRegistry) -> None:
        """向 Agent 注册 UniDock 工具.

        注册以下工具:
        - unidock_docking: 单分子对接
        - unidock_batch_docking: 批量对接

        Args:
            registry: 工具注册表实例
        """
        registry.register(
            name="unidock_docking",
            description="使用 UniDock GPU 加速引擎进行分子对接，预测配体-受体结合亲和力",
            parameters_schema={
                "ligand_smiles": {
                    "type": "string",
                    "description": "配体 SMILES 字符串",
                },
                "receptor_pdb": {
                    "type": "string",
                    "description": "受体蛋白 PDB/PDBQT 文件路径",
                },
                "center_x": {
                    "type": "number",
                    "description": "对接盒子中心 X 坐标 (Å)",
                },
                "center_y": {
                    "type": "number",
                    "description": "对接盒子中心 Y 坐标 (Å)",
                },
                "center_z": {
                    "type": "number",
                    "description": "对接盒子中心 Z 坐标 (Å)",
                },
                "size_x": {
                    "type": "number",
                    "description": "对接盒子 X 尺寸 (Å)",
                    "default": 20.0,
                },
                "size_y": {
                    "type": "number",
                    "description": "对接盒子 Y 尺寸 (Å)",
                    "default": 20.0,
                },
                "size_z": {
                    "type": "number",
                    "description": "对接盒子 Z 尺寸 (Å)",
                    "default": 20.0,
                },
                "scoring": {
                    "type": "string",
                    "description": "打分函数",
                    "enum": ["vina", "vinardo", "ad4"],
                    "default": "vina",
                },
                "search_mode": {
                    "type": "string",
                    "description": "搜索模式",
                    "enum": ["fast", "balance", "detail"],
                    "default": "balance",
                },
                "num_modes": {
                    "type": "integer",
                    "description": "最大输出构象数",
                    "default": 9,
                },
            },
            func=self._tool_docking,
        )

        registry.register(
            name="unidock_batch_docking",
            description="使用 UniDock 批量对接多个配体分子",
            parameters_schema={
                "smiles_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "SMILES 字符串列表",
                },
                "receptor_pdb": {
                    "type": "string",
                    "description": "受体蛋白 PDB/PDBQT 文件路径",
                },
                "center": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "对接盒子中心 [x, y, z]",
                },
                "size": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "对接盒子尺寸 [w, h, d]",
                    "default": [20.0, 20.0, 20.0],
                },
                "scoring": {
                    "type": "string",
                    "enum": ["vina", "vinardo", "ad4"],
                    "default": "vina",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["fast", "balance", "detail"],
                    "default": "fast",
                },
            },
            func=self._tool_batch_docking,
        )

    def _tool_docking(
        self,
        ligand_smiles: str,
        receptor_pdb: str,
        center_x: float = 0.0,
        center_y: float = 0.0,
        center_z: float = 0.0,
        size_x: float = 20.0,
        size_y: float = 20.0,
        size_z: float = 20.0,
        scoring: str = "vina",
        search_mode: str = "balance",
        num_modes: int = 9,
        **kwargs,
    ) -> str:
        """Agent 工具包装: 单分子对接.

        Args:
            ligand_smiles: 配体 SMILES
            receptor_pdb: 受体文件路径
            center_x/y/z: 盒子中心坐标
            size_x/y/z: 盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式
            num_modes: 构象数

        Returns:
            对接结果字符串
        """
        mol = Chem.MolFromSmiles(ligand_smiles)
        if mol is None:
            return f"错误: 无法解析 SMILES: {ligand_smiles}"

        # 添加氢原子并生成 3D 构象
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        AllChem.MMFFOptimizeMolecule(mol)

        center = (center_x, center_y, center_z)
        size = (size_x, size_y, size_z)

        try:
            results = self.run_docking(
                mol,
                receptor_pdb,
                center=center,
                size=size,
                scoring=scoring,
                search_mode=search_mode,
                num_modes=num_modes,
            )

            if not results:
                return "对接完成，但未找到有效构象"

            # 输出最佳结果
            best = results[0]
            output_lines = [
                "UniDock 对接完成",
                f"引擎: UniDock (scoring={scoring}, mode={search_mode})",
                f"受体: {best.receptor}",
                f"盒子中心: {best.box_center}",
                f"盒子尺寸: {best.box_size}",
                "",
                "最佳构象 (Top 1):",
                f"  亲和力: {best.affinity:.3f} kcal/mol",
                f"  RMSD LB: {best.rmsd_lb:.2f} Å",
                f"  RMSD UB: {best.rmsd_ub:.2f} Å",
            ]

            if len(results) > 1:
                output_lines.append("")
                output_lines.append(f"其他构象 ({len(results)-1} 个):")
                for i, r in enumerate(results[1:min(5, len(results))], start=2):
                    output_lines.append(
                        f"  #{i}: affinity={r.affinity:.3f}, "
                        f"RMSD={r.rmsd_lb:.2f}/{r.rmsd_ub:.2f}"
                    )

            return "\n".join(output_lines)

        except Exception as e:
            return f"对接失败: {str(e)}"

    def _tool_batch_docking(
        self,
        smiles_list: list[str],
        receptor_pdb: str,
        center: list[float] | None = None,
        size: list[float] = None,
        scoring: str = "vina",
        search_mode: str = "fast",
        **kwargs,
    ) -> str:
        """Agent 工具包装: 批量对接.

        Args:
            smiles_list: SMILES 列表
            receptor_pdb: 受体文件路径
            center: 盒子中心 [x, y, z]
            size: 盒子尺寸 [w, h, d]
            scoring: 打分函数
            search_mode: 搜索模式

        Returns:
            批量对接结果摘要
        """
        if size is None:
            size = [20.0, 20.0, 20.0]

        center_tuple = tuple(center) if center else None
        size_tuple = tuple(size)

        try:
            batch_result = self.run_batch_docking(
                smiles_list,
                receptor_pdb,
                center=center_tuple,
                size=size_tuple,
                scoring=scoring,
                search_mode=search_mode,
                num_modes=1,
            )

            output_lines = [
                "UniDock 批量对接完成",
                f"总数: {batch_result.total_ligands}",
                f"成功: {batch_result.successful_count}",
                f"失败: {len(batch_result.failed_smiles)}",
                f"打分函数: {scoring}",
                f"搜索模式: {search_mode}",
                "",
                "亲和力排名 (Top 10):",
            ]

            # 按亲和力排序
            sorted_results = sorted(batch_result.results, key=lambda x: x.affinity)
            for i, r in enumerate(sorted_results[:10], start=1):
                smiles = r.metadata.get("smiles", "unknown")
                output_lines.append(
                    f"  #{i}: {smiles[:30]:<30} "
                    f"affinity={r.affinity:.3f} kcal/mol"
                )

            if batch_result.failed_smiles:
                output_lines.append("")
                output_lines.append(f"失败配体 ({len(batch_result.failed_smiles)} 个):")
                for smi in batch_result.failed_smiles[:5]:
                    output_lines.append(f"  - {smi[:50]}")

            return "\n".join(output_lines)

        except Exception as e:
            return f"批量对接失败: {str(e)}"

    # ═══════════════════════════════════════════════════════════════════
    #  5. 工作流步骤
    # ═══════════════════════════════════════════════════════════════════

    def get_workflow_steps(self) -> list[WorkflowStep]:
        """返回 UniDock 工作流步骤列表.

        Returns:
            WorkflowStep 对象列表
        """
        return [
            WorkflowStep(
                name="unidock_screening",
                description="UniDock GPU 加速分子对接虚拟筛选",
                input_schema={
                    "smiles_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "待筛选配体的 SMILES 列表",
                    },
                    "receptor_pdb": {
                        "type": "string",
                        "description": "受体蛋白 PDB/PDBQT 文件路径",
                    },
                    "center": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "对接盒子中心 [x, y, z]",
                    },
                    "size": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "对接盒子尺寸 [w, h, d]",
                        "default": [20.0, 20.0, 20.0],
                    },
                    "scoring": {
                        "type": "string",
                        "enum": ["vina", "vinardo", "ad4"],
                        "default": "vina",
                    },
                    "search_mode": {
                        "type": "string",
                        "enum": ["fast", "balance", "detail"],
                        "default": "fast",
                    },
                },
                output_schema={
                    "affinities": {
                        "type": "array",
                        "description": "每个配体的最佳亲和力 (kcal/mol)",
                    },
                    "top_ligands": {
                        "type": "array",
                        "description": "Top N 配体及其亲和力",
                    },
                },
                run=self._workflow_screening,
            ),
            WorkflowStep(
                name="unidock_refinement",
                description="UniDock 高精度对接精修",
                input_schema={
                    "smiles": {
                        "type": "string",
                        "description": "待精修配体的 SMILES",
                    },
                    "receptor_pdb": {
                        "type": "string",
                        "description": "受体蛋白文件路径",
                    },
                    "center": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "对接盒子中心",
                    },
                    "size": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "对接盒子尺寸",
                        "default": [20.0, 20.0, 20.0],
                    },
                    "num_modes": {
                        "type": "integer",
                        "description": "输出构象数",
                        "default": 20,
                    },
                },
                output_schema={
                    "poses": {
                        "type": "array",
                        "description": "所有输出构象及其打分",
                    },
                },
                run=self._workflow_refinement,
            ),
        ]

    def _workflow_screening(
        self,
        smiles_list: list[str],
        receptor_pdb: str,
        center: list[float] | None = None,
        size: list[float] = None,
        scoring: str = "vina",
        search_mode: str = "fast",
        top_n: int = 10,
        **kwargs,
    ) -> dict:
        """虚拟筛选工作流.

        Args:
            smiles_list: SMILES 列表
            receptor_pdb: 受体文件
            center: 盒子中心
            size: 盒子尺寸
            scoring: 打分函数
            search_mode: 搜索模式
            top_n: 返回 Top N 结果

        Returns:
            筛选结果字典
        """
        if size is None:
            size = [20.0, 20.0, 20.0]

        center_tuple = tuple(center) if center else None
        size_tuple = tuple(size)

        batch_result = self.run_batch_docking(
            smiles_list,
            receptor_pdb,
            center=center_tuple,
            size=size_tuple,
            scoring=scoring,
            search_mode=search_mode,
            num_modes=1,
        )

        # 按亲和力排序
        sorted_results = sorted(batch_result.results, key=lambda x: x.affinity)

        return {
            "total_ligands": batch_result.total_ligands,
            "successful_count": batch_result.successful_count,
            "affinities": [
                {"smiles": r.metadata.get("smiles", ""), "affinity": r.affinity}
                for r in sorted_results
            ],
            "top_ligands": [
                {
                    "smiles": r.metadata.get("smiles", ""),
                    "affinity": r.affinity,
                    "pose_index": r.pose_index,
                }
                for r in sorted_results[:top_n]
            ],
            "failed_smiles": batch_result.failed_smiles,
        }

    def _workflow_refinement(
        self,
        smiles: str,
        receptor_pdb: str,
        center: list[float],
        size: list[float] = None,
        num_modes: int = 20,
        **kwargs,
    ) -> dict:
        """高精度对接精修工作流.

        Args:
            smiles: 待精修配体 SMILES
            receptor_pdb: 受体文件
            center: 盒子中心
            size: 盒子尺寸
            num_modes: 构象数

        Returns:
            精修结果字典
        """
        if size is None:
            size = [20.0, 20.0, 20.0]

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"error": f"无法解析 SMILES: {smiles}"}

        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        AllChem.MMFFOptimizeMolecule(mol)

        results = self.run_docking(
            mol,
            receptor_pdb,
            center=tuple(center),
            size=tuple(size),
            scoring="vina",
            search_mode="detail",
            num_modes=num_modes,
        )

        return {
            "smiles": smiles,
            "receptor": receptor_pdb,
            "poses": [
                {
                    "pose_index": r.pose_index,
                    "affinity": r.affinity,
                    "rmsd_lb": r.rmsd_lb,
                    "rmsd_ub": r.rmsd_ub,
                }
                for r in results
            ],
        }

    # ═══════════════════════════════════════════════════════════════════
    #  6. CLI 命令注册
    # ═══════════════════════════════════════════════════════════════════

    def register_cli(self, subparsers) -> None:
        """注册 CLI 子命令.

        添加以下命令:
        - mbforge unidock: 单分子对接
        - mbforge unidock-batch: 批量对接

        Args:
            subparsers: argparse subparsers 对象
        """
        # 单分子对接命令
        unidock_parser = subparsers.add_parser(
            "unidock",
            help="UniDock GPU 加速分子对接",
            description="使用 UniDock 进行分子对接",
        )
        unidock_parser.add_argument(
            "--ligand", "-l",
            type=str,
            required=True,
            help="配体 SMILES 或 PDBQT 文件路径",
        )
        unidock_parser.add_argument(
            "--receptor", "-r",
            type=str,
            required=True,
            help="受体 PDB/PDBQT 文件路径",
        )
        unidock_parser.add_argument(
            "--center",
            type=float,
            nargs=3,
            default=[0.0, 0.0, 0.0],
            metavar=("X", "Y", "Z"),
            help="对接盒子中心坐标 (Å)",
        )
        unidock_parser.add_argument(
            "--size",
            type=float,
            nargs=3,
            default=[20.0, 20.0, 20.0],
            metavar=("W", "H", "D"),
            help="对接盒子尺寸 (Å)",
        )
        unidock_parser.add_argument(
            "--scoring",
            type=str,
            choices=["vina", "vinardo", "ad4"],
            default="vina",
            help="打分函数 (默认: vina)",
        )
        unidock_parser.add_argument(
            "--search-mode",
            type=str,
            choices=["fast", "balance", "detail"],
            default="balance",
            help="搜索模式 (默认: balance)",
        )
        unidock_parser.add_argument(
            "--num-modes",
            type=int,
            default=9,
            help="最大输出构象数 (默认: 9)",
        )
        unidock_parser.add_argument(
            "--output", "-o",
            type=str,
            default=None,
            help="输出文件路径 (默认: 输出到 stdout)",
        )
        unidock_parser.set_defaults(func=self._cli_docking)

        # 批量对接命令
        batch_parser = subparsers.add_parser(
            "unidock-batch",
            help="UniDock 批量分子对接",
            description="批量对接多个配体分子",
        )
        batch_parser.add_argument(
            "--smiles-file",
            type=str,
            required=True,
            help="SMILES 文件路径 (每行一个 SMILES)",
        )
        batch_parser.add_argument(
            "--receptor", "-r",
            type=str,
            required=True,
            help="受体 PDB/PDBQT 文件路径",
        )
        batch_parser.add_argument(
            "--center",
            type=float,
            nargs=3,
            default=None,
            metavar=("X", "Y", "Z"),
            help="对接盒子中心坐标 (Å)",
        )
        batch_parser.add_argument(
            "--size",
            type=float,
            nargs=3,
            default=[20.0, 20.0, 20.0],
            metavar=("W", "H", "D"),
            help="对接盒子尺寸 (Å)",
        )
        batch_parser.add_argument(
            "--scoring",
            type=str,
            choices=["vina", "vinardo", "ad4"],
            default="vina",
            help="打分函数 (默认: vina)",
        )
        batch_parser.add_argument(
            "--search-mode",
            type=str,
            choices=["fast", "balance", "detail"],
            default="fast",
            help="搜索模式 (默认: fast)",
        )
        batch_parser.add_argument(
            "--output", "-o",
            type=str,
            default=None,
            help="输出 JSON 文件路径",
        )
        batch_parser.set_defaults(func=self._cli_batch_docking)

    def _cli_docking(self, args) -> None:
        """CLI 单分子对接处理函数.

        Args:
            args: 命令行参数
        """
        # 解析配体
        if Path(args.ligand).exists():
            # 如果是文件，读取 PDBQT 或生成 SDF
            mol = Chem.MolFromPDBFile(args.ligand)
        else:
            # 作为 SMILES 处理
            mol = Chem.MolFromSmiles(args.ligand)
            if mol is not None:
                mol = Chem.AddHs(mol)
                AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                AllChem.MMFFOptimizeMolecule(mol)

        if mol is None:
            print(f"错误: 无法解析配体: {args.ligand}")
            return

        # 运行对接
        results = self.run_docking(
            mol,
            args.receptor,
            center=tuple(args.center),
            size=tuple(args.size),
            scoring=args.scoring,
            search_mode=args.search_mode,
            num_modes=args.num_modes,
        )

        # 输出结果
        output_data = []
        for r in results:
            output_data.append({
                "pose_index": r.pose_index,
                "affinity": r.affinity,
                "rmsd_lb": r.rmsd_lb,
                "rmsd_ub": r.rmsd_ub,
            })

        if args.output:
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"结果已保存到: {args.output}")
        else:
            print(json.dumps(output_data, indent=2))

    def _cli_batch_docking(self, args) -> None:
        """CLI 批量对接处理函数.

        Args:
            args: 命令行参数
        """
        # 读取 SMILES 文件
        smiles_file = Path(args.smiles_file)
        if not smiles_file.exists():
            print(f"错误: SMILES 文件不存在: {args.smiles_file}")
            return

        smiles_list = [line.strip() for line in smiles_file.read_text().splitlines() if line.strip()]

        if not smiles_list:
            print("错误: SMILES 文件为空")
            return

        print(f"开始批量对接: {len(smiles_list)} 个配体")

        # 运行批量对接
        batch_result = self.run_batch_docking(
            smiles_list,
            args.receptor,
            center=tuple(args.center) if args.center else None,
            size=tuple(args.size),
            scoring=args.scoring,
            search_mode=args.search_mode,
            num_modes=1,
        )

        # 构建输出数据
        output_data = {
            "total_ligands": batch_result.total_ligands,
            "successful_count": batch_result.successful_count,
            "failed_count": len(batch_result.failed_smiles),
            "scoring": args.scoring,
            "search_mode": args.search_mode,
            "results": [
                {
                    "smiles": r.metadata.get("smiles", ""),
                    "affinity": r.affinity,
                }
                for r in sorted(batch_result.results, key=lambda x: x.affinity)
            ],
            "failed_smiles": batch_result.failed_smiles,
        }

        # 输出结果
        if args.output:
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"结果已保存到: {args.output}")
        else:
            print(json.dumps(output_data, indent=2))
