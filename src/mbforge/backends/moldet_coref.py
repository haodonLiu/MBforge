"""MolDetect Coref 后端：分子-标号共指消解.

基于 MolDetect 模型的 coref 模式，自动检测图像中的分子和标识符，
并建立它们之间的共指关系（哪个标号对应哪个分子）。

模型来源：modelscope download --model studio-test/MolDetectCkpt
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from mbforge.utils.helpers import is_gpu_available
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# ---- 可选依赖探测 ----

def _has_torch() -> bool:
    """运行时检查 torch 是否安装."""
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _has_easyocr() -> bool:
    """运行时检查 easyocr 是否安装."""
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False


# ---- 数据类型 ----

@dataclass
class CorefBbox:
    """检测到的边界框（分子或标识符）"""
    category_id: int  # 1=分子, 3=标识符
    bbox: tuple[float, float, float, float]  # 归一化坐标 [x1, y1, x2, y2]
    smiles: str | None = None  # 分子的 SMILES（仅 category_id=1）
    molfile: str | None = None  # 分子的 MOL 文件（可选）
    text: str | None = None  # 标识符的文本（仅 category_id=3）
    score: float = 0.0  # 检测置信度

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式."""
        return {
            "category_id": self.category_id,
            "bbox": list(self.bbox),
            "smiles": self.smiles,
            "molfile": self.molfile,
            "text": self.text,
            "score": self.score,
        }


@dataclass
class CorefResult:
    """共指消解结果"""
    bboxes: list[CorefBbox] = field(default_factory=list)
    corefs: list[tuple[int, int]] = field(default_factory=list)  # [(mol_idx, idt_idx), ...]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式."""
        return {
            "bboxes": [b.to_dict() for b in self.bboxes],
            "corefs": self.corefs,
        }


# ---- 模型路径管理 ----

def _resolve_model_path(model_path: Path | None = None) -> Path | None:
    """解析模型文件路径 — 统一走 ResourceManager."""
    if model_path is not None:
        if model_path.exists():
            return model_path
        logger.warning("指定的模型路径不存在：%s", model_path)
        return None

    try:
        from mbforge.core.resource_manager import ResourceManager
        resolved = ResourceManager.resolve_model_for_backend("moldet_coref")
        if resolved is not None:
            return resolved
    except ImportError:
        pass

    # 兜底：环境变量
    env_path = os.getenv("MBFORGE_MOLDETECT_COREF_MODEL")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    logger.warning("MolDetect coref 模型未找到")
    return None


# ---- MolDetect Coref 后端 ----

