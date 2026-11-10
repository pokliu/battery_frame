# -*- coding: utf-8 -*-
"""
电池支架 v2 —— 受力分析（FreeCAD FEM + Gmsh + CalculiX）

先 exec battery_holder_v2.py（只取函数和参数，不需要 build_all），再 exec 本文件：
    exec(open('/Users/admin/Downloads/battery/battery_holder_v2.py', encoding='utf-8').read())
    exec(open('/Users/admin/Downloads/battery/fem_v2.py', encoding='utf-8').read())
    setup_cap(); solve()            # 端盖：电芯轴向冲击
    setup_slice('down'); solve()    # 主体切片：竖直向下冲击
    setup_slice('up');   solve()    # 主体切片：竖直向上（回弹顶压框）

只在独立文档「电池支架_v2_FEA」里建模，不改动「电池支架_v2」。
线性静力分析：应力与载荷成正比，10 g 结果 = 5 g 结果 × 2。
"""
import math

import FreeCAD as App
import ObjectsFem
import Part
from FreeCAD import Vector as V

FEA_DOC = "电池支架_v2_FEA"

FP = {
    "cell_mass": 0.300,        # kg/只
    "g": 9.81,
    "a_design": 5.0,           # 设计冲击（g）：40 km/h 过坑/减速带的等效静载假设
    # PETG 50 °C（打印件、估算值）
    "E_50": 1700.0,            # MPa（室温约 2000）
    "E_23": 2000.0,
    "nu": 0.38,
    "rho": 1270.0,
    "cell_end_r": 16.6,        # 电芯端面外缘半径（接触环外径）
    "slice_t": 2.0,            # 主体切片厚度
    "frame_pad_w": 3.0,        # 压框左墙压在主体左上沿的宽度
    "mesh": {"cap": (1.2, 0.4), "slice": (0.9, 0.3)},
}


def cell_force(a=None):
    return FP["cell_mass"] * FP["g"] * (a or FP["a_design"])


def fea_doc(reset=True):
    for name, doc in App.listDocuments().items():
        if name == FEA_DOC or doc.Label == FEA_DOC:
            if not reset:
                return doc
            App.closeDocument(name)
            break
    doc = App.newDocument(FEA_DOC)
    doc.Label = FEA_DOC
    return doc


def z_edge(shape):
    """找一条沿 Z 的直棱，供力方向引用。返回 (EdgeN, 是否需要 Reversed 才指向 -Z)。"""
    for k, e in enumerate(shape.Edges):
        if e.Curve.TypeId == "Part::GeomLine":
            d = e.Vertexes[-1].Point - e.Vertexes[0].Point
            if abs(d.x) < 1e-6 and abs(d.y) < 1e-6 and d.Length > 1:
                return "Edge%d" % (k + 1), d.z > 0
    raise RuntimeError("no Z edge")


def y_edge(shape):
    for k, e in enumerate(shape.Edges):
        if e.Curve.TypeId == "Part::GeomLine":
            d = e.Vertexes[-1].Point - e.Vertexes[0].Point
            if abs(d.x) < 1e-6 and abs(d.z) < 1e-6 and d.Length > 1:
                return "Edge%d" % (k + 1), d.y
    raise RuntimeError("no Y edge")


def base_analysis(doc, shape, kind):
    geo = doc.addObject("Part::Feature", "Geo")
    geo.Shape = shape
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    mat = ObjectsFem.makeMaterialSolid(doc, "PETG_50C")
    mat.Material = {"Name": "PETG 打印件 50°C（估算）", "YoungsModulus": "%g MPa" % FP["E_50"],
                    "PoissonRatio": str(FP["nu"]), "Density": "%g kg/m^3" % FP["rho"]}
    an.addObject(mat)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = geo
    mx, mn = FP["mesh"][kind]
    mesh.CharacteristicLengthMax = mx
    mesh.CharacteristicLengthMin = mn
    # 压框的 45° 菱形窗会产生扁平四面体，二阶单元出现负雅可比；压框以受压为主，用一阶 + 细网格
    mesh.ElementOrder = "1st" if kind == "frame" else "2nd"
    # 端盖：中间节点取直线，避免负雅可比（载荷面都是平面）。
    # 切片：载荷加在圆柱孔面上，中间节点必须落在曲面上，否则 FreeCAD 找不到面单元、载荷为 0。
    mesh.SecondOrderLinear = (kind in ("cap", "frame"))
    an.addObject(mesh)
    doc.recompute()
    from femmesh.gmshtools import GmshTools
    err = GmshTools(mesh).create_mesh()
    sv = ObjectsFem.makeSolverCalculiXCcxTools(doc, "SolverCcxTools")
    # 自带 ccx 的 spooles 在 ~35 万节点以上会段错误；pastix/pardiso 没有链接，用迭代 Cholesky
    # 端盖/压框是薄板，迭代法收敛极慢 → 用 spooles，网格控制在 33 万节点以内
    sv.MatrixSolverType = "iterativecholesky" if kind == "slice" else "spooles"
    an.addObject(sv)
    doc.recompute()
    return geo, an, mesh, err


