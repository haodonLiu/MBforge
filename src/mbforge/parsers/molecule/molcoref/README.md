# molcoref — MolDetect 分子-标识符共指消解后端

为 MBForge 提供"MolDetect coref"模型的 Python 推理代码。
基于论文 *MolDet: Characterize the Unseen* (Wang et al.) 的 pix2seq 实现，
结合 `molScribe` 识别分子结构、EasyOCR 识别标识符文本、最近邻配对得到 coref 关系。

## 来源与许可

代码 vendor 自 [thomas0809/RxnScribe](https://github.com/thomas0809/RxnScribe)，
原始作者：Xiaoyu Wang（thomas0809），即 MolScribe / MolDetect 作者。
原仓库协议：MIT License（见 `LICENSE_RXN_SCRIBE`）。

vendor 的具体文件：
- `tokenizer.py`（仅 `BboxTokenizer` 类，`make_tokenizer`）— 解码 pix2seq 输出序列为 bbox
- `dataset.py`（仅 `make_transforms`）— 测试时图像变换
- `pix2seq/*.py`（attention_layer / backbone / misc / pix2seq / position_encoding / transformer）— pix2seq 模型架构

本目录**新增**的（不来自上游）：
- `data.py::postprocess_coref_results` — MolDetect 的 coref 后处理（最近邻配对 + 可选 molscribe/ocr），

上上游 LICENSE 全文附在 `LICENSE_RXN_SCRIBE`。

## 使用入口

通过 `mbforge.backends.moldet_coref.MolDetectCorefBackend` 调用。
`detect_coref(image)` 返回 `CorefResult{bboxes, corefs}`。
`detect_coref_with_mapping(image, mol_bboxes)` 映射到 MolDetv2 检测结果。

## 依赖

- `torch`, `torchvision` — 模型推理
- `pycocotools` — `dataset.py` 内部使用
- `easyocr`（可选）— 标识符 OCR
- `mbforge.backends.molscribe`（可选）— 分子 SMILES

模型权重 `coref_best.ckpt` 由 Rust 端从 `polyai/MolDetect` 下载，
存于 `~/mbforge/models/polyai/MolDetect/coref_best.ckpt`。