class MolDetectCorefBackend:
    """MolDetect coref 后端：分子-标号共指消解.

    使用 MolDetect 模型的 coref 模式检测图像中的分子和标识符，
    并建立它们之间的共指关系。

    依赖：
    - torch: 模型推理
    - easyocr: 标识符文本识别（可选）
    - molscribe: 分子 SMILES 识别（可选，复用现有后端）
    """

    def __init__(
        self,
        model_path: Path | None = None,
        device: str | None = None,
    ) -> None:
        """初始化后端.

        Args:
            model_path: 模型文件路径（.pt/.pth）。None 时自动查找。
            device: 推理设备，None=自动，'cpu', 'cuda', 'cuda:0' 等
        """
        self.device = device or os.getenv("MBFORGE_DEVICE", "auto")
        self.model_path = _resolve_model_path(model_path)
        self._model = None
        self._tokenizer = None
        self._molscribe = None
        self._ocr_reader = None
        self._loaded = False

        if self.model_path is None:
            logger.warning(
                "MolDetect coref 模型未找到，共指消解功能不可用。"
                "请运行：modelscope download --model studio-test/MolDetectCkpt"
            )
            return

        self._load_model()

    def _load_model(self) -> None:
        """加载 MolDetect 模型."""
        if not _has_torch():
            logger.warning("torch 未安装，MolDetect coref 不用")
            return

        try:
            import torch
            import sys

            # 临时修改 __init__.py 避免导入 molscribe
            ref_dir = Path(__file__).parent.parent.parent.parent / "ref" / "MolDetect"
            init_file = ref_dir / "rxnscribe" / "__init__.py"
            init_backup = None

            if init_file.exists():
                # 备份原始 __init__.py
                init_backup = init_file.read_text()
                # 写入空的 __init__.py
                init_file.write_text("# Temporary empty init\n")

            try:
                # 将 ref/MolDetect 添加到 Python 路径
                if ref_dir.exists() and str(ref_dir) not in sys.path:
                    sys.path.insert(0, str(ref_dir))

                logger.info("正在加载 MolDetect coref 模型：%s", self.model_path)
                start = time.perf_counter()

                # 确定设备
                if self.device == "auto":
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                else:
                    device = torch.device(self.device)

                # Monkey-patch torchvision.models.resnet50 避免下载预训练权重
                # coref_best.ckpt 已经包含了完整的 backbone 权重
                import torchvision.models
                _original_resnet50 = torchvision.models.resnet50
                def _resnet50_no_pretrained(**kwargs):
                    kwargs['pretrained'] = False
                    return _original_resnet50(**kwargs)
                torchvision.models.resnet50 = _resnet50_no_pretrained

                try:
                    # 设置模型参数
                    class Args:
                        pass
                    args = Args()
                    args.backbone = 'resnet50'
                    args.dilation = False
                    args.position_embedding = 'sine'
                    args.enc_layers = 6
                    args.dec_layers = 6
                    args.dim_feedforward = 1024
                    args.hidden_dim = 256
                    args.dropout = 0.1
                    args.nheads = 8
                    args.pre_norm = False
                    args.format = 'coref'
                    args.input_size = 1333
                    args.pix2seq = True
                    args.pix2seq_ckpt = None
                    args.pred_eos = True
                    args.is_coco = False
                    args.use_hf_transformer = False  # Checkpoint 使用原生 Transformer 格式
                    args.coord_bins = 2000
                    args.sep_xy = False

                    # 导入 rxnscribe 子模块
                    from rxnscribe.pix2seq import build_pix2seq_model
                    from rxnscribe.tokenizer import get_tokenizer
                    from rxnscribe.dataset import make_transforms

                    # 加载 tokenizer
                    tokenizer = get_tokenizer(args)

                    # 先加载 checkpoint，获取 state_dict
                    states = torch.load(str(self.model_path), map_location=torch.device('cpu'))

                    # 构建模型（此时 pretrained=False，不下载权重）
                    model = build_pix2seq_model(args, tokenizer[args.format])

                    # 从 checkpoint 加载完整权重（包括 backbone）
                    state_dict = states.get('state_dict', states)

                    # 移除 'model.' 前缀
                    # Checkpoint 和模型的 key 格式已经匹配
                    cleaned_state_dict = {}
                    for k, v in state_dict.items():
                        new_key = k.replace('model.', '') if k.startswith('model.') else k
                        cleaned_state_dict[new_key] = v

                    # 加载权重
                    missing, unexpected = model.load_state_dict(cleaned_state_dict, strict=False)
                    if missing:
                        logger.warning("Missing keys: %s", missing[:5])
                    if unexpected:
                        logger.warning("Unexpected keys: %s", unexpected[:5])
                    logger.info("Loaded %d keys successfully", len(cleaned_state_dict))

                    model.to(device)
                    model.eval()
                finally:
                    # 恢复原始的 resnet50 函数
                    torchvision.models.resnet50 = _original_resnet50

                self._model = model
                self._tokenizer = tokenizer[args.format]
                self._transform = make_transforms('test', augment=False, debug=False)
                self._device = device

                logger.info(
                    "MolDetect coref 模型加载完成，耗时 %.2fs",
                    time.perf_counter() - start,
                )
                self._loaded = True

            finally:
                # 恢复原始 __init__.py
                if init_backup is not None and init_file.exists():
                    init_file.write_text(init_backup)

        except Exception as exc:
            logger.warning("MolDetect coref 模型加载失败：%s", exc)
            import traceback
            traceback.print_exc()
            self._model = None
            self._loaded = False

    def _get_molscribe(self):
        """获取 MolScribe 实例（惰性加载，使用现有的 backends.molscribe）."""
        if self._molscribe is None:
            try:
                from . import molscribe as molscribe_backend
                from mbforge.utils.helpers import is_gpu_available

                dev = self.device
                if dev in (None, "", "auto"):
                    dev = "cuda" if is_gpu_available() else "cpu"
                molscribe_backend.load(device=dev)
                if molscribe_backend._MODEL is not None:
                    # 包装为 rxnscribe 兼容的接口
                    self._molscribe = type('MolScribeWrapper', (), {
                        'predict_images': lambda self, images, **kwargs: [
                            {'smiles': molscribe_backend.predict(img).esmiles,
                             'molfile': '',
                             'atoms': [],
                             'bonds': []}
                            for img in images
                        ]
                    })()
                    logger.info("MolScribe loaded for coref backend")
            except Exception as exc:
                logger.warning("MolScribe load failed for coref: %s", exc)
        return self._molscribe

    def _get_ocr_reader(self):
        """获取 EasyOCR reader（惰性加载）."""
        if self._ocr_reader is None and _has_easyocr():
            try:
                import easyocr

                use_gpu = "cuda" in str(self.device) or (
                    self.device == "auto" and is_gpu_available()
                )
                self._ocr_reader = easyocr.Reader(["en"], gpu=use_gpu)
                logger.info("EasyOCR loaded for coref backend")
            except Exception as exc:
                logger.warning("EasyOCR load failed: %s", exc)
        return self._ocr_reader

    def is_available(self) -> bool:
        """后端是否可用."""
        return self._loaded and self._model is not None

    def detect_coref(
        self,
        image: Image.Image | np.ndarray,
        use_molscribe: bool = True,
        use_ocr: bool = True,
    ) -> CorefResult:
        """检测分子和标识符的共指关系.

        Args:
            image: 输入图像（PIL Image 或 numpy array）
            use_molscribe: 是否使用 MolScribe 识别分子 SMILES
            use_ocr: 是否使用 EasyOCR 识别标识符文本

        Returns:
            CorefResult 包含检测到的 bboxes 和 corefs 关系
        """
        if not self.is_available():
            raise RuntimeError("MolDetect coref 后端不可用")

        import torch
        import sys
        # 导入 postprocess 模块
        ref_dir = Path(__file__).parent.parent.parent.parent / "ref" / "MolDetect"
        if ref_dir.exists() and str(ref_dir) not in sys.path:
            sys.path.insert(0, str(ref_dir))
        from rxnscribe.data import postprocess_coref_results

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        try:
            # 预处理图像
            img_tensor, ref = self._transform(image)
            img_tensor = img_tensor.unsqueeze(0).to(self._device)

            # 模型推理
            with torch.no_grad():
                pred_seqs, pred_scores = self._model(img_tensor, max_len=self._tokenizer.max_len)

            # 解码序列
            bboxes = self._tokenizer.sequence_to_data(
                pred_seqs[0].tolist(),
                pred_scores[0].tolist(),
                scale=ref['scale'],
            )

            # 后处理
            # 准备 molscribe 和 ocr 对象
            molscribe_obj = None
            if use_molscribe:
                molscribe_obj = self._get_molscribe()

            ocr_obj = None
            if use_ocr and _has_easyocr():
                ocr_obj = self._get_ocr_reader()

            raw_result = postprocess_coref_results(
                bboxes,
                image=image,
                molscribe=molscribe_obj,
                ocr=ocr_obj,
            )

        except Exception as exc:
            logger.error("MolDetect coref 推理失败：%s", exc)
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Coref detection failed: {exc}") from exc

        # 解析结果
        return self._parse_result(raw_result)

    def _parse_result(self, raw_result: dict[str, Any]) -> CorefResult:
        """解析 MolDetect 原始输出为 CorefResult."""
        bboxes = []
        for bbox_data in raw_result.get("bboxes", []):
            category_id = bbox_data.get("category_id", 0)
            bbox_tuple = tuple(bbox_data.get("bbox", [0, 0, 0, 0]))
            smiles = bbox_data.get("smiles")
            molfile = bbox_data.get("molfile")
            text = bbox_data.get("text")
            score = bbox_data.get("score", 0.0)

            bboxes.append(
                CorefBbox(
                    category_id=category_id,
                    bbox=bbox_tuple,
                    smiles=smiles,
                    molfile=molfile,
                    text=text,
                    score=score,
                )
            )

        corefs = [tuple(pair) for pair in raw_result.get("corefs", [])]

        return CorefResult(bboxes=bboxes, corefs=corefs)

    def detect_coref_with_mapping(
        self,
        image: Image.Image | np.ndarray,
        mol_bboxes: list[dict[str, float]],
    ) -> dict[str, Any]:
        """检测共指关系，并将结果映射到输入的分子 bbox.

        Args:
            image: 输入图像
            mol_bboxes: MolDetv2 检测到的分子 bbox 列表
                格式: [{"x1": 100, "y1": 200, "x2": 300, "y2": 400}, ...]

        Returns:
            {
                "corefs": [{"mol_idx": 0, "idt_bbox": [x1,y1,x2,y2]}, ...],
                "idt_bboxes": [[x1,y1,x2,y2], ...]
            }
        """
        # 1. 运行 MolDetect coref 模型
        result = self.detect_coref(image, use_molscribe=False, use_ocr=False)

        if not result.corefs:
            return {"corefs": [], "idt_bboxes": []}

        # 2. 获取图像尺寸
        img_width, img_height = image.size

        # 3. 将输入的 mol_bboxes 转换为归一化坐标
        mol_bboxes_normalized = []
        for bbox in mol_bboxes:
            x1 = bbox.get("x1", 0) / img_width
            y1 = bbox.get("y1", 0) / img_height
            x2 = bbox.get("x2", 0) / img_width
            y2 = bbox.get("y2", 0) / img_height
            mol_bboxes_normalized.append((x1, y1, x2, y2))

        # 4. 提取 MolDetect coref 检测到的分子 bbox 和标识符 bbox
        mol_detect_mols = []  # MolDetect 检测到的分子 bbox
        idt_bboxes = []       # 标识符 bbox

        for i, bbox in enumerate(result.bboxes):
            if bbox.category_id == 1:  # 分子
                mol_detect_mols.append(bbox.bbox)
            elif bbox.category_id == 3:  # 标识符
                idt_bboxes.append(bbox.bbox)

        if not mol_detect_mols or not mol_bboxes_normalized:
            return {"corefs": [], "idt_bboxes": []}

        # 3. IoU 匹配：MolDetect 的分子 bbox ↔ MolDetv2 的分子 bbox
        # 构建映射：MolDetect mol_idx → MolDetv2 mol_idx
        mol_mapping = {}  # mol_detect_idx → molDetv2_idx
        used_moldetv2 = set()

        for md_idx, md_bbox in enumerate(mol_detect_mols):
            best_iou = 0.0
            best_moldetv2_idx = -1

            for m2_idx, m2_bbox in enumerate(mol_bboxes_normalized):
                if m2_idx in used_moldetv2:
                    continue

                # 计算 IoU
                iou = self._compute_iou(md_bbox, m2_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_moldetv2_idx = m2_idx

            if best_moldetv2_idx >= 0 and best_iou > 0.3:  # IoU 阈值
                mol_mapping[md_idx] = best_moldetv2_idx
                used_moldetv2.add(best_moldetv2_idx)

        # 4. 映射 corefs
        mapped_corefs = []
        for mol_idx, idt_idx in result.corefs:
            if mol_idx in mol_mapping:
                moldetv2_idx = mol_mapping[mol_idx]
                if idt_idx < len(idt_bboxes):
                    mapped_corefs.append({
                        "mol_idx": moldetv2_idx,
                        "idt_bbox": list(idt_bboxes[idt_idx]),
                    })

        return {
            "corefs": mapped_corefs,
            "idt_bboxes": [list(b) for b in idt_bboxes],
        }

    def _compute_iou(self, bbox1, bbox2) -> float:
        """计算两个 bbox 的 IoU.

        bbox1 格式: (x1, y1, x2, y2) 或 [x1, y1, x2, y2]
        bbox2 格式: dict {"x1": ..., "y1": ..., "x2": ..., "y2": ...}
        """
        # 转换 bbox1
        if isinstance(bbox1, dict):
            b1 = [bbox1.get('x1', 0), bbox1.get('y1', 0), bbox1.get('x2', 0), bbox1.get('y2', 0)]
        else:
            b1 = list(bbox1)

        # 转换 bbox2
        if isinstance(bbox2, dict):
            b2 = [bbox2.get('x1', 0), bbox2.get('y1', 0), bbox2.get('x2', 0), bbox2.get('y2', 0)]
        else:
            b2 = list(bbox2)

        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])

        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0


# ---- 单例访问 ----

_coref_instance: MolDetectCorefBackend | None = None


def get_coref() -> MolDetectCorefBackend | None:
    """获取全局 MolDetectCorefBackend 单例."""
    global _coref_instance
    if _coref_instance is None:
        if not is_gpu_available():
            logger.warning("MolDetect coref 需要 GPU，当前环境不可用")
            return None
        _coref_instance = MolDetectCorefBackend()
    return _coref_instance


def reset_coref() -> None:
    """重置 MolDetectCorefBackend 单例."""
    global _coref_instance
    _coref_instance = None


# ---- Backend convention wrappers ----

def load(device: str | None = None) -> None:
    """Lazy-load MolDetect coref backend."""
    global _coref_instance
    if _coref_instance is None:
        from mbforge.utils.helpers import is_gpu_available

        if not is_gpu_available():
            return
        _coref_instance = MolDetectCorefBackend(device=device)


def unload() -> None:
    """Release backend."""
    reset_coref()


def health() -> dict[str, str]:
    """Health check."""
    backend = get_coref()
    if backend is None:
        return {"status": "error", "error": "no GPU or model unavailable"}
    return {"status": "ready" if backend.is_available() else "loading"}
