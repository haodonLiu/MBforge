"""In-tree replacement for the four ``onmt`` symbols MolScribe's decoder imports.

Originally the inference module imported:

- ``onmt.decoders.decoder.DecoderBase`` — abstract base for decoder stacks.
- ``onmt.modules.MultiHeadedAttention`` — multi-head dot-product attention.
- ``onmt.modules.AverageAttention`` — average-attention network (AAN).
- ``onmt.modules.position_ffn.ActivationFunction`` and ``PositionwiseFeedForward``.
- ``onmt.modules.util_class.Elementwise`` — element-wise module container.

All of these came from ``OpenNMT-py==2.2.0``, which itself depends on
``torch<2.5``-style ``torch.cuda.amp.custom_fwd`` / ``custom_bwd`` decorators
that emit deprecation warnings on every PyTorch 2.x install. Since MolScribe
only needs a tiny slice of onmt's transformer primitives (and that slice is
the same standard transformer code that any textbook reproduces), the
project vendors the four symbols here and drops the ``OpenNMT-py`` dep.

**State-dict compatibility.** The vendored classes use the **exact same
attribute names** as their onmt counterparts (``linear_keys`` / ``linear_values``
/ ``linear_query`` / ``final_linear`` for MHA; ``w_1`` / ``w_2`` /
``layer_norm`` for FFN) so that ``state_dict()`` is bit-identical and the
production checkpoint (``module.decoder.chartok_coords.*``) loads cleanly
after the ``module.`` prefix is stripped by ``safe_load``.

**Numerical parity.** The replay test
``tests/unit/parsers/test_molscribe_decoder_replay.py`` pins decoder logits
to L_inf < 1e-5 against a frozen baseline tensor — any drift in MHA / FFN
behavior surfaces there.

**Dead code note.** ``AverageAttention`` is imported only so that
``isinstance(self.self_attn, AverageAttention)`` in ``TransformerDecoderLayer
Base._forward_self_attn`` doesn't raise ``NameError``. MolScribe instantiates
``self_attn_type="scaled-dot"`` only (see ``model.py:TransformerDecoderBase``),
so ``AverageAttention`` is never constructed at runtime — but it must remain
a class symbol. Its ``forward`` raises ``NotImplementedError`` to surface any
future code that mistakenly enables the AAN path.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# DecoderBase (adapted from onmt.decoders.decoder)
# ---------------------------------------------------------------------------


class DecoderBase(nn.Module):
    """Abstract base class for decoders.

    Mirrors ``onmt.decoders.decoder.DecoderBase`` enough that
    ``TransformerDecoderBase`` can subclass it without behavioural change.
    The ``from_opt`` classmethod is the only API onmt adds beyond ``nn.Module``;
    MolScribe never calls it (it constructs the decoder directly), so the
    raise-NotImplementedError default is kept for safety.
    """

    def __init__(self, attentional: bool = True) -> None:
        super().__init__()
        self.attentional = attentional

    @classmethod
    def from_opt(cls, opt, embeddings):  # noqa: D401, ANN001 — onmt signature
        """Alternate constructor — not used by MolScribe."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ActivationFunction + PositionwiseFeedForward (adapted from onmt.modules.position_ffn)
# ---------------------------------------------------------------------------


class ActivationFunction:
    """Activation-function identifier constants used by ``PositionwiseFeedForward``.

    onmt stores these as plain string constants on a namespace-like class so
    callers can write ``pos_ffn_activation_fn=ActivationFunction.gelu``. We
    keep the same surface area; the values themselves are just strings that
    the FFN looks up in ``ACTIVATION_FUNCTIONS``.
    """

    relu = "relu"
    gelu = "gelu"


_ACTIVATION_FUNCTIONS: dict[str, Callable[[torch.Tensor], torch.Tensor]] = {
    ActivationFunction.relu: F.relu,
    ActivationFunction.gelu: F.gelu,
}


