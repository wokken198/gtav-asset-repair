"""Badge diffuse -> tangent-space normal map.

The height field is deliberately simple and deterministic:

    h = w_luma * percentile-normalised luma + w_mask * alpha

then a Gaussian blur, then central differences. Two details matter in practice:

* normalise luma inside the alpha mask only (transparent margins are black and
  would otherwise drag the 5th percentile down),
* flatten the margin to (128,128,255) after conversion, otherwise the atlas cell
  border keeps a slope and lights up as a rectangle around the glyph.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def load_rgba(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0


def height_field(rgba: np.ndarray, luma_weight: float = 0.7, mask_weight: float = 0.3,
                 blur: float = 1.2) -> np.ndarray:
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    has_alpha = bool(alpha.max() > 0.05)
    if has_alpha:
        inside = alpha > 0.09
        lo, hi = np.percentile(luma[inside], [5, 95]) if inside.sum() > 32 else (0.0, 1.0)
        lum = np.clip((luma - lo) / max(hi - lo, 1e-3), 0, 1)
        # alpha-gated height: transparent pixels stay flat instead of forming a box
        h = alpha * (luma_weight * lum + mask_weight)
    else:
        h = luma
    h = np.clip(h, 0, 1)
    if blur > 0:
        img = Image.fromarray((h * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(blur))
        h = np.asarray(img, np.float32) / 255.0
    return h


def normal_from_height(h: np.ndarray, strength: float = 6.5, flat_margin: bool = True) -> np.ndarray:
    gy, gx = np.gradient(h)
    nx, ny = -gx * strength, gy * strength
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.dstack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5]) * 255.0
    out = out.astype(np.uint8)
    if flat_margin:
        out[h <= 0.02] = (128, 128, 255)
    return out


def shade_preview(rgba: np.ndarray, normal: np.ndarray, light=(-0.4, -0.6, 0.7),
                  ambient: float = 0.35, diffuse: float = 0.85, spec: float = 0.0) -> np.ndarray:
    n = normal.astype(np.float32) / 127.5 - 1.0
    n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-5)
    lam = np.clip(n @ np.asarray(light, np.float32), 0, 1)[..., None]
    rgb = rgba[..., :3] * (ambient + diffuse * lam)
    if spec:
        rgb = rgb + spec * np.power(lam, 18)
    a = rgba[..., 3:4]
    return np.clip(rgb * a + (1 - a), 0, 1)


def contact_sheet(rows, out_path: str, cell: int = 300) -> None:
    """rows: list of (label, diffuse_rgb, normal_rgb, lit_rgb) PIL images."""
    sheet = Image.new("RGB", (cell * 3 + 24, len(rows) * (cell // 2 + 18) + 12), (26, 26, 26))
    y = 6
    for _, diff, norm, lit in rows:
        for i, im in enumerate((diff, norm, lit)):
            im = im.copy()
            im.thumbnail((cell - 10, cell // 2 - 6), Image.LANCZOS)
            sheet.paste(im, (6 + i * cell, y))
        y += cell // 2 + 18
    sheet.save(out_path)
