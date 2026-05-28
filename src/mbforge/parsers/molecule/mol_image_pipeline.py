"""MolDetv2 + MolScribe 图像分子提取管线.

Week 1 (P0) 引擎接口层：
- MolDetv2DocDetector: 整页图像检测（Doc 版，输入 960×960）
- MolDetv2GeneralDetector: 裁剪区域复检（General 版，输入 640×640）
- MolScribeRecognizer: 图像 → SMILES
- MolImagePipeline: 组合上述组件的主管线

模型路径约定（可通过 ModelConfig 覆盖）：
- ~/.cache/mbforge/models/moldetv2-doc.pt (或 .onnx)
- ~/.cache/mbforge/models/moldetv2-general.pt
- ~/.cache/mbforge/models/molscribe/...
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from .coords import image_to_pdf_bbox, scale_from_page_size
from .extraction_result import ExtractionResult
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# ---- 可选依赖探测（懒加载，避免启动时导入重型库） ----


def _has_ultralytics() -> bool:
    """运行时检查 ultralytics 是否安装."""
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        return False


def _has_molscribe() -> bool:
    """运行时检查 molscribe 是否安装."""
    try:
        import molscribe  # noqa: F401
        return True
    except ImportError:
        return False

# ---------------------------------------------------------------------------
# 模型路径管理
# ---------------------------------------------------------------------------


def default_model_dir() -> Path:
    """返回默认模型缓存目录."""
    cache_dir = Path.home() / ".cache" / "mbforge" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# ---------------------------------------------------------------------------
# MolDetv2 检测器
# ---------------------------------------------------------------------------


class MolDetv2DocDetector:
    """MolDetv2-Doc：整页图像分子结构检测.

    输入：整页 PDF 渲染图像（建议 >= 300 DPI）
    输出：图像坐标系中的 bbox 列表 [(x1, y1, x2, y2, conf), ...]
    """

    MODEL_SUBDIR = "moldetv2-doc"
    DEFAULT_INPUT_SIZE = (960, 960)

    def __init__(
        self,
        model_path: Path | None = None,
        device: str | None = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> None:
        """初始化检测器.

        Args:
            model_path: 模型文件路径（.pt 或 .onnx）。若为 None，
                       则在默认目录下查找 moldetv2-doc.*
            device: 推理设备，None=自动，'cpu', 'cuda', 'cuda:0' 等
            conf_threshold: 置信度阈值
            iou_threshold: NMS IoU 阈值
        """
        if not _has_ultralytics():
            raise RuntimeError(
                "ultralytics 未安装，无法使用 MolDetv2 检测器。"
                "请运行：uv pip install 'mbforge[moldetv2_deps]'"
            )

        self.device = device or os.getenv("MBFORGE_DEVICE", "auto")
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

        self.model_path = self._resolve_model_path(model_path)
        self.model: Any | None = None
        self._load_model()

    def _resolve_model_path(self, model_path: Path | None) -> Path:
        """解析模型路径（支持实际文件名 moldet_v2_yolo11n_960_doc.*）."""
        if model_path is not None:
            return Path(model_path)

        model_dir = default_model_dir() / self.MODEL_SUBDIR
        # 先尝试精确匹配，再模糊匹配
        patterns = ["moldetv2-doc.*", "*doc*.pt", "*doc*.onnx"]
        for pat in patterns:
            candidates = list(model_dir.glob(pat))
            if candidates:
                # 优先 .pt，其次 .onnx
                for ext in (".pt", ".onnx", ".engine"):
                    for c in candidates:
                        if c.suffix.lower() == ext:
                            return c
                return candidates[0]
        return model_dir / "moldetv2-doc.pt"

    def _load_model(self) -> None:
        """加载 YOLO 模型."""
        if not self.model_path.exists():
            logger.warning(
                "MolDetv2-Doc 模型未找到：%s（图像分子检测功能不可用，不影响核心功能）",
                self.model_path,
            )
            self.model = None
            return

        model_name = getattr(self, "MODEL_SUBDIR", "moldetv2")
        logger.info("正在加载 %s 模型：%s", model_name, self.model_path)
        start = time.perf_counter()
        from ultralytics import YOLO

        self.model = YOLO(str(self.model_path))
        # 第一次 warmup
        _ = self.model.predict(
            np.zeros((*self.DEFAULT_INPUT_SIZE, 3), dtype=np.uint8),
            verbose=False,
            device=self.device if self.device != "auto" else None,
        )
        logger.info(
            "%s 加载完成，耗时 %.2fs", model_name, time.perf_counter() - start
        )

    def is_available(self) -> bool:
        """检测器是否可用（模型已加载）."""
        return self.model is not None

    def detect(
        self, image: Image.Image | np.ndarray
    ) -> list[tuple[float, float, float, float, float]]:
        """对整页图像进行分子结构检测.

        Args:
            image: PIL Image 或 numpy array (H, W, C)

        Returns:
            bbox 列表，每个元素为 (x1, y1, x2, y2, conf)，
            坐标系为**图像坐标系**（左上原点，像素单位）
        """
        if not self.is_available():
            raise RuntimeError(
                f"MolDetv2-Doc 模型未加载：{self.model_path} 不存在。"
            )

        # ultralytics 支持 PIL Image 和 np.ndarray
        results = self.model.predict(  # type: ignore[union-attr]
            image,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            verbose=False,
            device=self.device if self.device != "auto" else None,
        )
        if not results:
            return []

        boxes = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0].cpu().item())
                boxes.append((x1, y1, x2, y2, conf))
        return boxes


class MolDetv2GeneralDetector(MolDetv2DocDetector):
    """MolDetv2-General：裁剪区域复检/精修.

    输入：裁剪后的分子区域图像
    输出：更精确的 bbox（通常比 Doc 版更准）

    注意：MODEL_SUBDIR 和 DEFAULT_INPUT_SIZE 为类属性，
    通过 Python MRO 在父类 __init__ 中自动正确解析，无需实例覆盖。
    """

    MODEL_SUBDIR = "moldetv2-general"
    DEFAULT_INPUT_SIZE = (640, 640)

    def __init__(
        self,
        model_path: Path | None = None,
        device: str | None = None,
        conf_threshold: float = 0.3,
        iou_threshold: float = 0.45,
    ) -> None:
        super().__init__(model_path, device, conf_threshold, iou_threshold)

    def _resolve_model_path(self, model_path: Path | None) -> Path:
        """解析模型路径（支持实际文件名 moldet_v2_yolo11n_640_general.*）."""
        if model_path is not None:
            return Path(model_path)

        model_dir = default_model_dir() / self.MODEL_SUBDIR
        patterns = ["moldetv2-general.*", "*general*.pt", "*general*.onnx"]
        for pat in patterns:
            candidates = list(model_dir.glob(pat))
            if candidates:
                for ext in (".pt", ".onnx", ".engine"):
                    for c in candidates:
                        if c.suffix.lower() == ext:
                            return c
                return candidates[0]
        return model_dir / "moldetv2-general.pt"

    def detect(
        self, image: Image.Image | np.ndarray
    ) -> list[tuple[float, float, float, float, float]]:
        """对裁剪区域进行分子结构检测.

        返回图像坐标系中的 bbox。
        """
        return super().detect(image)


# ---------------------------------------------------------------------------
# MolScribe 识别器
# ---------------------------------------------------------------------------


class MolScribeRecognizer:
    """MolScribe：化学结构图像 → SMILES.

    支持两种后端模式：
    - "molscribe": 官方 molscribe 包（pip install molscribe）
    - "transformers": Hugging Face transformers pipeline（备用）
    """

    def __init__(
        self,
        model_path: Path | None = None,
        device: str | None = None,
        backend: Literal["molscribe", "transformers", "auto"] = "auto",
    ) -> None:
        """初始化识别器.

        Args:
            model_path: 模型路径或 Hugging Face 模型 ID。
                       None 时使用默认路径 ~/.cache/mbforge/models/molscribe/
            device: 推理设备
            backend: 后端模式，auto 时优先 molscribe，其次 transformers
        """
        self.device = device or os.getenv("MBFORGE_DEVICE", "auto")
        self.backend = backend
        self.model_path = model_path
        self._model: object | None = None
        self._backend_name: str | None = None
        self._load_backend()

    def _load_backend(self) -> None:
        """尝试加载可用的后端."""
        if self.backend in ("auto", "molscribe") and _has_molscribe():
            self._load_molscribe()
            if self._model is not None:
                self._backend_name = "molscribe"
                return

        if self.backend in ("auto", "transformers"):
            self._load_transformers()
            if self._model is not None:
                self._backend_name = "transformers"
                return

        logger.warning(
            "MolScribe 后端不可用（SMILES 识别功能不可用，不影响核心功能）"
        )

    def _load_molscribe(self) -> None:
        """加载官方 molscribe 后端."""
        try:
            # molscribe 的典型初始化：
            # model = molscribe.MolScribe.from_pretrained(model_path)
            # 但 API 可能因版本而异，这里做通用封装
            if self.model_path is None:
                model_dir = default_model_dir() / "molscribe"
                self.model_path = model_dir
            else:
                self.model_path = Path(self.model_path)

            logger.info(
                "尝试加载 MolScribe (molscribe 后端)：%s", self.model_path
            )
            # 延迟加载，避免 ImportError 在类定义时触发
            import molscribe as ms

            self._model = ms.MolScribe.from_pretrained(str(self.model_path))
            if hasattr(self._model, "to") and self.device != "auto":

                dev = "cuda" if "cuda" in self.device else self.device
                self._model = self._model.to(dev)
            logger.info("MolScribe (molscribe 后端) 加载成功")
        except Exception as exc:
            logger.warning("MolScribe molscribe 后端加载失败：%s", exc)
            self._model = None

    def _load_transformers(self) -> None:
        """加载 transformers 后端（备用）."""
        try:
            # 兼容新旧版本 transformers
            # transformers < 5.x: AutoModelForVision2Seq
            # transformers >= 5.x: AutoModelForImageTextToText
            try:
                from transformers import AutoModelForVision2Seq, AutoProcessor

                ModelClass = AutoModelForVision2Seq
            except ImportError:
                from transformers import AutoModelForImageTextToText, AutoProcessor

                ModelClass = AutoModelForImageTextToText

            model_id = (
                str(self.model_path)
                if self.model_path
                else "yujieq/MolScribe"
            )
            logger.info(
                "尝试加载 MolScribe (transformers 后端)：%s", model_id
            )
            self._processor = AutoProcessor.from_pretrained(
                model_id, local_files_only=True
            )
            self._model = ModelClass.from_pretrained(
                model_id, local_files_only=True
            )
            if self.device != "auto":
                dev = "cuda" if "cuda" in self.device else self.device
                self._model = self._model.to(dev)
            logger.info("MolScribe (transformers 后端) 加载成功")
        except Exception as exc:
            logger.warning("MolScribe transformers 后端加载失败：%s", exc)
            self._model = None
            self._processor = None

    def is_available(self) -> bool:
        """识别器是否可用."""
        return self._model is not None

    def predict(
        self, image: Image.Image | np.ndarray
    ) -> tuple[str, float]:
        """将分子图像转换为 SMILES.

        Args:
            image: PIL Image 或 numpy array

        Returns:
            (smiles, confidence)
        """
        if not self.is_available():
            raise RuntimeError(
                "MolScribe 不可用。请安装依赖并下载模型。"
            )

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        if self._backend_name == "molscribe":
            return self._predict_molscribe(image)
        elif self._backend_name == "transformers":
            return self._predict_transformers(image)
        else:
            raise RuntimeError(f"未知后端：{self._backend_name}")

    def _predict_molscribe(self, image: Image.Image) -> tuple[str, float]:
        """使用 molscribe 后端预测."""
        # molscribe 的典型 API：
        # results = model.predict_images([image], return_atoms_bonds=True)
        # smiles = results[0]["smiles"]
        # conf = results[0].get("confidence", 0.5)
        try:
            results = self._model.predict_images([image])  # type: ignore[union-attr]
            result = results[0]
            if isinstance(result, dict):
                smiles = result.get("smiles", "")
                conf = result.get("confidence", 0.5)
            else:
                smiles = str(result)
                conf = 0.5
            return smiles, float(conf)
        except Exception as exc:
            logger.warning("MolScribe 预测失败：%s", exc)
            return "", 0.0

    def _predict_transformers(self, image: Image.Image) -> tuple[str, float]:
        """使用 transformers 后端预测."""
        try:
            import torch

            inputs = self._processor(images=image, return_tensors="pt")  # type: ignore[union-attr]
            if self.device != "auto":
                dev = "cuda" if "cuda" in self.device else self.device
                inputs = {k: v.to(dev) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(**inputs)  # type: ignore[union-attr]
            smiles = self._processor.batch_decode(  # type: ignore[union-attr]
                outputs, skip_special_tokens=True
            )[0]
            # transformers 后端没有原生置信度，用 heuristic
            conf = 0.7 if smiles else 0.0
            return smiles, conf
        except Exception as exc:
            logger.warning("MolScribe (transformers) 预测失败：%s", exc)
            return "", 0.0


# ---------------------------------------------------------------------------
# 主管线：组合检测 + 识别
# ---------------------------------------------------------------------------


class MolImagePipeline:
    """MolDetv2 + MolScribe 图像分子提取主管线.

    使用模式：
        pipeline = MolImagePipeline()
        # 检测整页
        results = pipeline.extract_page(image, page_idx=0, page_w=595, page_h=842)
        # 复检单个区域
        result = pipeline.extract_region(crop_image, page_idx=0)
    """

    def __init__(
        self,
        doc_detector: MolDetv2DocDetector | None = None,
        general_detector: MolDetv2GeneralDetector | None = None,
        recognizer: MolScribeRecognizer | None = None,
        device: str | None = None,
        crop_cache_dir: Path | None = None,
    ) -> None:
        """初始化管线.

        Args:
            doc_detector: Doc 版检测器，None 时自动创建
            general_detector: General 版检测器，None 时自动创建
            recognizer: SMILES 识别器，None 时自动创建
            device: 统一设备设置
            crop_cache_dir: 裁剪图像缓存目录
        """
        self.device = device or os.getenv("MBFORGE_DEVICE", "auto")
        self.crop_cache_dir = crop_cache_dir

        self.doc_detector = doc_detector or MolDetv2DocDetector(
            device=self.device
        )
        self.general_detector = general_detector or MolDetv2GeneralDetector(
            device=self.device
        )
        self.recognizer = recognizer or MolScribeRecognizer(
            device=self.device
        )

    def is_available(self) -> bool:
        """管线核心组件是否可用（至少检测器可用）."""
        return self.doc_detector.is_available()

    def extract_page(
        self,
        image: Image.Image | np.ndarray,
        page_idx: int,
        page_w_pts: float,
        page_h_pts: float,
        image_w: int,
        image_h: int,
        dpi: float = 300.0,
        cache_prefix: str | None = None,
    ) -> list[ExtractionResult]:
        """对整页 PDF 渲染图像进行分子提取.

        Args:
            image: 整页渲染图像
            page_idx: PDF 页码（从 0 开始）
            page_w_pts: PDF 页面宽度（点单位）
            page_h_pts: PDF 页面高度（点单位）
            image_w: 渲染图像宽度（像素）
            image_h: 渲染图像高度（像素）
            dpi: 渲染 DPI
            cache_prefix: 裁剪图像缓存前缀

        Returns:
            ExtractionResult 列表（status=pending）
        """
        if not self.doc_detector.is_available():
            logger.warning("MolDetv2-Doc 不可用，跳过整页检测")
            return []

        # 1. 检测
        img_boxes = self.doc_detector.detect(image)
        if not img_boxes:
            return []

        # 2. 准备裁剪缓存目录
        if self.crop_cache_dir is not None:
            self.crop_cache_dir.mkdir(parents=True, exist_ok=True)

        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        if isinstance(image, np.ndarray):
            pil_image = Image.fromarray(image)
        else:
            pil_image = image

        results: list[ExtractionResult] = []
        for idx, (x1, y1, x2, y2, det_conf) in enumerate(img_boxes):
            # 2.1 裁剪分子区域
            x1_int, y1_int = max(0, int(x1)), max(0, int(y1))
            x2_int, y2_int = min(image_w, int(x2)), min(image_h, int(y2))
            crop = pil_image.crop((x1_int, y1_int, x2_int, y2_int))

            # 2.2 保存裁剪图像
            mol_img_path: Path | None = None
            if self.crop_cache_dir is not None:
                prefix = cache_prefix or f"page_{page_idx:04d}"
                mol_img_path = (
                    self.crop_cache_dir
                    / f"{prefix}_mol_{idx:03d}.png"
                )
                crop.save(mol_img_path)

            # 2.3 坐标转换：图像坐标 → PDF 坐标
            bbox_pdf = image_to_pdf_bbox(
                (x1, y1, x2, y2),
                page_h_pts,
                scale,
            )

            # 2.4 识别 SMILES（如果识别器可用）
            smiles = ""
            scribe_conf = 0.0
            if self.recognizer.is_available():
                try:
                    smiles, scribe_conf = self.recognizer.predict(crop)
                except Exception as exc:
                    logger.warning(
                        "SMILES 识别失败 (page=%d, bbox=%s): %s",
                        page_idx, bbox_pdf, exc,
                    )

            results.append(
                ExtractionResult(
                    smiles=smiles,
                    source="image",
                    moldet_conf=det_conf,
                    scribe_conf=scribe_conf,
                    bbox_pdf=bbox_pdf,
                    page_idx=page_idx,
                    mol_img_path=mol_img_path,
                    status="pending",
                )
            )

        logger.info(
            "页面 %d 检测到 %d 个分子区域，识别 %d 个 SMILES",
            page_idx, len(img_boxes), sum(1 for r in results if r.smiles),
        )
        return results

    def extract_region(
        self,
        crop_image: Image.Image | np.ndarray,
        page_idx: int,
        bbox_pdf: tuple[float, float, float, float] | None = None,
    ) -> ExtractionResult:
        """对已知裁剪区域进行复检精修.

        Args:
            crop_image: 裁剪后的分子区域图像
            page_idx: 所属 PDF 页码
            bbox_pdf: PDF 坐标系中的 bbox（可选）

        Returns:
            ExtractionResult
        """
        if isinstance(crop_image, np.ndarray):
            crop_image = Image.fromarray(crop_image)

        # 1. General 版复检（可选，如果不可用则跳过）
        det_conf = 0.0
        if self.general_detector.is_available():
            try:
                boxes = self.general_detector.detect(crop_image)
                if boxes:
                    # 取置信度最高的
                    boxes.sort(key=lambda b: b[4], reverse=True)
                    _, _, _, _, det_conf = boxes[0]
            except Exception as exc:
                logger.warning("General 版复检失败：%s", exc)

        # 2. 识别 SMILES
        smiles = ""
        scribe_conf = 0.0
        if self.recognizer.is_available():
            try:
                smiles, scribe_conf = self.recognizer.predict(crop_image)
            except Exception as exc:
                logger.warning("复检区域 SMILES 识别失败：%s", exc)

        return ExtractionResult(
            smiles=smiles,
            source="image",
            moldet_conf=det_conf,
            scribe_conf=scribe_conf,
            bbox_pdf=bbox_pdf,
            page_idx=page_idx,
            status="pending",
        )

    def extract_from_manual_crop(
        self,
        page_image: Image.Image | np.ndarray,
        crop_bbox_img: tuple[int, int, int, int],
        page_idx: int,
        page_w_pts: float,
        page_h_pts: float,
        image_w: int,
        image_h: int,
    ) -> ExtractionResult:
        """处理用户手动框选的分子区域.

        Args:
            page_image: 整页图像
            crop_bbox_img: 图像坐标系中的框选 bbox (x1, y1, x2, y2, 像素)
            page_idx: PDF 页码
            page_w_pts, page_h_pts: PDF 页面尺寸
            image_w, image_h: 渲染图像尺寸

        Returns:
            ExtractionResult
        """
        if isinstance(page_image, np.ndarray):
            page_image = Image.fromarray(page_image)

        x1, y1, x2, y2 = crop_bbox_img
        crop = page_image.crop((x1, y1, x2, y2))

        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        bbox_pdf = image_to_pdf_bbox(
            (float(x1), float(y1), float(x2), float(y2)),
            page_h_pts,
            scale,
        )

        return self.extract_region(crop, page_idx, bbox_pdf)