class PositionwiseFeedForward(nn.Module):
    """Two-layer FFN with residual + LayerNorm, matching onmt's order.

    Forward:
        inter = dropout1(activation(w_1(layer_norm(x))))
        out   = dropout2(w_2(inter))
        return out + x
    """

    def __init__(
        self,
        d_model: int,
        d_ff: int,
        dropout: float = 0.1,
        activation_fn: str = ActivationFunction.relu,
    ) -> None:
        super().__init__()
        self.w_1 = nn.Linear(d_model, d_ff)
        self.w_2 = nn.Linear(d_ff, d_model)
        self.layer_norm = nn.LayerNorm(d_model, eps=1e-6)
        self.dropout_1 = nn.Dropout(dropout)
        self.dropout_2 = nn.Dropout(dropout)
        self.activation = _ACTIVATION_FUNCTIONS[activation_fn]
        self.dropout = dropout  # kept for parity with onmt API

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        inter = self.dropout_1(self.activation(self.w_1(self.layer_norm(x))))
        output = self.dropout_2(self.w_2(inter))
        return output + x

    def update_dropout(self, dropout: float) -> None:
        self.dropout_1.p = dropout
        self.dropout_2.p = dropout


# ---------------------------------------------------------------------------
# Elementwise (adapted from onmt.modules.util_class)
# ---------------------------------------------------------------------------


class Elementwise(nn.ModuleList):
    """Element-wise module container — last-dim split, apply, merge.

    Used by ``Embeddings.make_embedding`` to apply a per-feature embedding to
    each column of a 3-D input. MolScribe only passes ``merge='mlp'`` paths,
    but the full set of merge modes is preserved for parity.
    """

    def __init__(self, merge: str | None = None, *args) -> None:  # noqa: ANN002 — onmt signature
        assert merge in [None, "first", "concat", "sum", "mlp"]
        self.merge = merge
        super().__init__(*args)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor | list[torch.Tensor]:
        inputs_ = [feat.squeeze(2) for feat in inputs.split(1, dim=2)]
        assert len(self) == len(inputs_)
        outputs = [f(x) for f, x in zip(self, inputs_)]
        if self.merge == "first":
            return outputs[0]
        if self.merge == "concat" or self.merge == "mlp":
            return torch.cat(outputs, 2)
        if self.merge == "sum":
            return sum(outputs)
        return outputs


# ---------------------------------------------------------------------------
# AverageAttention (adapted from onmt.modules.average_attn)
# ---------------------------------------------------------------------------


class AverageAttention(nn.Module):
    """Average-attention network (AAN) — stub.

    MolScribe's ``TransformerDecoderBase`` always passes
    ``self_attn_type="scaled-dot"`` (``model.py:TransformerDecoderBase.__init__``),
    which instantiates ``MultiHeadedAttention`` instead of this class. The
    ``isinstance(self.self_attn, AverageAttention)`` branch in
    ``TransformerDecoderLayerBase._forward_self_attn`` is therefore never
    taken at inference time, but the symbol must remain importable.

    Any accidental instantiation of this stub at runtime will raise
    ``NotImplementedError`` rather than silently producing garbage.
    """

    def __init__(
        self,
        model_dim: int,
        dropout: float = 0.1,
        aan_useffn: bool = False,
        pos_ffn_activation_fn: str = ActivationFunction.relu,
    ) -> None:  # noqa: ARG002 — parity with onmt signature, never reached
        super().__init__()
        # Storing the args lets debugging tools inspect what would have been
        # built, but no parameters are allocated.
        self.model_dim = model_dim
        self.aan_useffn = aan_useffn

    def forward(self, *args, **kwargs):  # noqa: ANN002, ANN201, D401
        raise NotImplementedError(
            "AverageAttention is intentionally unimplemented in MBForge's "
            "vendored onmt stub: MolScribe inference uses "
            "self_attn_type='scaled-dot' (MultiHeadedAttention) only. If "
            "this path is reached, the decoder was reconfigured to "
            "self_attn_type='average' — which the production checkpoint "
            "does not support."
        )


# ---------------------------------------------------------------------------
# MultiHeadedAttention (adapted from onmt.modules.multi_headed_attn)
# ---------------------------------------------------------------------------


