"""Preserve the source scan's original geometry, normals and texture seams.

Offline conversion only: trimesh, DracoPy and NumPy. No simplification or
nearest-vertex UV transfer is performed. Runtime reads the bundled gzip JSON.
"""
from pathlib import Path
import gzip
import hashlib
import json
import numpy as np
import trimesh

root = Path(__file__).resolve().parent
source = root / "usnm_46926-source.glb"
mesh = trimesh.load(source, force="scene").to_geometry()
points = mesh.vertices.copy()
low, high = points.min(axis=0), points.max(axis=0)
points[:,:2] -= (low[:2]+high[:2])/2
points[:,2] -= low[2]
radius = np.linalg.norm(points[:,:2],axis=1).max()
height = points[:,2].max()
points[:,:2] /= radius
points[:,2] /= height
normals = mesh.vertex_normals.copy()
bad = np.linalg.norm(normals,axis=1) < 1e-12
if bad.any():
    by_position = {tuple(np.round(p,8)):n for p,n,invalid in zip(mesh.vertices,normals,bad) if not invalid}
    for i in np.flatnonzero(bad):
        normals[i] = by_position.get(tuple(np.round(mesh.vertices[i],8)),(0.,0.,1.))
normals[:,:2] *= radius
normals[:,2] *= height
normals /= np.linalg.norm(normals,axis=1)[:,None]
uv = np.asarray(mesh.visual.uv)
texture = np.asarray(mesh.visual.material.baseColorTexture.convert("RGB"))
x = np.clip(np.rint(uv[:,0]*(texture.shape[1]-1)).astype(int),0,texture.shape[1]-1)
y = np.clip(np.rint((1-uv[:,1])*(texture.shape[0]-1)).astype(int),0,texture.shape[0]-1)
data = {"asset":"pocillopora_damicornis_hero","source_specimen":"USNM 46926",
        "source_radius":float(radius),"source_height":float(height),
        "source_bounds_m":mesh.bounds.tolist(),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "conversion":"original full-resolution geometry and UV seams retained; no simplification",
        "points":np.round(points,7).tolist(),"normals":np.round(normals,7).tolist(),
        "colors":np.round(texture[y,x]/255.,5).tolist(),"uvs":np.round(uv,7).tolist(),
        "counts":[3]*len(mesh.faces),"indices":mesh.faces.ravel().tolist()}
target = root / "pocillopora_damicornis_hero.json.gz"
target.write_bytes(gzip.compress(json.dumps(data,separators=(",",":"),allow_nan=False).encode(),compresslevel=9,mtime=0))
print(json.dumps({"vertices":len(points),"triangles":len(mesh.faces),"bytes":target.stat().st_size,
                  "radius":radius,"height":height}))
