"""Export bundled CC0 scan/PBR assets for the offline Three.js laboratory.

No downloads. Binary meshes: uint32 vertex/index count, float32 positions,
float32 normals, float32 UVs, uint32 triangle indices. Y-up; unit radius;
original specimen aspect preserved. Texture downsampling does not alter UVs.
"""
from pathlib import Path
import gzip, json, math, struct
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/lab/assets'
OUT.mkdir(parents=True, exist_ok=True)

def mesh(src, name):
    data = json.load(gzip.open(ROOT / src, 'rt'))
    ratio = data['source_height'] / data['source_radius']
    p = [v for x,y,z in data['points'] for v in (x,z*ratio,-y)]
    n=[]
    for x,y,z in data['normals']:
        z/=ratio
        size=math.hypot(x,y,z) or 1
        n.extend((x/size,z/size,-y/size))
    uv=[v for row in data['uvs'] for v in row]
    indices=data['indices']
    with (OUT/name).open('wb') as f:
        f.write(struct.pack('<II',len(p)//3,len(indices)))
        for values,fmt in ((p,'f'),(n,'f'),(uv,'f'),(indices,'I')):
            f.write(struct.pack('<'+fmt*len(values),*values))

def texture(src, name, size=1024):
    im=Image.open(ROOT/src).convert('RGB')
    im.thumbnail((size,size),Image.Resampling.LANCZOS)
    im.save(OUT/name,quality=88,optimize=True)

mesh('assets/pocillopora/pocillopora_damicornis_20k.json.gz','pocillopora.bin')
mesh('assets/pocillopora/pocillopora_damicornis_hero.json.gz','pocillopora-hero.bin')
mesh('assets/corals/acropora_secale_15k.json.gz','acropora.bin')
for phenotype in ('tan','pink','violet','green','blue'):
    texture(f'assets/materials/pocillopora_tissue/healthy_{phenotype}_diffuse.jpg',f'healthy-{phenotype}.jpg')
texture('assets/materials/pocillopora_tissue/bleached_alive_tan_diffuse.jpg','bleached.jpg')
texture('assets/materials/pocillopora_tissue/dead_diffuse.jpg','dead.jpg')
texture('assets/pocillopora/pocillopora_normal.png','coral-normal.jpg')
texture('assets/materials/pocillopora_tissue/healthy_roughness.png','coral-roughness.jpg')
for kind in ('fine_sand','rubble'):
    for layer in ('diffuse','normal_gl','roughness'):
        texture(f'assets/materials/seabed/{kind}_{layer}.jpg',f'{kind}-{layer}.jpg')
texture('assets/materials/coral/coral_normal_gl.png','branch-normal.jpg')
texture('assets/corals/acropora_secale_basecolor.jpg','acropora-color.jpg')
texture('assets/corals/acropora_secale_normal.png','acropora-normal.jpg')
(OUT/'CREDITS.txt').write_text('''Coral morphology: Smithsonian Institution, National Museum of Natural History, with The Hydrous. Pocillopora damicornis USNM 46926 and Acropora secale USNM 268. Public-domain/CC0 specimen scans. Not a Smithsonian endorsement. Specimens are dried skeletons, not scans of living tissue or this scene.\nSand 03: Charlotte Baglioni / Poly Haven, CC0. Coral Ground 02: Rob Tuytel / Poly Haven, CC0.\nArtistic tissue maps and browser scene: PELAGIC. No biological recovery is inferred from appearance.\nOriginal source URLs, hashes and license details: assets/LICENSES.md, assets/pocillopora/manifest.json, assets/corals/manifest.json, assets/materials/manifest.json in the source repository.\nhttps://3d.si.edu/es/object/3d/pocillopora-damicornis:ae26ad01-e7be-4664-8a3a-b8bffd42a186\nhttps://polyhaven.com/a/sand_03\nhttps://polyhaven.com/a/coral_ground_02\n''')
print(f'Exported {len(list(OUT.iterdir()))} browser assets')