class MultiHeadedAttention(nn.Module):
    """Multi-head scaled-dot-product attention.

    Mirrors ``onmt.modules.multi_headed_attn.MultiHeadedAttention`` line-for-line
    for the cases MolScribe exercises:

    - ``max_relative_positions == 0`` (the production default — relative
      positions branch is dead code; the test fixture in
      ``tests/unit/parsers/test_molscribe_decoder_replay.py`` loads the
      real checkpoint which contains no ``relative_positions_embeddings``
      keys, confirming the branch is unused).
    - ``layer_cache`` schema: ``{"self_keys", "self_values"}`` for
      ``attn_type="self"``; ``{"memory_keys", "memory_values"}`` for
      ``attn_type="context"``. Used by autoregressive decoding for KV-cache
      reuse across steps.
    - The exact ``masked_fill(-1e18)`` + ``scores.float()`` + softmax + cast
      back to query.dtype pipeline from the onmt implementation. Substituting
      ``scaled_dot_product_attention`` would change the output by ~1e-3 and
      break the replay test.
    """

    def __init__(
        self,
        head_count: int,
        model_dim: int,
        dropout: float = 0.1,
        max_relative_positions: int = 0,
    ) -> None:
        assert model_dim % head_count == 0
        self.dim_per_head = model_dim // head_count
        self.model_dim = model_dim

        super().__init__()
        self.head_count = head_count

        self.linear_keys = nn.Linear(model_dim, head_count * self.dim_per_head)
        self.linear_values = nn.Linear(model_dim, head_count * self.dim_per_head)
        self.linear_query = nn.Linear(model_dim, head_count * self.dim_per_head)
        self.softmax = nn.Softmax(dim=-1)
        self.dropout = nn.Dropout(dropout)
        self.final_linear = nn.Linear(model_dim, model_dim)

        self.max_relative_positions = max_relative_positions

        # Relative-position branch is unreachable for MolScribe (default
        # max_relative_positions=0). Kept as no-op for state-dict symmetry.
        if max_relative_positions > 0:
            vocab_size = max_relative_positions * 2 + 1
            self.relative_positions_embeddings = nn.Embedding(
                vocab_size, self.dim_per_head
            )

    def forward(  # noqa: C901, PLR0912, PLR0915 — onmt-parity implementation
        self,
        key: torch.Tensor,
        value: torch.Tensor,
        query: torch.Tensor,
        mask: torch.Tensor | None = None,
        layer_cache: dict | None = None,
        attn_type: str | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        batch_size = key.size(0)
        dim_per_head = self.dim_per_head
        head_count = self.head_count

        def shape(x: torch.Tensor) -> torch.Tensor:
            return x.view(batch_size, -1, head_count, dim_per_head).transpose(1, 2)

        def unshape(x: torch.Tensor) -> torch.Tensor:
            return (
                x.transpose(1, 2)
                .contiguous()
                .view(batch_size, -1, head_count * dim_per_head)
            )

        # 1) Project key, value, and query.
        if layer_cache is not None:
            if attn_type == "self":
                query_proj, key_proj, value_proj = (
                    self.linear_query(query),
                    self.linear_keys(query),
                    self.linear_values(query),
                )
                key_proj = shape(key_proj)
                value_proj = shape(value_proj)
                if layer_cache.get("self_keys") is not None:
                    key_proj = torch.cat((layer_cache["self_keys"], key_proj), dim=2)
                if layer_cache.get("self_values") is not None:
                    value_proj = torch.cat(
                        (layer_cache["self_values"], value_proj), dim=2
                    )
                layer_cache["self_keys"] = key_proj
                layer_cache["self_values"] = value_proj
                key = key_proj
                value = value_proj
            elif attn_type == "context":
                query_proj = self.linear_query(query)
                if layer_cache.get("memory_keys") is None:
                    key_proj = self.linear_keys(key)
                    value_proj = self.linear_values(value)
                    key_proj = shape(key_proj)
                    value_proj = shape(value_proj)
                else:
                    key_proj = layer_cache["memory_keys"]
                    value_proj = layer_cache["memory_values"]
                layer_cache["memory_keys"] = key_proj
                layer_cache["memory_values"] = value_proj
                key = key_proj
                value = value_proj
            else:
                raise ValueError(
                    f"attn_type must be 'self' or 'context', got {attn_type!r}"
                )
        else:
            key = shape(self.linear_keys(key))
            value = shape(self.linear_values(value))

        query = shape(self.linear_query(query))

        # 2) Calculate and scale scores.
        query = query / math.sqrt(dim_per_head)
        scores = torch.matmul(query, key.transpose(2, 3))
        scores = scores.float()

        if mask is not None:
            mask = mask.unsqueeze(1)  # [B, 1, 1, T_values]
            scores = scores.masked_fill(mask, -1e18)

        # 3) Apply attention dropout and compute context vectors.
        attn = self.softmax(scores).to(query.dtype)
        drop_attn = self.dropout(attn)

        context = unshape(torch.matmul(drop_attn, value))
        output = self.final_linear(context)

        # Reshape attn to (B, H, Q_len, K_len) for the caller.
        key_len = key.size(2)
        query_len = query.size(2)
        attns = attn.view(batch_size, head_count, query_len, key_len)

        return output, attns

    def update_dropout(self, dropout: float) -> None:
        self.dropout.p = dropout
