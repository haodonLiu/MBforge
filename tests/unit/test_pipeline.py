"""PDF 管线集成测试 — 验证解析、分类、提取链路."""



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
    """测试配置系统集成.

    embed/rerank 已随 qwen3 后端一起移除，当前 AppConfig 仅保留
    llm / ocr / vlm / model_server 等业务配置。
    """

    def test_load_global_config(self):
        """验证全局配置加载不崩溃."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        assert config is not None
        assert hasattr(config, 'llm')
        assert hasattr(config, 'ocr')

    def test_config_sections_have_required_fields(self):
        """验证配置节有必需字段."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        # LLM config
        assert hasattr(config.llm, 'model')
        assert hasattr(config.llm, 'provider')

    def test_unknown_fields_are_ignored(self, tmp_path, monkeypatch):
        """回归测试 — 旧版 config.json 中的 embed/rerank 字段不能被加载崩溃.

        A1 之后 pydantic-settings 使用 extra='ignore'，但需确保用户本地残留的
        embed/rerank 配置不会导致 AppConfig.model_validate 失败。
        """
        import json

        from mbforge.utils import config as cfg_mod

        fake_settings = tmp_path / "settings.json"
        fake_settings.write_text(json.dumps({
            "llm": {"provider": "openai_compatible", "model": "default"},
            # 旧字段应被静默忽略
            "embed": {"provider": "qwen3", "model_name": "Qwen/Qwen3-Embedding-0.6B"},
            "rerank": {"provider": "qwen3", "model_name": "Qwen/Qwen3-Reranker-0.6B"},
        }), encoding="utf-8")
        monkeypatch.setattr(cfg_mod, "_SETTINGS_PATH", fake_settings)
        cfg_mod.reset_config_cache()

        loaded = cfg_mod.load_global_config()
        assert loaded.llm.provider == "openai_compatible"
        assert loaded.llm.model == "default"
        # 不再暴露 embed/rerank
        assert not hasattr(loaded, 'embed')
        assert not hasattr(loaded, 'rerank')

        # 保存回去不能产生 embed/rerank
        cfg_mod.save_global_config(loaded)
        cfg_mod.reset_config_cache()
        reloaded = cfg_mod.load_global_config()
        dumped = reloaded.model_dump()
        assert "embed" not in dumped
        assert "rerank" not in dumped


# TestProjectIntegration 已迁移：Python `Project` 类已删除。原
# `TestProjectIntegration` 覆盖的逻辑由 `tests/integration/test_real_pdfs.py`
# 下的 `test_project_*` 用例负责。
