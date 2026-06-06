# MolScribe 双拷贝差异对比

## 共有文件（名称相同）

### __init__.py
- setup/MolScribe: 1 nodes
- molscribe_inference: 1 nodes
- 完全相同的节点: 0
- setup 独有: 1 个
  - __init__.py
- inference 独有: 1 个
  - MolScribe inference module (stripped from original for MBForge).  Only retains i

## setup/MolScribe 独有文件

- evaluate.py (5 nodes)
- molscribe/augment.py (12 nodes)
- molscribe/chemistry.py (16 nodes)
- molscribe/constants.py (2 nodes)
- molscribe/dataset.py (4 nodes)
- molscribe/evaluate.py (2 nodes)
- molscribe/indigo/__init__.py (19 nodes)
- molscribe/indigo/bingo.py (6 nodes)
- molscribe/indigo/inchi.py (8 nodes)
- molscribe/indigo/renderer.py (2 nodes)
- molscribe/inference/__init__.py (1 nodes)
- molscribe/inference/beam_search.py (10 nodes)
- molscribe/inference/decode_strategy.py (8 nodes)
- molscribe/inference/greedy_search.py (9 nodes)
- molscribe/interface.py (2 nodes)
- molscribe/loss.py (5 nodes)
- molscribe/model.py (7 nodes)
- molscribe/tokenizer.py (14 nodes)
- molscribe/transformer/__init__.py (1 nodes)
- molscribe/transformer/decoder.py (14 nodes)
- molscribe/transformer/embedding.py (8 nodes)
- molscribe/transformer/swin_transformer.py (23 nodes)
- molscribe/utils.py (10 nodes)
- molscribe/vocab/vocab_chars.json (43 nodes)
- molscribe/vocab/vocab_uspto.json (415 nodes)
- predict.py (1 nodes)
- scripts/eval_uspto_joint_chartok.sh (2 nodes)
- scripts/eval_uspto_joint_chartok_1m680k.sh (2 nodes)
- scripts/train_uspto_joint_chartok.sh (2 nodes)
- scripts/train_uspto_joint_chartok_1m680k.sh (2 nodes)
- setup.py (1 nodes)
- train.py (1 nodes)

## molscribe_inference 独有文件

- chemistry.py (18 nodes)
- constants.py (3 nodes)
- download.py (3 nodes)
- inference/__init__.py (1 nodes)
- inference/beam_search.py (10 nodes)
- inference/decode_strategy.py (8 nodes)
- inference/greedy_search.py (9 nodes)
- interface.py (3 nodes)
- model.py (7 nodes)
- tokenizer.py (13 nodes)
- transformer/decoder.py (14 nodes)
- transformer/embedding.py (8 nodes)
- transformer/swin_transformer.py (23 nodes)
- utils.py (10 nodes)
- vocab/vocab_chars.json (43 nodes)