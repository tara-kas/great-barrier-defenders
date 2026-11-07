"""Optional one-time conversion; requires trimesh, scipy and fast_simplification.

Not imported at runtime. Source GLB is the unmodified Smithsonian download.
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
source = root / 'usnm_268-source.glb'
original = trimesh.load(source, force='scene').to_geometry()
# Remove the rectangular museum plinth, retaining the coral stalk above it.
keep = (original.vertices[original.faces, 2] >= .041).all(axis=1)
working = trimesh.Trimesh(original.vertices, original.faces[keep], process=True)
working.merge_vertices(merge_tex=True, merge_norm=True)
v, f = fast_simplification.simplify(working.vertices, working.faces,
                                   target_count=15000, agg=7)
mesh = trimesh.Trimesh(v, f, process=True)
_, nearest = cKDTree(original.vertices).query(mesh.vertices)
uv = np.asarray(original.visual.uv)[nearest]
image = original.visual.material.baseColorTexture.convert('RGB')
pixels = np.asarray(image)
x = np.clip(np.rint(uv[:, 0] * (image.width - 1)).astype(int), 0, image.width - 1)
y = np.clip(np.rint((1 - uv[:, 1]) * (image.height - 1)).astype(int), 0, image.height - 1)
colors = pixels[y, x] / 255.
p = mesh.vertices.copy()
low, high = p.min(axis=0), p.max(axis=0)
p[:, :2] -= (low[:2] + high[:2]) / 2
p[:, 2] -= low[2]
radius, height = np.linalg.norm(p[:, :2], axis=1).max(), p[:, 2].max()
p[:, :2] /= radius
p[:, 2] /= height
normals = mesh.vertex_normals.copy()
normals[:, :2] *= radius
normals[:, 2] *= height
normals /= np.linalg.norm(normals, axis=1)[:, None]
data = {'asset': 'acropora_secale', 'source_specimen': 'USNM 268',
        'source_radius': float(radius), 'source_height': float(height),
        'pedestal_trim_z': .041,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'points': np.round(p, 7).tolist(), 'normals': np.round(normals, 7).tolist(),
        'colors': np.round(colors, 5).tolist(), 'uvs': np.round(uv, 7).tolist(),
        'counts': [3] * len(mesh.faces), 'indices': mesh.faces.ravel().tolist()}
(root / 'acropora_secale_15k.json.gz').write_bytes(gzip.compress(
    json.dumps(data, separators=(',', ':')).encode(), compresslevel=9, mtime=0))
image.save(root / 'acropora_secale_basecolor.jpg', quality=92)
original.visual.material.normalTexture.save(root / 'acropora_secale_normal.png')
print('vertices', len(p), 'triangles', len(mesh.faces), 'radius', radius, 'height', height)
