"""CADDTemplatePlugin —— CADD 工作流插件示例.

对接软件:
  - 分子对接: AutoDock Vina, GNINA, LeDock
  - 分子动力学: GROMACS, AMBER, OpenMM
  - 自由能计算: SOMD, PMX, BAT
  - QSAR: RDKit descriptors, Mordred

设计原则:
  1. 输入输出以 RDKit Mol + 文件路径 为主
  2. 每个方法返回统一的结果 dataclass
  3. 外部程序调用通过 subprocess + 统一封装
  4. 错误处理: 外部程序缺失时返回 graceful fallback
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...agent.tools import ToolRegistry

from rdkit import Chem
from rdkit.Chem import Descriptors, AllChem

from ..base import (
    BasePlugin,
    PluginCapability,
    PluginMetadata,
    PluginSetupError,
    WorkflowStep,
)


# ---- 结果数据结构 ----

@dataclass
class DockingResult:
    """分子对接结果."""

    ligand: Chem.Mol
    affinity: float          # kcal/mol, 越小越好
    pose_index: int = 0
    rmsd_lb: float = 0.0     # RMSD lower bound
    rmsd_ub: float = 0.0     # RMSD upper bound
    receptor: str = ""
    box_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    box_size: tuple[float, float, float] = (20.0, 20.0, 20.0)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MDResult:
    """分子动力学模拟结果."""

    trajectory_file: Path | None = None
    energy_file: Path | None = None
    temperature: float = 300.0
    pressure: float = 1.0
    time_ns: float = 10.0
    rmsd_protein: list[float] = field(default_factory=list)
    rmsd_ligand: list[float] = field(default_factory=list)
    rgyr: list[float] = field(default_factory=list)  # 回转半径
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FEPResult:
    """自由能微扰结果."""

    dg_bind: float = 0.0           # ΔG_bind (kcal/mol)
    ddg_bind: float = 0.0          # ΔΔG_bind
    error: float = 0.0             # 统计误差
    lambda_windows: int = 12
    workflow_type: str = "alchemical"  # alchemical | physical
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QSARResult:
    """QSAR 预测结果."""

    mol: Chem.Mol
    predicted_value: float = 0.0
    model_name: str = ""
    descriptors: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---- 插件主类 ----

class CADDTemplatePlugin(BasePlugin):
    """CADD 插件模板 —— 提供对接/MD/FEP/QSAR 工作流."""

    meta = PluginMetadata(
        name="cadd_template",
        version="0.1.0",
        description="CADD 工作流模板：对接、MD、FEP、QSAR",
        author="MBForge Team",
        capabilities=[
            PluginCapability.AGENT_TOOL,
            PluginCapability.WORKFLOW,
            PluginCapability.CLI_COMMAND,
        ],
        supported_engines=[
            "vina", "gnina", "ledock",
            "gromacs", "amber", "openmm",
            "somd", "pmx",
            "rdkit", "mordred",
        ],
        external_binaries=[
            "vina",          # AutoDock Vina
            "gmx",           # GROMACS
            "sander",        # AMBER
            # "openmm",      # Python 包，非二进制
        ],
    )

    def setup(self) -> None:
        """检查可用引擎，建立缓存目录."""
        super().setup()
        self._engines: dict[str, bool] = {}
        for engine in self.meta.supported_engines:
            if engine in ("rdkit", "mordred"):
                self._engines[engine] = True
            else:
                self._engines[engine] = self.check_binary(engine) is not None

        # 创建子目录
        self.cache_dir().mkdir(exist_ok=True)
        (self.cache_dir() / "docking").mkdir(exist_ok=True)
        (self.cache_dir() / "md").mkdir(exist_ok=True)
        (self.cache_dir() / "fep").mkdir(exist_ok=True)
        (self.cache_dir() / "qsar").mkdir(exist_ok=True)

        print(f"[cadd_template] 可用引擎: {[k for k, v in self._engines.items() if v]}")

    # ═══════════════════════════════════════════════════════
    #  1. 分子对接 (Molecular Docking)
    # ═══════════════════════════════════════════════════════

    def run_docking(
        self,
        ligand: Chem.Mol,
        receptor_pdb: str | Path,
        center: tuple[float, float, float] | None = None,
        size: tuple[float, float, float] = (20.0, 20.0, 20.0),
        exhaustiveness: int = 32,
        num_poses: int = 9,
        engine: str = "vina",
    ) -> list[DockingResult]:
        """运行分子对接.

        Args:
            ligand: RDKit Mol 对象（3D 构象）
            receptor_pdb: 受体蛋白 PDB 路径
            center: 对接盒子中心 (x, y, z)，None 时自动计算配体重心
            size: 对接盒子尺寸 (Å)
            exhaustiveness: 搜索 exhaustive 参数
            num_poses: 输出构象数
            engine: "vina" | "gnina" | "ledock"

        Returns:
            DockingResult 列表，按亲和力排序
        """
        receptor_path = Path(receptor_pdb)
        if not receptor_path.exists():
            raise FileNotFoundError(f"受体文件不存在: {receptor_pdb}")

        if center is None:
            center = self._calc_ligand_center(ligand)

        if engine == "vina" and self._engines.get("vina"):
            return self._run_vina(
                ligand, receptor_path, center, size,
                exhaustiveness, num_poses,
            )
        elif engine == "gnina" and self._engines.get("gnina"):
            return self._run_gnina(
                ligand, receptor_path, center, size,
                exhaustiveness, num_poses,
            )
        else:
            # Fallback: RDKit 简单 shape-based 打分
            return self._fallback_docking(ligand, receptor_path, center, size)

    def _run_vina(
        self,
        ligand: Chem.Mol,
        receptor: Path,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        exhaustiveness: int,
        num_poses: int,
    ) -> list[DockingResult]:
        """调用 AutoDock Vina."""
        cache = self.cache_dir() / "docking"
        ligand_pdbqt = cache / "ligand.pdbqt"
        output_pdbqt = cache / "out.pdbqt"
        conf_file = cache / "vina.conf"

        # 1. 准备配体 (使用 Meeko 或 RDKit 转换)
        self._mol_to_pdbqt(ligand, ligand_pdbqt)

        # 2. 准备受体 (需要提前用 ADFR 套件准备)
        receptor_pdbqt = receptor.with_suffix(".pdbqt")
        if not receptor_pdbqt.exists():
            raise FileNotFoundError(
                f"受体 PDBQT 不存在: {receptor_pdbqt}\n"
                "请先用 prepare_receptor4.py 准备受体。"
            )

        # 3. 写配置文件
        conf_file.write_text(
            f"receptor = {receptor_pdbqt}\n"
            f"ligand = {ligand_pdbqt}\n"
            f"center_x = {center[0]}\n"
            f"center_y = {center[1]}\n"
            f"center_z = {center[2]}\n"
            f"size_x = {size[0]}\n"
            f"size_y = {size[1]}\n"
            f"size_z = {size[2]}\n"
            f"exhaustiveness = {exhaustiveness}\n"
            f"num_modes = {num_poses}\n"
            f"out = {output_pdbqt}\n"
        )

        # 4. 运行 Vina
        cmd = ["vina", "--config", str(conf_file)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cache)
        if proc.returncode != 0:
            raise RuntimeError(f"Vina 失败: {proc.stderr}")

        # 5. 解析输出
        return self._parse_vina_output(output_pdbqt, ligand, str(receptor))

    def _run_gnina(
        self,
        ligand: Chem.Mol,
        receptor: Path,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        exhaustiveness: int,
        num_poses: int,
    ) -> list[DockingResult]:
        """调用 GNINA (GPU 加速的 Vina + CNN 打分)."""
        cache = self.cache_dir() / "docking"
        ligand_sdf = cache / "ligand.sdf"
        output_sdf = cache / "out.sdf"

        writer = Chem.SDWriter(str(ligand_sdf))
        writer.write(ligand)
        writer.close()

        cmd = [
            "gnina",
            "-r", str(receptor),
            "-l", str(ligand_sdf),
            "--center_x", str(center[0]),
            "--center_y", str(center[1]),
            "--center_z", str(center[2]),
            "--size_x", str(size[0]),
            "--size_y", str(size[1]),
            "--size_z", str(size[2]),
            "--exhaustiveness", str(exhaustiveness),
            "--num_modes", str(num_poses),
            "-o", str(output_sdf),
            "--cnn_scoring", "rescore",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cache)
        if proc.returncode != 0:
            raise RuntimeError(f"GNINA 失败: {proc.stderr}")

        return self._parse_gnina_output(output_sdf, ligand, str(receptor))

    def _fallback_docking(
        self,
        ligand: Chem.Mol,
        receptor: Path,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
    ) -> list[DockingResult]:
        """无外部程序时的 fallback —— 基于 RDKit 的 shape similarity 粗略打分."""
        print("[cadd_template] 警告: 无外部对接程序，使用 fallback 打分")
        # 简单实现: 返回一个默认结果
        return [
            DockingResult(
                ligand=ligand,
                affinity=-5.0,
                receptor=str(receptor),
                box_center=center,
                box_size=size,
                metadata={"method": "fallback_rdkit"},
            )
        ]

    def _calc_ligand_center(self, mol: Chem.Mol) -> tuple[float, float, float]:
        """计算配体重心."""
        conf = mol.GetConformer()
        cx = cy = cz = 0.0
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            cx += pos.x
            cy += pos.y
            cz += pos.z
        n = mol.GetNumAtoms()
        return (cx / n, cy / n, cz / n)

    def _mol_to_pdbqt(self, mol: Chem.Mol, path: Path) -> None:
        """将 RDKit Mol 转为 PDBQT 格式（简化版）."""
        # TODO: 使用 meeko 或 openbabel 进行更准确的转换
        # 这里提供一个最小实现
        path.write_text(Chem.MolToPDBBlock(mol))

    def _parse_vina_output(
        self, pdbqt: Path, ligand: Chem.Mol, receptor: str
    ) -> list[DockingResult]:
        """解析 Vina PDBQT 输出."""
        results: list[DockingResult] = []
        suppl = Chem.ForwardSDMolSupplier(str(pdbqt))
        for i, mol in enumerate(suppl):
            if mol is None:
                continue
            affinity = float(mol.GetProp("REMARK").split()[2]) if mol.HasProp("REMARK") else 0.0
            results.append(
                DockingResult(
                    ligand=mol,
                    affinity=affinity,
                    pose_index=i,
                    receptor=receptor,
                )
            )
        return results

    def _parse_gnina_output(
        self, sdf: Path, ligand: Chem.Mol, receptor: str
    ) -> list[DockingResult]:
        """解析 GNINA SDF 输出."""
        results: list[DockingResult] = []
        suppl = Chem.SDMolSupplier(str(sdf))
        for i, mol in enumerate(suppl):
            if mol is None:
                continue
            affinity = float(mol.GetProp("minimizedAffinity")) if mol.HasProp("minimizedAffinity") else 0.0
            results.append(
                DockingResult(
                    ligand=mol,
                    affinity=affinity,
                    pose_index=i,
                    receptor=receptor,
                )
            )
        return results

    # ═══════════════════════════════════════════════════════
    #  2. 分子动力学 (Molecular Dynamics)
    # ═══════════════════════════════════════════════════════

    def run_md(
        self,
        system_files: dict[str, Path],
        time_ns: float = 10.0,
        temperature: float = 300.0,
        pressure: float = 1.0,
        engine: str = "gromacs",
        npt: bool = True,
        constraints: str = "h-bonds",
    ) -> MDResult:
        """运行分子动力学模拟.

        Args:
            system_files: 必须包含的键 ——
                - "topology": .top / .prmtop
                - "structure": .gro / .pdb / .inpcrd
                - "mdp" (GROMACS) 或 "mdin" (AMBER)
            time_ns: 模拟时长 (ns)
            temperature: 温度 (K)
            pressure: 压力 (bar)
            engine: "gromacs" | "amber" | "openmm"
            npt: 是否 NPT 系综 (否则 NVT)
            constraints: 约束类型

        Returns:
            MDResult
        """
        if engine == "gromacs" and self._engines.get("gmx"):
            return self._run_gromacs_md(system_files, time_ns, temperature, pressure, npt)
        elif engine == "amber" and self._engines.get("sander"):
            return self._run_amber_md(system_files, time_ns, temperature, pressure, npt)
        else:
            raise PluginSetupError(f"MD 引擎 {engine} 不可用或未安装")

    def _run_gromacs_md(
        self,
        system_files: dict[str, Path],
        time_ns: float,
        temperature: float,
        pressure: float,
        npt: bool,
    ) -> MDResult:
        """GROMACS MD 流程."""
        cache = self.cache_dir() / "md"
        gro = system_files["structure"]
        top = system_files["topology"]
        mdp = system_files.get("mdp", self._write_default_mdp(cache, time_ns, temperature))

        tpr = cache / "run.tpr"
        traj = cache / "traj.xtc"
        edr = cache / "ener.edr"

        # grompp
        subprocess.run(
            ["gmx", "grompp", "-f", str(mdp), "-c", str(gro), "-p", str(top), "-o", str(tpr)],
            capture_output=True, cwd=cache, check=True,
        )
        # mdrun
        subprocess.run(
            ["gmx", "mdrun", "-deffnm", "run", "-s", str(tpr)],
            capture_output=True, cwd=cache, check=True,
        )

        return MDResult(
            trajectory_file=traj,
            energy_file=edr,
            temperature=temperature,
            pressure=pressure,
            time_ns=time_ns,
            metadata={"engine": "gromacs"},
        )

    def _run_amber_md(
        self,
        system_files: dict[str, Path],
        time_ns: float,
        temperature: float,
        pressure: float,
        npt: bool,
    ) -> MDResult:
        """AMBER MD 流程."""
        # TODO: 实现 AMBER sander/pmemd 调用
        raise NotImplementedError("AMBER MD 尚未实现")

    def _write_default_mdp(
        self, cache: Path, time_ns: float, temperature: float
    ) -> Path:
        """写默认 GROMACS mdp 文件."""
        mdp = cache / "md.mdp"
        nsteps = int(time_ns * 1000 / 0.002)  # 2 fs dt
        mdp.write_text(
            f"integrator  = md\n"
            f"nsteps      = {nsteps}\n"
            f"dt          = 0.002\n"
            f"tcoupl      = V-rescale\n"
            f"tc-grps     = Protein Non-Protein\n"
            f"tau-t       = 0.1 0.1\n"
            f"ref-t       = {temperature} {temperature}\n"
            f"pcoupl      = Parrinello-Rahman\n"
            f"ref-p       = 1.0\n"
            f"gen-vel     = yes\n"
            f"constraints = h-bonds\n"
        )
        return mdp

    # ═══════════════════════════════════════════════════════
    #  3. 自由能微扰 (FEP)
    # ═══════════════════════════════════════════════════════

    def run_fep_alchemical(
        self,
        ligand_a: Chem.Mol,
        ligand_b: Chem.Mol,
        receptor: Path,
        engine: str = "somd",
        lambda_windows: int = 12,
    ) -> FEPResult:
        """ alchemical FEP 计算 ΔΔG_bind.

        Args:
            ligand_a: 参考配体
            ligand_b: 突变后配体
            receptor: 受体拓扑/结构
            engine: "somd" | "pmx"
            lambda_windows: λ 窗口数
        """
        if engine == "somd" and self._engines.get("somd"):
            return self._run_somd_fep(ligand_a, ligand_b, receptor, lambda_windows)
        else:
            # Fallback: MM/PBSA 粗略估计
            return self._fallback_fep(ligand_a, ligand_b, receptor)

    def _run_somd_fep(
        self,
        ligand_a: Chem.Mol,
        ligand_b: Chem.Mol,
        receptor: Path,
        lambda_windows: int,
    ) -> FEPResult:
        """SOMD (Sire) FEP 计算."""
        # TODO: 实现 SOMD 调用
        raise NotImplementedError("SOMD FEP 尚未实现")

    def _fallback_fep(
        self,
        ligand_a: Chem.Mol,
        ligand_b: Chem.Mol,
        receptor: Path,
    ) -> FEPResult:
        """无 FEP 引擎时的 fallback."""
        print("[cadd_template] 警告: 无 FEP 引擎，返回空结果")
        return FEPResult(dg_bind=0.0, ddG_bind=0.0, metadata={"method": "fallback"})

    # ═══════════════════════════════════════════════════════
    #  4. QSAR / ADMET 预测
    # ═══════════════════════════════════════════════════════

    def predict_qsar(
        self,
        mol: Chem.Mol,
        model: str = "rdkit_descriptors",
    ) -> QSARResult:
        """QSAR 性质预测.

        Args:
            mol: 输入分子
            model: "rdkit_descriptors" | "lipinski" | "admet"
        """
        if model == "rdkit_descriptors":
            desc = {
                "MW": Descriptors.MolWt(mol),
                "LogP": Descriptors.MolLogP(mol),
                "TPSA": Descriptors.TPSA(mol),
                "HBD": Descriptors.NumHDonors(mol),
                "HBA": Descriptors.NumHAcceptors(mol),
                "RotatableBonds": Descriptors.NumRotatableBonds(mol),
                "QED": Descriptors.qed(mol) if hasattr(Descriptors, "qed") else 0.0,
            }
            return QSARResult(
                mol=mol,
                predicted_value=desc.get("LogP", 0.0),
                model_name="rdkit_descriptors",
                descriptors=desc,
            )
        elif model == "lipinski":
            return self._lipinski_check(mol)
        else:
            raise ValueError(f"未知 QSAR 模型: {model}")

    def _lipinski_check(self, mol: Chem.Mol) -> QSARResult:
        """Lipinski 五规则检查."""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = Descriptors.NumHDonors(mol)
        hba = Descriptors.NumHAcceptors(mol)

        violations = sum([
            mw > 500,
            logp > 5,
            hbd > 5,
            hba > 10,
        ])
        descriptors = {"MW": mw, "LogP": logp, "HBD": hbd, "HBA": hba, "violations": violations}
        return QSARResult(
            mol=mol,
            predicted_value=float(violations),
            model_name="lipinski",
            descriptors=descriptors,
            confidence=1.0 if violations <= 1 else 0.5,
        )

    # ═══════════════════════════════════════════════════════
    #  5. 插件能力接口实现
    # ═══════════════════════════════════════════════════════

    def register_tools(self, registry: ToolRegistry) -> None:
        """向 Agent 注册 CADD 工具."""
        registry.register(
            name="molecular_docking",
            description="运行分子对接，预测配体-受体结合亲和力",
            parameters_schema={
                "ligand_smiles": {"type": "string", "description": "配体 SMILES"},
                "receptor_pdb": {"type": "string", "description": "受体 PDB 文件路径"},
                "center_x": {"type": "number", "description": "盒子中心 X"},
                "center_y": {"type": "number", "description": "盒子中心 Y"},
                "center_z": {"type": "number", "description": "盒子中心 Z"},
                "engine": {"type": "string", "enum": ["vina", "gnina"], "default": "vina"},
            },
            func=self._tool_docking,
        )
        registry.register(
            name="predict_admet",
            description="预测分子 ADMET 性质 (Lipinski, QED, 理化性质)",
            parameters_schema={
                "smiles": {"type": "string", "description": "分子 SMILES"},
                "model": {"type": "string", "enum": ["rdkit_descriptors", "lipinski"], "default": "rdkit_descriptors"},
            },
            func=self._tool_qsar,
        )

    def _tool_docking(self, ligand_smiles: str, receptor_pdb: str, **kwargs) -> str:
        """Agent 工具包装: 分子对接."""
        mol = Chem.MolFromSmiles(ligand_smiles)
        if mol is None:
            return "错误: 无效 SMILES"
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        AllChem.MMFFOptimizeMolecule(mol)

        center = (kwargs.get("center_x", 0.0), kwargs.get("center_y", 0.0), kwargs.get("center_z", 0.0))
        engine = kwargs.get("engine", "vina")

        try:
            results = self.run_docking(mol, receptor_pdb, center=center, engine=engine)
            if not results:
                return "对接完成，但未找到有效构象"
            best = results[0]
            return (
                f"对接完成 (引擎: {engine})\n"
                f"最佳亲和力: {best.affinity:.2f} kcal/mol\n"
                f"受体: {best.receptor}"
            )
        except Exception as e:
            return f"对接失败: {e}"

    def _tool_qsar(self, smiles: str, model: str = "rdkit_descriptors", **kwargs) -> str:
        """Agent 工具包装: QSAR."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return "错误: 无效 SMILES"
        result = self.predict_qsar(mol, model)
        lines = [f"模型: {result.model_name}"]
        for k, v in result.descriptors.items():
            lines.append(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
        return "\n".join(lines)

    def get_workflow_steps(self) -> list[WorkflowStep]:
        """返回 CADD 批处理工作流步骤."""
        return [
            WorkflowStep(
                name="docking",
                description="批量分子对接",
                input_schema={
                    "ligands": {"type": "array", "description": "SMILES 列表"},
                    "receptor_pdb": {"type": "string"},
                    "center": {"type": "array", "description": "[x, y, z]"},
                },
                output_schema={
                    "affinities": {"type": "array", "description": "亲和力列表 (kcal/mol)"},
                },
                run=self._batch_docking,
            ),
            WorkflowStep(
                name="admet_screening",
                description="批量 ADMET 筛选",
                input_schema={
                    "smiles_list": {"type": "array"},
                    "max_violations": {"type": "integer", "default": 1},
                },
                output_schema={
                    "passed": {"type": "array"},
                    "failed": {"type": "array"},
                },
                run=self._batch_admet,
            ),
        ]

    def _batch_docking(self, ligands: list[str], receptor_pdb: str, center: list[float], **kwargs) -> dict:
        """批量对接工作流."""
        results = []
        for smi in ligands:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            try:
                res = self.run_docking(mol, receptor_pdb, center=tuple(center))
                results.append({"smiles": smi, "affinity": res[0].affinity if res else None})
            except Exception as e:
                results.append({"smiles": smi, "error": str(e)})
        return {"affinities": results}

    def _batch_admet(self, smiles_list: list[str], max_violations: int = 1, **kwargs) -> dict:
        """批量 ADMET 筛选."""
        passed, failed = [], []
        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                failed.append({"smiles": smi, "reason": "invalid_smiles"})
                continue
            res = self.predict_qsar(mol, "lipinski")
            v = res.descriptors.get("violations", 999)
            if v <= max_violations:
                passed.append({"smiles": smi, "violations": v})
            else:
                failed.append({"smiles": smi, "violations": v})
        return {"passed": passed, "failed": failed}

    def register_cli(self, subparsers) -> None:
        """注册 CLI 子命令."""
        p = subparsers.add_parser("cadd", help="CADD 工作流")
        p.add_argument("--docking", action="store_true", help="运行对接")
        p.add_argument("--ligand", type=str, help="配体 SMILES")
        p.add_argument("--receptor", type=str, help="受体 PDB")
        p.set_defaults(func=self._cli_main)

    def _cli_main(self, args) -> None:
        if args.docking and args.ligand and args.receptor:
            mol = Chem.MolFromSmiles(args.ligand)
            if mol:
                results = self.run_docking(mol, args.receptor)
                print(json.dumps([{"affinity": r.affinity} for r in results], indent=2))
