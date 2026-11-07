"""Depth-clipped visible-light single-scattering proxy for offline cameras.

This complements an RTX light's real surface footprint. It models a smooth
visible cone, bounded inverse-square illumination and extinction along the
source and camera paths. It is not spectral radiative transfer, a UV display,
or a source-shadow map. A UV inspection mode must supply its *visible pilot*
colour; invisible UV radiation must never be passed here as visible light.
"""
from __future__ import annotations

import math
import numpy as np


def _positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _rays(x, y, width, height, focal, aperture, rotation):
    """USD camera looks along local -Z; transform row vectors to world."""
    horizontal = (x / width - .5) * aperture / focal
    vertical = (.5 - y / height) * aperture * height / width / focal
    xx, yy = np.meshgrid(horizontal, vertical)
    local = np.stack((xx, yy, -np.ones_like(xx)), axis=-1)
    world = local @ rotation
    lengths = np.linalg.norm(world, axis=-1)
    if np.any(lengths < 1e-8):
        raise ValueError("camera_world has a singular camera rotation")
    return world / lengths[..., None], lengths


def _upsample(values, height, width):
    """Separable bilinear resize, requiring NumPy only."""
    source_h, source_w = values.shape
    x = np.clip((np.arange(width) + .5) * source_w / width - .5, 0., source_w - 1.)
    y = np.clip((np.arange(height) + .5) * source_h / height - .5, 0., source_h - 1.)
    x0, y0 = x.astype(np.intp), y.astype(np.intp)
    x1, y1 = np.minimum(x0 + 1, source_w - 1), np.minimum(y0 + 1, source_h - 1)
    wx, wy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
    horizontal = values[:, x0] * (1 - wx) + values[:, x1] * wx
    return horizontal[y0] * (1 - wy[:, None]) + horizontal[y1] * wy[:, None]


def _cone_visible_before_surface(rays, lengths, delta, axis, cosine):
    """Analytic finite camera-segment / forward-cone intersection mask.

    This full-resolution mask prevents bilinear upsampling from brightening
    foreground pixels whose first opaque surface ends before the beam.
    """
    hd = float(np.dot(delta, axis))
    vd = np.einsum("...i,i->...", rays, axis)
    lo = np.zeros_like(lengths)
    hi = lengths.copy()
    parallel = np.abs(vd) < 1e-8
    valid = (~parallel) | (hd > 0)
    division = np.divide(-hd, vd, out=np.zeros_like(vd), where=~parallel)
    lo = np.where(vd > 1e-8, np.maximum(lo, division), lo)
    hi = np.where(vd < -1e-8, np.minimum(hi, division), hi)
    valid &= hi > lo + 1e-6
    cosine2 = cosine * cosine
    a = vd * vd - cosine2
    b = 2 * (hd * vd - cosine2 * np.einsum("...i,i->...", rays, delta))
    c = hd * hd - cosine2 * float(np.dot(delta, delta))
    q_lo = (a * lo + b) * lo + c
    q_hi = (a * hi + b) * hi + c
    # A concave quadratic can intersect the cone between two outside endpoints.
    vertex = np.divide(-b, 2 * a, out=lo.copy(), where=np.abs(a) > 1e-8)
    vertex = np.clip(vertex, lo, np.maximum(lo, hi))
    q_vertex = (a * vertex + b) * vertex + c
    maximum = np.maximum(q_lo, q_hi)
    maximum = np.where(a < -1e-8, np.maximum(maximum, q_vertex), maximum)
    return valid & (maximum > 1e-10)