def add_force(doc, an, geo, faces, newton, dir_edge, reversed_, name):
    f = ObjectsFem.makeConstraintForce(doc, name)
    f.References = [(geo, faces)]
    f.Force = App.Units.Quantity("%.4f N" % newton)
    f.Direction = (geo, [dir_edge])
    f.Reversed = reversed_
    an.addObject(f)
    return f


def add_fixed(doc, an, geo, faces, name):
    c = ObjectsFem.makeConstraintFixed(doc, name)
    c.References = [(geo, faces)]
    an.addObject(c)
    return c


# ------------------------------------------------------------
# 工况 1：端盖，电芯沿轴向冲向端盖
# ------------------------------------------------------------
CTX = {}


def setup_cap():
    doc = fea_doc()
    cap = make_cap("A")                          # A 端端盖，贴合面 Z=0，外侧 Z<0
    disks = [Part.Face(Part.Wire(Part.makeCircle(FP["cell_end_r"], V(*cc(*c), 0)))) for c in cells()]
    from BOPTools import SplitAPI
    frag = SplitAPI.booleanFragments([cap] + disks, "Split", 0.0)
    cap_s = max(frag.Solids, key=lambda s: s.Volume)
    geo, an, mesh, err = base_analysis(doc, cap_s, "cap")
    # 接触环：Z=0 平面上、中心在电芯 Ø33.2 圆内的面
    ring = []
    for k, f in enumerate(cap_s.Faces):
        c = f.CenterOfMass
        if f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax) < 1e-6 and abs(f.BoundBox.ZMin) < 1e-6:
            if any(math.hypot(c.x - cc(*q)[0], c.y - cc(*q)[1]) < 1.0 for q in cells()) and f.Area < 700:
                ring.append("Face%d" % (k + 1))
    # 螺丝头压面：沉孔底（Z=-boss_t）环面
    fix = []
    for k, f in enumerate(cap_s.Faces):
        if f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax + P["boss_t"]) < 1e-6 \
                and abs(f.BoundBox.ZMin + P["boss_t"]) < 1e-6:
            fix.append("Face%d" % (k + 1))
    edge, rev = z_edge(cap_s)
    F = cell_force()
    for n, fc in enumerate(ring):
        add_force(doc, an, geo, [fc], F, edge, rev, "Cell%02d" % n)
    add_fixed(doc, an, geo, fix, "ScrewHeads")
    doc.recompute()
    CTX.clear()
    CTX.update(kind="cap", doc=doc, an=an, mesh=mesh, n_ring=len(ring), n_fix=len(fix),
               total_N=F * len(ring), mesh_err=err)
    return dict(接触环面数=len(ring), 螺丝压面数=len(fix), 单只力N=round(F, 2), 合力N=round(F * len(ring), 1),
                网格节点=mesh.FemMesh.NodeCount, 网格单元=mesh.FemMesh.VolumeCount, gmsh=err)


# ------------------------------------------------------------
# 工况 2/3：主体中段切片（Z 70~72），竖直冲击
# ------------------------------------------------------------
def slice_shape():
    d = D()
    t = FP["slice_t"]
    z0 = 70.0
    s = outline_face(z0).extrude(V(0, 0, t))
    rails = [box(x - P["rail_w"] / 2, x + P["rail_w"] / 2, d["H5"], d["H5"] + P["rail_h"], z0, z0 + t)
             for x in rail_xs()]
    pad = box(0, FP["frame_pad_w"], d["H5"], d["H5"] + 0.5, z0, z0 + t)   # 压框左墙接触带
    s = s.fuse(rails + [pad])
    tools = [cyl(P["lighten_d"] / 2, z0 - 1, z0 + t + 1, x, y) for x, y in lighten_stars()]
    tools.append(ntc_slot_solid(ntc_end()))
    s = s.cut(tools).removeSplitter()
    # 电芯孔按上下半圆分两次切，孔面自然分成上半、下半
    r = P["hole_d"] / 2
    up, lo = [], []
    for c in cells():
        x, y = cc(*c)
        u = Part.makeCylinder(r, t + 2, V(x, y, z0 - 1), V(0, 0, 1), 180)
        l_ = u.copy()
        l_.rotate(V(x, y, 0), V(0, 0, 1), 180)
        up.append(u)
        lo.append(l_)
    s = s.cut(Part.makeCompound(up))
    s = s.cut(Part.makeCompound(lo))
    return s


