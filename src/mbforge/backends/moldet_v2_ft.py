"""MolDetv2-FT: 同时检测分子结构和 coref 标识符的微调模型。

与 MolDetv2DocDetector 不同，该模型一次推理同时输出：
- 分子结构 bbox (category_id=1)
- Coref 标识符 bbox (category_id=3)

输入：整页 PDF 渲染图像
输出：CorefResult（包含 bboxes 和 corefs 配对信息）
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from mbforge.utils.config import load_global_config
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# 延迟导入 ultralytics（避免未安装时报错）
_ultralytics: Any | None = None


def default_model_dir() -> Path:
    """返回模型缓存目录(使用统一常量).

    与 ``backends/moldet.py`` 旧版同名函数语义一致,挪到此处是因为
    moldet.py 已被瘦壳化(只保留兼容入口),新代码应直接走 FT 后端。
    """
    from mbforge.utils.paths import get_model_cache_dir

    cache_dir = Path(get_model_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _has_ultralytics() -> bool:
    global _ultralytics
    if _ultralytics is None:
        try:
            import ultralytics

            _ultralytics = ultralytics
            return True
        except ImportError:
            return False
    return True


class MolDetv2FTDetector:
    """MolDetv2-FT：分子 + Coref 联合检测器。

    输入：整页 PDF 渲染图像（建议 >= 300 DPI）
    输出：CorefResult，包含：
        - bboxes: CorefBbox 列表，每个包含 category_id (1=分子, 3=标识符) 和归一化 bbox
        - corefs: [(mol_idx, idt_idx), ...] 配对列表
    """

    # 默认权重文件名（相对于模型目录）
    DEFAULT_SUBPATH = "last.pt"

    def __init__(
        self,
        model_path: Path | None = None,
        device: str | None = None,
        conf_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        mol_conf_threshold: float = 0.3,
        idt_conf_threshold: float = 0.3,
    ) -> None:
        """初始化检测器。

        Args:
            model_path: 模型权重路径。None 时通过 ResourceManager 解析
            device: 推理设备，None=自动
            conf_threshold: 通用置信度阈值
            iou_threshold: NMS IoU 阈值
            mol_conf_threshold: 分子检测置信度阈值
            idt_conf_threshold: 标识符检测置信度阈值
        """
        if not _has_ultralytics():
            raise RuntimeError(
                "ultralytics 未安装，无法使用 MolDetv2-FT 检测器。"
                "请运行：uv pip install ultralytics"
            )

        self.device = device or load_global_config().moldet.device
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.mol_conf_threshold = mol_conf_threshold
        self.idt_conf_threshold = idt_conf_threshold

        self.model_path = model_path or self._resolve_model_path()
        self._load_model()

    def _resolve_model_path(self) -> Path:
        """通过 ResourceManager 解析模型路径。"""
        from mbforge.core.resource_manager import ResourceManager

        resolved = ResourceManager.resolve_model_for_backend(
            "moldet", subpath=self.DEFAULT_SUBPATH
        )
        if resolved is not None and resolved.exists():
            return resolved

        # 兜底：使用默认模型目录
        return default_model_dir() / "moldet" / self.DEFAULT_SUBPATH

    def _load_model(self) -> None:
        """加载 YOLO 模型。"""
        if not self.model_path.exists():
            logger.warning(
                "MolDetv2-FT 模型未找到：%s（联合检测功能不可用）",
                self.model_path,
            )
            self.model = None
            return

        logger.info("正在加载 MolDetv2-FT 模型：%s", self.model_path)
        start = time.perf_counter()
        from ultralytics import YOLO

        self.model = YOLO(str(self.model_path))

        # Warmup
        _ = self.model.predict(
            np.zeros((960, 960, 3), dtype=np.uint8),
            verbose=False,
            device=self.device if self.device != "auto" else None,
        )
        logger.info("MolDetv2-FT 加载完成，耗时 %.2fs", time.perf_counter() - start)

    def is_available(self) -> bool:
        """检测器是否可用。"""
        return self.model is not None

    def detect(
        self, image: Image.Image | np.ndarray
    ) -> list[tuple[float, float, float, float, float, int]]:
        """对整页图像进行分子 + 标识符联合检测。

        Args:
            image: PIL Image 或 numpy array (H, W, C)

        Returns:
            bbox 列表，每个元素为 (x1, y1, x2, y2, conf, category_id)，
            坐标系为**图像坐标系**（左上原点，像素单位）
            category_id: 1=分子, 3=标识符
        """
        if not self.is_available():
            raise RuntimeError(f"MolDetv2-FT 模型未加载：{self.model_path} 不存在。")

        results = self.model.predict(
            image,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            verbose=False,
            device=self.device if self.device != "auto" else None,
        )
        if not results:
            return []

        # 计算图像面积用于尺寸过滤
        if hasattr(image, "width") and hasattr(image, "height"):
            img_area = image.width * image.height
        else:
            img_area = image.shape[0] * image.shape[1]

        boxes = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0].cpu().item())
                cls = int(box.cls[0].cpu().item())

                # 类别映射：模型输出 0=分子, 1=标识符 → 内部 1=分子, 3=标识符
                category_id = 1 if cls == 0 else 3

                # 尺寸过滤
                w, h = x2 - x1, y2 - y1
                box_area = w * h
                area_ratio = box_area / img_area if img_area > 0 else 0

                # 过滤太小或太大的框
                if area_ratio < 0.0001:
                    continue
                if area_ratio > 0.5:
                    continue
                if w > 0 and h > 0:
                    ratio = max(w / h, h / w)
                    if ratio > 10.0:
                        continue

                boxes.append((x1, y1, x2, y2, conf, category_id))

        return boxes

    def detect_with_coref(
        self, image: Image.Image | np.ndarray
    ) -> tuple[
        list[tuple[float, float, float, float, float]],
        list[tuple[float, float, float, float, float]],
    ]:
        """检测并分离分子和标识符 bbox。

        Args:
            image: PIL Image 或 numpy array

        Returns:
            (mol_boxes, idt_boxes)
            mol_boxes: [(x1, y1, x2, y2, conf), ...] 分子 bbox
            idt_boxes: [(x1, y1, x2, y2, conf), ...] 标识符 bbox
        """
        all_boxes = self.detect(image)

        mol_boxes = []
        idt_boxes = []

        for x1, y1, x2, y2, conf, cat_id in all_boxes:
            if cat_id == 1 and conf >= self.mol_conf_threshold:
                mol_boxes.append((x1, y1, x2, y2, conf))
            elif cat_id == 3 and conf >= self.idt_conf_threshold:
                idt_boxes.append((x1, y1, x2, y2, conf))

        return mol_boxes, idt_boxes


# ---- 单例便捷访问 ----

_detector_singleton: MolDetv2FTDetector | None = None


def get_moldet_ft() -> MolDetv2FTDetector:
    """获取全局 MolDetv2-FT 检测器单例。"""
    global _detector_singleton
    if _detector_singleton is None:
        _detector_singleton = MolDetv2FTDetector()
    return _detector_singleton
