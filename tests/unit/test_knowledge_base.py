"""测试知识库模块."""

import tempfile
from pathlib import Path


from mbforge.core.knowledge_base import KnowledgeBase
from mbforge.core.document import ExtractedContent


class FakeEmbedder:
    """测试用假 embedder，避免下载模型."""

    def embed(self, texts):
        import random
        return [[random.random() for _ in range(384)] for _ in texts]

    async def aembed(self, texts):
        return self.embed(texts)


class TestKnowledgeBase:
    def test_init(self):
        tmpdir = tempfile.mkdtemp()
        try:
            kb = KnowledgeBase(Path(tmpdir))
            stats = kb.get_stats()
            assert stats["total_chunks"] == 0
            kb.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_index_and_search(self):
        tmpdir = tempfile.mkdtemp()
        try:
            kb = KnowledgeBase(Path(tmpdir), embedder=FakeEmbedder())
            content = ExtractedContent(
                text="This is a test document about molecular docking.",
                chunks=["This is a test document about molecular docking."],
            )
            kb.index_document("doc1", content)
            stats = kb.get_stats()
            assert stats["total_chunks"] == 1

            results = kb.search("molecular docking", top_k=3)
            assert len(results) >= 1
            kb.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