def add_visible_beam(image, depth, *, camera_world, focal_length_mm,
                     horizontal_aperture_mm, light_origin, light_direction,
                     half_angle_degrees, color_rgb, strength, visibility_m,
                     max_width=240, samples=28):
    """Add a subtle visible flashlight cone to an RGB uint8 camera image.

    ``depth`` is H×W metres of positive image-plane distance (USD local -Z),
    not Euclidean ray range. ``camera_world`` is a rigid USD row-vector 4×4
    transform, with translation in its last row. Lamp vectors are in world
    metres; ``color_rgb`` is its visible linear-RGB colour in [0,1].

    ``strength`` is an artistic exposure/scattering gain: approximately .3–1
    is useful with a normalized flashlight intensity. It does not represent
    calibrated watts. Zero returns an unchanged copy. Extinction is derived
    from the visibility assumption; scattering albedo=.55 and HG g=.20 are
    fixed illustrative parameters. Added radiance is bounded to .07 linear
    RGB, retaining scene detail rather than drawing an opaque cone.

    Camera rays stop at the first opaque surface. Positive infinity denotes
    open water; zero, negative and NaN depths receive no beam. Fine scene
    occluders are conservatively retained when depth is downsampled. The
    coarse integration is at most 240 pixels wide with 24–32 midpoint samples.
    Inputs are never mutated. Source-to-water shadows require the renderer.
    """
    image = np.asarray(image)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be H×W×3 RGB uint8")
    height, width = image.shape[:2]
    if not width or not height:
        raise ValueError("image dimensions must be nonzero")
    strength = float(strength)
    if not math.isfinite(strength) or strength < 0:
        raise ValueError("strength must be finite and nonnegative")
    if strength == 0:
        return image.copy()
    depth = np.asarray(depth, dtype=np.float32)
    if depth.shape != (height, width):
        raise ValueError("depth must match image height and width")
    focal = _positive(focal_length_mm, "focal_length_mm")
    aperture = _positive(horizontal_aperture_mm, "horizontal_aperture_mm")
    visibility = _positive(visibility_m, "visibility_m")
    angle = _positive(half_angle_degrees, "half_angle_degrees")
    if angle >= 85:
        raise ValueError("half_angle_degrees must be below 85")
    if isinstance(samples, bool) or int(samples) != samples or not 24 <= samples <= 32:
        raise ValueError("samples must be an integer from 24 to 32")
    if isinstance(max_width, bool) or int(max_width) != max_width or max_width < 1:
        raise ValueError("max_width must be a positive integer")
    matrix = np.asarray(camera_world, dtype=np.float32)
    origin = np.asarray(light_origin, dtype=np.float32)
    axis = np.asarray(light_direction, dtype=np.float32)
    colour = np.asarray(color_rgb, dtype=np.float32)
    if matrix.size != 16:
        raise ValueError("camera_world must contain a 4×4 transform")
    matrix = matrix.reshape(4, 4)
    if any(a.shape != (3,) for a in (origin, axis, colour)):
        raise ValueError("lamp origin, direction and colour must contain three components")
    if not all(np.all(np.isfinite(a)) for a in (matrix, origin, axis, colour)):
        raise ValueError("camera and lamp values must be finite")
    axis_length = float(np.linalg.norm(axis))
    if axis_length < 1e-8:
        raise ValueError("light_direction must be nonzero")
    if np.any(colour < 0) or np.any(colour > 1):
        raise ValueError("color_rgb must be linear RGB in [0,1]")
    if not np.any(colour):
        return image.copy()
    axis = axis / axis_length
    camera = matrix[3, :3]
    rotation = matrix[:3, :3]
    coarse_w = min(width, int(max_width), 240)
    coarse_h = max(1, int(round(height * coarse_w / width)))
    x_start = np.floor(np.arange(coarse_w) * width / coarse_w).astype(np.intp)
    y_start = np.floor(np.arange(coarse_h) * height / coarse_h).astype(np.intp)
    x_end = np.r_[x_start[1:], width]
    y_end = np.r_[y_start[1:], height]
    x_centres = (x_start + x_end).astype(np.float32) * .5
    y_centres = (y_start + y_end).astype(np.float32) * .5
    max_path = min(20., visibility * 2.)
    valid_depth = np.where(np.isnan(depth) | (depth <= 0), 0., np.minimum(depth, max_path))
    coarse_depth = np.minimum.reduceat(np.minimum.reduceat(valid_depth, y_start, axis=0), x_start, axis=1)
    rays, ray_scale = _rays(x_centres, y_centres, width, height, focal, aperture, rotation)
    path = np.minimum(coarse_depth * ray_scale, max_path)
    step = path / int(samples)
    energy = np.zeros((coarse_h, coarse_w), dtype=np.float32)
    beta = 3. / max(visibility, .001)
    beta_scatter = beta * .55
    outer_cosine = math.cos(math.radians(angle))
    inner_cosine = math.cos(math.radians(angle * .72))
    delta = camera - origin
    g = .20
    for index in range(int(samples)):
        travel = (index + .5) * step
        from_light = delta + rays * travel[..., None]
        distance2 = np.einsum("...i,...i->...", from_light, from_light)
        lamp_distance = np.sqrt(np.maximum(distance2, 1e-10))
        alignment = np.einsum("...i,i->...", from_light, axis) / lamp_distance
        edge = np.clip((alignment - outer_cosine) / (inner_cosine - outer_cosine), 0., 1.)
        cone = edge * edge * (3 - 2 * edge)
        # Incoming photon direction is source->sample, outgoing is sample->camera.
        cosine_scatter = -np.einsum("...i,...i->...", from_light, rays) / lamp_distance
        phase = (1 - g*g) / np.maximum(1 + g*g - 2*g*cosine_scatter, .1)**1.5
        transmittance = np.exp(-beta * (lamp_distance + travel))
        energy += cone * phase * transmittance * step / (distance2 + .12**2)
    # A nominal visible-source exposure of 3 keeps gain≈1 legible at typical
    # reef-camera distances. This scale is artistic, not calibrated power.
    energy *= np.float32(3. * beta_scatter * min(strength, 50.))
    if not np.any(energy > 1e-9):
        return image.copy()
    radiance = .07 * (-np.expm1(-np.minimum(energy, 80.)))
    radiance = _upsample(radiance, height, width)
    full_rays, full_scale = _rays(np.arange(width, dtype=np.float32) + .5,
                                  np.arange(height, dtype=np.float32) + .5,
                                  width, height, focal, aperture, rotation)
    full_path = np.minimum(valid_depth * full_scale, max_path)
    visible = _cone_visible_before_surface(full_rays, full_path, delta, axis, outer_cosine)
    radiance *= visible
    encoded = image.astype(np.float32) / 255.
    linear = np.where(encoded <= .04045, encoded / 12.92, ((encoded + .055) / 1.055)**2.4)
    linear = np.clip(linear + radiance[..., None] * colour, 0., 1.)
    encoded = np.where(linear <= .0031308, linear * 12.92, 1.055 * linear**(1/2.4) - .055)
    return np.clip(np.rint(encoded * 255.), 0, 255).astype(np.uint8)
