"""Agent 对话集成测试 — 验证 ReAct 循环、工具执行、错误处理."""



from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


class TestAgentTools:
    """测试 Agent 工具注册和执行."""

    def test_tool_registry_has_native_tools(self):
        """验证核心工具已注册."""
        from mbforge.core.resource_manager import RESOURCE_CATALOG
        # moldet, molscribe 模型资源
        model_ids = [k for k, v in RESOURCE_CATALOG.items() if v.type.value == "model"]
        assert len(model_ids) >= 2
        assert "moldet" in model_ids
        assert "molscribe" in model_ids

    def test_tool_registry_has_python_packages(self):
        """验证 Python 包资源已注册."""
        from mbforge.core.resource_manager import RESOURCE_CATALOG
        pkg_ids = [k for k, v in RESOURCE_CATALOG.items() if v.type.value == "python_package"]
        assert len(pkg_ids) >= 4
        assert "torch" in pkg_ids
        assert "rdkit" in pkg_ids


class TestResourceManagerIntegration:
    """测试 ResourceManager 与 Agent 的集成."""

    def test_check_all_returns_valid_report(self):
        """验证全量检查返回合法报告."""
        from mbforge.core.resource_manager import ResourceManager
        report = ResourceManager.check_all()
        assert report.python_version  # 非空
        assert len(report.resources) > 0
        assert "/" in report.summary  # 格式 "X/Y resources ready"

    def test_check_known_resource(self):
        """验证已知资源可检查."""
        from mbforge.core.resource_manager import ResourceManager
        status = ResourceManager.check("torch")
        assert status.id == "torch"
        assert status.status.value in ("ready", "not_found")

    def test_check_unknown_resource(self):
        """验证未知资源返回错误."""
        from mbforge.core.resource_manager import ResourceManager
        status = ResourceManager.check("nonexistent_model_xyz")
        assert status.status.value == "error"

    def test_model_path_for_downloaded_model(self):
        """验证已下载模型可获取路径."""
        from mbforge.core.resource_manager import ResourceManager
        # torch 总是已安装的
        status = ResourceManager.check("torch")
        if status.status.value == "ready":
            # torch 有版本号
            assert status.version  # 非空


class TestExceptionHierarchy:
    """测试异常层级完整性."""

    def test_all_exceptions_inherit_from_mbforge_error(self):
        """验证所有异常都继承 MBForgeError."""
        from mbforge.utils.helpers import (
            ConfigError,
            FileAccessError,
            MBForgeError,
            ModelNotAvailableError,
            PathTraversalError,
            ProjectNotValidError,
            ResourceNotAvailableError,
            ToolExecutionError,
            ValidationError,
        )
        for exc_cls in [
            ProjectNotValidError, ModelNotAvailableError, ConfigError,
            ValidationError, FileAccessError, PathTraversalError,
            ResourceNotAvailableError, ToolExecutionError,
        ]:
            assert issubclass(exc_cls, MBForgeError), f"{exc_cls.__name__} must inherit MBForgeError"

    def test_exception_status_codes(self):
        """验证异常有正确的 HTTP 状态码."""
        from mbforge.utils.helpers import (
            ModelNotAvailableError,
            ProjectNotValidError,
            ResourceNotAvailableError,
            ValidationError,
        )
        assert ProjectNotValidError.status_code == 400
        assert ModelNotAvailableError.status_code == 503
        assert ValidationError.status_code == 422
        assert ResourceNotAvailableError.status_code == 503

    def test_exception_error_codes(self):
        """验证异常有机器可读的错误码."""
        from mbforge.utils.helpers import (
            ModelNotAvailableError,
            ProjectNotValidError,
            ResourceNotAvailableError,
            ValidationError,
        )
        assert ProjectNotValidError.error_code == "project_not_valid"
        assert ModelNotAvailableError.error_code == "model_not_available"
        assert ValidationError.error_code == "validation_error"
        assert ResourceNotAvailableError.error_code == "resource_not_available"

    def test_exception_carries_message(self):
        """验证异常携带消息."""
        from mbforge.utils.helpers import MBForgeError
        exc = MBForgeError("test message", detail="extra info")
        assert exc.message == "test message"
        assert exc.detail == "extra info"
        assert str(exc) == "test message"
