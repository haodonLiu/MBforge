# UniDock 插件使用文档

## 目录

- [1. UniDock 简介](#1-unidock-简介)
- [2. 安装指南](#2-安装指南)
- [3. 输入文件准备](#3-输入文件准备)
- [4. 参数说明](#4-参数说明)
- [5. 使用示例](#5-使用示例)
- [6. 结果解读](#6-结果解读)
- [7. FAQ](#7-faq)

---

## 1. UniDock 简介

### 什么是 UniDock

UniDock 是由深势科技开发的高性能 GPU 加速分子对接引擎（Apache 2.0 开源）。它基于 AutoDock Vina 的算法框架，通过 CUDA 并行化实现分子对接的极致加速。相比传统 CPU 对接，UniDock 在 V100 GPU 上可实现 **2000 倍**以上的速度提升，使千万级化合物库的虚拟筛选成为可能。

### 与 AutoDock Vina 的区别

| 特性 | AutoDock Vina | UniDock |
|------|---------------|---------|
| 计算平台 | CPU | GPU (CUDA) |
| 计算速度 | 基准 | 快 2000 倍 |
| 适用场景 | 数十至数百个配体 | 百万至千万级配体 |
| 批量对接 | 串行 | GPU 并行批处理 |
| 开源协议 | Apache 2.0 | Apache 2.0 |

### 适用场景

- **虚拟筛选（Virtual Screening）**：对化合物库进行大规模初筛
- **靶点验证**：快速评估候选分子与靶点的结合潜力
- **先导化合物优化**：评估系列化合物的构效关系
- **重对接验证**：验证对接方法的准确性

### 性能数据

- **GPU**: NVIDIA V100 / A100 / RTX 3090 及以上
- **显存需求**: 4GB+（单批次）
- **加速比**: CPU Vina 相比 GPU UniDock ≈ 1:2000
- **吞吐量**: 单卡 V100 可达 ~100,000 配体/小时（fast 模式）

---

## 2. 安装指南

### 系统要求

| 要求 | 规格 |
|------|------|
| GPU | NVIDIA GPU (compute capability >= 7.0) |
| CUDA | >= 11.8 |
| 显存 | >= 4GB（推荐 8GB+） |
| 操作系统 | Linux / Windows (WSL2) |

### conda 安装

```bash
# 创建新环境并安装 UniDock
conda create -n unidock_env unidock -c conda-forge

# 激活环境
conda activate unidock_env

# 验证安装
unidock --version
```

### 备选安装方式

```bash
# 使用 pip（需要先安装 CUDA 环境）
pip install unidock

# 或从源码编译（适用于高级用户）
git clone https://github.com/dptech-corp/Uni-Dock.git
cd Uni-Dock
mkdir build && cd build
cmake .. -DCUDA_ARCH=70 -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### 验证安装

```bash
# 检查版本
unidock --version

# 查看帮助
unidock --help
```

---

## 3. 输入文件准备

### 3.1 受体准备

受体文件需要转换为 PDBQT 格式（包含原子电荷和可旋转键信息）。

#### 方法一：使用 AutoDockTools

```bash
# 准备 PDB 文件（去除水分子、添加氢原子）
# 使用 AutoDockTools 的 prepare_receptor4.py 脚本
python prepare_receptor4.py -r receptor.pdb -o receptor.pdbqt
```

#### 方法二：使用 Meeko（推荐）

```bash
# 安装 meeko
pip install meeko

# 转换受体
python -c "
from meeko import PDBQTMolecule
mol = PDBQTMolecule.from_file('receptor.pdb')
mol.write('receptor.pdbqt')
"
```

### 3.2 配体准备

配体可以从 SDF、MOL2 或 SMILES 转换。

#### 从 SDF 转换

```bash
# 使用 obabel
obabel ligands.sdf -opdbqt -O ligands.pdbqt -p 7.4

# 使用 meeko
python -c "
from meeko import RDKitMolCreate
from rdkit import Chem
suppl = Chem.SDMolSupplier('ligands.sdf')
mols = [mol for mol in suppl if mol]
pdbqt_strings = RDKitMolCreate.from_rdkit_mols(mols)
# 保存到文件
"
```

#### 从 SMILES 转换

```bash
# 使用 obabel
obabel -:\"CCO\" -osmi --gen3d -opdbqt -O ethanol.pdbqt

# 使用 RDKit + Meeko
python -c "
from rdkit import Chem
from meeko import MoleculePreparation

smiles = 'CCO'
mol = Chem.MolFromSmiles(smiles)
mol = Chem.AddHs(mol)
Chem.AllChem.EmbedMolecule(mol)
Chem.AllChem.MMFFOptimizeMolecule(mol)

prep = MoleculePreparation()
mol_pdbqt, msgs = prep.prepare(mol)
mol_pdbqt.export('ethanol.pdbqt')
"
```

### 3.3 定义对接盒子

确定结合位点的中心坐标和盒子尺寸是成功对接的关键。

#### 方法一：基于已知配体

```python
# 使用已知结合配体定义盒子
from rdkit import Chem
from rdkit.Chem import AllChem

ligand = Chem.MolFromSmiles('已知配体SMILES')
ligand = Chem.AddHs(ligand)
AllChem.EmbedMolecule(ligand)

conf = ligand.GetConformer()
center = (
    sum(conf.GetAtomPosition(i).x for i in range(conf.GetNumAtoms())) / conf.GetNumAtoms(),
    sum(conf.GetAtomPosition(i).y for i in range(conf.GetNumAtoms())) / conf.GetNumAtoms(),
    sum(conf.GetAtomPosition(i).z for i in range(conf.GetNumAtoms())) / conf.GetNumAtoms()
)
# 盒子尺寸通常设为覆盖结合口袋再加 5-10 Å
size = (25.0, 25.0, 25.0)
```

#### 方法二：使用 PyMOL 可视化确定

1. 打开受体-配体复合物结构
2. 识别活性位点
3. 记录中心坐标 (center_x, center_y, center_z)
4. 根据口袋大小设置 size

---

## 4. 参数说明

### 4.1 主要参数

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--receptor` | `-r` | str | 必需 | 受体 PDBQT 文件路径 |
| `--ligand` | `-l` | str | 必需 | 配体 PDBQT/SDF/MOL2 文件路径 |
| `--out` | `-o` | str | ligand_out.pdbqt | 输出文件路径 |
| `--scoring` | - | str | vina | 打分函数: `vina`, `vinardo`, `ad4` |
| `--center_x` | - | float | 0.0 | 对接盒子中心 X 坐标 (Å) |
| `--center_y` | - | float | 0.0 | 对接盒子中心 Y 坐标 (Å) |
| `--center_z` | - | float | 0.0 | 对接盒子中心 Z 坐标 (Å) |
| `--size_x` | - | float | 20.0 | 对接盒子 X 尺寸 (Å) |
| `--size_y` | - | float | 20.0 | 对接盒子 Y 尺寸 (Å) |
| `--size_z` | - | float | 20.0 | 对接盒子 Z 尺寸 (Å) |
| `--autobox` | - | bool | False | 根据配体自动设置盒子大小 |
| `--flex` | - | str | None | 柔性侧链 PDBQT 文件路径 |

### 4.2 搜索参数

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--search_mode` | - | str | balance | 搜索模式: `fast`, `balance`, `detail` |
| `--exhaustiveness` | - | int | None | 搜索穷尽度（覆盖 search_mode） |
| `--num_modes` | - | int | 9 | 最大输出构象数 |
| `--energy_range` | - | float | 3.0 | 最佳与最差构象最大能量差 (kcal/mol) |
| `--max_step` | - | int | 40 | 搜索最大迭代步数 |

### 4.3 GPU 参数

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--gpu_batch` | - | str | None | GPU 批处理配体文件路径 |
| `--ligand_index` | - | str | None | 配体索引文件路径（避免命令行过长） |
| `--paired_batch_size` | - | int | 1 | 配对批处理大小 |
| `--paired_config` | - | str | None | 配对批处理配置文件 (JSON) |
| `--max_gpu_memory` | - | int | 0 | GPU 显存上限 (MB)，0 表示不限制 |
| `--device` | - | int | 0 | GPU 设备编号 |

### 4.4 搜索模式说明

| 模式 | exhaustiveness | max_step | 适用场景 | 速度 |
|------|---------------|----------|----------|------|
| `fast` | 128 | 20 | 大规模初筛，数百万配体 | 最快 |
| `balance` | 384 | 40 | 常规虚拟筛选（推荐） | 较快 |
| `detail` | 512 | 40 | 高精度需求，少量配体 | 较慢 |

### 4.5 打分函数说明

| 函数 | 说明 | 适用场景 |
|------|------|----------|
| `vina` | AutoDock Vina 打分函数（默认） | 通用场景 |
| `vinardo` | Vinardo 打分函数 | 轻量级快速评估 |
| `ad4` | AutoDock4 打分函数 | 兼容性要求高的场景 |

---

## 5. 使用示例

### 5.1 单配体对接

```bash
# 基本用法
unidock --receptor receptor.pdbqt --ligand ligand.pdbqt \
    --center_x 15.0 --center_y 25.0 --center_z 40.0 \
    --size_x 20.0 --size_y 20.0 --size_z 20.0 \
    --out result.pdbqt

# 使用 fast 模式（快速筛选）
unidock --receptor receptor.pdbqt --ligand ligand.pdbqt \
    --center_x 15.0 --center_y 25.0 --center_z 40.0 \
    --size 20.0 20.0 20.0 \
    --search_mode fast \
    --out result.pdbqt

# 使用 autobox（根据配体自动设置盒子）
unidock --receptor receptor.pdbqt --ligand ligand.pdbqt \
    --center_x 15.0 --center_y 25.0 --center_z 40.0 \
    --autobox \
    --out result.pdbqt
```

### 5.2 批量对接

#### 方法一：使用配体索引文件

```bash
# 创建配体索引文件 ligands.txt
# 每行格式：SMILES 或 文件路径
CCO
CCOCCC
c1ccccc1
/path/to/ligand1.pdbqt
/path/to/ligand2.pdbqt

# 使用 ligand_index 进行批量对接
unidock --receptor receptor.pdbqt \
    --ligand_index ligands.txt \
    --center_x 15.0 --center_y 25.0 --center_z 40.0 \
    --size 20.0 20.0 20.0 \
    --search_mode fast \
    --out batch_results/
```

#### 方法二：使用 GPU 批处理

```bash
# 准备配体列表文件（每行一个 PDBQT 文件路径）
echo "ligand1.pdbqt" > batch_ligands.txt
echo "ligand2.pdbqt" >> batch_ligands.txt
echo "ligand3.pdbqt" >> batch_ligands.txt

# GPU 批处理
unidock --receptor receptor.pdbqt \
    --gpu_batch batch_ligands.txt \
    --center_x 15.0 --center_y 25.0 --center_z 40.0 \
    --size 20.0 20.0 20.0 \
    --out batch_results/
```

### 5.3 配对批处理（Paired Batch）

当受体-配体以 1:1 方式配对时，使用配对批处理可获得最优性能。

```bash
# 创建配对配置文件 paired_config.json
cat > paired_config.json << 'EOF'
{
    "pairs": [
        {"receptor": "receptor1.pdbqt", "ligand": "ligand1.pdbqt"},
        {"receptor": "receptor2.pdbqt", "ligand": "ligand2.pdbqt"}
    ]
}
EOF

# 执行配对对接
unidock --paired_config paired_config.json \
    --paired_batch_size 32 \
    --out results/
```

### 5.4 MBForge CLI 使用

```bash
# 单分子对接
mbforge unidock --ligand "CCO" --receptor receptor.pdbqt \
    --center 15.0 25.0 40.0 --size 20.0 20.0 20.0 \
    --search-mode balance

# 批量对接
mbforge unidock-batch --smiles-file ligands.smi \
    --receptor receptor.pdbqt \
    --center 15.0 25.0 40.0 --size 20.0 20.0 20.0 \
    --search-mode fast --output results.json
```

### 5.5 Python API 使用

```python
from rdkit import Chem
from mbforge.plugins.unidock import UniDockPlugin

# 初始化插件
plugin = UniDockPlugin()
plugin.setup()

# 准备配体
mol = Chem.MolFromSmiles('CCO')
mol = Chem.AddHs(mol)
Chem.AllChem.EmbedMolecule(mol)
Chem.AllChem.MMFFOptimizeMolecule(mol)

# 运行对接
results = plugin.run_docking(
    ligand=mol,
    receptor_pdb='receptor.pdbqt',
    center=(15.0, 25.0, 40.0),
    size=(20.0, 20.0, 20.0),
    scoring='vina',
    search_mode='balance',
)

# 获取最佳结果
best = results[0]
print(f"最佳亲和力: {best.affinity:.3f} kcal/mol")
print(f"RMSD: {best.rmsd_lb:.2f}/{best.rmsd_ub:.2f} Å")
```

### 5.6 搜索模式选用建议

| 场景 | 推荐模式 | 说明 |
|------|----------|------|
| **千万级初筛** | `fast` | 速度优先，牺牲部分精度 |
| **百万级筛选** | `fast` | 平衡速度与质量 |
| **万级精筛** | `balance` | 推荐默认模式 |
| **候选分子优化** | `balance` | 较好精度 |
| **高精度重对接** | `detail` | 最高精度，耗时较长 |
| **方法验证** | `detail` | 追求准确结果 |

---

## 6. 结果解读

### 6.1 输出文件说明

UniDock 输出 PDBQT 格式文件，包含多个对接构象。

```
MODEL        1                          # 模型 1
REMARK  VINA RESULT:      -8.5      0.000      0.000    # 亲和力和 RMSD
ATOM      1  N   LIG A   1      15.234  25.678  40.123  ...
...
ENDMDL                             # 模型结束
MODEL        2                          # 模型 2
...
```

### 6.2 输出字段含义

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `MODEL` | 构象编号 | MODEL 1 |
| `REMARK VINA RESULT` | 对接结果行 | - |
| `affinity` | 结合亲和力 (kcal/mol)，**越小越好** | -8.5 |
| `rmsd_lb` | RMSD lower bound (Å) | 0.000 |
| `rmsd_ub` | RMSD upper bound (Å) | 0.000 |
| `ATOM/HETATM` | 原子坐标 | - |

### 6.3 亲和力（Affinity）含义

| 亲和力范围 | 含义 | 预期活性 |
|------------|------|----------|
| < -9.0 kcal/mol | 强结合 | nM 级活性 |
| -7.0 ~ -9.0 kcal/mol | 中等结合 | μM 级活性 |
| -5.0 ~ -7.0 kcal/mol | 弱结合 | μM ~ mM 级 |
| > -5.0 kcal/mol | 无明显结合 | 可能无活性 |

**注意**：这是基于经验规则的一般性指导，实际活性需通过实验验证。

### 6.4 RMSD 含义

- **rmsd_lb (Lower Bound)**: 所有构象相对于参考构象的 RMSD 下界
- **rmsd_ub (Upper Bound)**: 所有构象相对于参考构象的 RMSD 上界

在重对接验证中，RMSD < 2.0 Å 通常被认为是成功再现晶体结构。

### 6.5 批量结果排序

```python
# 按亲和力排序
results.sort(key=lambda x: x.affinity)

# 提取 Top N
top_10 = results[:10]
```

---

## 7. FAQ

### Q1: GPU 显存不足 (OOM) 怎么处理？

**问题**：运行时报错 `CUDA out of memory`

**解决方案**：

1. **减小批处理大小**
   ```bash
   # 使用 ligand_index 而不是 gpu_batch
   unidock --receptor receptor.pdbqt \
       --ligand_index small_batch.txt \
       --center 15.0 25.0 40.0 --size 20.0 20.0 20.0
   ```

2. **限制 GPU 显存使用**
   ```bash
   # 限制显存为 4GB
   unidock --receptor receptor.pdbqt \
       --ligand ligand.pdbqt \
       --max_gpu_memory 4096 \
       --center 15.0 25.0 40.0 --size 20.0 20.0 20.0
   ```

3. **使用 CPU 模式（慢但可靠）**
   ```bash
   # 设置 device 为 -1 强制使用 CPU
   unidock --receptor receptor.pdbqt \
       --ligand ligand.pdbqt \
       --device -1 \
       --center 15.0 25.0 40.0 --size 20.0 20.0 20.0
   ```

### Q2: 命令行过长怎么处理？

**问题**：配体文件列表太长，命令行超出限制

**解决方案**：使用 `ligand_index` 参数

```bash
# 错误：配体列表过长
unidock --receptor receptor.pdbqt \
    --ligand ligand1.pdbqt ligand2.pdbqt ... ligand1000.pdbqt \
    # 命令行过长！

# 正确：使用配体索引文件
echo "ligand1.pdbqt" > ligands.txt
echo "ligand2.pdbqt" >> ligands.txt
# ... 添加更多配体

unidock --receptor receptor.pdbqt \
    --ligand_index ligands.txt \
    --center 15.0 25.0 40.0 --size 20.0 20.0 20.0
```

### Q3: 少量配体时速度慢的原因？

**问题**：只有几个配体时，对接速度不如预期快

**原因**：
- GPU 初始化开销在少量计算时被放大
- GPU 并行优势需要一定批处理量才能体现
- 单卡多任务调度开销

**建议**：
1. 对于 < 10 个配体，直接使用 AutoDock Vina 可能更方便
2. 将多个任务合并为批次提交
3. 使用 `paired_batch` 模式提高效率

### Q4: 如何处理柔性侧链？

```bash
# 准备柔性侧链 PDBQT
# 首先识别需要设为柔性的残基
# 使用 meeko 准备
python -c "
from meeko import FlexmolBuilder
flex = FlexmolBuilder.from_pdb_or_pdbqt('receptor.pdbqt', residues=['HIS:41', 'GLU:45'])
flex.write('flex.pdbqt')
"

# 运行带柔性侧链的对接
unidock --receptor receptor.pdbqt \
    --ligand ligand.pdbqt \
    --flex flex.pdbqt \
    --center 15.0 25.0 40.0 --size 20.0 20.0 20.0
```

### Q5: 对接结果与晶体结构偏差大？

**检查项**：
1. 盒子中心/大小是否准确
2. 是否使用了正确的打分函数
3. 尝试使用 `detail` 模式重新对接
4. 检查受体准备是否正确（加氢、电荷）

```bash
# 高精度重对接
unidock --receptor receptor.pdbqt \
    --ligand ligand.pdbqt \
    --center 15.0 25.0 40.0 --size 25.0 25.0 25.0 \
    --search_mode detail \
    --num_modes 20 \
    --exhaustiveness 512 \
    --out high_precision_result.pdbqt
```

### Q6: 如何安装 GPU 驱动和 CUDA？

```bash
# 检查当前驱动
nvidia-smi

# 检查 CUDA 版本
nvcc --version

# 如需安装 CUDA，访问 NVIDIA 官网下载
# https://developer.nvidia.com/cuda-downloads
```

---

## 附录

### 相关链接

- **UniDock GitHub**: https://github.com/dptech-corp/Uni-Dock
- **AutoDock Vina**: https://vina.scripps.edu/
- **Meeko**: https://github.com/forlilab/Meeko
- **MBForge**: https://github.com/your-repo/MBForge

### 许可证

UniDock 采用 Apache 2.0 开源许可证。

### 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1.0 | 2024 | MBForge 集成版，支持 GPU 对接、批量对接、柔性侧链 |
