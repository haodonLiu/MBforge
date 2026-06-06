# Isolated Nodes Classification Report

- **Total nodes in graph:** 6857
- **Isolated nodes (degree <= 1):** 2717
- **Isolation rate:** 39.6%

---

## Summary by Category

| Category | Count | Share | Verdict |
|----------|-------|-------|---------|
| Vendor: setup/MolScribe（完整拷贝） | 583 | 21.5% | Expected / Low Risk |
| 前端源码 | 403 | 14.8% | Needs Attention |
| 前端 i18n 翻译词条 | 356 | 13.1% | Expected / Low Risk |
| 文档/概念（有源文件） | 323 | 11.9% | Documentation debt |
| 文档/概念（无源文件） | 248 | 9.1% | Documentation debt |
| Rust: Core 层 | 239 | 8.8% | Needs Attention |
| Vendor: molscribe_inference（运行时拷贝） | 112 | 4.1% | Review needed |
| 测试代码 | 91 | 3.3% | Expected (tests) |
| Rust: Parsers 层 | 85 | 3.1% | Needs Attention |
| 前端配置文件 | 66 | 2.4% | Expected / Low Risk |
| Rust: Commands 层 | 49 | 1.8% | Needs Attention |
| PDF 管线测试数据（JSON） | 48 | 1.8% | Expected / Low Risk |
| Python: mbforge 源码 | 40 | 1.5% | Needs Attention |
| Shell 安装脚本 | 33 | 1.2% | Expected / Low Risk |
| 其他 JSON 配置 | 20 | 0.7% | Review needed |
| Rust: 其他 | 12 | 0.4% | Review needed |
| 其他 | 6 | 0.2% | Review needed |
| Python: 其他 | 3 | 0.1% | Review needed |

---

## Vendor: setup/MolScribe（完整拷贝） (583 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 415 | setup/MolScribe/molscribe/vocab/vocab_uspto.json |
| 43 | setup/MolScribe/molscribe/vocab/vocab_chars.json |
| 14 | setup/MolScribe/molscribe/tokenizer.py |
| 12 | setup/MolScribe/molscribe/augment.py |
| 11 | setup/MolScribe/molscribe/transformer/swin_transformer.py |
| 9 | setup/MolScribe/molscribe/utils.py |
| 8 | setup/MolScribe/molscribe/indigo/inchi.py |
| 8 | setup/MolScribe/molscribe/inference/decode_strategy.py |
| 6 | setup/MolScribe/molscribe/chemistry.py |
| 6 | setup/MolScribe/molscribe/indigo/__init__.py |
| 6 | setup/MolScribe/molscribe/indigo/bingo.py |
| 6 | setup/MolScribe/molscribe/inference/beam_search.py |
| 4 | setup/MolScribe/evaluate.py |
| 4 | setup/MolScribe/molscribe/inference/greedy_search.py |
| 4 | setup/MolScribe/molscribe/transformer/decoder.py |

**Sample labels from setup/MolScribe/molscribe/vocab/vocab_uspto.json:**

- <pad>
- <sos>
- <eos>
- <unk>
- <mask>
- [OR12]
- [Z;]
- [LG]
- [10*:0]
- [R35]
- [U1]
- [CH2)]
- [(XV)]
- [fmoc]
- [(Z)n]
- [(L)m]
- [24*]
- [CN;]
- [E,]
- [OC4H9(n)]

**Sample labels from setup/MolScribe/molscribe/vocab/vocab_chars.json:**

- <pad>
- <sos>
- <eos>
- <unk>
- <mask>
- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 8
- 9
- a
- b
- c
- d
- e

**Sample labels from setup/MolScribe/molscribe/tokenizer.py:**

- .__len__()
- .output_constraint()
- .save()
- .fit_on_texts()
- .text_to_sequence()
- .__len__()
- .offset()
- .output_constraint()
- .len_symbols()
- .fit_atom_symbols()
- .labels_to_symbols()
- .grid_to_nodes()
- .fit_on_texts()
- .fit_atom_symbols()

---

