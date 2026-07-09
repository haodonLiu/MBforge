"""MolScribe inference interface — stripped for MBForge.

No albumentations, no indigo. Uses PIL for image preprocessing.
"""

import argparse
import logging

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

from .chemistry import convert_graph_to_smiles
from .model import Decoder, Encoder
from .tokenizer import get_tokenizer

BOND_TYPES = ["", "single", "double", "triple", "aromatic", "solid wedge", "dashed wedge"]


def safe_load(module, module_states):
    def remove_prefix(state_dict):
        return {k.replace("module.", ""): v for k, v in state_dict.items()}

    module.load_state_dict(remove_prefix(module_states), strict=False)


def _preprocess_image(image, input_size=384):
    """PIL Image → normalized tensor (replaces albumentations transforms).

    Original pipeline: grayscale → resize → normalize (RGB mean/std) → to_tensor.
    Model expects 3-channel input from grayscale (all channels same).
    """
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    image = image.convert("L")  # grayscale first
    image = image.resize((input_size, input_size), Image.BILINEAR)
    arr = np.array(image, dtype=np.float32) / 255.0  # [0, 1]
    # Expand grayscale to 3 channels
    arr = np.stack([arr, arr, arr], axis=0)  # (3, H, W)
    mean = np.array([0.485, 0.456, 0.406]).reshape(3, 1, 1)
    std = np.array([0.229, 0.224, 0.225]).reshape(3, 1, 1)
    arr = (arr - mean) / std
    tensor = torch.from_numpy(arr).unsqueeze(0).float()  # (1, 3, H, W)
    return tensor


