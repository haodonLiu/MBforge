"""常用分子片段预设库 — 用于分子编辑器快速插入."""

from __future__ import annotations

PRESETS: list[dict] = [
    # --- 小分子片段 ---
    {"name": "苯环", "esmiles": "c1ccccc1"},
    {"name": "环己烷", "esmiles": "C1CCCCC1"},
    {"name": "环戊烷", "esmiles": "C1CCCC1"},
    {"name": "吡啶", "esmiles": "c1ccncc1"},
    {"name": "噻唑", "esmiles": "c1cncs1"},
    {"name": "呋喃", "esmiles": "c1ccoc1"},
    {"name": "哌啶", "esmiles": "C1CCNCC1"},
    {"name": "吡咯", "esmiles": "c1cc[nH]c1"},
    {"name": "吲哚", "esmiles": "c1ccc2c(c1)[nH]cc2"},
    # --- 官能团 ---
    {"name": "羧基", "esmiles": "*C(=O)O<sep><a>0:<dum></a>"},
    {"name": "氨基", "esmiles": "*N"},
    {"name": "甲基", "esmiles": "*C"},
    {"name": "羟基", "esmiles": "*O"},
    {"name": "酰胺", "esmiles": "*C(=O)N"},
    {"name": "磺酰基", "esmiles": "*S(=O)(=O)O"},
    {"name": "酯基", "esmiles": "*C(=O)O*"},
    {"name": "酮基", "esmiles": "*C(=O)*"},
    {"name": "醛基", "esmiles": "*C=O"},
    {"name": "氰基", "esmiles": "*C#N"},
    {"name": "硝基", "esmiles": "*[N+](=O)[O-]"},
    # --- Halogens ---
    {"name": "氟", "esmiles": "*F"},
    {"name": "氯", "esmiles": "*Cl"},
    {"name": "溴", "esmiles": "*Br"},
    {"name": "碘", "esmiles": "*I"},
    # --- Markush 常用 ---
    {"name": "R[1] 连接点", "esmiles": "*<sep><a>0:R[1]</a>"},
    {"name": "R[1] 苯环", "esmiles": "*c1ccccc1<sep><a>0:R[1]</a>"},
    {"name": "R[1] 羧基", "esmiles": "*C(=O)O<sep><a>0:R[1]</a>"},
    {"name": "R[1]+R[2] 苯环", "esmiles": "*c1ccccc1<sep><a>0:R[1]</a><a>0:R[2]</a>"},
]