## 前端源码 (403 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 15 | frontend/src/hooks/useAnimations.ts |
| 12 | frontend/src/types/index.ts |
| 11 | frontend/src/App.tsx |
| 11 | frontend/src/components/SettingsModal.tsx |
| 10 | frontend/src/styles/patterns.ts |
| 9 | frontend/src/api/tauri/agent.ts |
| 8 | frontend/src/components/dashboard/Sparkline.tsx |
| 8 | frontend/src/components/ui/Toast.tsx |
| 7 | frontend/src/components/molecule/CorrectionPanel.tsx |
| 7 | frontend/src/components/settings/ModelComponents.tsx |
| 6 | frontend/src/api/tauri/pdf.ts |
| 6 | frontend/src/components/ErrorBoundary.tsx |
| 6 | frontend/src/components/PdfCanvas.tsx |
| 6 | frontend/src/components/SARAnalysis.tsx |
| 6 | frontend/src/components/ui/Progress.tsx |

**Sample labels from frontend/src/hooks/useAnimations.ts:**

- scaleIn
- scaleInBounce
- slideFromLeft
- slideFromBottom
- staggerContainer
- staggerContainerSlow
- staggerContainerFast
- staggerItem
- staggerItemFadeOnly
- hoverScale
- hoverLift
- hoverBorderHighlight
- fadeUpWithDelay()
- fadeInWithDelay()
- makeStaggerContainer()

**Sample labels from frontend/src/types/index.ts:**

- Message
- Project
- SearchResult
- ModelStatus
- HealthResponse
- FileNode
- ChatMessage
- CompoundEntry
- ActivityEntry
- FindingEntry
- UncertainItem
- DocumentMetadata

**Sample labels from frontend/src/App.tsx:**

- ProjectView
- Search
- Chat
- MoleculeLibrary
- Workflow
- SARAnalysis
- Dashboard
- Notes
- RouteFallback()
- App()
- AppRoutes()

---

## 前端 i18n 翻译词条 (356 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 178 | frontend/src/i18n/locales/en.json |
| 178 | frontend/src/i18n/locales/zh-CN.json |

**Sample labels from frontend/src/i18n/locales/en.json:**

- common.loading
- common.save
- common.cancel
- common.close
- common.refresh
- common.retry
- common.copy
- common.copied
- common.search
- common.noResults
- common.project
- nav.dashboard
- nav.project
- nav.notes
- nav.search
- nav.chat
- nav.molecules
- nav.sar
- nav.workflow
- nav.fileTree

**Sample labels from frontend/src/i18n/locales/zh-CN.json:**

- common.loading
- common.save
- common.cancel
- common.close
- common.refresh
- common.retry
- common.copy
- common.copied
- common.search
- common.noResults
- common.project
- nav.dashboard
- nav.project
- nav.notes
- nav.search
- nav.chat
- nav.molecules
- nav.sar
- nav.workflow
- nav.fileTree

---

## 文档/概念（有源文件） (323 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 19 | src/mbforge/parsers/molecule/mol_image_pipeline.py |
| 13 | setup/MolScribe/molscribe/indigo/__init__.py |
| 12 | setup/MolScribe/molscribe/transformer/swin_transformer.py |
| 12 | src/mbforge/csar/sar.py |
| 12 | src/mbforge/parsers/molecule/molscribe_inference/transformer/swin_transformer.py |
| 12 | tests/unit/test_sar.py |
| 11 | src/mbforge/parsers/molecule/molscribe_inference/chemistry.py |
| 10 | setup/MolScribe/molscribe/chemistry.py |
| 10 | setup/MolScribe/molscribe/transformer/decoder.py |
| 10 | src/mbforge/parsers/molecule/molscribe_inference/transformer/decoder.py |
| 10 | src/mbforge/utils/exceptions.py |
| 9 | src/mbforge/parsers/molecule/coords.py |
| 7 | src/mbforge/models/embedding.py |
| 6 | setup/MolScribe/molscribe/transformer/embedding.py |
| 6 | src/mbforge/core/resource_manager.py |

**Sample labels from src/mbforge/parsers/molecule/mol_image_pipeline.py:**

