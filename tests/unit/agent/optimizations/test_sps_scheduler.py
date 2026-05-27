"""测试 SPS 预测器."""

import pytest

from mbforge.agent.optimizations.sps_scheduler import (
    SPSConfig,
    SpeculativeScheduler,
    ToolCallPredictor,
)


class TestToolCallPredictor:
    def test_fallback_for_kb_search(self):
        predictor = ToolCallPredictor(SPSConfig(enabled=True))
        preds = predictor.predict_next("search_knowledge_base", top_k=2)
        assert len(preds) >= 1
        assert preds[0][0] in (
            "read_document_abstract",
            "read_document_overview",
            "read_document_detail",
        )

    def test_learn_improves_predictions(self):
        predictor = ToolCallPredictor(
            SPSConfig(enabled=True, speculation_threshold=0.0)
        )
        predictor.learn(["search_knowledge_base", "read_document_abstract"])
        predictor.learn(["search_knowledge_base", "read_document_abstract"])
        predictor.learn(["search_knowledge_base", "read_document_overview"])

        preds = predictor.predict_next("search_knowledge_base", top_k=1)
        assert len(preds) >= 1
        assert preds[0][0] == "read_document_abstract"

    def test_disabled_returns_empty(self):
        predictor = ToolCallPredictor(SPSConfig(enabled=False))
        assert predictor.predict_next("search_knowledge_base") == []

    def test_unknown_tool_no_data(self):
        predictor = ToolCallPredictor(SPSConfig(enabled=True))
        preds = predictor.predict_next("unknown_tool")
        assert preds == []


class TestSpeculativeScheduler:
    def test_record_and_predict_kb_search(self):
        scheduler = SpeculativeScheduler(config=SPSConfig(enabled=True))
        # result 需包含 _chunk_ 模式才能提取 doc_id
        preds = scheduler.record_and_predict(
            "search_knowledge_base",
            {"query": "aspirin", "top_k": 5},
            "1. aspirin_doc_chunk_0 aspirin is a COX inhibitor...",
        )
        assert any(p["name"] == "read_document_abstract" for p in preds)

    def test_disabled_scheduler(self):
        scheduler = SpeculativeScheduler(config=SPSConfig(enabled=False))
        preds = scheduler.record_and_predict("search_knowledge_base", {}, "")
        assert preds == []

    def test_confidence_in_range(self):
        scheduler = SpeculativeScheduler(config=SPSConfig(enabled=True))
        preds = scheduler.record_and_predict(
            "search_knowledge_base", {}, "result"
        )
        for p in preds:
            assert 0.0 <= p["confidence"] <= 1.0
            assert "name" in p
            assert "args" in p
