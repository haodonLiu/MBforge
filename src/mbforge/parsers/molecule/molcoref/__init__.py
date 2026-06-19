"""molcoref — MolDetect 分子-标识符共指消解后端。

vendor 自 thomas0809/RxnScribe（MIT），详见 README.md 和 LICENSE_RXN_SCRIBE。
"""
from . import pix2seq  # noqa: F401  （vendor 子包，构造 build_pix2seq_model 需要）
from .tokenizer import BboxTokenizer, get_tokenizer  # noqa: F401
from .dataset import make_transforms  # noqa: F401
from .data import postprocess_coref_results  # noqa: F401