class MolScribe:
    """MolScribe inference — chemical structure image → SMILES."""

    def __init__(self, model_path, device=None, num_workers=1):
        model_states = torch.load(model_path, map_location=torch.device("cpu"), weights_only=False)
        args = self._get_args(model_states["args"])
        if device is None:
            device = torch.device("cpu")
        self.device = device
        self.input_size = args.input_size
        self.tokenizer = get_tokenizer(args)
        self.encoder, self.decoder = self._get_model(args, self.tokenizer, self.device, model_states)
        self.num_workers = num_workers

    def _get_args(self, args_states=None):
        parser = argparse.ArgumentParser()
        parser.add_argument("--encoder", type=str, default="swin_base")
        parser.add_argument("--decoder", type=str, default="transformer")
        parser.add_argument("--trunc_encoder", action="store_true")
        parser.add_argument("--no_pretrained", action="store_true")
        parser.add_argument("--use_checkpoint", action="store_true", default=True)
        parser.add_argument("--dropout", type=float, default=0.5)
        parser.add_argument("--embed_dim", type=int, default=256)
        parser.add_argument("--enc_pos_emb", action="store_true")
        group = parser.add_argument_group("transformer_options")
        group.add_argument("--dec_num_layers", type=int, default=6)
        group.add_argument("--dec_hidden_size", type=int, default=256)
        group.add_argument("--dec_attn_heads", type=int, default=8)
        group.add_argument("--dec_num_queries", type=int, default=128)
        group.add_argument("--hidden_dropout", type=float, default=0.1)
        group.add_argument("--attn_dropout", type=float, default=0.1)
        group.add_argument("--max_relative_positions", type=int, default=0)
        parser.add_argument("--continuous_coords", action="store_true")
        parser.add_argument("--compute_confidence", action="store_true")
        parser.add_argument("--input_size", type=int, default=384)
        parser.add_argument("--vocab_file", type=str, default=None)
        parser.add_argument("--coord_bins", type=int, default=64)
        parser.add_argument("--sep_xy", action="store_true", default=True)
        args = parser.parse_args([])
        if args_states:
            for key, value in args_states.items():
                args.__dict__[key] = value
        return args

    def _get_model(self, args, tokenizer, device, states):
        encoder = Encoder(args, pretrained=False)
        args.encoder_dim = encoder.n_features
        decoder = Decoder(args, tokenizer)
        safe_load(encoder, states["encoder"])
        safe_load(decoder, states["decoder"])
        encoder.to(device)
        decoder.to(device)
        encoder.eval()
        decoder.eval()
        return encoder, decoder

    def predict_images(
        self,
        input_images: list,
        return_atoms_bonds=False,
        return_confidence=False,
        batch_size=16,
    ):
        device = self.device
        predictions = []
        self.decoder.compute_confidence = return_confidence

        # If a batch raises a tensor-shape mismatch (Swin/attention batch
        # inconsistency seen with certain checkpoints), fall back to per-image
        # prediction so one bad image does not waste a whole batch.
        def _decode_one(img):
            t = _preprocess_image(img, self.input_size).unsqueeze(0).to(device)
            with torch.no_grad():
                f, h = self.encoder(t)
                return self.decoder.decode(f, h)[0]

        for idx in range(0, len(input_images), batch_size):
            batch_images = input_images[idx : idx + batch_size]
            tensors = [_preprocess_image(img, self.input_size) for img in batch_images]
            images = torch.cat(tensors, dim=0).to(device)
            try:
                with torch.no_grad():
                    features, hiddens = self.encoder(images)
                    batch_predictions = self.decoder.decode(features, hiddens)
            except RuntimeError as exc:
                msg = str(exc)
                if "batch" in msg and ("tensor" in msg or "dimension" in msg):
                    logger.warning(
                        "MolScribe batch=%d failed (%s); falling back to per-image",
                        len(batch_images), msg,
                    )
                    batch_predictions = [_decode_one(img) for img in batch_images]
                else:
                    raise
            predictions += batch_predictions

        smiles = [pred["chartok_coords"]["smiles"] for pred in predictions]

        # chemistry.py 期望 numpy array (H, W, C)，不是 PIL Image
        images_np = []
        for img in input_images:
            if isinstance(img, Image.Image):
                images_np.append(np.array(img.convert("RGB")))
            else:
                images_np.append(np.array(img))

        smiles_list, molblock_list, r_success = convert_graph_to_smiles(
            [pred["chartok_coords"]["coords"] for pred in predictions],
            [pred["chartok_coords"]["symbols"] for pred in predictions],
            [pred["edges"] for pred in predictions],
            images=images_np,
            num_workers=self.num_workers,
        )

        outputs = []
        for smiles, molblock, pred in zip(smiles_list, molblock_list, predictions):
            pred_dict = {"smiles": smiles, "molfile": molblock}
            if return_confidence:
                pred_dict["confidence"] = pred["overall_score"]
            if return_atoms_bonds:
                coords = pred["chartok_coords"]["coords"]
                symbols = pred["chartok_coords"]["symbols"]
                atom_list = []
                for i, (symbol, coord) in enumerate(zip(symbols, coords)):
                    atom_dict = {"atom_symbol": symbol, "x": coord[0], "y": coord[1]}
                    if return_confidence:
                        atom_dict["confidence"] = pred["chartok_coords"]["atom_scores"][i]
                    atom_list.append(atom_dict)
                pred_dict["atoms"] = atom_list
                bond_list = []
                num_atoms = len(symbols)
                for i in range(num_atoms - 1):
                    for j in range(i + 1, num_atoms):
                        bond_type_int = pred["edges"][i][j]
                        if bond_type_int != 0:
                            bond_type_str = BOND_TYPES[bond_type_int]
                            bond_dict = {"bond_type": bond_type_str, "endpoint_atoms": (i, j)}
                            if return_confidence:
                                bond_dict["confidence"] = pred["edge_scores"][i][j]
                            bond_list.append(bond_dict)
                pred_dict["bonds"] = bond_list
            outputs.append(pred_dict)
        return outputs

    def predict_image(self, image, return_atoms_bonds=False, return_confidence=False):
        return self.predict_images(
            [image],
            return_atoms_bonds=return_atoms_bonds,
            return_confidence=return_confidence,
        )[0]

    def predict_image_file(self, image_file: str, return_atoms_bonds=False, return_confidence=False):
        image = Image.open(image_file)
        return self.predict_image(
            image,
            return_atoms_bonds=return_atoms_bonds,
            return_confidence=return_confidence,
        )
