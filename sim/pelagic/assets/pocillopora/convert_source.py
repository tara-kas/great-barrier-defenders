"""Optional offline conversion of the unmodified Smithsonian USNM 46926 GLB.

Requires trimesh, DracoPy, numpy, scipy and fast_simplification only during
conversion. The simulator uses the resulting standard-library JSON/gzip mesh.
"""
from pathlib import Path
import gzip
import hashlib
import json
import numpy as np
import trimesh
import fast_simplification
from scipy.spatial import cKDTree


root = Path(__file__).resolve().parent
source = root / "usnm_46926-source.glb"
original = trimesh.load(source, force="scene").to_geometry()
# The specimen is a complete compact branching skeleton, without an artificial
# mounting plinth. Keep its whole original geometry; no height trimming.
working = trimesh.Trimesh(original.vertices, original.faces, process=True)
working.merge_vertices(merge_tex=True, merge_norm=True)
vertices, faces = fast_simplification.simplify(working.vertices, working.faces,
                                             target_count=20000, agg=7)
mesh = trimesh.Trimesh(vertices, faces, process=True)
mesh.update_faces(mesh.nondegenerate_faces())
mesh.remove_unreferenced_vertices()
# QEM leaves a handful of isolated 2–4 triangle artefacts; retain the connected
# whole colony rather than scattering those tiny pieces around the seabed.
mesh = max(mesh.split(only_watertight=False), key=lambda part: len(part.faces))
_, nearest = cKDTree(original.vertices).query(mesh.vertices)
uv = np.asarray(original.visual.uv)[nearest]
base_color = original.visual.material.baseColorTexture.convert("RGB")
pixels = np.asarray(base_color)
x = np.clip(np.rint(uv[:, 0] * (base_color.width - 1)).astype(int), 0, base_color.width - 1)
y = np.clip(np.rint((1 - uv[:, 1]) * (base_color.height - 1)).astype(int), 0, base_color.height - 1)
colors = pixels[y, x] / 255.
points = mesh.vertices.copy()
low, high = points.min(axis=0), points.max(axis=0)
points[:, :2] -= (low[:2] + high[:2]) / 2
points[:, 2] -= low[2]
radius = np.linalg.norm(points[:, :2], axis=1).max()
height = points[:, 2].max()
points[:, :2] /= radius
points[:, 2] /= height
normals = mesh.vertex_normals.copy()
bad = np.linalg.norm(normals, axis=1) < 1e-12
normals[bad] = original.vertex_normals[nearest[bad]]
bad = np.linalg.norm(normals, axis=1) < 1e-12
normals[bad] = (0., 0., 1.)
normals[:, :2] *= radius
normals[:, 2] *= height
normals /= np.linalg.norm(normals, axis=1)[:, None]
data = {
    "asset": "pocillopora_damicornis", "source_specimen": "USNM 46926",
    "source_radius": float(radius), "source_height": float(height),
    "source_bounds_m": original.bounds.tolist(), "trim": "none; whole specimen, no museum plinth",
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "points": np.round(points, 7).tolist(), "normals": np.round(normals, 7).tolist(),
    "colors": np.round(colors, 5).tolist(), "uvs": np.round(uv, 7).tolist(),
    "counts": [3] * len(mesh.faces), "indices": mesh.faces.ravel().tolist(),
}
(root / "pocillopora_damicornis_20k.json.gz").write_bytes(gzip.compress(
    json.dumps(data, separators=(",", ":"), allow_nan=False).encode(), compresslevel=9, mtime=0))
base_color.save(root / "pocillopora_basecolor.jpg", quality=94)
original.visual.material.normalTexture.save(root / "pocillopora_normal.png")
print(json.dumps({"vertices": len(points), "triangles": len(mesh.faces), "radius_m": radius,
                  "height_m": height, "height_radius_ratio": height / radius}))
