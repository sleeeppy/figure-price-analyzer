"""DINOv2 embedder.

- Loads facebook/dinov2-large (1024-dim CLS token) onto MPS.
- Background removal via rembg before encoding (figure-only signal).
- Returns L2-normalized float32 vectors so L2 distance ≡ cosine distance.
"""
from __future__ import annotations
import io
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from config import DINOV2_MODEL, EMBED_DIM, TORCH_DEVICE


def _resolve_device(preferred: str) -> str:
    if preferred == "mps" and torch.backends.mps.is_available():
        return "mps"
    if preferred == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


class FigureEmbedder:
    _processor = None
    _model = None
    _device = None
    _rembg_session = None

    def __init__(self):
        if FigureEmbedder._model is None:
            device = _resolve_device(TORCH_DEVICE)
            print(f"[embedder] loading {DINOV2_MODEL} on {device}")
            FigureEmbedder._processor = AutoImageProcessor.from_pretrained(DINOV2_MODEL)
            FigureEmbedder._model = (
                AutoModel.from_pretrained(DINOV2_MODEL).to(device).eval()
            )
            FigureEmbedder._device = device

    # ---- preprocessing ----------------------------------------------------

    @staticmethod
    def _get_rembg_session():
        if FigureEmbedder._rembg_session is None:
            from rembg import new_session
            # u2net is the default; u2netp is lighter but lower quality.
            FigureEmbedder._rembg_session = new_session("u2net")
        return FigureEmbedder._rembg_session

    @classmethod
    def remove_background(cls, img: Image.Image) -> Image.Image:
        from rembg import remove
        rgba = remove(img.convert("RGBA"), session=cls._get_rembg_session())
        # Composite over white to avoid alpha-edge artifacts in the embedding.
        white = Image.new("RGB", rgba.size, (255, 255, 255))
        white.paste(rgba, mask=rgba.split()[3])
        return white

    # ---- encoding ---------------------------------------------------------

    @torch.no_grad()
    def embed_pil(self, img: Image.Image, *, remove_bg: bool = True) -> np.ndarray:
        if remove_bg:
            img = self.remove_background(img)
        else:
            img = img.convert("RGB")

        inputs = self._processor(images=img, return_tensors="pt").to(self._device)
        outputs = self._model(**inputs)
        # CLS token is the global descriptor for DINOv2.
        cls = outputs.last_hidden_state[:, 0, :].cpu().numpy()[0].astype(np.float32)
        n = float(np.linalg.norm(cls))
        if n > 0:
            cls /= n
        assert cls.shape == (EMBED_DIM,), f"unexpected dim {cls.shape}"
        return cls

    def embed_path(self, path: str, *, remove_bg: bool = True) -> np.ndarray:
        return self.embed_pil(Image.open(path), remove_bg=remove_bg)

    def embed_bytes(self, data: bytes, *, remove_bg: bool = True) -> np.ndarray:
        return self.embed_pil(Image.open(io.BytesIO(data)), remove_bg=remove_bg)

    # ---- multi-crop test-time augmentation -------------------------------
    # The query side often has very different framing than our MFC reference
    # set (which is uniformly full-body product shots). A close-up of just the
    # face/torso lives in a totally different region of CLS-feature space and
    # tanks recall. To bridge that, embed several crops of the query and merge
    # candidates by min-distance per figure downstream.

    @staticmethod
    def _bbox_from_alpha(rgba: Image.Image) -> tuple[int, int, int, int] | None:
        """Tightest bbox of the non-transparent figure region (used to crop
        before generating sub-crops, so '70% center crop' means '70% of the
        figure', not '70% of an arbitrary user photo with lots of padding')."""
        alpha = rgba.split()[3]
        bbox = alpha.getbbox()
        return bbox

    @classmethod
    def _multi_crops(cls, img_rgb: Image.Image) -> list[Image.Image]:
        """Return original + center-70% + center-50% + top-half + bottom-half.
        Each is a fresh PIL RGB image at whatever resolution; the HF processor
        will resize uniformly downstream.
        """
        W, H = img_rgb.size
        crops = [img_rgb]

        def center(pct: float) -> Image.Image:
            w, h = int(W * pct), int(H * pct)
            x = (W - w) // 2
            y = (H - h) // 2
            return img_rgb.crop((x, y, x + w, y + h))

        crops.append(center(0.7))
        crops.append(center(0.5))
        # Top half — likely face/upper body of a figure.
        crops.append(img_rgb.crop((0, 0, W, H // 2)))
        # Bottom half — likely outfit/base.
        crops.append(img_rgb.crop((0, H // 2, W, H)))
        return crops

    @torch.no_grad()
    def embed_pil_multi(self, img: Image.Image, *, remove_bg: bool = True) -> list[np.ndarray]:
        """Multi-crop test-time augmentation. Returns one normalized vector
        per crop. Cost: ~N × single-embed time (rembg runs once).

        Variants:
          0) full image, same pipeline as the index (rembg → composite on white,
             NO bbox-tighten). Crucial: keeps query↔index distance ≈ 0 for
             identical images so the merge step still ranks exact matches first.
          1) bbox-tight figure crop (cancels framing/zoom mismatch).
          2) tight center-70% of the figure.
          3) tight top half (face/upper body of close-ups).
          4) tight bottom half (outfit/base).
        """
        if remove_bg:
            rgba = self._rembg_to_rgba(img)
        else:
            rgba = img.convert("RGBA")

        # Variant 0 — match the index pipeline exactly.
        whole = Image.new("RGB", rgba.size, (255, 255, 255))
        whole.paste(rgba, mask=rgba.split()[3])

        # Tight figure crop, used as base for variants 1–4.
        bbox = self._bbox_from_alpha(rgba) or (0, 0, *rgba.size)
        tight_rgba = rgba.crop(bbox)
        tight = Image.new("RGB", tight_rgba.size, (255, 255, 255))
        tight.paste(tight_rgba, mask=tight_rgba.split()[3])

        W, H = tight.size

        def center(pct: float) -> Image.Image:
            w, h = int(W * pct), int(H * pct)
            x = (W - w) // 2
            y = (H - h) // 2
            return tight.crop((x, y, x + w, y + h))

        crops = [
            whole,                                       # 0: index-compatible
            tight,                                       # 1: bbox-tight
            center(0.7),                                 # 2: center 70%
            tight.crop((0, 0, W, H // 2)),               # 3: top half
            tight.crop((0, H // 2, W, H)),               # 4: bottom half
        ]

        vecs: list[np.ndarray] = []
        for c in crops:
            inputs = self._processor(images=c, return_tensors="pt").to(self._device)
            outputs = self._model(**inputs)
            cls = outputs.last_hidden_state[:, 0, :].cpu().numpy()[0].astype(np.float32)
            n = float(np.linalg.norm(cls))
            if n > 0:
                cls /= n
            vecs.append(cls)
        return vecs

    @classmethod
    def _rembg_to_rgba(cls, img: Image.Image) -> Image.Image:
        from rembg import remove
        return remove(img.convert("RGBA"), session=cls._get_rembg_session())

    def embed_bytes_multi(self, data: bytes, *, remove_bg: bool = True) -> list[np.ndarray]:
        return self.embed_pil_multi(Image.open(io.BytesIO(data)), remove_bg=remove_bg)


# Module-level singleton for convenience in FastAPI dependency injection.
_singleton: FigureEmbedder | None = None


def get_embedder() -> FigureEmbedder:
    global _singleton
    if _singleton is None:
        _singleton = FigureEmbedder()
    return _singleton