def setup_slice(case="down"):
    d = D()
    doc = fea_doc()
    s = slice_shape()
    geo, an, mesh, err = base_analysis(doc, s, "slice")
    r = P["hole_d"] / 2
    halves = {}
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Radius - r) < 1e-4:
            c = f.CenterOfMass
            for q in cells():
                x, y = cc(*q)
                if math.hypot(c.x - x, c.y - y) < r:
                    halves.setdefault(q, {"up": [], "lo": []})["up" if c.y > y else "lo"].append("Face%d" % (k + 1))
    edge, ydir = y_edge(s)
    F = cell_force() * FP["slice_t"] / P["cell_len"]
    key = "lo" if case == "down" else "up"
    # down：力指向 -Y；up：力指向 +Y
    want_pos = case == "up"
    rev = (ydir > 0) != want_pos
    n = 0
    for q, hv in halves.items():
        add_force(doc, an, geo, hv[key], F, edge, rev, "Cell_%d_%d" % q)
        n += 1
    fix = []
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId != "Part::GeomPlane":
            continue
        bb = f.BoundBox
        if abs(bb.YMax - bb.YMin) > 1e-6:
            continue
        if case == "down" and abs(bb.YMin) < 1e-6:
            fix.append("Face%d" % (k + 1))                                   # 箱底
        if case == "up" and (abs(bb.YMin - d["HT"]) < 1e-6 or
                             (abs(bb.YMin - d["H5"] - 0.5) < 1e-6 and bb.XMax <= FP["frame_pad_w"] + 1e-6)):
            fix.append("Face%d" % (k + 1))                                   # 压框接触面
    add_fixed(doc, an, geo, fix, "Support")
    doc.recompute()
    CTX.clear()
    CTX.update(kind="slice_" + case, doc=doc, an=an, mesh=mesh, total_N=F * n)
    return dict(工况=case, 加载电芯数=n, 每只切片力N=round(F, 4), 支撑面=len(fix), 等效整段合力N=round(cell_force() * n, 1),
                网格节点=mesh.FemMesh.NodeCount, 网格单元=mesh.FemMesh.VolumeCount, gmsh=err)


# ------------------------------------------------------------
# 求解与后处理
# ------------------------------------------------------------
def solve():
    from femtools import ccxtools
    fea = ccxtools.FemToolsCcx(CTX["an"])
    fea.update_objects()
    fea.setup_working_dir()
    fea.setup_ccx()
    msg = fea.check_prerequisites()
    if msg:
        return {"error": msg}
    fea.purge_results()
    fea.write_inp_file()
    fea.ccx_run()
    tail = (getattr(fea, "ccx_stdout", "") or "")
    if "*ERROR" in tail:
        return {"error": tail[tail.find("*ERROR"):][:500], "dir": fea.working_dir}
    fea.load_results()
    return post()


def post():
    doc = CTX["doc"]
    res = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemResultObject")][-1]
    vm = list(res.vonMises)
    dl = list(res.DisplacementLengths)
    nodes = res.Mesh.FemMesh.Nodes
    nn = list(res.NodeNumbers)
    srt = sorted(vm)
    imax = max(range(len(vm)), key=lambda i: vm[i])
    p = nodes[nn[imax]]
    s1 = list(res.PrincipalMax) if hasattr(res, "PrincipalMax") else []
    out = dict(工况=CTX["kind"], 节点数=len(vm),
               vonMises最大MPa=round(srt[-1], 2),
               vonMises_99_9分位MPa=round(srt[int(len(srt) * 0.999)], 2),
               vonMises_99分位MPa=round(srt[int(len(srt) * 0.99)], 2),
               最大应力位置=(round(p.x, 1), round(p.y, 1), round(p.z, 1)),
               最大位移mm=round(max(dl), 4))
    if s1:
        out["最大主拉应力MPa"] = round(max(s1), 2)
    CTX["res"] = res
    return out


# ------------------------------------------------------------
# 工况 4：顶部压框，整包向上冲击、压框顶住箱盖
# ------------------------------------------------------------
def pack_mass():
    """被压框挡住的质量：电芯 + 主体/端盖（按 30% 填充 + 4 圈壁估 55% 实体）+ BMS 约 0.35 kg。"""
    d = D()
    body = make_body()
    caps = make_cap("A").Volume + make_cap("B").Volume
    plastic = (body.Volume + caps) * 1e-9 * FP["rho"] * 0.55
    return len(cells()) * FP["cell_mass"] + plastic + 0.35


def setup_frame(mass=None):
    d = D()
    doc = fea_doc()
    s = make_frame()
    geo, an, mesh, err = base_analysis(doc, s, "frame")
    load, fix = [], []
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId != "Part::GeomPlane":
            continue
        bb = f.BoundBox
        if abs(bb.YMax - bb.YMin) > 1e-6:
            continue
        if abs(bb.YMin - d["H5"]) < 1e-6 or abs(bb.YMin - d["HT"]) < 1e-6:
            load.append("Face%d" % (k + 1))
        if abs(bb.YMin - d["YT"]) < 1e-6:
            fix.append("Face%d" % (k + 1))
    m = mass or pack_mass()
    F = m * FP["g"] * FP["a_design"]
    edge, ydir = y_edge(s)
    add_force(doc, an, geo, load, F, edge, ydir < 0, "PackUp")
    add_fixed(doc, an, geo, fix, "Lid")
    doc.recompute()
    CTX.clear()
    CTX.update(kind="frame_up", doc=doc, an=an, mesh=mesh, total_N=F)
    return dict(受压质量kg=round(m, 2), 合力N=round(F, 1), 加载面=len(load), 箱盖面=len(fix),
                网格节点=mesh.FemMesh.NodeCount, gmsh=err)


FP["mesh"]["frame"] = (2.5, 0.8)
