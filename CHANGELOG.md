# Changelog

MBForge 的重要变更记录在此文件。格式遵循 Keep a Changelog，版本号遵循 Semantic
Versioning；发布规则见 `docs/VERSION_CONTROL.md`。

## [Unreleased]

### Added

- 建立贡献、项目管理、版本控制和发布规范，并提供 Issue/PR 模板。
- 分子详情支持使用 Ketcher 手动编辑骨架并直接保存修正后的 E-SMILES。

### Changed

- 分子库将未人工修正的识别结果标记为“自动识别”，不再因筛选该状态而进入逐条审批流程。
- MoleCode 在分子卡片和详情中以原始文本展示，不再作为第二种结构图渲染。
