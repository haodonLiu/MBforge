"""Replay test: verify that the in-tree MolScribe decoder produces bit-stable
outputs when loaded with the production checkpoint.

This test exists for two reasons:

1. **Baseline for the onmt replacement.** The current implementation imports
   ``onmt.modules.{MultiHeadedAttention, AverageAttention}`` and
   ``onmt.modules.position_ffn.{ActivationFunction, PositionwiseFeedForward}``
   from the pinned ``OpenNMT-py==2.2.0``. After replacing those with the
   in-tree ``_onmt_stub`` module, the decoder logits must reproduce this
   baseline to within tight numerical tolerance — otherwise SMILES outputs
   diverge.

2. **Smoke test for checkpoint loading.** It exercises the full
   ``module.decoder.chartok_coords.*`` state-dict path that production uses,
   including the ``module.`` prefix stripping done by ``safe_load``.

The test is **skipped** when the MolScribe checkpoint is not present locally
(``~/MBForge/models/MolScribe/swin_base_char_aux_1m680k.pth`` or whatever
``ResourceManager.get_molscribe_path()`` resolves to).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

REPLAY_TENSOR_PATH = Path(__file__).parent / "_molscribe_decoder_replay.npy"
TOLERANCE = 1e-5


def _find_checkpoint() -> Path | None:
    """Resolve the MolScribe checkpoint via the same path the runtime uses."""
    try:
        from mbforge.core.resource_manager import ResourceManager

        path = ResourceManager.get_molscribe_path()
        if path is not None and path.exists():
            return path
    except Exception:
        pass

    default = (
        Path.home()
        / "MBForge"
        / "models"
        / "MolScribe"
        / "swin_base_char_aux_1m680k.pth"
    )
    if default.exists():
        return default
    return None


@pytest.fixture(scope="module")
def molscribe_ckpt() -> Path:
    ckpt = _find_checkpoint()
    if ckpt is None:
        pytest.skip(
            "MolScribe checkpoint not found — replay test requires real weights"
        )
    return ckpt


def _build_decoder_and_logits(ckpt: Path) -> torch.Tensor:
    """Build the chartok_coords decoder exactly as MolScribe inference does,
    load the real checkpoint weights, run forward on a fixed random input,
    and return the resulting logits tensor."""
    from mbforge.parsers.molecule.molscribe_inference.interface import MolScribe
    from mbforge.parsers.molecule.molscribe_inference.model import Decoder, Encoder
    from mbforge.parsers.molecule.molscribe_inference.tokenizer import PAD_ID

    torch.manual_seed(0)
    ms = MolScribe(str(ckpt), device="cpu")
    # Mirror interface._get_model: build encoder first so encoder_dim is set
    # on args (TransformerDecoderBase.__init__ requires it for enc_trans_layer).
    args = ms._get_args()  # noqa: SLF001 — internal access for test parity
    args.formats = ["chartok_coords"]
    encoder = Encoder(args, pretrained=False)
    args.encoder_dim = encoder.n_features
    decoder = Decoder(args, ms.tokenizer)

    state = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    decoder_sd = {k.replace("module.", ""): v for k, v in state["decoder"].items()}
    missing, _unexpected = decoder.load_state_dict(decoder_sd, strict=False)
    chartok_missing = [k for k in missing if "chartok_coords" in k]
    assert not chartok_missing, f"chartok weights failed to load: {chartok_missing}"
    decoder.eval()

    branch = decoder.decoder["chartok_coords"]
    branch.eval()
    with torch.no_grad():
        # Encoder output: (batch=1, num_pixels=144, encoder_dim=1024).
        # swin_base emits 144 tokens at 128-dim; chartok_coords concatenates
        # multi-resolution features so the decoder sees 1024-dim.
        encoder_out = torch.randn(1, 144, 1024, generator=torch.manual_seed(42))
        labels = torch.randint(
            low=0,
            high=len(ms.tokenizer["chartok_coords"]),
            size=(1, 64),
            generator=torch.manual_seed(7),
        )
        labels[:, -1] = PAD_ID
        label_lengths = torch.tensor([63])
        logits, _, _ = branch(encoder_out, labels, label_lengths)
    return logits.detach().cpu()


def test_decoder_replay_matches_baseline(molscribe_ckpt: Path) -> None:
    """Decoder logits must remain numerically stable across the onmt → in-tree
    replacement."""
    current = _build_decoder_and_logits(molscribe_ckpt).numpy()

    if not REPLAY_TENSOR_PATH.exists():
        np.save(REPLAY_TENSOR_PATH, current)
        pytest.skip(
            f"Baseline tensor written to {REPLAY_TENSOR_PATH}. "
            "Subsequent runs will compare against this baseline."
        )

    baseline = np.load(REPLAY_TENSOR_PATH)
    assert baseline.shape == current.shape, (
        f"Shape changed: baseline {baseline.shape} vs current {current.shape}. "
        "Decoder structure changed (layer added/removed, dims altered, or the "
        "wrong branch of MultiHeadedAttention / PositionwiseFeedForward was "
        "exercised)."
    )
    max_abs = float(np.max(np.abs(baseline - current)))
    assert max_abs < TOLERANCE, (
        f"Decoder logits diverged from baseline by L_inf={max_abs:.3e} "
        f"(tolerance={TOLERANCE}). If you intentionally changed decoder "
        f"behavior, delete {REPLAY_TENSOR_PATH} and re-run."
    )


def test_decoder_load_state_dict_is_complete(molscribe_ckpt: Path) -> None:
    """After loading the chartok_coords subset of the checkpoint, no keys
    from that subset should remain uninitialized."""
    from mbforge.parsers.molecule.molscribe_inference.interface import MolScribe
    from mbforge.parsers.molecule.molscribe_inference.model import Decoder, Encoder

    state = torch.load(str(molscribe_ckpt), map_location="cpu", weights_only=False)
    ms = MolScribe(str(molscribe_ckpt), device="cpu")
    args = ms._get_args()  # noqa: SLF001
    args.formats = ["chartok_coords"]
    encoder = Encoder(args, pretrained=False)
    args.encoder_dim = encoder.n_features
    decoder = Decoder(args, ms.tokenizer)
    decoder_sd = {k.replace("module.", ""): v for k, v in state["decoder"].items()}
    missing, _unexpected = decoder.load_state_dict(decoder_sd, strict=False)
    chartok_missing = [k for k in missing if "chartok_coords" in k]
    assert not chartok_missing, (
        f"chartok_coords weights failed to load — would force random init "
        f"for these params at inference: {chartok_missing}"
    )
