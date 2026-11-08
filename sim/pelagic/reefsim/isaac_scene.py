"""Procedural OpenUSD reef renderer for Isaac Sim 6.0.

Import this module only *after* ``SimulationApp`` is running.  The mission core
integrates the vehicle dynamics; this adapter renders its state.  In particular,
the ROVs and their arms are visual kinematic models, not PhysX articulations.
No runtime asset downloads, proprietary motion planners, or external extensions
are required. Bundled assets supply reef detail. Dimensions are metres, Z-up.
"""

from __future__ import annotations

import math
import copy
import random
import re
from pathlib import Path
from typing import Any

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, Vt
from .organic import generate_coral, generate_fragment
from .reef_landscape import build_reef_scenery, build_reef_foundation
from .reef_quality import plan_reef_quality, generate_quality_coral
from .fauna import build_fauna, fauna_pose
from .scanned_coral import generate_scanned_coral
from .inspection import MODES, beam_exposure, inspection_response, auto_inspection_mode
from .uv_detection import mission_profile, scan_light_pose, beam_unoccluded
from .reef_motion import generate_soft_coral, current_pose
from .polyp_motion import generate_polyp_patch, polyp_current_pose
from .reef_tissue import material_files as tissue_maps, tissue_color
from .reef_substrate import generate_reef_rock
from .pocillopora import generate_pocillopora, generate_contact_fragment
from .pocillopora_scan import generate_pocillopora_scan, texture_files as pocillopora_textures


def _name(value: Any) -> str:
    """Stable valid USD identifiers, including IDs which begin with digits."""
    result = re.sub(r"[^a-zA-Z0-9_]", "_", str(value))
    return result if result and not result[0].isdigit() else "item_" + result


def _v(value: Any, fallback=(0.0, 0.0, 0.0)) -> Gf.Vec3d:
    try:
        return Gf.Vec3d(*(float(x) for x in value[:3]))
    except (TypeError, ValueError, IndexError):
        return Gf.Vec3d(*fallback)


def _color(value) -> Gf.Vec3f:
    return Gf.Vec3f(*(float(x) for x in value))


def _mix(a, b, t):
    return tuple(a[i] * (1.0 - t) + b[i] * t for i in range(3))


def _wrist_offset(robot, offset):
    """Rotate a tool-local offset into body coordinates; wrist_yaw is radians."""
    angle = float(robot.get("wrist_yaw", 0.))
    c, s = math.cos(angle), math.sin(angle)
    return Gf.Vec3d(c*offset[0]-s*offset[1], s*offset[0]+c*offset[1], offset[2])


class _Mesh:
    """Small asset-free mesh builder; batches branches into a single USD mesh."""

    def __init__(self):
        self.points: list[tuple[float, float, float]] = []
        self.counts: list[int] = []
        self.indices: list[int] = []
        self.colors: list[tuple[float, float, float]] = []
        self.uvs: list[tuple[float, float]] = []

    def face(self, vertices, color, vertex_colors=None, vertex_uvs=None):
        start = len(self.points)
        self.points.extend(tuple(float(v) for v in p) for p in vertices)
        self.counts.append(len(vertices))
        self.indices.extend(range(start, start + len(vertices)))
        self.colors.extend(vertex_colors if vertex_colors is not None else [color] * len(vertices))
        self.uvs.extend(vertex_uvs if vertex_uvs is not None else [(float(p[0]) / 2, float(p[1]) / 2) for p in vertices])

    def tube(self, start, end, radius, color, tip_radius=None, sides=7):
        start, end = _v(start), _v(end)
        axis = end - start
        if axis.GetLength() < 1e-8:
            return
        axis.Normalize()
        reference = Gf.Vec3d(0, 0, 1) if abs(axis[2]) < 0.9 else Gf.Vec3d(0, 1, 0)
        u = Gf.Cross(axis, reference).GetNormalized()
        v = Gf.Cross(axis, u).GetNormalized()
        tip_radius = radius * 0.65 if tip_radius is None else tip_radius
        lower, upper = [], []
        for i in range(sides):
            offset = u * math.cos(2 * math.pi * i / sides) + v * math.sin(2 * math.pi * i / sides)
            lower.append(start + offset * radius)
            upper.append(end + offset * tip_radius)
        for i in range(sides):
            j = (i + 1) % sides
            shade = tuple(c * (0.85 + 0.15 * i / max(1, sides - 1)) for c in color)
            self.face((lower[i], lower[j], upper[j], upper[i]), shade)
        self.face(tuple(reversed(lower)), color)
        self.face(upper, _mix(color, (0.9, 0.92, 0.82), 0.18))

    def ellipsoid(self, center, radii, color, rings=8, sectors=14, brain=False):
        center = _v(center)
        for row in range(rings):
            a0, a1 = math.pi * row / rings, math.pi * (row + 1) / rings
            for col in range(sectors):
                b0, b1 = 2 * math.pi * col / sectors, 2 * math.pi * (col + 1) / sectors
                vertices = []
                for a, b in ((a0, b0), (a0, b1), (a1, b1), (a1, b0)):
                    pattern = 1.0 + (0.08 * math.sin(15 * a + 3 * math.sin(4 * b)) if brain else 0.0)
                    vertices.append(center + Gf.Vec3d(
                        radii[0] * math.sin(a) * math.cos(b) * pattern,
                        radii[1] * math.sin(a) * math.sin(b) * pattern,
                        radii[2] * math.cos(a) * pattern,
                    ))
                variation = 0.8 + 0.2 * math.sin(a0) ** 2
                circumference = math.tau * (radii[0] + radii[1]) * .5
                arc = math.pi * (radii[0] + radii[2]) * .5
                uvs = [(b / math.tau * circumference / 2, a / math.pi * arc / 2)
                       for a, b in ((a0, b0), (a0, b1), (a1, b1), (a1, b0))]
                self.face(vertices, tuple(x * variation for x in color), vertex_uvs=uvs)

    def author(self, stage, path, material=None, collision=False):
        mesh = UsdGeom.Mesh.Define(stage, path)
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in self.points]))
        mesh.CreateFaceVertexCountsAttr(self.counts)
        mesh.CreateFaceVertexIndicesAttr(self.indices)
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex).Set(
            Vt.Vec3fArray([_color(c) for c in self.colors])
        )
        # Old batched meshes duplicate face vertices. Average their normals by
        # shared position so rocks and sediment do not look like flat polygons.
        sums = {}
        cursor = 0
        for count in self.counts:
            ids = self.indices[cursor:cursor + count]
            cursor += count
            if count < 3:
                continue
            a, b, c = (_v(self.points[i]) for i in ids[:3])
            normal = Gf.Cross(b - a, c - a)
            for index in ids:
                key = tuple(round(x, 6) for x in self.points[index])
                sums[key] = sums.get(key, Gf.Vec3d(0)) + normal
        normals = []
        for point in self.points:
            normal = sums.get(tuple(round(x, 6) for x in point), Gf.Vec3d(0, 0, 1))
            normals.append(Gf.Vec3f(normal.GetNormalized()) if normal.GetLength() > 1e-8 else Gf.Vec3f(0, 0, 1))
        mesh.CreateNormalsAttr(Vt.Vec3fArray(normals))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
            UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in self.uvs]))
        if self.points:
            mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(mesh.GetPointsAttr().Get()))
        if material:
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
        if collision:
            UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        return mesh


