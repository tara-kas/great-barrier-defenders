"""Approximate underwater image formation; no claim of calibrated seawater optics."""
from __future__ import annotations

import io


def underwater_image(rgb, depth, visibility=4.0, seed=0, *, attenuation_rgb=None, backscatter_rgb=None):
    """Channel-dependent Beer–Lambert transmission and veiling backscatter.

    depth is axial renderer depth in metres, approximating range. RGB input
    is renderer sRGB; this model converts to linear light before attenuation.
    Synthetic depth is not a simulated real underwater RGB-D sensor.
    """
    import numpy as np

    color = np.asarray(rgb)[..., :3].astype(np.float32) / 255.0
    linear = np.where(color <= 0.04045, color / 12.92, ((color + .055) / 1.055) ** 2.4)
    distance = np.asarray(depth, dtype=np.float32).squeeze()
    if distance.shape != color.shape[:2]:
        raise ValueError("Depth and RGB resolution must match")
    distance = np.nan_to_num(distance, nan=30., posinf=30., neginf=0.)
    distance = np.clip(distance, 0., 30.)[..., None]
    visibility = max(.3, float(visibility))
    coefficients = np.array(attenuation_rgb if attenuation_rgb is not None else [.62, .23, .15], dtype=np.float32) * (4. / visibility)
    transmission = np.exp(-distance * coefficients)
    water_light = np.array(backscatter_rgb if backscatter_rgb is not None else [.012, .105, .12], dtype=np.float32)
    image = linear * transmission + water_light * (1. - transmission)
    image += np.random.default_rng(seed).normal(0., .0015, image.shape)
    image = np.clip(image, 0., 1.)
    srgb = np.where(image <= .0031308, image * 12.92, 1.055 * image ** (1 / 2.4) - .055)
    return np.uint8(np.clip(srgb * 255., 0., 255.))


def png_bytes(rgb):
    from PIL import Image
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return buffer.getvalue()
