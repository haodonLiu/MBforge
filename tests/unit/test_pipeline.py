"""PDF 管线集成测试 — 验证解析、分类、提取链路."""

import tempfile
from pathlib import Path

import pytest

from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


class TestDocumentClassification:
    """测试文档分类逻辑."""

    def test_classify_text_document(self):
        """验证纯文本文档分类."""
        from mbforge.parsers.molecule.extraction_result import ExtractionResult
        result = ExtractionResult(
            esmiles="CCO",
            source="text",
            moldet_conf=0.0,
            scribe_conf=0.0,
            page_idx=0,
            status="pending",
        )
        assert result.esmiles == "CCO"
        assert result.source == "text"
        assert result.status == "pending"

    def test_extraction_result_serialization(self):
        """验证 ExtractionResult 序列化/反序列化."""
        from mbforge.parsers.molecule.extraction_result import ExtractionResult
        original = ExtractionResult(
            esmiles="CC(=O)Oc1ccccc1C(=O)O",
            source="image",
            moldet_conf=0.95,
            scribe_conf=0.88,
            page_idx=3,
            status="confirmed",
        )
        d = original.to_dict()
        restored = ExtractionResult.from_dict(d)
        assert restored.esmiles == original.esmiles
        assert restored.source == original.source
        assert restored.moldet_conf == original.moldet_conf
        assert restored.page_idx == original.page_idx


class TestCoordinateTransform:
    """测试坐标转换."""

    def test_image_to_pdf_bbox(self):
        """验证图像坐标到 PDF 坐标转换."""
        from mbforge.parsers.molecule.coords import image_to_pdf_bbox
        # 图像坐标 (100, 200, 300, 400), 页面高度 842pt
        pdf_bbox = image_to_pdf_bbox((100, 200, 300, 400), 842.0, 1.0)
        assert len(pdf_bbox) == 4
        x1, y1, x2, y2 = pdf_bbox
        # PDF 坐标系 Y 轴反转
        assert y1 < y2  # PDF 下边 < 上边

    def test_scale_from_page_size(self):
        """验证缩放因子计算."""
        from mbforge.parsers.molecule.coords import scale_from_page_size
        scale = scale_from_page_size(595.0, 842.0, 1190, 1684)
        # image_w/page_w = 1190/595 = 2.0
        assert abs(scale - 2.0) < 0.01


class TestConfigIntegration:
    """测试配置系统集成（sidecar 裁剪版）.

    LLM/OCR/ModelServer 配置已迁移到 Rust 侧（`core::config::settings.rs`），
    本测试仅覆盖 sidecar 需要的 embed/rerank/vlm 三个子配置。
    """

    def test_load_global_config(self):
        """验证全局配置加载不崩溃."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        assert config is not None
        assert hasattr(config, 'embed')
        assert hasattr(config, 'rerank')

    def test_config_sections_have_required_fields(self):
        """验证配置节有必需字段."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        # Embed config
        assert hasattr(config.embed, 'model_name')
        assert hasattr(config.embed, 'device')
        # Rerank config
        assert hasattr(config.rerank, 'model_name')
        assert hasattr(config.rerank, 'device')

    def test_embed_provider_preserved_across_python_load(self, tmp_path, monkeypatch):
        """Rust 端写入的 provider/base_url/api_key 不能被 Python load 抹掉.

        回归测试 — A1 (pydantic-settings 迁移) 之前，Python 端 EmbedConfig
        dataclass 没有 provider/base_url/api_key 字段；改 Pydantic 后如果
        漏掉这些字段，model_dump() 会永久抹掉 Rust 端写入的值，下次
        Embedder::new 会因空 api_key 走到 DeterministicEmbedder 分支，导致
        RAG 检索静默失灵。
        """
        import json
        from mbforge.utils import config as cfg_mod
        from mbforge.utils.config import AppConfig, EmbedConfig, RerankConfig

        # 1. 准备：把全局 _CONFIG_PATH 重定向到 tmp_path
        fake_config = tmp_path / "config.json"
        fake_config.write_text(json.dumps({
            "embed": {
                "model_name": "Qwen/Qwen3-Embedding-0.6B",
                "device": "cpu",
                "mrl_dim": None,
                "instruction": "",
                "provider": "qwen3",
                "base_url": "http://rust.example/v1",
                "api_key": "sk-rust-wrote-this",
            },
            "rerank": {
                "model_name": "Qwen/Qwen3-Reranker-0.6B",
                "device": "cpu",
                "max_length": 8192,
                "provider": "qwen3",
            },
            "model_cache_dir": "/some/cache",
        }), encoding="utf-8")
        monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", fake_config)
        cfg_mod.reset_config_cache()

        # 2. 加载（模拟 Python 端 load_global_config 第一次调用）
        loaded = cfg_mod.load_global_config()
        assert loaded.embed.provider == "qwen3"
        assert loaded.embed.base_url == "http://rust.example/v1"
        assert loaded.embed.api_key == "sk-rust-wrote-this"
        assert loaded.rerank.provider == "qwen3"

        # 3. 保存回去（模拟 env fallback 路径会触发的写回）
        cfg_mod.save_global_config(loaded)

        # 4. 重新读取，断言关键字段还在（不能被空默认值覆盖）
        cfg_mod.reset_config_cache()
        reloaded = cfg_mod.load_global_config()
        assert reloaded.embed.provider == "qwen3", \
            f"provider field was wiped: {reloaded.embed.provider!r}"
        assert reloaded.embed.base_url == "http://rust.example/v1", \
            f"base_url field was wiped: {reloaded.embed.base_url!r}"
        assert reloaded.embed.api_key == "sk-rust-wrote-this", \
            f"api_key field was wiped: {reloaded.embed.api_key!r}"
        assert reloaded.rerank.provider == "qwen3", \
            f"rerank.provider field was wiped: {reloaded.rerank.provider!r}"


# TestProjectIntegration 已迁移：Python `Project` 类已删除
# (被 Rust `core::project::Project` 取代)。原 `TestProjectIntegration` 覆盖
# 的逻辑由 Rust 侧单元测试 + 集成测试负责（`src-tauri/src/core/project/`）。