- MolDetv2 + MolScribe 图像分子提取管线.  Week 1 (P0) 引擎接口层： - MolDetv2DocDetector: 整页图
- 运行时检查 ultralytics 是否安装.
- 运行时检查 molscribe 是否可用（本地 molscribe_inference 包）.
- MolDetv2-Doc：整页图像分子结构检测.      输入：整页 PDF 渲染图像（建议 >= 300 DPI）     输出：图像坐标系中的 bb
- 初始化检测器.          Args:             model_path: 模型文件路径（.pt 或 .onnx）。若为 None，
- 对整页图像进行分子结构检测.          Args:             image: PIL Image 或 numpy array (H,
- MolDetv2-General：裁剪区域复检/精修.      输入：裁剪后的分子区域图像     输出：更精确的 bbox（通常比 Doc 版更准）
- 对裁剪区域进行分子结构检测.          返回图像坐标系中的 bbox。
- MolScribe：化学结构图像 → SMILES.      支持两种后端模式：     - "molscribe": 官方 molscribe 包（p
- 初始化识别器.          Args:             model_path: 模型路径或 Hugging Face 模型 ID。
- 加载 MolScribe 推理后端（通过 molscribe 封装模块）.
- 加载 transformers 后端（备用）.
- 将分子图像转换为 SMILES.          Args:             image: PIL Image 或 numpy array
- 使用 transformers 后端预测.
- MolDetv2 + MolScribe 图像分子提取主管线.      使用模式：         pipeline = MolImagePipelin
- 初始化管线.          Args:             doc_detector: Doc 版检测器，None 时自动创建
- 对整页 PDF 渲染图像进行分子提取.          Args:             image: 整页渲染图像             pag
- 对已知裁剪区域进行复检精修.          Args:             crop_image: 裁剪后的分子区域图像
- 处理用户手动框选的分子区域.          Args:             page_image: 整页图像             crop_

**Sample labels from setup/MolScribe/molscribe/indigo/__init__.py:**

- Docstring for class IndigoObject.
- ::              Since version 1.3.0
- ::              Since version 1.3.0
- ::              Since version 1.3.0
- ::              Since version 1.3.0
- ::              Since version 1.3.0
- ::              Since version 1.3.0
- Returns:             XY coordinates for Data sgroup         ::             Si
- Loads molecule from given buffer. Automatically detects input format
- Creates a fingerprint from the supplied binary data          :param buffer:  a
- Packs a list of molecule descriptors into a fingerprint object          :param
- Converts a chemical name into a corresponding structure          Args:
- ::              Since version 1.3.0

**Sample labels from setup/MolScribe/molscribe/transformer/swin_transformer.py:**

- Swin Transformer A PyTorch impl of : `Swin Transformer: Hierarchical Vision Tra
- Args:         x: (B, H, W, C)         window_size (int): window size      Re
- Args:         windows: (num_windows*B, window_size, window_size, C)         wi
- r""" Window based multi-head self attention (W-MSA) module with relative positio
- Args:             x: input features with shape of (num_windows*B, N, C)
- r""" Swin Transformer Block.      Args:         dim (int): Number of input ch
- r""" Patch Merging Layer.      Args:         input_resolution (tuple[int]): R
- A basic Swin Transformer layer for one stage.      Args:         dim (int): N
- 2D Image to Patch Embedding
- r""" Swin Transformer         A PyTorch impl of : `Swin Transformer: Hierarchic
- Swin-B @ 384x384, pretrained ImageNet-22k, fine tune 1k
- Swin-L @ 384x384, pretrained ImageNet-22k, fine tune 1k

---

## 文档/概念（无源文件） (248 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 248 | ? |

---

## Rust: Core 层 (239 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 14 | src-tauri/src/core/chem/markush.rs |
| 11 | src-tauri/src/core/agent/rig_adapter.rs |
| 10 | src-tauri/src/core/molecule/molecule_engine.rs |
| 9 | src-tauri/src/core/chem/abbreviation_map.rs |
| 9 | src-tauri/src/core/config/settings.rs |
| 9 | src-tauri/src/core/document/semantic_cache.rs |
| 8 | src-tauri/src/core/agent/arxiv.rs |
| 8 | src-tauri/src/core/document/ingest_queue.rs |
| 8 | src-tauri/src/core/document/knowledge_base.rs |
| 8 | src-tauri/src/core/executor/arxiv.rs |
| 7 | src-tauri/src/core/agent/observability.rs |
| 7 | src-tauri/src/core/agent/rig_hooks.rs |
| 7 | src-tauri/src/core/agent/skills.rs |
| 6 | src-tauri/src/core/agent/memory.rs |
| 6 | src-tauri/src/core/project/resource_manager.rs |

**Sample labels from src-tauri/src/core/chem/markush.rs:**

- RGroupAttachment
- AbstractRing
- RGroupDef
- SubstituentClass
- MatchLevel
- RGroupResult
- MatchLevel
- Atom
- Bond
- Result
- core_smiles()
- is_extended()
- test_core_smiles_extraction()
- test_is_extended()

**Sample labels from src-tauri/src/core/agent/rig_adapter.rs:**

- AuditLogHook
- TrajectoryHook
- PromptHook
- M
- CompletionResponse
- Response
- F
- StreamingError
- MultiTurnStreamItem
- R
- test_mbforge_provider_kind_as_str()

**Sample labels from src-tauri/src/core/molecule/molecule_engine.rs:**

- MoleculeRelationDb
- Self
- RelationStats
- AnalogWithActivity
- ScaffoldProfile
- ActivityCliff
- DedupResult
- MarkushOverlap
- MarkushPattern
- TempDir

---

## Vendor: molscribe_inference（运行时拷贝） (112 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 43 | src/mbforge/parsers/molecule/molscribe_inference/vocab/vocab_chars.json |
| 13 | src/mbforge/parsers/molecule/molscribe_inference/tokenizer.py |
| 11 | src/mbforge/parsers/molecule/molscribe_inference/transformer/swin_transformer.py |
| 9 | src/mbforge/parsers/molecule/molscribe_inference/utils.py |
| 8 | src/mbforge/parsers/molecule/molscribe_inference/inference/decode_strategy.py |
| 7 | src/mbforge/parsers/molecule/molscribe_inference/chemistry.py |
| 6 | src/mbforge/parsers/molecule/molscribe_inference/inference/beam_search.py |
| 4 | src/mbforge/parsers/molecule/molscribe_inference/inference/greedy_search.py |
| 4 | src/mbforge/parsers/molecule/molscribe_inference/transformer/decoder.py |
| 2 | src/mbforge/parsers/molecule/molscribe_inference/constants.py |
| 2 | src/mbforge/parsers/molecule/molscribe_inference/model.py |
| 2 | src/mbforge/parsers/molecule/molscribe_inference/transformer/embedding.py |
| 1 | src/mbforge/parsers/molecule/molscribe_inference/inference/__init__.py |

**Sample labels from src/mbforge/parsers/molecule/molscribe_inference/vocab/vocab_chars.json:**

- <pad>
- <sos>
- <eos>
- <unk>
- <mask>
- 0
- 1
- 2
- 3
- 4
- 5
- 6
- 7
- 8
- 9
- a
- b
- c
- d
- e

**Sample labels from src/mbforge/parsers/molecule/molscribe_inference/tokenizer.py:**

- .__len__()
- .output_constraint()
- .save()
- .fit_on_texts()
- .__len__()
- .offset()
- .output_constraint()
- .len_symbols()
- .fit_atom_symbols()
- .labels_to_symbols()
- .grid_to_nodes()
- .fit_on_texts()
- .fit_atom_symbols()

**Sample labels from src/mbforge/parsers/molecule/molscribe_inference/transformer/swin_transformer.py:**

- _cfg()
- Tensor
- .forward()
- .flops()
- .forward()
- .forward()
- .no_weight_decay()
- .no_weight_decay_keywords()
- .get_classifier()
- .reset_classifier()
- .forward()

---

## 测试代码 (91 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 23 | src-tauri/tests/test_pipeline_integration.rs |
| 13 | tests/integration/test_real_pdfs.py |
| 12 | tests/unit/test_embed_rerank.py |
| 9 | tests/unit/test_agent.py |
| 7 | tests/unit/test_pipeline.py |
| 5 | tests/unit/parsers/test_coords.py |
| 5 | tests/unit/parsers/test_extraction_result.py |
| 5 | tests/unit/parsers/test_mol_image_pipeline.py |
| 5 | tests/unit/test_project.py |
| 3 | src-tauri/tests/test_e2e_real_pdf.rs |
| 1 | ref/_test_gen.py |
| 1 | tests/conftest.py |
| 1 | tests/unit/__init__.py |
| 1 | tests/unit/test_sar.py |

**Sample labels from src-tauri/tests/test_pipeline_integration.rs:**

- test_heading_extraction_markdown()
- test_heading_extraction_uppercase()
- test_heading_extraction_empty()
- test_heading_extraction_mixed()
- test_heading_extraction_numbered()
- test_section_building_basic()
- test_section_building_no_headings()
- test_section_building_preserves_content()
- test_association_compound_names()
- test_association_activity_ic50()
- test_association_activity_ki()
- test_association_no_activity()
- test_keywords_extraction()
- test_keywords_empty_input()
- test_extract_json_clean()
- test_extract_json_code_fence()
- test_extract_json_think_block()
- test_extract_json_truncated()
- test_document_tree_index()
- test_knowledge_base_search()

**Sample labels from tests/integration/test_real_pdfs.py:**

- cn_text()
- .test_cn_pdf_has_text()
- .test_cn_pdf_contains_chemistry()
- .test_us_pdf_extraction()
- .test_known_smiles_valid()
- .test_smiles_property_calculation()
- .test_project_open_or_create()
- .test_project_scan_finds_pdfs()
- .test_project_doc_types()
- .test_project_document_metadata()
- .test_model_cache_dir_exists()
- .test_embedding_model_resolves()
- .test_reranker_model_resolves()

**Sample labels from tests/unit/test_embed_rerank.py:**

- .test_embed_single()
- .test_embed_batch()
- .test_embed_empty_list()
- .test_embed_dimension()
- .test_embed_deterministic()
- .test_embed_different_texts_different_vectors()
- .test_embed_performance()
- .test_rerank_basic()
- .test_rerank_ordering()
- .test_rerank_empty()
- .test_rerank_single()
- .test_rerank_performance()

---

## Rust: Parsers 层 (85 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 10 | src-tauri/src/parsers/pipeline.rs |
| 8 | src-tauri/src/parsers/chem/vlm_chem.rs |
| 7 | src-tauri/src/parsers/doc_types.rs |
| 7 | src-tauri/src/parsers/structure/intent.rs |
| 7 | src-tauri/src/parsers/structure/post_process.rs |
| 6 | src-tauri/src/parsers/pipeline/merge.rs |
| 5 | src-tauri/src/parsers/chem/association.rs |
| 4 | src-tauri/src/parsers/chem/chem_validate.rs |
| 4 | src-tauri/src/parsers/pdf/mineru.rs |
| 3 | src-tauri/src/parsers/chem/molecule_extractor.rs |
| 3 | src-tauri/src/parsers/pdf/liteparse.rs |
| 3 | src-tauri/src/parsers/pdf/uniparser.rs |
| 3 | src-tauri/src/parsers/pipeline/helpers.rs |
| 3 | src-tauri/src/parsers/structure/sections.rs |
| 2 | src-tauri/src/parsers/chem/claim_policy.rs |

**Sample labels from src-tauri/src/parsers/pipeline.rs:**

- From
- PostProcessResult
- DocProgressEvent
- DocStructure
- Path
- test_pdf_parse_result_serde_roundtrip()
- test_compound_entry_to_record_skips_empty_esmiles()
- test_extract_images_from_both_patents()
- test_supervised_pipeline_cn_patent()
- test_supervised_pipeline_us_patent()

**Sample labels from src-tauri/src/parsers/chem/vlm_chem.rs:**

- Default
- PathBuf
- CacheEntry
- .set()
- test_read_image_base64_not_found()
- test_chem_image_result()
- test_molscribe_result()
- test_is_likely_chemical_structure()

**Sample labels from src-tauri/src/parsers/doc_types.rs:**

- HashMap
- Self
- StructuredData
- CompoundEntry
- ActivityEntry
- FindingEntry
- UncertainItem

---

## 前端配置文件 (66 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 47 | frontend/package.json |
| 19 | frontend/tsconfig.json |

**Sample labels from frontend/package.json:**

- name
- private
- version
- type
- node
- dev
- build
- preview
- test
- test:watch
- lint
- lint:fix
- @tanstack/react-virtual
- @tauri-apps/api
- @tauri-apps/plugin-dialog
- framer-motion
- i18next
- katex
- ketcher-core
- ketcher-react

**Sample labels from frontend/tsconfig.json:**

- target
- useDefineForClassFields
- lib
- module
- skipLibCheck
- moduleResolution
- allowImportingTsExtensions
- isolatedModules
- moduleDetection
- noEmit
- jsx
- strict
- noUnusedLocals
- noUnusedParameters
- noFallthroughCasesInSwitch
- types
- baseUrl
- @/*
- include

---

## Rust: Commands 层 (49 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 10 | src-tauri/src/commands/agent.rs |
| 6 | src-tauri/src/commands/mod.rs |
| 6 | src-tauri/src/commands/molecule.rs |
| 5 | src-tauri/src/commands/mol_engine.rs |
| 4 | src-tauri/src/commands/file_ops.rs |
| 3 | src-tauri/src/commands/extractor.rs |
| 3 | src-tauri/src/commands/project_ops.rs |
| 3 | src-tauri/src/commands/sidecar.rs |
| 2 | src-tauri/src/commands/gesim.rs |
| 2 | src-tauri/src/commands/notes.rs |
| 2 | src-tauri/src/commands/pdf.rs |
| 2 | src-tauri/src/commands/text_ops.rs |
| 1 | src-tauri/src/commands/molecode.rs |

**Sample labels from src-tauri/src/commands/agent.rs:**

- LayeredContext
- CompositeMemory
- Mutex
- AuditLogHook
- TrajectoryHook
- Self
- AppHandle
- Message
- AuditEntry
- MbforgeAgentSpec

**Sample labels from src-tauri/src/commands/mod.rs:**

- mod.rs
- Fn
- Invoke
- Wry
- Send
- Sync

**Sample labels from src-tauri/src/commands/molecule.rs:**

- RelationStats
- AnalogWithActivity
- ScaffoldProfile
- ActivityCliff
- DedupResult
- SmilesValidation

---

## PDF 管线测试数据（JSON） (48 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 16 | docs/pdf-pipeline-test/reference_table1.json |
| 12 | docs/pdf-pipeline-test/06_parse_result.json |
| 8 | docs/pdf-pipeline-test/01_classification.json |
| 6 | docs/pdf-pipeline-test/03_document_classification.json |
| 4 | docs/pdf-pipeline-test/05_molecules.json |
| 2 | docs/pdf-pipeline-test/04_chunks.json |

**Sample labels from docs/pdf-pipeline-test/reference_table1.json:**

- document
- title
- target
- assay
- total_compounds_in_patent
- compounds_extracted
- total_compounds
- pic50_min
- pic50_max
- pic50_mean
- strong_gte8
- moderate_7to8
- weak_6to7
- very_weak_lt6
- compounds
- top_10

**Sample labels from docs/pdf-pipeline-test/06_parse_result.json:**

- content
- text_density
- is_scanned
- has_molecular_patterns
- metadata_hints
- pages
- needs_confirmation
- chunks
- smiles
- activities
- parser
- page_count

**Sample labels from docs/pdf-pipeline-test/01_classification.json:**

- pdf_type
- confidence
- page_count
- pages_needing_ocr
- text_density_avg
- has_complex_layout
- has_encoding_issues
- title

---

## Python: mbforge 源码 (40 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 3 | src/mbforge/model_server/routers/embed.py |
| 3 | src/mbforge/molecules/schema.py |
| 3 | src/mbforge/parsers/molecule/extraction_result.py |
| 3 | src/mbforge/utils/logger.py |
| 2 | src/mbforge/cli.py |
| 2 | src/mbforge/model_server/dependencies.py |
| 2 | src/mbforge/model_server/main.py |
| 2 | src/mbforge/model_server/routers/download.py |
| 2 | src/mbforge/model_server/routers/sar.py |
| 2 | src/mbforge/models/base.py |
| 1 | src/mbforge/core/__init__.py |
| 1 | src/mbforge/core/project.py |
| 1 | src/mbforge/csar/sar.py |
| 1 | src/mbforge/model_server/__init__.py |
| 1 | src/mbforge/model_server/models/__init__.py |

**Sample labels from src/mbforge/model_server/routers/embed.py:**

- Request
- str
- Any

**Sample labels from src/mbforge/molecules/schema.py:**

- .__post_init__()
- .clear_mol_cache()
- .copy()

**Sample labels from src/mbforge/parsers/molecule/extraction_result.py:**

- .__post_init__()
- .to_dict()
- .from_dict()

---

## Shell 安装脚本 (33 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 12 | setup/common.sh |
| 2 | setup/index.sh |
| 2 | setup/modules/01_check_env.sh |
| 2 | setup/modules/02_config_uniparser.sh |
| 2 | setup/modules/03_detect_ollama.sh |
| 2 | setup/modules/04_config_llm.sh |
| 2 | setup/modules/05_config_models.sh |
| 2 | setup/modules/06_install_modelscope.sh |
| 2 | setup/modules/07b_config_cache.sh |
| 2 | setup/modules/08_verify.sh |
| 2 | src-tauri/build.sh |
| 1 | setup/modules/07_write_env.sh |

**Sample labels from setup/common.sh:**

- common.sh script
- info()
- ok()
- warn()
- fail()
- header()
- ask()
- confirm()
- detect_cuda()
- get_gpu_name()
- has_cmd()
- has_module()

**Sample labels from setup/index.sh:**

- index.sh
- index.sh script

**Sample labels from setup/modules/01_check_env.sh:**

- 01_check_env.sh script
- run_check_env()

---

## 其他 JSON 配置 (20 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 14 | src-tauri/tauri.conf.json |
| 6 | src-tauri/capabilities/default.json |

**Sample labels from src-tauri/tauri.conf.json:**

- productName
- version
- identifier
- frontendDist
- devUrl
- beforeDevCommand
- beforeBuildCommand
- windows
- withGlobalTauri
- csp
- dangerousDisableAssetCspModification
- active
- targets
- icon

**Sample labels from src-tauri/capabilities/default.json:**

- $schema
- identifier
- description
- windows
- permissions
- platforms

---

## Rust: 其他 (12 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 9 | src-tauri/src/sidecar.rs |
| 2 | src-tauri/build.rs |
| 1 | src-tauri/src/lib.rs |

**Sample labels from src-tauri/src/sidecar.rs:**

- Value
- Mutex
- Option
- Child
- AtomicBool
- AtomicU32
- Instant
- Self
- Result

**Sample labels from src-tauri/build.rs:**

- build.rs
- main()

**Sample labels from src-tauri/src/lib.rs:**

- lib.rs

---

## 其他 (6 nodes)

### By source file

| Count | Source File |
|-------|-------------|
| 1 | frontend/eslint.config.js |
| 1 | frontend/vite.config.ts |
| 1 | frontend/vitest.config.ts |
| 1 | ref/pull-all.ps1 |
| 1 | src-tauri/test-quick.ps1 |
| 1 | src-tauri/vendor/pdfium/setup.ps1 |

**Sample labels from frontend/eslint.config.js:**

- eslint.config.js

**Sample labels from frontend/vite.config.ts:**

- vite.config.ts

**Sample labels from frontend/vitest.config.ts:**

- vitest.config.ts

---