class IsaacReefScene:
    """Render a :class:`ReefSimulation` snapshot in an existing USD stage.

    Public cameras: ``/World/Cameras/Overview``, ``/World/Cameras/ROV`` (survey
    camera), ``/World/Cameras/Chase``, ``/World/Cameras/Top``. ``set_camera`` also selects a viewport, when one
    exists. The renderer remains usable in headless mode without a viewport.
    """

    CAMERA_PATHS = {
        "overview": "/World/Cameras/Overview",
        "rov": "/World/Cameras/ROV",
        "chase": "/World/Cameras/Chase",
        "top": "/World/Cameras/Top",
        "director": "/World/Cameras/Director",
        "scout": "/World/Cameras/ScoutOptical",
        "worker": "/World/Cameras/WorkerTool",
    }

    def __init__(self, stage, config: dict):
        self.stage = stage
        self.config = config
        self.materials = {}
        self.robots = {}
        self.corals = {}
        self.fragments = {}
        self.scenery = []
        self.fauna = []
        self.scanned_colony_count = 0
        self.camera_mode = "overview"
        self._camera_ops = {}
        self._rng = random.Random(config.get("seed", 42) + 771)
        self._last_water = None
        self._last_time = -1.0
        self._particles = None
        self._particle_origins = []
        self._particle_speeds = []
        self._built = False
        self._director_key = None
        self._director_angle = None
        self.inspection_profiles = {}
        self._inspection_surfaces = {}
        self._inspection_enabled = bool(config.get("inspection", {}).get("enabled", False))
        self._inspection_mode = config.get("inspection", {}).get("mode", "white") if self._inspection_enabled else "off"
        self._inspection_target = None
        self._inspection_strength = 1.
        self._inspection_snapshot = None
        self._inspection_info = {}
        self._inspection_beam = None
        self._observer_torch = None
        self._soft_corals = []
        self._polyp_patches = []
        self._motion_info = {}
        self._last_soft_time = -1.

    def _material(self, name, color, roughness=0.65, metallic=0.0, emission=None,
                  opacity=1.0, vertex_color=False):
        material = UsdShade.Material.Define(self.stage, "/World/Looks/" + _name(name))
        shader = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild("Surface"))
        shader.CreateIdAttr("UsdPreviewSurface")
        diffuse = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
        if vertex_color:
            reader = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild("VertexColor"))
            reader.CreateIdAttr("UsdPrimvarReader_float3")
            reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("displayColor")
            reader.CreateOutput("result", Sdf.ValueTypeNames.Float3)
            diffuse.ConnectToSource(reader.ConnectableAPI(), "result")
        else:
            diffuse.Set(_color(color))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        if emission:
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(_color(emission))
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        self.materials[name] = material
        return material

    def _bind(self, obj, material):
        UsdShade.MaterialBindingAPI.Apply(obj.GetPrim()).Bind(self.materials[material])
        return obj

    def _surface_maps(self, material_name, directory, prefix, diffuse=True, normal_strength=.65):
        """Local PBR maps; renderer never downloads textures during a run."""
        material = self.materials[material_name]
        surface = UsdShade.Shader.Get(self.stage, material.GetPath().AppendChild("Surface"))
        uv = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild("UV"))
        uv.CreateIdAttr("UsdPrimvarReader_float2")
        uv.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        uv.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        assets = Path(__file__).resolve().parent.parent / "assets" / "materials" / directory
        maps = (("diffuseColor", "diffuse", "rgb", "sRGB"),
                ("roughness", "roughness", "r", "raw"),
                ("normal", "normal_gl", "rgb", "raw"))
        for input_name, suffix, channel, color_space in maps:
            if input_name == "diffuseColor" and not diffuse:
                continue
            candidates = [assets / f"{prefix}_{suffix}.{ext}" for ext in ("jpg", "png")]
            filename = next((p for p in candidates if p.exists()), None)
            if filename is None:
                raise FileNotFoundError(f"Required offline material asset missing: {candidates[0]}")
            texture = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild(input_name + "Texture"))
            texture.CreateIdAttr("UsdUVTexture")
            texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(filename)))
            texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(color_space)
            texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
            texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
            texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
            output_type = Sdf.ValueTypeNames.Float if channel == "r" else Sdf.ValueTypeNames.Float3
            texture.CreateOutput(channel, output_type)
            if input_name == "normal":
                surface.CreateInput("normal", Sdf.ValueTypeNames.Normal3f)
                texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2 * normal_strength, 2 * normal_strength, 2, 1))
                texture.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-normal_strength, -normal_strength, -1, 0))
            surface.GetInput(input_name).ConnectToSource(texture.ConnectableAPI(), channel)

    def _organic_mesh(self, path, morphology, health, radius, height, seed, collision=False, detail="full"):
        data = generate_coral(morphology, health, radius, height, seed, detail=detail)
        if self.config.get("render", {}).get("realistic_tissue", False):
            pigment = tissue_color(health, seed)
            mean = sum(sum(c)/3 for c in data["colors"])/len(data["colors"])
            data["colors"] = [tuple(min(1., p*(.70+.30*(sum(c)/3)/max(mean,.02)))
                                    for p in pigment) for c in data["colors"]]
        return self._mesh_data(path, data, collision)

    def _tissue_texture_inputs(self, name, health, phenotype=None):
        """UV-aligned scanned calice detail and patchy living-tissue albedo."""
        maps = tissue_maps(health, phenotype)
        material = self.materials[name]
        surface = UsdShade.Shader.Get(self.stage, material.GetPath().AppendChild("Surface"))
        surface.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
        surface.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.025))
        surface.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(0.)
        uv = UsdShade.Shader.Get(self.stage, material.GetPath().AppendChild("UV"))
        for key, channel, space in (("diffuse", "rgb", "sRGB"), ("roughness", "r", "raw"), ("normal", "rgb", "raw")):
            input_name = "diffuseColor" if key == "diffuse" else key
            texture = UsdShade.Shader.Define(self.stage, material.GetPath().AppendChild(input_name + "Texture"))
            texture.CreateIdAttr("UsdUVTexture")
            texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(maps[key]))
            texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(space)
            texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
            texture.CreateOutput(channel, Sdf.ValueTypeNames.Float3 if channel == "rgb" else Sdf.ValueTypeNames.Float)
            if key == "normal":
                texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(1.5,1.5,2,1))
                texture.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-.75,-.75,-1,0))
            surface.GetInput(input_name).ConnectToSource(texture.ConnectableAPI(), channel)

    def _bind_tissue(self, mesh, health, phenotype="tan"):
        name = "tissue_" + health + "_" + phenotype
        if name not in self.materials:
            self._material(name, (1.,1.,1.), roughness=.85)
            self._surface_maps(name, "coral", "coral", diffuse=False)
            self._tissue_texture_inputs(name, health, phenotype)
        self._bind(mesh, name)

    def _mesh_data(self, path, data, collision=False):
        mesh = UsdGeom.Mesh.Define(self.stage, path)
        mesh.CreatePointsAttr(Vt.Vec3fArray([_color(p) for p in data["points"]]))
        mesh.CreateFaceVertexCountsAttr(data["counts"])
        mesh.CreateFaceVertexIndicesAttr(data["indices"])
        mesh.CreateNormalsAttr(Vt.Vec3fArray([_color(n) for n in data["normals"]]))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex).Set(Vt.Vec3fArray([_color(c) for c in data["colors"]]))
        UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
            UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in data["uvs"]]))
        mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(mesh.GetPointsAttr().Get()))
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(self.materials["organic"])
        if collision:
            UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        return mesh

    def _xform(self, path, position=(0, 0, 0), scale=None, rotation=None):
        obj = UsdGeom.Xform.Define(self.stage, path)
        obj.AddTranslateOp().Set(_v(position))
        if rotation is not None:
            obj.AddRotateXYZOp().Set(_color(rotation))
        if scale is not None:
            obj.AddScaleOp().Set(_color(scale))
        return obj

    def _sphere(self, path, position, scale, material):
        sphere = UsdGeom.Sphere.Define(self.stage, path)
        sphere.CreateRadiusAttr(1.0)
        sphere.AddTranslateOp().Set(_v(position))
        sphere.AddScaleOp().Set(_color(scale))
        return self._bind(sphere, material)

    def _cube(self, path, position, scale, material):
        cube = UsdGeom.Cube.Define(self.stage, path)
        cube.CreateSizeAttr(1.0)
        cube.AddTranslateOp().Set(_v(position))
        cube.AddScaleOp().Set(_color(scale))
        return self._bind(cube, material)

    def _cylinder(self, path, start, end, radius, material):
        cylinder = UsdGeom.Cylinder.Define(self.stage, path)
        cylinder.CreateRadiusAttr(float(radius))
        cylinder.CreateAxisAttr(UsdGeom.Tokens.z)
        cylinder.CreateHeightAttr(1.0)
        translate = cylinder.AddTranslateOp()
        orient = cylinder.AddOrientOp()
        scale = cylinder.AddScaleOp()
        self._set_cylinder((translate, orient, scale), start, end)
        self._bind(cylinder, material)
        return (translate, orient, scale)

    @staticmethod
    def _set_cylinder(ops, start, end):
        start, end = _v(start), _v(end)
        delta = end - start
        length = max(1e-6, delta.GetLength())
        rotation = Gf.Rotation(Gf.Vec3d(0, 0, 1), delta / length)
        ops[0].Set((start + end) * 0.5)
        quat = rotation.GetQuat()
        ops[1].Set(Gf.Quatf(float(quat.GetReal()), Gf.Vec3f(quat.GetImaginary())))
        ops[2].Set(Gf.Vec3f(1, 1, length))

    def _line(self, path, points, material, width=0.012):
        curve = UsdGeom.BasisCurves.Define(self.stage, path)
        curve.CreateTypeAttr(UsdGeom.Tokens.linear)
        curve.CreateWrapAttr(UsdGeom.Tokens.nonperiodic)
        curve.CreatePointsAttr(Vt.Vec3fArray([_color(p) for p in points]))
        curve.CreateCurveVertexCountsAttr([len(points)])
        curve.CreateWidthsAttr([width])
        curve.SetWidthsInterpolation(UsdGeom.Tokens.constant)
        self._bind(curve, material)
        return curve

    @staticmethod
    def _circle(center, radius, z=0.04, count=48):
        return [(center[0] + radius * math.cos(i * 2 * math.pi / count),
                 center[1] + radius * math.sin(i * 2 * math.pi / count), z)
                for i in range(count + 1)]

    def build(self, snapshot: dict) -> None:
        """Author a complete reef; rebuild our /World subtree on reset.

        Render products live outside /World and keep references to the stable
        camera paths, so a runner can rebuild without recreating annotators.
        """
        if self._built:
            self.stage.RemovePrim("/World")
            configuration = dict(self.config)
            configuration["seed"] = snapshot.get("seed", configuration.get("seed", 42))
            self.__init__(self.stage, configuration)
        UsdGeom.SetStageUpAxis(self.stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(self.stage, 1.0)
        world = UsdGeom.Xform.Define(self.stage, "/World")
        self.stage.SetDefaultPrim(world.GetPrim())
        for scope in ("Looks", "Environment", "Corals", "Robots", "Telemetry", "Cameras", "Fragments", "DonorStems"):
            UsdGeom.Scope.Define(self.stage, "/World/" + scope)
        world.GetPrim().SetCustomDataByKey("reefsim:simulation", "external-reduced-dynamics")
        world.GetPrim().SetCustomDataByKey("reefsim:arm", "kinematic-visual-proxy")
        self._make_materials()
        self._make_environment(snapshot)
        for i, coral in enumerate(snapshot.get("corals", [])):
            self._make_coral(coral, i)
        self._make_fragments(snapshot)
        for i, robot in enumerate(snapshot.get("robots", [])):
            self._make_robot(robot, i)
        self._make_cameras(snapshot)
        self._built = True
        self.update(snapshot)
        self.set_camera("overview", snapshot)

    def _make_materials(self):
        self._material("organic", (0.3, 0.5, 0.45), vertex_color=True, roughness=0.85)
        self._material("living_tissue", (.75, .69, .60), vertex_color=True, roughness=.86)
        self._material("sand", (0.36, 0.41, 0.29), vertex_color=True, roughness=0.97)
        self._material("rock", (0.11, 0.19, 0.17), vertex_color=True, roughness=0.95)
        self._material("white", (0.64, 0.76, 0.72), roughness=0.36, metallic=0.15)
        self._material("dark", (0.012, 0.025, 0.03), roughness=0.42)
        self._material("metal", (0.13, 0.23, 0.24), roughness=0.3, metallic=0.8)
        self._material("survey", (0.02, 0.52, 0.54), roughness=0.3, metallic=0.2)
        self._material("restore", (0.93, 0.48, 0.085), roughness=0.4, metallic=0.15)
        self._material("cyan_light", (0.015, 0.32, 0.35), emission=(0.01, 0.25, 0.28))
        self._material("amber_light", (0.6, 0.28, 0.025), emission=(0.8, 0.30, 0.03))
        self._material("blue_light", (0.035, 0.16, 0.32), emission=(0.015, 0.14, 0.42))
        self._material("lamp", (0.8, 0.92, 0.9), emission=(4, 4.6, 4.4))
        self._material("glass", (0.015, 0.045, 0.055), roughness=0.06, metallic=0.75)
        # A warm living tissue tint stays distinguishable from the dark jaws
        # and algal skeletons at the tool light's short working range.
        self._material("fragment", (0.66, 0.34, 0.24), roughness=0.78)
        self._material("snow", (0.38, 0.48, 0.44), opacity=.48, roughness=1)
        self._material("water_surface", (0.025, 0.27, 0.31), roughness=0.12,
                       metallic=0.4, opacity=0.18)
        self._material("grass", (0.09, 0.23, 0.14), vertex_color=True, roughness=0.95)
        self._surface_maps("sand", "seabed", "fine_sand", normal_strength=.8)
        self._surface_maps("rock", "seabed", "rubble", normal_strength=.6)
        self._surface_maps("organic", "coral", "coral", diffuse=False, normal_strength=.42)
        self._material("pocillopora_surface", (.8,.7,.6), vertex_color=True, roughness=.72)
        self._surface_maps("pocillopora_surface", "coral", "coral", diffuse=False, normal_strength=.45)
        UsdShade.Shader.Get(self.stage, "/World/Looks/pocillopora_surface/normalTexture").GetInput("file").Set(
            Sdf.AssetPath(pocillopora_textures()["normal"]))

    def _make_environment(self, snapshot):
        world = self.config.get("world", {})
        width = float(world.get("width", 10))
        length = float(world.get("length", 10))
        depth = float(world.get("depth", 8))
        self.width, self.length, self.depth = width, length, depth
        self._world_half = max(width, length) * 0.5
        ground = _Mesh()
        ground_normals = []
        segments = 160
        span = max(width, length) + 18.0

        def floor(x, y):
            # Low relief preserves the core's flat collision/planning assumption.
            phase = x * 6.2 + .9 * math.sin(y * .7) + .3 * math.sin(x * .3)
            return (-.075 + .012 * math.sin(phase) + .004 * math.sin(phase * 2 + .6)
                    + .022 * math.sin(x * .33 + .5) * math.cos(y * .28))

        def sand_color(x, y):
            # Continuous colour at shared vertices avoids a tiled/checkerboard
            # appearance even though the mesh is authored as individual quads.
            caustic = (math.sin(x * 3.2 + 1.7 * math.sin(y * 2)) *
                        math.sin(y * 3.5 + math.cos(x * 1.7))) ** 12
            tint = (0.88 + 0.04 * math.sin(x * 0.61 + y * 0.83)
                    + 0.025 * math.sin(x * 2.1 - y * 1.7) + 0.13 * caustic)
            return (0.33 * tint, 0.39 * tint, 0.29 * tint)

        for ix in range(segments):
            for iy in range(segments):
                x = -span / 2 + span * ix / segments
                y = -span / 2 + span * iy / segments
                step = span / segments
                vertices = ((x, y, floor(x, y)), (x + step, y, floor(x + step, y)),
                            (x + step, y + step, floor(x + step, y + step)),
                            (x, y + step, floor(x, y + step)))
                ground.face(vertices, (0.33, 0.39, 0.29),
                            vertex_colors=[sand_color(p[0], p[1]) for p in vertices])
                for px, py, _ in vertices:
                    dzdx = (floor(px + .005, py) - floor(px - .005, py)) / .01
                    dzdy = (floor(px, py + .005) - floor(px, py - .005)) / .01
                    ground_normals.append(Gf.Vec3f(-dzdx, -dzdy, 1).GetNormalized())
        seabed = ground.author(self.stage, "/World/Environment/Seabed", self.materials["sand"], collision=True)
        seabed.CreateNormalsAttr(Vt.Vec3fArray(ground_normals))
        seabed.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

        # Static bathymetric outcrops around the mission area, never hidden
        # obstacles inside the planner's free space.
        rocks = _Mesh()
        for i in range(75):
            angle = self._rng.uniform(0, math.tau)
            radius = self._world_half + self._rng.uniform(1.1, 6.5)
            x, y = math.cos(angle) * radius, math.sin(angle) * radius
            r = self._rng.uniform(0.25, 0.85)
            path = f"/World/Environment/Limestone/Outcrop{i:03d}"
            self._xform(path, (x, y, floor(x, y) - .015), rotation=(0, 0, i*71.))
            self._bind(self._mesh_data(path + "/Rock", generate_reef_rock(r, r*.8, 981+i)), "rock")
        # Core obstacles are displayed exactly where the planner sees them.
        for index, obstacle in enumerate(snapshot.get("obstacles", self.config.get("obstacles", []))):
            position = obstacle.get("position", obstacle.get("center", [0, 0, 0]))
            radius = float(obstacle.get("radius", 0.45))
            height = float(obstacle.get("height", 0.6))
            path = f"/World/Environment/Limestone/Obstacle{index:03d}"
            base_z = min(float(position[2]), floor(position[0], position[1]) - .015)
            self._xform(path, (position[0], position[1], base_z))
            self._bind(self._mesh_data(path + "/Rock", generate_reef_rock(
                radius, height + float(position[2]) - base_z, 171+index), collision=True), "rock")
        # Broken limestone and shell-sized pieces sit below the vehicle
        # clearance and never introduce unmodelled tall navigation obstacles.
        for i in range(330):
            x, y = self._rng.uniform(-7.5, 7.5), self._rng.uniform(-7.5, 7.5)
            r = self._rng.uniform(.012, .065)
            rocks.ellipsoid((x, y, floor(x, y) + r * .3), (r, r * .65, r * .4),
                            (.40, .36, .27), 5, 8)
        rocks.author(self.stage, "/World/Environment/Outcrops", self.materials["rock"], collision=True)

        grass = _Mesh()
        for _ in range(220):
            x, y = self._rng.uniform(-span / 2, span / 2), self._rng.uniform(-span / 2, span / 2)
            # Maintain a clear demonstration corridor between reef patches.
            if abs(x) < width / 2 and abs(y) < length / 2 and self._rng.random() < 0.83:
                continue
            for j in range(self._rng.randint(4, 8)):
                angle = self._rng.uniform(0, math.tau)
                height = self._rng.uniform(0.1, 0.31)
                base = (x + self._rng.uniform(-0.08, 0.08), y + self._rng.uniform(-0.08, 0.08), -0.04)
                tip = (base[0] + 0.08 * math.cos(angle), base[1] + 0.08 * math.sin(angle), height)
                previous = base
                blade_width = self._rng.uniform(.006, .014)
                for k in range(1, 6):
                    t = k / 5
                    point = (base[0] + .1 * math.cos(angle) * t*t,
                             base[1] + .1 * math.sin(angle) * t*t, base[2] + height * t)
                    w = blade_width * (1 - t * .85)
                    side = (-math.sin(angle), math.cos(angle), 0)
                    vertices = [(previous[0] - w * side[0], previous[1] - w * side[1], previous[2]),
                                (previous[0] + w * side[0], previous[1] + w * side[1], previous[2]),
                                (point[0] + w * side[0], point[1] + w * side[1], point[2]),
                                (point[0] - w * side[0], point[1] - w * side[1], point[2])]
                    grass.face(vertices, (.12, .25 + j * .007, .10))
                    previous = point
        grass.author(self.stage, "/World/Environment/Seagrass", self.materials["grass"])

        self.scenery = build_reef_scenery(self.config, snapshot)
        fan_sites = []
        render = self.config.get("render", {})
        soft_count = max(0, min(48, int(render.get("soft_coral_count",24))))
        fan_radius = float(render.get("soft_coral_radius",.15))
        if render.get("realistic_tissue",False):
            candidates = [c for c in self.scenery if c["health"] == "healthy"] if soft_count else []
            candidates.sort(key=lambda c: math.hypot(c["position"][0]+4.2,c["position"][1]+3.5))
            for candidate in candidates:
                x,y = candidate["position"][:2]
                if any(math.hypot(x-c["position"][0],y-c["position"][1]) < c["radius"]+fan_radius+.25
                       for c in snapshot["corals"]+snapshot.get("obstacles",[])):
                    continue
                if any(math.hypot(x-c["position"][0],y-c["position"][1]) < fan_radius*2+.18 for c in fan_sites):
                    continue
                fan_sites.append(candidate)
                if len(fan_sites) >= soft_count:
                    break
            # Reserve open pockets so the moving fans aren't buried inside
            # rigid decorative branches. Their bases remain on reef pavement.
            self.scenery = [c for c in self.scenery if not any(
                math.hypot(c["position"][0]-f["position"][0],c["position"][1]-f["position"][1]) < fan_radius+c["radius"]*.30
                for f in fan_sites)]
        pavement = self._mesh_data("/World/Environment/ReefPavement", build_reef_foundation(self.config, snapshot))
        self._bind(pavement, "rock")
        scanned_reef = bool(render.get("reef_quality", render.get("realistic_tissue", False)))
        quality = plan_reef_quality(self.scenery, snapshot, self.config) if scanned_reef else {}
        self.scenery_quality_stats = {"enabled": scanned_reef, "colonies": len(quality),
                                      "triangles": sum(s["triangles"] for s in quality.values()),
                                      "hero_colonies": sum(s["detail"] == "hero" for s in quality.values())}
        for index, colony in enumerate(self.scenery):
            path = "/World/Environment/ReefMosaic/" + _name(colony["id"])
            self._xform(path, colony["position"])
            if scanned_reef:
                # Build once: real connected scanned branches at every LOD,
                # with original texture UVs reserved for worksite close-ups.
                result = generate_quality_coral(colony, quality[colony["id"]])
                mesh = self._mesh_data(path + "/Colony", result["mesh"])
                if result["material"] == "tissue":
                    self._bind_tissue(mesh, result["health"], result["phenotype"])
                for key, value in (("source_asset", result["asset"]), ("mesh_detail", result["detail"]),
                                   ("uv_mode", result["uv_mode"]), ("health", result["health"]),
                                   ("display_only", True)):
                    mesh.GetPrim().SetCustomDataByKey("reefsim:" + key, value)
                self.scanned_colony_count += 1
                # USD owns its arrays now; do not retain a second full Python
                # copy of the reef, and never regenerate it during playback.
                del result
            elif colony["morphology"] == "branching" and colony["health"] != "dead" and index % 3 == 0:
                factory = generate_pocillopora_scan if index % 2 == 0 else generate_scanned_coral
                data = factory(colony["health"], colony["radius"], colony["height"], colony["seed"], preserve_aspect=True)
                if factory is generate_pocillopora_scan and render.get("realistic_tissue",False):
                    # Distant simplified meshes do not preserve museum UV
                    # seams. Use local microdetail rather than stretching the
                    # full source atlas across those simplified triangles.
                    pigment = tissue_color(colony["health"],colony["seed"])
                    data["colors"] = [tuple(min(1.,pigment[k]*(.55+.6*sum(c)/3)) for k in range(3)) for c in data["colors"]]
                    data["uvs"] = [(p[0]*5.,p[1]*2.+p[2]*5.) for p in data["points"]]
                mesh = self._mesh_data(path + "/Colony", data)
                if factory is generate_pocillopora_scan:
                    if self.config.get("render", {}).get("realistic_tissue", False):
                        self._bind(mesh, "organic")
                    else:
                        self._bind(mesh, "pocillopora_surface")
                self.scanned_colony_count += 1
            else:
                self._organic_mesh(path + "/Colony", colony["morphology"], colony["health"],
                                   colony["radius"], colony["height"], colony["seed"], detail="low")
        self._make_fauna(snapshot)
        # Flexible gorgonian-like fans respond to current; rigid stony coral
        # skeletons and manipulated cuttings do not wobble like soft bodies.
        candidates = [c for c in self.scenery if c["health"] == "healthy" and c["morphology"] == "branching"]
        sites = fan_sites if render.get("realistic_tissue",False) else candidates[::max(1,len(candidates)//max(1,soft_count))][:soft_count]
        for index, colony in enumerate(sites):
            data = generate_soft_coral(colony["seed"], height=float(render.get("soft_coral_height",min(.32,colony["height"]))),
                                       radius=fan_radius)
            path = f"/World/Environment/SoftCorals/Fan{index:03d}"
            self._xform(path, colony["position"], rotation=(0, 0, index * 47.))
            mesh = self._mesh_data(path + "/Tissue", data)
            self._bind(mesh, "living_tissue")
            self._soft_corals.append({"mesh":mesh,"data":data,"yaw":math.radians(index*47.),
                                     "position":colony["position"],"tip_index":max(range(len(data["points"])),key=lambda i:data["points"][i][2])})

        # The mission is fully submerged. An overhead translucent sheet casts
        # an artificial square shadow in RTX, so the surface is represented by
        # filtered illumination instead of a shadow-casting mesh.
        dome = UsdLux.DomeLight.Define(self.stage, "/World/Environment/WaterAmbient")
        dome.CreateColorAttr(_color((0.14, 0.23, 0.28)))
        dome.CreateIntensityAttr(110.0)
        sun = UsdLux.DistantLight.Define(self.stage, "/World/Environment/FilteredSun")
        sun.CreateColorAttr(_color((0.88, 0.94, 0.96)))
        sun.CreateIntensityAttr(950.0)
        sun.CreateAngleAttr(20.0)
        sun.AddRotateXYZOp().Set(Gf.Vec3f(-25, -32, -16))
        # Broad light sources above the surface produce diffuse underwater pools.
        for i, (x, y) in enumerate(((-3, -2), (3, 2), (0, 0))):
            light = UsdLux.DiskLight.Define(self.stage, f"/World/Environment/SurfaceGlow{i}")
            light.CreateRadiusAttr(2.3)
            light.CreateIntensityAttr(190.0)
            light.CreateColorAttr(_color((0.14, 0.59, 0.66)))
            light.AddTranslateOp().Set(Gf.Vec3d(x, y, depth - 0.3))

        self._make_particles()
        # Survey fixtures belong to the optional diagnostic view, not the reef
        # beauty capture. Their luminous tips otherwise resemble floating orbs.
        if self.config.get("render", {}).get("show_telemetry", False):
            self._make_region_markers(snapshot)
            for i, (x, y) in enumerate(((-width/2, -length/2), (width/2, -length/2),
                                        (width/2, length/2), (-width/2, length/2))):
                self._cylinder(f"/World/Environment/Stake{i}", (x, y, 0), (x, y, 0.4), 0.025, "metal")
                self._sphere(f"/World/Environment/StakeLight{i}", (x, y, 0.42), (0.045, 0.045, 0.045), "cyan_light")

    def _make_particles(self):
        count = int(self.config.get("render", {}).get("particle_count", 1800))
        count = max(0, min(8000, count))
        for _ in range(count):
            self._particle_origins.append((self._rng.uniform(-9, 9), self._rng.uniform(-9, 9),
                                           self._rng.uniform(0.1, min(self.depth, 6.5))))
            self._particle_speeds.append(self._rng.uniform(0.005, 0.022))
        particles = UsdGeom.Points.Define(self.stage, "/World/Environment/MarineSnow")
        particles.CreatePointsAttr(Vt.Vec3fArray([_color(p) for p in self._particle_origins]))
        particles.CreateWidthsAttr([self._rng.uniform(0.0015, 0.006) for _ in range(count)])
        self._bind(particles, "snow")
        self._particles = particles

    def _make_fauna(self, snapshot):
        """Author stable fish meshes once; only transforms change on replay."""
        self._material("fish", (.3, .5, .5), vertex_color=True, roughness=.32, metallic=.08)
        UsdGeom.Scope.Define(self.stage, "/World/Environment/Fauna")
        for record in build_fauna(self.config, snapshot):
            path = "/World/Environment/Fauna/" + _name(record["id"])
            root = self._xform(path, rotation=(0, 0, 0))
            body = self._mesh_data(path + "/Body", record["body_mesh"])
            self._bind(body, "fish")
            tail = self._xform(path + "/Tail", record["tail_pivot"], rotation=(0, 0, 0))
            self._bind(self._mesh_data(path + "/Tail/Fin", record["tail_mesh"]), "fish")
            for index, eye in enumerate(record["eyes"]):
                self._sphere(path + f"/Eye{index}", eye["position"], (eye["radius"],) * 3, "glass")
            self.fauna.append({"record": record, "position": root.GetOrderedXformOps()[0],
                               "rotation": root.GetOrderedXformOps()[1], "tail": tail.GetOrderedXformOps()[1]})

    def _make_region_markers(self, snapshot):
        # A small survey beacon per region; no bright artificial region walls.
        for i, region in enumerate(snapshot.get("regions", [])):
            center = region.get("center", [0, 0, 0])
            material = "amber_light" if "hazard" in str(region.get("id", "")).lower() else "cyan_light"
            x, y = float(center[0]), float(center[1])
            self._cylinder(f"/World/Telemetry/RegionBeacon{i}", (x, y, 0.01), (x, y, 0.12), 0.018, "metal")
            self._sphere(f"/World/Telemetry/RegionLight{i}", (x, y, 0.14), (0.025, 0.025, 0.025), material)

    def _make_coral(self, coral, index):
        identifier = str(coral.get("id", f"coral_{index}"))
        path = "/World/Corals/" + _name(identifier)
        position = coral.get("position", [0, 0, 0])
        root = self._xform(path, position)
        health = str(coral.get("health", "healthy")).lower()
        root.GetPrim().SetCustomDataByKey("reefsim:coral_id", identifier)
        root.GetPrim().SetCustomDataByKey("reefsim:health", health)
        height = float(coral.get("height", 0.5))
        radius = float(coral.get("radius", 0.3))
        rng = random.Random(int(self.config.get("seed", 42)) + index * 813)
        palette = ((0.62, 0.23, 0.25), (0.23, 0.48, 0.49), (0.57, 0.40, 0.17), (0.45, 0.28, 0.50))
        if health in ("bleached_alive", "bleached"):
            color = (0.72, 0.77, 0.64)
        elif health == "dead":
            color = (0.22, 0.31, 0.25)
        else:
            color = palette[index % len(palette)]
        morphology = str(coral.get("morphology", "branching")).lower()
        colony_seed = int(self.config.get("seed", 26)) + index * 813
        contact_proxy = (coral.get("species") == "pocillopora_damicornis_proxy"
                         or self.config.get("inspection", {}).get("pocillopora_only", False))
        if coral.get("scanned_partition"):
            from .scanned_fragment import split_scanned_donor
            data = split_scanned_donor(radius, height, colony_seed, slots=coral["scanned_partition_slots"],detail=coral["source_mesh_detail"])["parent"]
            mesh = self._mesh_data(path + "/Colony", data, collision=True)
            self._bind_tissue(mesh, health)
            self.scanned_colony_count += 1
        elif contact_proxy:
            detail_options = {"detail":"hero"} if self.config.get("render",{}).get("realistic_tissue",False) else {}
            mesh = self._mesh_data(path + "/Colony", generate_pocillopora_scan(health, radius, height, colony_seed, **detail_options), collision=True)
            if self.config.get("render", {}).get("realistic_tissue", False):
                self._bind_tissue(mesh, health)
            else:
                self._bind(mesh, "pocillopora_surface")
            self.scanned_colony_count += 1
        elif self.config.get("render",{}).get("reef_quality"):
            from .reef_quality import generate_quality_coral
            specimen = dict(coral, seed=colony_seed)
            spec = {"asset":"pocillopora_damicornis", "detail":"hero", "material":"tissue",
                    "uv_mode":"source_atlas", "phenotype":"tan", "health":health}
            result = generate_quality_coral(specimen,spec)
            mesh = self._mesh_data(path + "/Colony", result["mesh"],collision=True)
            self._bind_tissue(mesh,health)
            self.scanned_colony_count += 1
        elif morphology == "branching" and health == "bleached_alive":
            self._mesh_data(path + "/Colony", generate_scanned_coral(
                health, radius, height, colony_seed, preserve_aspect=not contact_proxy), collision=True)
            self.scanned_colony_count += 1
        else:
            self._organic_mesh(path + "/Colony", morphology, health, radius, height,
                               colony_seed, collision=True)
        if morphology == "branching" and health == "healthy" and not contact_proxy and not self.config.get("render",{}).get("reef_quality"):
            # A scanned lower crown joins the taller donor branches into a
            # dense colony while retaining their original cutting geometry.
            self._mesh_data(path + "/LowerCrown", generate_scanned_coral(
                health, radius * .95, height * .65, colony_seed, preserve_aspect=True))
            self.scanned_colony_count += 1
        if health != "dead":
            self._living_polyps(path, height, colony_seed, health)
        # Registered colonies have a Z=0 reference while the rippled sand sits
        # a few centimetres below it. Static limestone fills that small gap;
        # it is authored at scene build and never changes during restoration.
        footing = _Mesh()
        for j in range(5):
            angle = j * math.tau / 5 + index * .47
            footing.ellipsoid((radius * .38 * math.cos(angle), radius * .38 * math.sin(angle), -.055),
                              (radius * (.70 + .08 * math.sin(j)), radius * .63, .075),
                              (.32, .31, .24), 8, 20)
        footing.author(self.stage, path + "/ReefFoundation", self.materials["rock"])
        halo = self._line(path + "/InspectionHalo", self._circle((0, 0), radius * 1.15), "cyan_light", 0.008)
        halo.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        # The planting surface is present from the beginning. Nothing grows
        # or appears at placement: the existing cutting is simply released.
        planting = coral.get("planting_point")
        if planting and coral.get("contact_fixture"):
            self._contact_fixture(path, coral)
        elif planting:
            local = _v(planting) - _v(position)
            pad = _Mesh()
            pad.ellipsoid((local[0], local[1], local[2] - .095), (.125, .105, .095),
                          (.40, .37, .29), 12, 24)
            pad.author(self.stage, path + "/ExistingLimestone", self.materials["rock"])
        marker = self._line(path + "/VerifiedHalo", self._circle((0, 0), radius * 1.2, .05), "blue_light", .005)
        marker.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        visual_height = max(float(p[2]) for p in UsdGeom.Mesh.Get(self.stage, path + "/Colony").GetPointsAttr().Get())
        self.corals[identifier] = {"root": root, "halo": halo, "verified": marker, "visual_height": visual_height}
        if self._inspection_enabled:
            profile = mission_profile(coral,index,int(self.config.get("seed",26)))
            profile["scan_asset"] = "pocillopora" if (contact_proxy or self.config.get("render",{}).get("reef_quality")) else None
            if self.config.get("render",{}).get("realistic_tissue",False) and not (coral.get("genotype_known") and coral.get("genet_id") in ("R","G")):
                profile["pigment_rgb"] = list(tissue_color(health,colony_seed))
            self.inspection_profiles[identifier] = profile
            meshes = [path + "/Colony"]
            if self.stage.GetPrimAtPath(path + "/LowerCrown"):
                meshes.append(path + "/LowerCrown")
            if self.stage.GetPrimAtPath(path + "/LivingPolyps"):
                meshes.append(path + "/LivingPolyps")
            if self.stage.GetPrimAtPath(path + "/RecipientContactTissue"):
                meshes.append(path + "/RecipientContactTissue")
            self._inspection_material(identifier, profile, health, meshes,
                                      [position[0], position[1], position[2] + visual_height * .5])

    def _contact_fixture(self, path, coral):
        """Permanent recipient tissue and basal support; no roots at release."""
        fixture = coral["contact_fixture"]
        origin = _v(coral["position"])
        if fixture.get("kind") == "natural_branch":
            # The recipient surface is already part of /Colony. Only the
            # prepared basal securing compound is a separate mesh.
            if fixture.get("natural_fragment_contact_local") is not None:
                # Small adhesive saddle at the true contact, no extension rod.
                contact = _v(coral["contact_point"]) - origin
                support = _Mesh()
                support.ellipsoid(contact-Gf.Vec3d(0,0,.007),(.008,.007,.005),(.48,.43,.35),8,16)
                support.author(self.stage,path+"/BasalSecuringCompound",self.materials["rock"])
                return
            anchor = _v(fixture["support_point"]) - origin
            base = _v(coral["contact_base"]) - origin - Gf.Vec3d(0,0,.003)
            support = _Mesh()
            support.tube(anchor, base, .006, (.42,.38,.30), .005, 9)
            support.ellipsoid(anchor, (.008,.008,.005), (.46,.41,.33), 6, 10)
            support.ellipsoid(base, (.006,.006,.004), (.48,.43,.35), 6, 10)
            support.author(self.stage, path + "/BasalSecuringCompound", self.materials["rock"])
            return
        anchor = _v(fixture["recipient_branch_anchor"]) - origin
        stem_base = _v(fixture["recipient_stem_base"]) - origin
        stem_top = _v(fixture["recipient_stem_top"]) - origin
        tissue = _Mesh()
        # A living lateral branch connects all the way back into the colony.
        bend = (anchor + stem_base)*.5 + Gf.Vec3d(0, 0, .025)
        tissue.tube(anchor, bend, .020, (.82,.77,.66), .013, 12)
        tissue.tube(bend, stem_base, .013, (.85,.79,.70), .008, 12)
        # Rounded verrucae break up the otherwise plumbing-like support limb.
        # Keep these on the colony-side limb, outside the audited contact band.
        tissue.ellipsoid(bend, (.014,.014,.014), (.85,.79,.70), 6, 12)
        for a, b, r0, r1 in ((anchor, bend, .020, .013), (bend, stem_base, .013, .008)):
            axis = (b - a).GetNormalized()
            side = Gf.Cross(axis, Gf.Vec3d(0,0,1)).GetNormalized()
            up = Gf.Cross(side, axis).GetNormalized()
            for index in range(16):
                t = (index + .5) / 16
                angle = index * 2.399963
                radial = side * math.cos(angle) + up * math.sin(angle)
                radius = r0*(1-t) + r1*t
                center = a*(1-t) + b*t + radial*radius*.95
                tissue.ellipsoid(center, (.0035,.0035,.0045), (.84,.76,.68), 4, 7)
        contact_end = _v(fixture["recipient_stem_bend"]) - origin
        tissue.tube(stem_base, contact_end, float(fixture["recipient_stem_radius"]), (.90,.82,.75),
                    float(fixture["recipient_stem_radius"]), 16)
        tissue.tube(contact_end, stem_top, float(fixture["recipient_stem_radius"]), (.90,.82,.75), .006, 16)
        tissue.ellipsoid(stem_top, (.006,)*3, (.92,.84,.76), 6, 12)
        tissue.author(self.stage, path + "/RecipientContactTissue", self.materials["living_tissue"])
        # The socket holds the cut skeletal ends below the contact interface.
        # It is an engineering support proxy, not glue between living faces.
        base = _v(coral["contact_base"]) - origin
        support = _Mesh()
        support.ellipsoid(base - Gf.Vec3d(0,0,.008), (.032,.029,.009), (.70,.67,.57), 8, 20)
        support.author(self.stage, path + "/ContactSupport", self.materials["rock"])
        self.stage.GetPrimAtPath(path + "/RecipientContactTissue").SetCustomDataByKey(
            "reefsim:contact_role", "permanent_living_recipient_tissue")

    def _living_polyps(self, path, height, seed, health="healthy"):
        """Retained pale living tissue, absent from dead skeletal controls."""
        colony = UsdGeom.Mesh.Get(self.stage, path + "/Colony")
        points, normals = colony.GetPointsAttr().Get(), colony.GetNormalsAttr().Get()
        colors = colony.GetDisplayColorPrimvar().Get()
        candidates = [i for i, p in enumerate(points) if p[2] > height*.15 and normals[i][2] > .15]
        random.Random(seed + 973).shuffle(candidates)
        moving_count = int(self.config.get("render", {}).get("moving_polyp_count",0))
        if moving_count:
            anchors = []
            for i in candidates:
                point = list(points[i])
                if any(math.dist(point,a["point"]) < .035 for a in anchors):
                    continue
                anchors.append({"point":point,"normal":list(normals[i]),
                                "color":[.79,.71,.61] if health=="bleached_alive" else [.48,.34,.24]})
                if len(anchors) >= min(16,moving_count):
                    break
            data = generate_polyp_patch(anchors,seed,health,tentacle_length=.008)
            mesh = self._mesh_data(path + "/LivingPolyps",data)
            self._bind(mesh,"living_tissue")
            mesh.GetPrim().SetCustomDataByKey("reefsim:deformable_tissue",True)
            self._polyp_patches.append({"mesh":mesh,"data":data})
            return
        mesh, used = _Mesh(), []
        for i in candidates:
            point, normal = Gf.Vec3d(points[i]), Gf.Vec3d(normals[i]).GetNormalized()
            if any((point-other).GetLength() < .025 for other in used):
                continue
            used.append(point)
            color = _mix(tuple(colors[i]), (.95, .81, .75), .22)
            mesh.ellipsoid(point + normal*.002, (.0035,)*3, color, 4, 6)
            ref = Gf.Vec3d(1, 0, 0) if abs(normal[2]) > .8 else Gf.Vec3d(0, 0, 1)
            u = Gf.Cross(normal, ref).GetNormalized()
            v = Gf.Cross(normal, u)
            for k in range(6):
                radial = u*math.cos(k*math.tau/6) + v*math.sin(k*math.tau/6)
                mesh.tube(point + normal*.003 + radial*.0015, point + normal*.007 + radial*.006,
                          .0008, color, .00035, 5)
            if len(used) >= 48:
                break
        mesh.author(self.stage, path + "/LivingPolyps", self.materials["living_tissue"])

    def _branching(self, mesh, radius, height, color, rng, branches=11):
        for i in range(branches):
            angle = i * math.tau / branches + rng.uniform(-0.2, 0.2)
            spread = rng.uniform(0.3, 1.0)
            base = (radius * 0.16 * math.cos(angle), radius * 0.16 * math.sin(angle), height * 0.08)
            fork = (radius * spread * 0.55 * math.cos(angle), radius * spread * 0.55 * math.sin(angle), height * rng.uniform(0.4, 0.72))
            tip = (radius * spread * math.cos(angle + 0.12), radius * spread * math.sin(angle + 0.12), height * rng.uniform(0.8, 1.05))
            thickness = max(0.009, radius * rng.uniform(0.07, 0.115))
            mesh.tube(base, fork, thickness, color, thickness * 0.7)
            mesh.tube(fork, tip, thickness * 0.7, color, thickness * 0.38)
            for side in (-1, 1):
                branch_angle = angle + side * rng.uniform(0.5, 1.1)
                branch_tip = (fork[0] + radius * 0.45 * math.cos(branch_angle),
                              fork[1] + radius * 0.45 * math.sin(branch_angle),
                              min(height * 1.05, fork[2] + height * rng.uniform(0.20, 0.4)))
                mesh.tube(fork, branch_tip, thickness * 0.57, _mix(color, (0.85, 0.82, 0.65), 0.12), thickness * 0.22, 6)
                mesh.ellipsoid(branch_tip, (thickness * 0.35,) * 3, _mix(color, (0.95, 0.86, 0.65), 0.28), 4, 6)

    def _fan(self, mesh, radius, height, color, rng):
        mesh.tube((0, 0, 0), (0, 0, height * 0.3), radius * 0.06, color)
        for i in range(17):
            angle = -1.1 + i * 2.2 / 16
            previous = (0, 0, height * 0.25)
            for j in range(1, 6):
                t = j / 5
                tip = (math.sin(angle) * radius * t, 0.025 * math.sin(4 * angle + j),
                       height * (0.25 + 0.75 * math.cos(angle) * t))
                mesh.tube(previous, tip, max(0.003, 0.012 * (1 - t * 0.6)), color, sides=5)
                previous = tip

    def _make_fragments(self, snapshot):
        """One persistent mesh per cutting, present on its living donor at t=0."""
        donors = {c["id"]: c for c in snapshot.get("corals", [])}
        for fragment in snapshot.get("fragments", []):
            identifier = fragment["id"]
            path = "/World/Fragments/" + _name(identifier)
            root = self._xform(path, fragment.get("base_world", fragment["position"]), rotation=(0, 0, 0))
            natural = "source_slot" in fragment
            if natural:
                from .scanned_fragment import split_scanned_donor
                donor = donors[fragment["donor_id"]]
                data = split_scanned_donor(donor["radius"],donor["height"],fragment["source_mesh_seed"],
                    slots=donor["scanned_partition_slots"],detail=fragment["source_mesh_detail"])["fragments"][fragment["source_slot"]]["mesh"]
            else:
                factory = generate_contact_fragment if fragment.get("attachment_method") == "same_genet_contact" else generate_fragment
                data = factory(fragment["seed"], fragment.get("height", .14), fragment.get("radius", .025))
            cutting = self._mesh_data(path + "/Cutting", data)
            if natural:
                self._bind_tissue(cutting, "healthy")
            else:
                self._bind(cutting, "organic" if fragment.get("attachment_method") == "same_genet_contact" else "fragment")
            root.GetPrim().SetCustomDataByKey("reefsim:fragment_id", identifier)
            root.GetPrim().SetCustomDataByKey("reefsim:donor_id", fragment["donor_id"])
            self.fragments[identifier] = {"root": root, "position": root.GetOrderedXformOps()[0],
                                          "rotation": root.GetOrderedXformOps()[1],
                                          "mesh": self.stage.GetPrimAtPath(path + "/Cutting")}
            source = _v(fragment["source_position"])
            donor = donors.get(fragment["donor_id"], {})
            if not natural:
                base = _v(donor.get("position", source))
                start = Gf.Vec3d(source[0] * .65 + base[0] * .35,
                                source[1] * .65 + base[1] * .35, source[2] - .14)
                stem = _Mesh()
                stem.tube(start, source, .009, data["colors"][0], .006, 12)
                stem.author(self.stage, "/World/DonorStems/" + _name(identifier), self.materials["organic"])
            if self._inspection_enabled:
                profile = self.inspection_profiles[fragment["donor_id"]]
                self._inspection_material(identifier, profile, "healthy", [path + "/Cutting"],
                                          list(source + Gf.Vec3d(0, 0, fragment.get("height",.14)*.5)), donor_id=fragment["donor_id"])
                if not natural:
                    self._bind(UsdGeom.Mesh.Get(self.stage, "/World/DonorStems/" + _name(identifier)),
                               "inspect_" + fragment["donor_id"])

    def _make_robot(self, robot, index):
        identifier = str(robot.get("id", f"rov_{index}"))
        path = "/World/Robots/" + _name(identifier)
        root = UsdGeom.Xform.Define(self.stage, path)
        position_op = root.AddTranslateOp()
        yaw_op = root.AddRotateZOp()
        role = str(robot.get("role", "survey")).lower()
        is_survey = "survey" in role or index == 0
        color = "survey" if is_survey else "restore"
        light_color = "cyan_light" if is_survey else "amber_light"
        root.GetPrim().SetCustomDataByKey("reefsim:robot_id", identifier)
        root.GetPrim().SetCustomDataByKey("reefsim:dynamics", "externally-integrated-kinematic-render")
        self._sphere(path + "/PressureHull", (0, 0, 0), (0.30, 0.17, 0.14), "white")
        self._cube(path + "/BuoyancyFoam", (-0.025, 0, 0.13), (0.46, 0.34, 0.09), color)
        # Open protective ROV frame.
        for j, z in enumerate((-0.18, 0.17)):
            for k, y in enumerate((-0.24, 0.24)):
                self._cylinder(f"{path}/FrameLong{j}{k}", (-0.36, y, z), (0.36, y, z), 0.017, "metal")
            for k, x in enumerate((-0.36, 0.36)):
                self._cylinder(f"{path}/FrameCross{j}{k}", (x, -0.24, z), (x, 0.24, z), 0.017, "metal")
        for j, x in enumerate((-0.36, 0.36)):
            for k, y in enumerate((-0.24, 0.24)):
                self._cylinder(f"{path}/FrameUpright{j}{k}", (x, y, -0.18), (x, y, 0.17), 0.017, "metal")
        for j, y in enumerate((-0.205, 0.205)):
            self._cylinder(f"{path}/Battery{j}", (-0.22, y, -0.075), (0.12, y, -0.075), 0.052, "dark")
        for j, (x, y) in enumerate(((-0.22, -0.26), (-0.22, 0.26), (0.23, -0.26), (0.23, 0.26))):
            self._cylinder(f"{path}/Thruster{j}", (x - 0.055, y, 0), (x + 0.055, y, 0), 0.073, "dark")
            self._cylinder(f"{path}/ThrusterRim{j}", (x + 0.052, y, 0), (x + 0.058, y, 0), 0.078, "metal")
            self._sphere(f"{path}/Motor{j}", (x + 0.06, y, 0), (0.018, 0.024, 0.024), light_color)
        for j, (x, y) in enumerate(((-0.22, 0), (0.2, 0))):
            self._cylinder(f"{path}/VerticalThruster{j}", (x, y, 0.15), (x, y, 0.23), 0.065, "dark")
        self._sphere(path + "/CameraPort", (0.30, 0, 0.01), (0.065, 0.075, 0.065), "glass")
        self._sphere(path + "/DownwardCamera", (0.08, 0, -0.145), (0.055, 0.055, 0.03), "glass")
        for j, y in enumerate((-0.15, 0.15)):
            self._sphere(f"{path}/Headlamp{j}", (0.33, y, 0.07), (0.025, 0.035, 0.025), "lamp")
            lamp = UsdLux.SphereLight.Define(self.stage, f"{path}/Headlight{j}")
            lamp.CreateRadiusAttr(0.025)
            lamp.CreateIntensityAttr(95.0)
            lamp.CreateColorAttr(_color((.92, .96, 1.0)))
            lamp.AddTranslateOp().Set(Gf.Vec3d(0.35, y, 0.03))
        self._line(path + "/IdentityBar", [(-0.2, -0.18, 0.185), (0.16, -0.18, 0.185)], light_color, 0.017)
        self._cylinder(path + "/Antenna", (-0.23, 0, 0.18), (-0.23, 0, 0.34), 0.009, "dark")
        self._sphere(path + "/Status", (-0.23, 0, 0.35), (0.022,) * 3, light_color)
        self._sphere(path + "/Shoulder", (0.17, 0, -0.12), (0.055,) * 3, "metal")
        arm1 = self._cylinder(path + "/ArmUpper", (0.17, 0, -0.12), (0.35, 0, -0.28), 0.027, color)
        arm2 = self._cylinder(path + "/ArmFore", (0.35, 0, -0.28), (0.22, 0, -0.35), 0.022, "white")
        elbow = self._sphere(path + "/Elbow", (0, 0, 0), (0.036,) * 3, "metal")
        # Change translations through their first authored xform op.
        elbow_op = elbow.GetOrderedXformOps()[0]
        gripper = self._xform(path + "/Gripper", (0.22, 0, -0.35))
        gripper_op = gripper.GetOrderedXformOps()[0]
        wrist_yaw_op = gripper.AddRotateZOp(UsdGeom.XformOp.PrecisionDouble)
        wrist_yaw_op.Set(0.)
        # Parallel jaws approach the vertical stem sideways. Their palm is
        # behind the cutting, so the crown cannot intersect the wrist.
        self._cube(path + "/Gripper/Palm", (-.075, 0, 0), (.045, .12, .045), "dark")
        self._cylinder(path + "/Gripper/Wrist", (-.115, 0, 0), (-.085, 0, 0), .023, "white")
        self._sphere(path + "/Gripper/WorkLamp", (-.06, -.055, .035), (.009,) * 3, "lamp")
        self._cylinder(path + "/Gripper/CameraBracket", (-.08, -.055, 0), (.10, -.18, .08), .005, "metal")
        self._sphere(path + "/Gripper/ToolCamera", (.10, -.18, .08), (.018, .018, .015), "glass")
        work_light = UsdLux.SphereLight.Define(self.stage, path + "/Gripper/InspectionLight")
        work_light.CreateRadiusAttr(.015)
        work_light.CreateIntensityAttr(65.)
        work_light.CreateColorAttr(_color((.92, .96, 1.)))
        work_light.AddTranslateOp().Set(Gf.Vec3d(-.06, -.055, .035))
        fingers = []
        for j, side in enumerate((-1, 1)):
            finger = self._xform(f"{path}/Gripper/Jaw{j}", (0, side * .056, 0))
            body = UsdGeom.Capsule.Define(self.stage, f"{path}/Gripper/Jaw{j}/Finger")
            body.CreateAxisAttr(UsdGeom.Tokens.x)
            body.CreateRadiusAttr(.009)
            body.CreateHeightAttr(.065)
            body.AddTranslateOp().Set(Gf.Vec3d(-.027, 0, 0))
            self._bind(body, "white")
            self._cube(f"{path}/Gripper/Jaw{j}/SoftPad", (0, -side * .009, 0), (.030, .006, .027), "dark")
            fingers.append(finger.GetOrderedXformOps()[0])
        trail = self._line("/World/Telemetry/Trail_" + _name(identifier), [(0, 0, 0), (0, 0, 0)], light_color, 0.004)
        trail.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        target = self._line("/World/Telemetry/Target_" + _name(identifier), [(0, 0, 0), (0, 0, 0)], light_color, 0.003)
        target.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        self.robots[identifier] = {"position": position_op, "yaw": yaw_op, "root": root,
                                  "arm1": arm1, "arm2": arm2, "elbow": elbow_op,
                                  "gripper": gripper_op, "wrist_yaw": wrist_yaw_op,
                                  "fingers": fingers,
                                  "trail": trail, "target": target, "survey": is_survey}
        if self._inspection_enabled and not is_survey:
            # A real wrist-mounted fixture. UV itself is not visible RGB light;
            # its illustrative visible response is driven separately below.
            self._cylinder(path + "/Gripper/MultispectralPod", (.13, -.20, .07),
                           (.13, -.20, .13), .023, "dark")
            self._material("inspection_lens", (.12, .15, .2), emission=(0., 0., 0.))
            self._sphere(path + "/Gripper/MultispectralLens", (.13, -.20, .065),
                         (.019, .019, .007), "inspection_lens")
            light = UsdLux.DiskLight.Define(self.stage, path + "/Gripper/MultispectralBeam")
            light.CreateRadiusAttr(.027)
            light.CreateNormalizeAttr(True)
            light.CreateIntensityAttr(0.)
            light.CreateColorAttr(_color((1., 1., 1.)))
            light.AddTranslateOp().Set(Gf.Vec3d(.13, -.20, .055))
            orient = light.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
            shape = UsdLux.ShapingAPI.Apply(light.GetPrim())
            shape.CreateShapingConeAngleAttr(float(self.config.get("inspection", {}).get("half_angle_degrees", 38.)))
            shape.CreateShapingConeSoftnessAttr(.3)
            self._inspection_beam = {"light": light, "orient": orient, "robot_id": identifier,
                                     "offset": Gf.Vec3d(.13, -.20, .055)}

    def _make_cameras(self, snapshot):
        # Fixed white observer-camera lamp for the controlled current review.
        # Authored once, off during the robot mission and optical comparisons.
        torch = UsdLux.DiskLight.Define(self.stage, "/World/Environment/ObserverCameraLamp")
        torch.CreateRadiusAttr(.04)
        torch.CreateNormalizeAttr(True)
        torch.CreateIntensityAttr(0.)
        torch.CreateColorAttr(Gf.Vec3f(.95,.98,1.))
        shape = UsdLux.ShapingAPI.Apply(torch.GetPrim())
        shape.CreateShapingConeAngleAttr(42.)
        shape.CreateShapingConeSoftnessAttr(.4)
        self._observer_torch = (torch,torch.AddTranslateOp(),torch.AddOrientOp(UsdGeom.XformOp.PrecisionDouble))
        for mode, path in self.CAMERA_PATHS.items():
            camera = UsdGeom.Camera.Define(self.stage, path)
            # The optical origin sits in its protective pod. Clip its own
            # 18-mm housing while preserving the nearby fingers/cutting.
            camera.CreateClippingRangeAttr(Gf.Vec2f(.04 if mode == "worker" else .05, 100.0))
            camera.CreateFocalLengthAttr({"overview": 22., "director": 23., "chase": 23.,
                                         "worker": 11., "scout": 18.}.get(mode, 18.))
            camera.CreateHorizontalApertureAttr(36.0)
            camera.CreateFocusDistanceAttr(4.0)
            camera.CreateFStopAttr(0.0)
            self._camera_ops[mode] = camera.AddTransformOp()
        self._update_cameras(snapshot)

    def _look_at(self, mode, eye, target, up=(0, 0, 1)):
        matrix = Gf.Matrix4d(1.0)
        matrix.SetLookAt(_v(eye), _v(target), _v(up))
        self._camera_ops[mode].Set(matrix.GetInverse())

    def _update_cameras(self, snapshot):
        half = getattr(self, "_world_half", 5.)
        self._look_at("overview", (-half * 1.05, -half * 1.12, 2.55), (-.8, -.35, .40))
        self._look_at("top", (0, 0, min(self.depth - .3, 7.6)), (0, 0, 0), (0, 1, 0))
        robots = snapshot.get("robots", [])
        if not robots:
            return
        survey = next((r for r in robots if r.get("role") == "survey"), robots[0])
        worker = next((r for r in robots if r.get("role") == "restoration"), robots[-1])
        sp = _v(survey["position"])
        sf = Gf.Vec3d(math.cos(survey.get("yaw", 0)), math.sin(survey.get("yaw", 0)), 0)
        eye = sp + sf * .08 + Gf.Vec3d(0, 0, -.19)
        self._look_at("rov", eye, eye + Gf.Vec3d(0, 0, -1.5), sf)
        self._look_at("scout", eye, eye + Gf.Vec3d(0, 0, -1.5), sf)

        p = _v(worker["position"])
        yaw = float(worker.get("yaw", 0))
        forward = Gf.Vec3d(math.cos(yaw), math.sin(yaw), 0)
        left = Gf.Vec3d(-math.sin(yaw), math.cos(yaw), 0)
        def world(local):
            return p + forward * local[0] + left * local[1] + Gf.Vec3d(0, 0, local[2])
        state = worker.get("state", "")
        pickup_states = {"APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT"}
        recovery_states = {"FRAGMENT_LOST", "RECOVER_FRAGMENT", "RECOVERY_APPROACH", "RECOVERY_GRASP", "RECOVERY_LIFT"}
        plant_states = {"LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER", "VERIFY_ATTACHMENT", "PUSH_TEST", "PUSH_APPROACH"}
        active = state in pickup_states | plant_states | recovery_states
        fragment = next((f for f in snapshot.get("fragments", []) if f["id"] == worker.get("fragment_id")), None)
        shoulder, elbow, tip = self._arm_pose(worker, snapshot)
        # Actual wrist-mounted camera: its pod and bracket share the gripper
        # transform, and the independent render product moves with the tool.
        worker_eye = world(tip + _wrist_offset(worker, (.10, -.18, .08)))
        tool_target = world(tip) + Gf.Vec3d(0, 0, .025)
        UsdGeom.Camera.Get(self.stage,self.CAMERA_PATHS["worker"]).GetFocalLengthAttr().Set(11.)
        if not active and not worker.get("carrying"):
            tool_target = p + forward * .7 + Gf.Vec3d(0, 0, -.85)
        self._look_at("worker", worker_eye, tool_target)
        scan_states = {"NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT", "SCAN_DONOR", "NAVIGATE_TO_DONOR"}
        scanning = state in scan_states and bool(worker.get("scan_target_world")) and not worker.get("carrying")
        if scanning:
            target = _v(worker["scan_target_world"])
            self._look_at("worker",worker_eye,target)
            UsdGeom.Camera.Get(self.stage,self.CAMERA_PATHS["worker"]).GetFocalLengthAttr().Set(14.)
            # Side-overhead view shows the complete illuminated patch, the
            # vehicle and its standoff before either manipulator operation.
            director_eye = target + Gf.Vec3d(2.1,-2.4,1.8)
            focal = 23.
        elif state in recovery_states and fragment:
            target = _v(fragment["position"]) + Gf.Vec3d(0,0,fragment.get("height",.08)*.5)
            director_eye = target + Gf.Vec3d(.48,-.62,.38)
            focal = 29.
            self._look_at("worker",worker_eye,target)
        elif active:
            UsdGeom.Camera.Get(self.stage,self.CAMERA_PATHS["worker"]).GetFocalLengthAttr().Set(11.)
            pickup = state in pickup_states
            subject_id = worker.get("donor_id") if pickup else worker.get("task_id")
            colony = next((c for c in snapshot.get("corals", []) if c["id"] == subject_id), None)
            if pickup and fragment:
                operation = _v(fragment["source_position"])
            elif colony:
                operation = _v(colony.get("planting_point") or colony.get("attachment_position") or colony["position"])
            else:
                operation = world(tip) - Gf.Vec3d(0, 0, .045)
            center = _v(colony["position"]) if colony else operation - forward
            outward = math.atan2(operation[1] - center[1], operation[0] - center[0])
            # Film from in front and beside the cage, close to the arm's
            # height. The old rear/top camera hid the gripper under the hull.
            push = max(0., min(1., float(worker.get("arm_extension", 0))))
            push = push * push * (3 - 2 * push)
            radius = 1.05 - .20 * push
            eye_z = .36 - .06 * push
            jaw_world = world(tip)
            # Keep the substrate and cutting in shot while the empty hand
            # retreats. Tracking the hand here loses the released cutting.
            anchor = operation + Gf.Vec3d(0, 0, .065)
            target = anchor
            key = (worker.get("fragment_id"), "pickup" if pickup else "plant")
            if key != self._director_key:
                self._director_key = key
                # Choose a clear side of the worksite, avoiding foreground
                # colonies/outcrops that would hide the gripper or substrate.
                # Evaluate the final stem/crown workspace, rather than the
                # initially stowed wrist. Otherwise a clear view of the wrist
                # can win while the final mount is behind another colony.
                subjects = [operation + Gf.Vec3d(0, 0, z) for z in (.025, .065, .13)]
                candidates = [outward + offset for offset in (-.60, .60, 0., -1.20, 1.20, math.pi)]
                candidates += [yaw + offset for offset in (-.75, .75, -.35, .35, 0.)]
                candidates += [outward + index * math.tau / 18 for index in range(18)]
                # Evaluate the fully extended arm too: a clear reef sightline
                # can still look straight through the gold elbow/forearm.
                posed = dict(worker, gripper_world=list(operation + Gf.Vec3d(0, 0, .045)))
                ps, pe, pj = self._arm_pose(posed, snapshot)
                arm_points = []
                for a, b, thickness in ((world(ps), world(pe), .065),
                                         (world(pe), world(pj + _wrist_offset(posed, (-.10, 0, 0))), .045)):
                    arm_points += [(a + (b - a) * (i / 12), thickness) for i in range(13)]
                def cost(angle):
                    eye = anchor + Gf.Vec3d(math.cos(angle) * .85, math.sin(angle) * .85, .30)
                    score = 0.
                    for subject in subjects:
                        delta = subject - eye
                        denom = delta[0] ** 2 + delta[1] ** 2
                        blockers = [dict(position=c["position"], radius=c["radius"], height=c["height"])
                                    for c in snapshot.get("corals", [])]
                        blockers += self.scenery
                        blockers += snapshot.get("obstacles", [])
                        for item in blockers:
                            center = _v(item["position"])
                            t = max(0., min(.98, ((center[0] - eye[0]) * delta[0] + (center[1] - eye[1]) * delta[1]) / max(1e-8, denom)))
                            point = eye + delta * t
                            if math.hypot(point[0] - center[0], point[1] - center[1]) < item["radius"] * 1.08 and point[2] < item["height"] + .10:
                                score += 100.
                        for arm_point, thickness in arm_points:
                            t = Gf.Dot(arm_point - eye, delta) / max(1e-8, Gf.Dot(delta, delta))
                            if .02 < t < .98 and (eye + delta * t - arm_point).GetLength() < thickness:
                                score += 500.
                    # A front-quarter view exposes the tissue between the
                    # pads; a view through the wrist hides the held stem.
                    score += 3. * max(0., .25 - math.cos(angle - yaw))
                    return score
                self._director_angle = min(candidates, key=cost)
            director_eye = anchor + Gf.Vec3d(math.cos(self._director_angle) * radius,
                                           math.sin(self._director_angle) * radius, eye_z)
            focal = 30. + 4. * push
        elif state in ("WAIT_FOR_MAP", "NO_STOCK"):
            # Establish the living habitat before the manipulation close-ups.
            # A slow lateral drift reveals connected reef cover and schools.
            t = float(snapshot.get("time", 0))
            director_eye = Gf.Vec3d(-4.5 + .25 * math.sin(t * .06), -5.15, 1.85)
            target = Gf.Vec3d(-2.35, -2.4, .48)
            focal = 23.
        else:
            director_eye = p + forward * 1.35 - left * 1.55 + Gf.Vec3d(0, 0, .50)
            if worker.get("carrying"):
                target = world(tip) + Gf.Vec3d(0, 0, .04)
                director_eye = world(tip) + forward * 1.05 - left * .65 + Gf.Vec3d(0, 0, .24)
                focal = 30.
            else:
                target = p + Gf.Vec3d(0, 0, -.25)
                focal = 23.
        UsdGeom.Camera.Get(self.stage, self.CAMERA_PATHS["director"]).GetFocalLengthAttr().Set(focal)
        UsdGeom.Camera.Get(self.stage, self.CAMERA_PATHS["chase"]).GetFocalLengthAttr().Set(focal)
        self._look_at("director", director_eye, target)
        self._look_at("chase", director_eye, target)

    def set_camera(self, mode: str, snapshot: dict | None = None) -> None:
        mode = mode.lower()
        if mode in ("follow",):
            mode = "chase"
        if mode in ("robot", "sensor"):
            mode = "rov"
        if mode in ("map", "overhead"):
            mode = "top"
        if mode not in self.CAMERA_PATHS:
            raise ValueError(f"Unknown camera {mode!r}; choose overview, rov, chase, or top")
        self.camera_mode = mode
        if snapshot is not None:
            self._update_cameras(snapshot)
        try:
            from omni.kit.viewport.utility import get_active_viewport
            viewport = get_active_viewport()
            if viewport:
                viewport.camera_path = self.CAMERA_PATHS[mode]
        except (ImportError, AttributeError):
            pass  # No viewport in headless render-product workflows.

    def _set_water(self, water):
        visibility = max(0.6, float(water.get("visibility", 5.0)))
        turbidity = max(0.0, min(1.0, float(water.get("turbidity", 0.48))))
        key = (round(visibility, 3), round(turbidity, 3))
        if self._last_water == key:
            return
        try:
            import carb
            import carb.settings
            settings = carb.settings.get_settings()
        except (ImportError, AttributeError, RuntimeError):
            return  # Allows offline USD stage generation without Kit.
        if settings is None:
            return
        self._last_water = key
        # Documented RTX exponential fog: an artistic visibility approximation,
        # not a wavelength-dependent radiative-transfer/sensor model.
        volumetric = bool(self.config.get("render", {}).get("volumetric_water", False))
        settings.set("/rtx/fog/enabled", not volumetric)
        settings.set("/rtx/raytracing/globalVolumetricEffects/enabled", volumetric)
        if volumetric:
            # Installed RTX UI documents these distances in internal centimetres.
            # Actual spot lights scatter in the water, rather than drawing a
            # solid translucent cone over the image.
            settings.set("/rtx/raytracing/inscattering/atmosphereHeight", 800.)
            settings.set("/rtx/raytracing/inscattering/maxDistance", 1400.)
            settings.set("/rtx/raytracing/inscattering/transmittanceMeasurementDistance", 550.)
            settings.set("/rtx/raytracing/inscattering/transmittanceColor", [.32,.65,.72])
            settings.set("/rtx/raytracing/inscattering/singleScatteringAlbedo", [.62,.80,.85])
            settings.set("/rtx/raytracing/inscattering/anisotropyFactor", .25)
            settings.set("/rtx/raytracing/inscattering/densityMult", .5)
            settings.set("/rtx/raytracing/inscattering/depthSlices", 128)
            settings.set("/rtx/raytracing/inscattering/maxAccumulationFrames", 8)
        settings.set("/rtx/fog/fogColor", [0.018 + 0.016 * turbidity,
                                          0.105 + 0.025 * turbidity,
                                          0.13 - 0.015 * turbidity])
        settings.set("/rtx/fog/fogColorIntensity", 0.75)
        settings.set("/rtx/fog/fogStartDist", 0.15)
        settings.set("/rtx/fog/fogEndDist", visibility * 2.5)
        settings.set("/rtx/fog/fogDistanceDensity", 1.2 + 1.6 * turbidity)
        settings.set("/rtx/fog/fogZup/enabled", True)
        settings.set("/rtx/post/tonemap/filmIso", 180.0)

    def _arm_pose(self, robot, snapshot):
        """Target-aware three-dimensional two-link *visual* IK.

        The mission validates attachment independently. This proxy places the
        gripper above the actual pickup/outplant coordinates so the animation
        does not visibly reach a generic point beside the operation.
        """
        shoulder = Gf.Vec3d(0.17, 0, -0.12)
        stowed = Gf.Vec3d(0.20, 0, -0.27)
        origin = _v(robot.get("position", [0, 0, 1.5]))
        yaw = float(robot.get("yaw", 0))
        jaw_world = robot.get("gripper_world")
        if jaw_world is not None:
            delta = _v(jaw_world) - origin
            jaw = Gf.Vec3d(math.cos(yaw) * delta[0] + math.sin(yaw) * delta[1],
                           -math.sin(yaw) * delta[0] + math.cos(yaw) * delta[1], delta[2])
        else:
            jaw = Gf.Vec3d(.34, 0, -.32)
        # Forearm ends at the wrist behind the contact point; jaw stays exactly
        # at the authoritative world-space grasp point from the mission core.
        tip = jaw + _wrist_offset(robot, (-.10, 0, 0))
        l1, l2 = 0.38, 0.40
        delta = tip - shoulder
        distance = delta.GetLength()
        if distance < 1e-6:
            delta, distance = Gf.Vec3d(0, 0, -1), 1.0
        axis = delta / distance
        distance = min(l1 + l2 - 0.001, max(abs(l1 - l2) + 0.001, distance))
        tip = shoulder + axis * distance
        along = (l1 * l1 - l2 * l2 + distance * distance) / (2.0 * distance)
        perpendicular = Gf.Vec3d(1, 0, 0) - axis * axis[0]
        if perpendicular.GetLength() < 1e-6:
            perpendicular = Gf.Vec3d(0, 1, 0) - axis * axis[1]
        perpendicular.Normalize()
        elbow = shoulder + axis * along + perpendicular * math.sqrt(max(0.0, l1 * l1 - along * along))
        return shoulder, elbow, jaw

    def _inspection_material(self, identifier, profile, health, mesh_paths, center, donor_id=None):
        """Author once: spatially gated host emission, independent of health labels."""
        name = "inspect_" + identifier
        self._material(name, (1., 1., 1.), vertex_color=True, roughness=.74, emission=(0., 0., 0.))
        self._surface_maps(name, "coral", "coral", diffuse=False, normal_strength=.5)
        if profile.get("scan_asset") == "pocillopora":
            UsdShade.Shader.Get(self.stage, self.materials[name].GetPath().AppendChild("normalTexture")).GetInput("file").Set(
                Sdf.AssetPath(pocillopora_textures()["normal"]))
        pigment = inspection_response(profile, health, 0., "white")["pigment_rgb"]
        for path in mesh_paths:
            mesh = UsdGeom.Mesh.Get(self.stage, path)
            colors = mesh.GetDisplayColorPrimvar().Get()
            mean = sum(sum(c) / 3 for c in colors) / max(1, len(colors))
            recolored = [_color(tuple(min(1., channel * max(.55, min(1.25, sum(c) / 3 / max(.02, mean))))
                                      for channel in pigment)) for c in colors]
            mesh.GetDisplayColorPrimvar().Set(Vt.Vec3fArray(recolored))
            self._bind(mesh, name)
        if (profile.get("scan_asset") == "pocillopora"
                and self.config.get("render", {}).get("realistic_tissue", False)):
            phenotype = "tan" if profile.get("synthetic_genotype") in ("R", "G") else profile["group"]
            self._tissue_texture_inputs(name, health, phenotype)
            # Polyps have local procedural UVs rather than the museum UV atlas.
            for path in mesh_paths:
                if path.endswith("/LivingPolyps"):
                    self._bind(UsdGeom.Mesh.Get(self.stage, path), "living_tissue")
        shader = UsdShade.Shader.Get(self.stage, self.materials[name].GetPath().AppendChild("Surface"))
        texture = UsdShade.Shader.Define(self.stage, self.materials[name].GetPath().AppendChild("HostResponse"))
        texture.CreateIdAttr("UsdUVTexture")
        response_map = (pocillopora_textures()["base_color"]
                        if profile.get("scan_asset") == "pocillopora"
                        else str(Path(__file__).resolve().parent.parent /
                                 "assets/materials/coral/coral_albedo_detail.png"))
        # The scan's spatial texture preserves recessed calices in the RGB
        # response proxy. It is not a measured fluorescence map.
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(response_map))
        texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        uv = UsdShade.Shader.Get(self.stage, self.materials[name].GetPath().AppendChild("UV"))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
        scale = texture.CreateInput("scale", Sdf.ValueTypeNames.Float4)
        scale.Set(Gf.Vec4f(0,0,0,1))
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.GetInput("emissiveColor").ConnectToSource(texture.ConnectableAPI(), "rgb")
        self._inspection_surfaces[identifier] = {"profile": profile, "health": health,
            "center": list(center), "donor_id": donor_id, "emission": scale}
        if (profile.get("scan_asset") == "pocillopora" and donor_id is None
                and self.config.get("render",{}).get("realistic_tissue",False)):
            import numpy as np
            colony = UsdGeom.Mesh.Get(self.stage,mesh_paths[0])
            matrix = UsdGeom.Xformable(colony.GetPrim()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            world = np.asarray([tuple(matrix.Transform(Gf.Vec3d(p))) for p in colony.GetPointsAttr().Get()],dtype=np.float32)
            normals = np.asarray(colony.GetNormalsAttr().Get(),dtype=np.float32)
            colors = np.asarray(colony.GetDisplayColorPrimvar().Get(),dtype=np.float32)
            detail = np.clip(colors.mean(axis=1)/max(.02,float(colors.mean())),.12,1.15)
            primvar = UsdGeom.PrimvarsAPI(colony).CreatePrimvar("hostEmission",Sdf.ValueTypeNames.Color3fArray,UsdGeom.Tokens.vertex)
            primvar.Set(Vt.Vec3fArray.FromNumpy(np.zeros_like(world)))
            reader = UsdShade.Shader.Define(self.stage,self.materials[name].GetPath().AppendChild("SpatialHostResponse"))
            reader.CreateIdAttr("UsdPrimvarReader_float3")
            reader.CreateInput("varname",Sdf.ValueTypeNames.Token).Set("hostEmission")
            reader.CreateOutput("result",Sdf.ValueTypeNames.Float3)
            shader.GetInput("emissiveColor").ConnectToSource(reader.ConnectableAPI(),"result")
            self._inspection_surfaces[identifier].update(spatial={"points":world,"normals":normals,"detail":detail,
                "primvar":primvar,"active":False,
                "bounds_center":((world.min(axis=0)+world.max(axis=0))*.5).tolist(),
                "bounds_radius":float(np.linalg.norm(world-(world.min(axis=0)+world.max(axis=0))*.5,axis=1).max())})

    def set_inspection_mode(self, mode, *, target_id=None, strength=1.):
        if mode not in MODES:
            raise ValueError(f"inspection mode must be one of {MODES}")
        if not math.isfinite(strength) or not 0. <= strength <= 1.:
            raise ValueError("inspection strength must be in [0,1]")
        if target_id is not None and target_id not in self.inspection_profiles:
            raise ValueError(f"Unknown inspection target: {target_id}")
        self._inspection_mode, self._inspection_target, self._inspection_strength = mode, target_id, strength
        if self._inspection_snapshot is not None:
            self._apply_inspection(self._inspection_snapshot)

    def inspection_metadata(self):
        return copy.deepcopy(self._inspection_info)

    def motion_metadata(self):
        return copy.deepcopy(self._motion_info)

    def aim_current(self, snapshot, time, current_override=None):
        """Fixed reef camera makes soft-tissue response observable at real speed."""
        state = copy.deepcopy(snapshot)
        state["time"] = float(time)
        if current_override is not None:
            state["water"]["current"] = list(current_override)
        recipient = next(c for c in state["corals"] if c["health"] == "bleached_alive")
        cx,cy,cz = recipient["position"]
        ch = self.corals[recipient["id"]]["visual_height"]
        worker = next(r for r in state["robots"] if r["role"] == "restoration")
        worker.update(position=[cx,cy-.85,cz+ch+.72],yaw=math.pi/2,wrist_yaw=0.,
                      gripper_world=[cx,cy-.37,cz+ch+.32],gripper_open=1.,state="INSPECTION_CASE",carrying=False)
        self._last_soft_time = -1.
        self._inspection_mode, self._inspection_target = "white", recipient["id"]
        self.update(state)
        self._look_at("worker",_v(worker["gripper_world"])+Gf.Vec3d(.18,.10,.08),(cx,cy,cz+ch*.5))
        UsdGeom.Camera.Get(self.stage,self.CAMERA_PATHS["worker"]).GetFocalLengthAttr().Set(25.)
        if not self._soft_corals:
            raise RuntimeError("Current review requires an unobstructed soft-coral site")
        fan = self._soft_corals[0]
        x,y,z = fan["position"]
        h = fan["data"]["motion"]["height"]
        eye = Gf.Vec3d(x,y-.85,z+.72)
        subject = Gf.Vec3d(x,y,z+h*.50)
        self._look_at("director",eye,subject)
        UsdGeom.Camera.Get(self.stage,self.CAMERA_PATHS["director"]).GetFocalLengthAttr().Set(25.)
        lamp,position,rotation = self._observer_torch
        position.Set(eye+Gf.Vec3d(.08,0,.04))
        rotation.Set(Gf.Rotation(Gf.Vec3d(0,0,-1),(subject-eye).GetNormalized()).GetQuat())
        lamp.GetIntensityAttr().Set(2000.)
        self._look_at("overview",(x+1.5,y-2.,z+1.2),(x,y,z+.3))
        state["motion"] = self.motion_metadata()
        return state

    @staticmethod
    def _beam_unoccluded(origin, destination, snapshot, ignore):
        # Conservative colony/rock volumes; actual raster visibility additionally
        # hides occluded surfaces. This is not spectral volumetric transport.
        return beam_unoccluded(origin,destination,snapshot.get("corals",[])+snapshot.get("obstacles",[]),ignore)

    def _apply_inspection(self, snapshot):
        if not self._inspection_enabled or self._inspection_beam is None:
            return
        self._inspection_snapshot = snapshot
        options = self.config.get("inspection", {})
        worker = next(r for r in snapshot["robots"] if r["id"] == self._inspection_beam["robot_id"])
        yaw = float(worker.get("yaw", 0.))
        def world(local):
            return _v(worker["position"]) + Gf.Vec3d(math.cos(yaw)*local[0] - math.sin(yaw)*local[1],
                math.sin(yaw)*local[0] + math.cos(yaw)*local[1], local[2])
        _, _, jaw = self._arm_pose(worker, snapshot)
        origin = world(jaw + _wrist_offset(worker, self._inspection_beam["offset"]))
        pickup = worker.get("state") in {"NAVIGATE_TO_DONOR", "NAVIGATE_TO_PICKUP", "SCAN_DONOR", "APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT"}
        scan_view = worker.get("state") in {"NAVIGATE_TO_SCAN_RECIPIENT", "SCAN_RECIPIENT", "NAVIGATE_TO_DONOR", "SCAN_DONOR"} and worker.get("scan_target_world")
        target_id = self._inspection_target or (worker.get("scan_target_id") if scan_view else None) or (worker.get("donor_id") if pickup else worker.get("task_id"))
        target = self._inspection_surfaces.get(target_id)
        destination = _v(target["center"]) if target else world(jaw) - Gf.Vec3d(0, 0, .4)
        if scan_view and self._inspection_target is None:
            destination = _v(worker["scan_target_world"])
        recipient = next((c for c in snapshot["corals"] if c["id"] == target_id), {})
        contact_view = worker.get("state") in {"LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER", "VERIFY_ATTACHMENT"} and recipient.get("contact_point")
        if contact_view:
            destination = _v(recipient["contact_point"])
        if worker.get("state") in {"FRAGMENT_LOST","RECOVER_FRAGMENT","RECOVERY_APPROACH","RECOVERY_GRASP","RECOVERY_LIFT"}:
            fragment=next((f for f in snapshot.get("fragments",[]) if f["id"]==worker.get("fragment_id")),None)
            if fragment:
                destination=_v(fragment["position"])+Gf.Vec3d(0,0,fragment.get("height",.08)*.5)
        direction = (destination - origin).GetNormalized()
        if scan_view and not self._inspection_target:
            pose = scan_light_pose(worker)
            assert (origin-_v(pose["light_position"])).GetLength()<2e-5,"Detection source differs from rendered wrist light"
            assert Gf.Dot(direction,_v(pose["light_direction"]))>1.-1e-7,"Detection direction differs from rendered wrist light"
        # The beam is parented to the rotating gripper. Aim its local gimbal
        # through the inverse combined body+wrist heading, not body yaw alone.
        tool_yaw = yaw + float(worker.get("wrist_yaw", 0.))
        local_direction = Gf.Vec3d(math.cos(tool_yaw)*direction[0] + math.sin(tool_yaw)*direction[1],
                                  -math.sin(tool_yaw)*direction[0] + math.cos(tool_yaw)*direction[1], direction[2])
        self._inspection_beam["orient"].Set(Gf.Rotation(Gf.Vec3d(0, 0, -1), local_direction).GetQuat())
        light_matrix = UsdGeom.Xformable(self._inspection_beam["light"]).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        rendered_origin = light_matrix.Transform(Gf.Vec3d(0))
        rendered_direction = light_matrix.TransformDir(Gf.Vec3d(0,0,-1)).GetNormalized()
        assert (rendered_origin-origin).GetLength()<2e-5,"Rendered wrist-light origin differs from optical model"
        assert Gf.Dot(rendered_direction,direction)>1.-1e-7,"Rendered wrist-light cone differs from optical model"
        mode, strength = self._inspection_mode, self._inspection_strength
        if mode == "auto":
            mode = auto_inspection_mode(worker["state"],carrying=bool(worker.get("carrying")))
        light = self._inspection_beam["light"]
        pilot = bool(options.get("visible_uv_pilot", False))
        light.GetColorAttr().Set(_color((.94, .98, 1.) if mode == "white" else
                                       (.34,.06,1.) if mode == "uv" and pilot else (.025, .12, 1.)))
        light.GetIntensityAttr().Set(strength * {"off": 0., "white": float(options.get("white_intensity", 450.)),
                                                "blue": float(options.get("blue_intensity", 35.)),
                                                "uv": float(options.get("uv_pilot_intensity", 45.)) if pilot else 0.}[mode])
        if options.get("auto_light_power",False):
            reference = max(.1,float(options.get("reference_distance_m",.6)))
            power_scale = max(.02,min(4.,((destination-origin).GetLength()/reference)**2))
            light.GetIntensityAttr().Set(light.GetIntensityAttr().Get()*power_scale)
        lens = UsdShade.Shader.Get(self.stage, "/World/Looks/inspection_lens/Surface")
        lens.GetInput("emissiveColor").Set(_color({"off": (0.,0.,0.), "white": (.4,.4,.4),
            "blue": (.01,.04,.7), "uv": (.08,.01,.12)}[mode]) * strength)
        # Identical low-ambient conditions in white/blue/UV comparisons.
        # UV itself contributes no visible illumination. An optional separate
        # violet aiming channel makes its co-aligned footprint visible.
        ambient = float(options.get("ambient_scale", .12))
        UsdLux.DistantLight.Get(self.stage, "/World/Environment/FilteredSun").GetIntensityAttr().Set(950. * ambient)
        UsdLux.DomeLight.Get(self.stage, "/World/Environment/WaterAmbient").GetIntensityAttr().Set(110. * ambient)
        for i in range(3):
            UsdLux.DiskLight.Get(self.stage, f"/World/Environment/SurfaceGlow{i}").GetIntensityAttr().Set(190. * ambient)
        for robot in snapshot["robots"]:
            base = "/World/Robots/" + _name(robot["id"])
            for path in (base + "/Headlight0", base + "/Headlight1", base + "/Gripper/InspectionLight"):
                UsdLux.SphereLight.Get(self.stage, path).GetIntensityAttr().Set(0.)
        fragments = {f["id"]: f for f in snapshot.get("fragments", [])}
        info = None
        active = []
        for identifier, surface in self._inspection_surfaces.items():
            point = _v(surface["center"])
            if (contact_view or scan_view) and identifier == target_id:
                point = destination
            if identifier in fragments:
                point = _v(fragments[identifier]["position"]) + Gf.Vec3d(0, 0, .07)
            exposure = strength * beam_exposure(list(point), list(origin), list(direction),
                range_m=float(options.get("range_m", 2.5)),
                half_angle_degrees=float(options.get("half_angle_degrees", 38.)),
                attenuation=float(options.get("attenuation", .35)))
            if not self._beam_unoccluded(origin, point, snapshot, {identifier, surface.get("donor_id")}):
                exposure = 0.
            response = inspection_response(surface["profile"], surface["health"], exposure, mode)
            emitted = _color(response["emission_rgb"]) * float(options.get("emission_gain", .22))
            surface["emission"].Set(Gf.Vec4f(*emitted, 1.))
            if "spatial" in surface:
                import numpy as np
                spatial = surface["spatial"]
                rgb = inspection_response(surface["profile"],surface["health"],1.,mode)["emission_rgb"]
                offset = _v(spatial["bounds_center"])-origin
                along = Gf.Dot(offset,direction)
                radius = spatial["bounds_radius"]
                lateral = (offset-direction*along).GetLength()
                # Conservative bounding sphere avoids updating large emission
                # arrays for colonies wholly outside the flashlight cone.
                intersects = (along+radius>0 and offset.GetLength()-radius<float(options.get("range_m",2.5))
                    and lateral-radius<=max(0.,along+radius)*math.tan(math.radians(float(options.get("half_angle_degrees",38.)))))
                active_spatial = strength > 0 and max(rgb) > 0 and intersects and self._beam_unoccluded(origin,point,snapshot,{identifier})
                if active_spatial:
                    delta = spatial["points"]-np.asarray(origin)
                    distance = np.linalg.norm(delta,axis=1)
                    cosine = (delta @ np.asarray(direction))/np.maximum(distance,1e-8)
                    angle = math.radians(float(options.get("half_angle_degrees",38.)))
                    angular = np.clip((cosine-math.cos(angle))/(math.cos(angle*.7)-math.cos(angle)),0,1)
                    angular = angular*angular*(3-2*angular)
                    taper = np.clip(1-(distance/float(options.get("range_m",2.5)))**2,0,1)**2
                    facing = np.clip(spatial["normals"] @ -np.asarray(direction)*2,0,1)
                    energy = angular*taper*np.exp(-float(options.get("attenuation",.35))*distance)*facing
                    energy *= spatial["detail"]*strength*float(options.get("emission_gain",.22))
                    values = (energy[:,None]*np.asarray(rgb)).astype(np.float32)
                    spatial["primvar"].Set(Vt.Vec3fArray.FromNumpy(values))
                elif spatial["active"]:
                    spatial["primvar"].Set(Vt.Vec3fArray.FromNumpy(np.zeros_like(spatial["points"])))
                spatial["active"] = active_spatial
            if max(response["emission_rgb"]) > .001:
                active.append(identifier)
            if identifier == target_id:
                info = dict(response, target_id=identifier, profile=surface["profile"],
                            light_position=list(origin), light_direction=list(direction))
        self._inspection_info = dict(info or {"target_id": target_id, "mode": mode, "exposure": 0.,
            "emission_rgb": [0.,0.,0.], "profile": {}}, source_strength=strength,
            active_surfaces=active, calibrated=False, ambient_scale=ambient,
            purpose="pre-harvest coral detection" if scan_view else "white-light manipulation or survey",
            scan_target_id=worker.get("scan_target_id"),
            visible_uv_pilot=pilot and mode == "uv" and strength > 0, uv_itself_visible=False,
            rendered_light_position=list(rendered_origin),rendered_light_direction=list(rendered_direction),
            visible_light_rgb=list(light.GetColorAttr().Get()),visible_light_intensity=float(light.GetIntensityAttr().Get()),
            beam_half_angle_degrees=float(options.get("half_angle_degrees",38.)),
            footprint_radius_m=(destination-origin).GetLength()*math.tan(math.radians(float(options.get("half_angle_degrees",38.)))))

    def aim_inspection(self, snapshot, target_id, mode):
        """Fixed-pose optical case tour, separate from autonomous mission time."""
        if not self._inspection_enabled:
            raise RuntimeError("Set inspection.enabled before building the scene")
        state = copy.deepcopy(snapshot)
        coral = next(c for c in state["corals"] if c["id"] == target_id)
        x, y, z = coral["position"]
        height = self.corals[target_id]["visual_height"]
        worker = next(r for r in state["robots"] if r["role"] == "restoration")
        worker.update(position=[x, y - .85, z + height + .72], yaw=math.pi/2, wrist_yaw=0.,
                      gripper_world=[x, y - .37, z + height + .32],
                      gripper_open=1., state="INSPECTION_CASE", carrying=False)
        self._inspection_mode, self._inspection_target, self._inspection_strength = mode, target_id, 1.
        self.update(state)
        eye = _v(worker["gripper_world"]) + Gf.Vec3d(.18, .10, .08)
        subject = Gf.Vec3d(x, y, z + height * .5)
        self._look_at("worker", eye, subject)
        UsdGeom.Camera.Get(self.stage, self.CAMERA_PATHS["worker"]).GetFocalLengthAttr().Set(19.)
        self._look_at("overview", (x + 1.65, y - 2.05, z + height + 1.05),
                      (x, y - .25, z + height * .65))
        self._look_at("director", (x + .9, y - 1.1, z + height + .25), subject)
        state["inspection"] = self.inspection_metadata()
        return state

    def update(self, snapshot: dict) -> None:
        """Update visual state without recreating scene geometry."""
        if self._observer_torch:
            self._observer_torch[0].GetIntensityAttr().Set(0.)
        time = float(snapshot.get("time", 0.0))
        water = snapshot.get("water", self.config.get("water", {}))
        render_options = self.config.get("render", {})
        show_telemetry = bool(render_options.get("show_telemetry", False))
        show_targets = bool(render_options.get("show_targets", False))
        self._set_water(water)
        for robot in snapshot.get("robots", []):
            identifier = str(robot.get("id", ""))
            data = self.robots.get(identifier)
            if not data:
                continue
            position = robot.get("position", [0, 0, 1.5])
            data["position"].Set(_v(position))
            data["yaw"].Set(math.degrees(float(robot.get("yaw", 0.0))))
            shoulder, elbow, tip = self._arm_pose(robot, snapshot)
            self._set_cylinder(data["arm1"], shoulder, elbow)
            self._set_cylinder(data["arm2"], elbow, tip + _wrist_offset(robot, (-.10, 0, 0)))
            data["elbow"].Set(_v(elbow))
            data["gripper"].Set(_v(tip))
            data["wrist_yaw"].Set(math.degrees(float(robot.get("wrist_yaw", 0.))))
            opening = max(0., min(1., float(robot.get("gripper_open", 1.))))
            separation = (float(robot.get("grasp_radius", .012)) + .006) + .038 * opening
            for index, side in enumerate((-1, 1)):
                data["fingers"][index].Set(Gf.Vec3d(0, side * separation, 0))
            trail = robot.get("trail", [])[-180:]
            data["trail"].GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if show_telemetry else UsdGeom.Tokens.invisible)
            if len(trail) > 1:
                # Thin, low-lying navigation lines preserve the reef silhouette.
                points = [_color((p[0], p[1], max(0.07, float(p[2]) - 0.55))) for p in trail]
                data["trail"].GetPointsAttr().Set(Vt.Vec3fArray(points))
                data["trail"].GetCurveVertexCountsAttr().Set([len(points)])
            target = robot.get("target")
            if isinstance(target, dict):
                target = target.get("position")
            if show_targets and isinstance(target, (list, tuple)) and len(target) >= 3:
                data["target"].GetPointsAttr().Set(Vt.Vec3fArray([_color(position), _color(target)]))
                data["target"].GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
            else:
                data["target"].GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        for coral in snapshot.get("corals", []):
            data = self.corals.get(str(coral.get("id", "")))
            if not data:
                continue
            observed = bool(coral.get("observed", False))
            attached = bool(coral.get("fragment_attached", False)) or str(coral.get("task_status", "")).lower() in ("attached", "verified", "complete", "fragment_attached")
            data["halo"].GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if show_telemetry and observed and not attached else UsdGeom.Tokens.invisible)
            data["verified"].GetVisibilityAttr().Set(UsdGeom.Tokens.inherited if show_telemetry and attached else UsdGeom.Tokens.invisible)
        for fragment in snapshot.get("fragments", []):
            data = self.fragments.get(fragment["id"])
            if data is None:
                raise RuntimeError(f"Fragment identity changed after scene build: {fragment['id']}")
            data["position"].Set(_v(fragment.get("base_world", fragment["position"])))
            data["rotation"].Set(Gf.Vec3f(0, 0, math.degrees(float(fragment.get("yaw", 0)))))
            data["root"].GetPrim().SetCustomDataByKey("reefsim:stage", fragment["stage"])
        for fish in self.fauna:
            pose = fauna_pose(fish["record"], time, snapshot)
            fish["position"].Set(_v(pose["position"]))
            fish["rotation"].Set(Gf.Vec3f(0, 0, math.degrees(pose["yaw"])))
            fish["tail"].Set(Gf.Vec3f(0, 0, math.degrees(pose["tail_angle"])))
        if self._soft_corals and (time - self._last_soft_time >= .025 or time < self._last_soft_time):
            import numpy as np
            flow = water.get("current", [0., 0., 0.])
            maximum = 0.
            for index,coral in enumerate(self._soft_corals):
                angle = coral["yaw"]
                local_flow = [math.cos(angle)*flow[0]+math.sin(angle)*flow[1],
                              -math.sin(angle)*flow[0]+math.cos(angle)*flow[1], flow[2]]
                pose = current_pose(coral["data"], time, local_flow)
                coral["mesh"].GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(pose["points"],dtype=np.float32)))
                coral["mesh"].GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(pose["normals"],dtype=np.float32)))
                maximum = max(maximum,math.hypot(*pose["tip_displacement"]))
                if index == 0:
                    tip = pose["points"][coral["tip_index"]]
                    origin = coral["position"]
                    self._motion_info = {"tracked_tip_world":[origin[0]+math.cos(angle)*tip[0]-math.sin(angle)*tip[1],
                        origin[1]+math.sin(angle)*tip[0]+math.cos(angle)*tip[1],origin[2]+tip[2]],
                        "flow_velocity":pose["flow_velocity"],"max_shear":pose["max_shear"],
                        "fan_count":len(self._soft_corals),"rigid_skeleton":True}
            polyp_maximum = 0.
            for patch in self._polyp_patches:
                pose = polyp_current_pose(patch["data"],time,flow)
                patch["mesh"].GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(pose["points"],dtype=np.float32)))
                patch["mesh"].GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(pose["normals"],dtype=np.float32)))
                polyp_maximum = max(polyp_maximum,pose["max_displacement"])
            self._motion_info.update(max_tip_displacement_m=maximum,max_polyp_displacement_m=polyp_maximum)
            self._last_soft_time = time
        if self._particles and (time - self._last_time > 0.1 or time < self._last_time):
            current = water.get("current", [0.03, 0.01, 0])
            if isinstance(current, dict):
                current = current.get("vector", [0.03, 0.01, 0])
            vx = float(current[0]) if len(current) else 0.03
            vy = float(current[1]) if len(current) > 1 else 0.01
            points = []
            for i, (x, y, z) in enumerate(self._particle_origins):
                points.append(_color((((x + vx * time + 9) % 18) - 9,
                                      ((y + vy * time + 0.015 * math.sin(time + i) + 9) % 18) - 9,
                                      0.1 + ((z - self._particle_speeds[i] * time) % min(self.depth - 0.2, 6.3)))))
            self._particles.GetPointsAttr().Set(Vt.Vec3fArray(points))
            self._last_time = time
        self._update_cameras(snapshot)
        self._apply_inspection(snapshot)
