"""MolDetect Coref 后端：分子-标号共指消解.

基于 pix2seq 模型检测图像中的分子和标识符，建立"哪个标号指向哪个分子"的关系。
模型来源：polyai/MolDetect（ModelScope），权重文件 coref_best.ckpt。
pix2seq / tokenizer / dataset vendor 自 thomas0809/RxnScribe（MIT）→ `mbforge.parsers.molecule.molcoref`。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from mbforge.utils.helpers import is_gpu_available
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


# ---- 数据类型 ----

@dataclass
class CorefBbox:
    category_id: int                # 1=分子, 3=标识符
    bbox: tuple[float, float, float, float]
    smiles: str | None = None
    text: str | None = None
    score: float = 0.0


@dataclass
class CorefResult:
    bboxes: list[CorefBbox]
    corefs: list[tuple[int, int]]    # [(mol_idx, idt_idx), ...]


# ---- 模型加载 ----

_PIX2SEQ_ARGS = {
    "backbone": "resnet50",
    "dilation": False,
    "position_embedding": "sine",
    "enc_layers": 6,
    "dec_layers": 6,
    "dim_feedforward": 1024,
    "hidden_dim": 256,
    "dropout": 0.1,
    "nheads": 8,
    "pre_norm": False,
    "format": "bbox",
    "input_size": 1333,
    "pix2seq": True,
    "pix2seq_ckpt": None,
    "pred_eos": True,
    "is_coco": False,
    "use_hf_transformer": False,    # Checkpoint 使用原生 Transformer 格式
    "coord_bins": 2000,
    "sep_xy": False,
}


class MolDetectCorefBackend:

    def __init__(self, model_path: Path | None = None, device: str | None = None) -> None:
        self.device = device or os.getenv("MBFORGE_DEVICE", "auto")
        self.model_path = _resolve_model_path(model_path)
        self._model: Any = None
        self._tokenizer: Any = None
        self._transform: Any = None
        self._device: Any = None
        # molscribe / ocr 惰性单例
        self._molscribe: Any = None
        self._ocr: Any = None

        if self.model_path is None:
            logger.warning(
                "MolDetect coref 模型未找到，共指消解功能不可用。"
                "请下载：polyai/MolDetect → coref_best.ckpt → ~/mbforge/models/polyai/MolDetect/"
            )
            return

        self._load_model()

    def _load_model(self) -> None:
        try:
            import torch
        except ImportError:
            logger.warning("torch 未安装，MolDetect coref 不用")
            return

        logger.info("正在加载 MolDetect coref 模型：%s", self.model_path)
        start = time.perf_counter()

        # ResourceManager snapshot 类型按契约返回目录；找到实际权重文件
        ckpt_path = self.model_path
        if ckpt_path.is_dir():
            # 优先 `best.ckpt`（多类别，Mol+Txt+Idt+Sup），其次 `coref_best.ckpt`（仅 Mol，coref 退化版）
            for name in ("best.ckpt", "best_hf.ckpt", "coref_best.ckpt"):
                candidate = ckpt_path / name
                if candidate.exists():
                    ckpt_path = candidate
                    break
            else:
                ckpts = sorted(ckpt_path.glob("*.ckpt"))
                if not ckpts:
                    raise FileNotFoundError(f"未在 {ckpt_path} 找到 .ckpt 权重文件")
                ckpt_path = ckpts[0]
            logger.info("MolDetect coref checkpoint：%s", ckpt_path)

        device = (
            torch.device("cuda" if torch.cuda.is_available() else "cpu")
            if self.device == "auto"
            else torch.device(self.device)
        )

        # Monkey-patch torchvision.models.resnet50：避免下载预训练权重
        # coref_best.ckpt 已含完整 backbone。
        import torchvision.models
        _orig_resnet50 = torchvision.models.resnet50

        def _resnet50_no_pretrained(**kwargs):
            kwargs["pretrained"] = False
            return _orig_resnet50(**kwargs)

        torchvision.models.resnet50 = _resnet50_no_pretrained
        try:
            from mbforge.parsers.molecule.molcoref.dataset import make_transforms
            from mbforge.parsers.molecule.molcoref.pix2seq import build_pix2seq_model
            from mbforge.parsers.molecule.molcoref.tokenizer import get_tokenizer

            args = _SimpleNamespace(**_PIX2SEQ_ARGS)
            tokenizer = get_tokenizer(args)
            self._tokenizer = tokenizer[args.format]

            states = torch.load(str(ckpt_path), map_location=torch.device("cpu"))
            state_dict = states.get("state_dict", states)
            # 移除 'model.' 前缀（checkpoint 与模型 key 格式差异）
            cleaned = {(k[6:] if k.startswith("model.") else k): v for k, v in state_dict.items()}

            self._model = build_pix2seq_model(args, self._tokenizer)
            missing, unexpected = self._model.load_state_dict(cleaned, strict=False)
            if missing:
                logger.warning("Missing keys: %s", missing[:5])
            if unexpected:
                logger.warning("Unexpected keys: %s", unexpected[:5])
            self._model.to(device).eval()
        finally:
            torchvision.models.resnet50 = _orig_resnet50

        self._transform = make_transforms("test", augment=False, debug=False)
        self._device = device
        logger.info("MolDetect coref 模型加载完成，耗时 %.2fs", time.perf_counter() - start)

    def is_available(self) -> bool:
        return self._model is not None

    # ---- 推理 ----

    def _get_molscribe(self) -> Any:
        if self._molscribe is not None:
            return self._molscribe
        try:
            from . import molscribe as molscribe_backend
            dev = "cuda" if self.device == "auto" and is_gpu_available() else self.device
            molscribe_backend.load(device=dev)
            if molscribe_backend._MODEL is not None:
                # MolScribe 暴露的 predict(image) 不直接对应 rxnscribe 的 predict_images
                # — 包装一个最小适配器
                def _adapter(_self, images, **_kw):
                    return [{"smiles": molscribe_backend.predict(img).esmiles, "molfile": ""}
                            for img in images]
                self._molscribe = type("MolScribeAdapter", (), {"predict_images": _adapter})()
                logger.info("MolScribe loaded for coref backend")
        except Exception as exc:
            logger.warning("MolScribe load failed for coref: %s", exc)
        return self._molscribe

    def _get_ocr(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        try:
            self._ocr = _RapidOCRAdapter()
            logger.info("RapidOCR loaded for coref backend")
        except Exception as exc:
            logger.warning("RapidOCR load failed: %s", exc)
        return self._ocr

    def detect_coref(
        self,
        image: Image.Image | np.ndarray,
        use_molscribe: bool = True,
        use_ocr: bool = True,
        page_width: float = 595.0,
        page_height: float = 842.0,
    ) -> CorefResult:
        """检测分子和标识符的共指关系。

        Args:
            image: 输入图像
            use_molscribe: 是否使用 MolScribe 识别 SMILES
            use_ocr: 是否使用 EasyOCR 识别标识符文本
            page_width: PDF 页面宽度（点单位），用于归一化距离计算
            page_height: PDF 页面高度（点单位），用于归一化距离计算
        """
        if not self.is_available():
            raise RuntimeError("MolDetect coref 后端不可用")

        from mbforge.parsers.molecule.molcoref.data import postprocess_coref_results

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        try:
            import torch
            with torch.no_grad():
                img_tensor, ref = self._transform(image)
                pred_seqs, pred_scores = self._model(
                    img_tensor.unsqueeze(0).to(self._device),
                    max_len=self._tokenizer.max_len,
                )
                bboxes = self._tokenizer.sequence_to_data(
                    pred_seqs[0].tolist(),
                    pred_scores[0].tolist(),
                    scale=ref["scale"],
                )
            # 传入页面尺寸用于增强的配对算法
            raw = postprocess_coref_results(
                bboxes,
                image=image,
                molscribe=self._get_molscribe() if use_molscribe else None,
                ocr=self._get_ocr() if use_ocr else None,
                page_width=page_width,
                page_height=page_height,
            )
        except Exception as exc:
            logger.error("MolDetect coref 推理失败：%s", exc)
            raise RuntimeError(f"Coref detection failed: {exc}") from exc

        return CorefResult(
            bboxes=[
                CorefBbox(
                    category_id=b["category_id"],
                    bbox=tuple(b["bbox"]),
                    smiles=b.get("smiles"),
                    text=b.get("text"),
                    score=b["score"],
                )
                for b in raw["bboxes"]
            ],
            corefs=[tuple(p) for p in raw["corefs"]],
        )

    def detect_coref_with_mapping(
        self,
        image: Image.Image | np.ndarray,
        mol_bboxes: list[dict[str, float]],
    ) -> dict[str, Any]:
        """检测 coref 并把 MolDetect 检测的分子 bbox 映射到 MolDetv2 分子 bbox.

        Returns: {"corefs": [{"mol_idx", "idt_bbox"}, ...], "idt_bboxes": [[x1,y1,x2,y2], ...]}
        """
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        result = self.detect_coref(image, use_molscribe=False, use_ocr=False)
        if not result.corefs:
            return {"corefs": [], "idt_bboxes": []}

        # 把 MolDetv2 输入 bbox 归一化到 [0, 1]
        w, h = image.size
        norm = [
            (b.get("x1", 0) / w, b.get("y1", 0) / h, b.get("x2", 0) / w, b.get("y2", 0) / h)
            for b in mol_bboxes
        ]

        # 拆出 MolDetect 输出的分子 / 标识符 bbox（坐标已是归一化的 [0, 1]）
        md_mols = [bb.bbox for bb in result.bboxes if bb.category_id == 1]
        idt_bboxes = [bb.bbox for bb in result.bboxes if bb.category_id == 3]
        if not md_mols or not norm:
            return {"corefs": [], "idt_bboxes": [list(b) for b in idt_bboxes]}

        # IoU 匹配：每个 MolDetect mol 找最相似的 MolDetv2 mol（阈值 0.3）
        md_to_m2 = _match_by_iou(md_mols, norm, iou_threshold=0.3)

        return {
            "corefs": [
                {"mol_idx": md_to_m2[md_idx], "idt_bbox": list(idt_bboxes[idt_idx])}
                for md_idx, idt_idx in result.corefs
                if md_idx in md_to_m2 and idt_idx < len(idt_bboxes)
            ],
            "idt_bboxes": [list(b) for b in idt_bboxes],
        }


# ---- 工具函数 ----

def _resolve_model_path(model_path: Path | None = None) -> Path | None:
    """解析模型文件路径 — 统一走 ResourceManager。"""
    if model_path is not None:
        p = Path(model_path)
        if p.exists():
            return p
        logger.warning("指定的模型路径不存在：%s", model_path)
        return None
    try:
        from mbforge.core.resource_manager import ResourceManager
        resolved = ResourceManager.resolve_model_for_backend("moldet_coref")
        if resolved is not None:
            return resolved
    except ImportError:
        pass
    env_path = os.getenv("MBFORGE_MOLDETECT_COREF_MODEL")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    return None


def _match_by_iou(
    query_boxes: list[tuple[float, float, float, float]],
    target_boxes: list[tuple[float, float, float, float]],
    iou_threshold: float = 0.3,
) -> dict[int, int]:
    """贪心 IoU 匹配：每个 query 找最相似的未占用 target。

    Returns: {query_idx: target_idx}
    """
    used: set[int] = set()
    matches: dict[int, int] = {}
    for q_i, q in enumerate(query_boxes):
        best_iou, best_t = 0.0, -1
        for t_i, t in enumerate(target_boxes):
            if t_i in used:
                continue
            iou = _iou(q, t)
            if iou > best_iou:
                best_iou, best_t = iou, t_i
        if best_t >= 0 and best_iou > iou_threshold:
            matches[q_i] = best_t
            used.add(best_t)
    return matches


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class _SimpleNamespace:
    """Namespace 替代 Args 类的最小替代品（避免每实例 23 行属性赋值）。"""
    __slots__ = ("__dict__",)

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _RapidOCRAdapter:
    """适配 RapidOCR 3.x 输出到 EasyOCR 兼容的 `readtext(image, detail=0) -> list[str]` 接口。

    `data.py::postprocess_coref_results:89` 调 `ocr.readtext(crop, detail=0)`。
    RapidOCR 3.x API 是 `engine(image) -> RapidOCROutput`，属性 `.txts/.scores/.boxes`。
    使用 PP-OCRv6 en tiny（最小 v6 模型，首启自动下载）。
    """

    def __init__(self) -> None:
        from rapidocr import RapidOCR, EngineType, LangDet, LangRec, ModelType, OCRVersion
        self._engine = RapidOCR(
            params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.EN,
                "Det.model_type": ModelType.MEDIUM,
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Det.use_dml": True,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.EN,
                "Rec.model_type": ModelType.MEDIUM,
                "Rec.ocr_version": OCRVersion.PPOCRV6,
                "Rec.use_dml": True,
            }
        )

    def readtext(self, image: Any, detail: int = 0) -> list[str]:
        import numpy as np
        if hasattr(image, "convert"):
            arr = np.array(image.convert("RGB"))
        else:
            arr = image
        out = self._engine(arr)
        if out is None or not getattr(out, "txts", None):
            return []
        txts = [t for t in out.txts if t]
        if detail == 0:
            return txts
        return list(zip(out.boxes.tolist(), txts, list(out.scores)))


# ---- 单例访问（按 molscribe / moldet 同样约定） ----

_coref_instance: MolDetectCorefBackend | None = None


def get_coref() -> MolDetectCorefBackend | None:
    """获取全局 MolDetectCorefBackend 单例。"""
    global _coref_instance
    if _coref_instance is None:
        if not is_gpu_available():
            logger.warning("MolDetect coref 需要 GPU，当前环境不可用")
            return None
        _coref_instance = MolDetectCorefBackend()
    return _coref_instance


def load(device: str | None = None) -> None:
    """Lazy-load（prewarm 入口）。CPU 环境静默返回，不报错。"""
    global _coref_instance
    if _coref_instance is not None:
        return
    if not is_gpu_available():
        return
    _coref_instance = MolDetectCorefBackend(device=device)
