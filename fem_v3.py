# -*- coding: utf-8 -*-
"""
电池支架 v3 —— 受力分析（FreeCAD FEM + Gmsh + CalculiX）

先 exec battery_holder_v3.py（只用函数和参数），再 exec 本文件：
    exec(open('/Users/admin/Downloads/battery/battery_holder_v3.py', encoding='utf-8').read())
    exec(open('/Users/admin/Downloads/battery/fem_v3.py', encoding='utf-8').read())
    setup_seat_axial(50); solve()     # 侧摔：电芯沿 Z 冲向挡边，支撑垫/外周凸台顶住
    setup_seat_lateral('x'); solve()  # 前后 5 g：电芯推孔壁，外侧面顶箱壁
    setup_seat_lateral('down'); solve()
    setup_seat_lateral('up'); solve()
    setup_frame(); solve()            # 整包向上 5 g，压框顶箱盖

只在独立文档「电池支架_v3_FEA」里建模。线性静力：应力与载荷成正比。
电芯座模型不含定位管和 BMS 导轨（偏保守）。无界面批量运行见 fem_run_v3.py。
"""
import math

import FreeCAD as App
import ObjectsFem
import Part
from FreeCAD import Vector as V

FEA_DOC = "电池支架_v3_FEA"

FP = {
    "g": 9.81,
    "a_axial": 50.0,           # 侧摔（Z）
    "a_road": 5.0,             # 前后 / 竖直（40 km/h 城市路面）
    "E_50": 1700.0, "nu": 0.38, "rho": 1270.0,
    "cell_end_r": 16.6,        # 电芯端面外缘（接触环外径）
    "frame_pad_w": 3.0,        # 压框左/右墙压在座顶面的宽度
    "mesh": {"seat": (2.5, 0.7), "frame": (2.5, 0.8)},
    "second_order_linear": {"seat": False, "frame": True},
}


def cell_force(a):
    return P["cell_mass"] * FP["g"] * a


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


def dir_edge(shape, axis):
    """找一条沿 axis（'x'/'y'/'z'）的直棱，返回 (EdgeN, 该棱方向分量符号)。"""
    k_ = "xyz".index(axis)
    for k, e in enumerate(shape.Edges):
        if e.Curve.TypeId == "Part::GeomLine":
            d = e.Vertexes[-1].Point - e.Vertexes[0].Point
            comp = (d.x, d.y, d.z)
            if all(abs(comp[i]) < 1e-6 for i in range(3) if i != k_) and d.Length > 1:
                return "Edge%d" % (k + 1), comp[k_]
    raise RuntimeError("no %s edge" % axis)


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
    # 压框菱形窗会出扁平单元，二阶报负雅可比 → 一阶 + 细网格
    mesh.ElementOrder = "1st" if kind == "frame" else "2nd"
    mesh.SecondOrderLinear = FP["second_order_linear"][kind]
    # 曲面上的二阶中间节点会造成负雅可比：让 Gmsh 做高阶优化
    if mesh.ElementOrder == "2nd" and not mesh.SecondOrderLinear and hasattr(mesh, "HighOrderOptimize"):
        opts = mesh.getEnumerationsOfProperty("HighOrderOptimize")
        for o in ("Optimization", "Elastic+Optimization"):
            if o in opts:
                mesh.HighOrderOptimize = o
                break
        CTX["hoo"] = (mesh.HighOrderOptimize, opts)
    an.addObject(mesh)
    doc.recompute()
    from femmesh.gmshtools import GmshTools
    err = GmshTools(mesh).create_mesh()
    sv = ObjectsFem.makeSolverCalculiXCcxTools(doc, "SolverCcxTools")
    n = mesh.FemMesh.NodeCount
    # spooles 在 ~35 万节点以上会段错误
    sv.MatrixSolverType = "spooles" if n < 330000 else "iterativecholesky"
    an.addObject(sv)
    doc.recompute()
    return geo, an, mesh, err


def add_force(doc, an, geo, faces, newton, edge, reversed_, name):
    f = ObjectsFem.makeConstraintForce(doc, name)
    f.References = [(geo, faces)]
    f.Force = App.Units.Quantity("%.4f N" % newton)
    f.Direction = (geo, [edge])
    f.Reversed = reversed_
    an.addObject(f)
    return f


def add_fixed(doc, an, geo, faces, name):
    c = ObjectsFem.makeConstraintFixed(doc, name)
    c.References = [(geo, faces)]
    an.addObject(c)
    return c


CTX = {}


# ------------------------------------------------------------
# 电芯座几何（A 座，不含定位管/导轨）
# ------------------------------------------------------------
def seat_plain(hole_tools=True):
    d = D()
    lip, zi = d["lip"], d["seat_in"]
    s = outline_face(-lip).extrude(V(0, 0, P["seat_depth"]))
    tools = []
    for c in cells():
        x, y = cc(*c)
        if hole_tools:
            tools.append(cyl(P["hole_d"] / 2, 0, zi + 1, x, y))
        tools.append(cyl(P["end_hole_d"] / 2, -lip - 1, 1, x, y))
    for st in lighten_stars():
        tools.append(cyl(P["lighten_d"] / 2, -lip - 1, zi + 1, *star(*st)))
    for x, y in rod_pts():
        tools.append(cyl(P["rod_hole_d"] / 2, -lip - 1, zi + 1, x, y))
    tools.append(cyl(P["ntc_hole_d"] / 2, -lip - 1, zi + 1, *star(*ntc_star())))
    return s.cut(tools).removeSplitter()


# ------------------------------------------------------------
# 工况 1：侧摔，电芯沿轴向冲向挡边
# ------------------------------------------------------------
def setup_seat_axial(a=None, end="A"):
    """end 决定用哪一端端盖的支撑垫布置（两端方片位置不同，支撑垫缺的位置不同）。
    两片座几何互为镜像，统一在 A 座坐标下计算。"""
    a = a or FP["a_axial"]
    d = D()
    lip = d["lip"]
    seat = seat_plain()
    disks = [Part.Face(Part.Wire(Part.makeCircle(FP["cell_end_r"], V(*cc(*c), 0)))) for c in cells()]
    pads = []
    for st in pad_stars(end):
        r = (P["rod_pad_d"] if st in P["rods"] else P["pad_d"]) / 2
        pads.append(Part.Face(Part.Wire(Part.makeCircle(r, V(*star(*st), -lip)))))
    of = outline_face(-lip)
    rim = of.cut(of.makeOffset2D(-P["rim_w"], 2))
    from BOPTools import SplitAPI
    frag = SplitAPI.booleanFragments([seat] + disks + pads + [rim], "Split", 0.0)
    s = max(frag.Solids, key=lambda x: x.Volume)
    doc_ = fea_doc()
    geo, an, mesh, err = base_analysis(doc_, s, "seat")
    load, fix = [], []
    corner = Part.Vertex(V(1.0, 1.0, -lip))
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId != "Part::GeomPlane":
            continue
        bb = f.BoundBox
        c = f.CenterOfMass
        if abs(bb.ZMax) < 1e-6 and abs(bb.ZMin) < 1e-6 and 100 < f.Area < 700:
            if any(math.hypot(c.x - cc(*q)[0], c.y - cc(*q)[1]) < 1.0 for q in cells()):
                load.append("Face%d" % (k + 1))
        if abs(bb.ZMax + lip) < 1e-6 and abs(bb.ZMin + lip) < 1e-6:
            in_pad = any(math.hypot(c.x - star(*st)[0], c.y - star(*st)[1]) < 1.0 for st in pad_stars(end))
            in_rim = f.distToShape(corner)[0] < 1e-6
            if in_pad or in_rim:
                fix.append("Face%d" % (k + 1))
    edge, comp = dir_edge(s, "z")
    F = cell_force(a)
    per = {}
    for fc in load:
        c = s.Faces[int(fc[4:]) - 1].CenterOfMass
        q = min(cells(), key=lambda q: math.hypot(c.x - cc(*q)[0], c.y - cc(*q)[1]))
        per.setdefault(q, []).append(fc)
    for q, fcs in per.items():
        add_force(doc_, an, geo, fcs, F, edge, comp > 0, "Cell_%d_%d" % q)     # 指向 -Z
    load = list(per)
    add_fixed(doc_, an, geo, fix, "PadsRim")
    doc_.recompute()
    fix_area = sum(s.Faces[int(n[4:]) - 1].Area for n in fix)
    CTX.clear()
    CTX.update(kind="seat_axial_%gg_lip%.1f_pads%s" % (a, lip, end), doc=doc_, an=an, mesh=mesh, fix_area=fix_area,
               total_N=F * len(load))
    return dict(工况=CTX["kind"], 加载环数=len(load), 支撑面数=len(fix), 支撑面积mm2=round(fix_area),
                合力N=round(F * len(load), 1), 平均支撑压应力MPa=round(F * len(load) / fix_area, 3),
                网格节点=mesh.FemMesh.NodeCount, gmsh=err)


# ------------------------------------------------------------
# 工况 2/3/4：前后 5 g（x）、竖直向下（down）、竖直向上（up）
# 每只电芯的力由两片座平分；载荷加在孔面的受压半圆上
# ------------------------------------------------------------
def setup_seat_lateral(case="x", a=None):
    a = a or FP["a_road"]
    d = D()
    lip, zi, W, H5, HT = d["lip"], d["seat_in"], d["W"], d["H5"], d["HT"]
    s = seat_plain(hole_tools=False)
    r = P["hole_d"] / 2
    rot = {"x": -90, "down": 180, "up": 0}[case]     # 受压半圆朝向：+X / -Y / +Y
    halves_a, halves_b = [], []
    for c in cells():
        x, y = cc(*c)
        h1 = Part.makeCylinder(r, zi + 1, V(x, y, 0), V(0, 0, 1), 180)
        h1.rotate(V(x, y, 0), V(0, 0, 1), rot)
        h2 = h1.copy()
        h2.rotate(V(x, y, 0), V(0, 0, 1), 180)
        halves_a.append(h1)
        halves_b.append(h2)
    s = s.cut(Part.makeCompound(halves_a)).cut(Part.makeCompound(halves_b))
    if case == "up":
        # 压框左墙（X 0~3，Y=H5）和右墙（X W-3~W，Y=HT）的接触带：切分顶面
        pw = FP["frame_pad_w"]
        from BOPTools import SplitAPI
        cut1 = Part.Face(Part.makePolygon([V(pw, H5 - 1, -lip - 1), V(pw, H5 + 1, -lip - 1), V(pw, H5 + 1, zi + 1),
                                           V(pw, H5 - 1, zi + 1), V(pw, H5 - 1, -lip - 1)]))
        cut2 = Part.Face(Part.makePolygon([V(W - pw, HT - 1, -lip - 1), V(W - pw, HT + 1, -lip - 1),
                                           V(W - pw, HT + 1, zi + 1), V(W - pw, HT - 1, zi + 1),
                                           V(W - pw, HT - 1, -lip - 1)]))
        s = max(SplitAPI.booleanFragments([s, cut1, cut2], "Split", 0.0).Solids, key=lambda x: x.Volume)
    doc = fea_doc()
    geo, an, mesh, err = base_analysis(doc, s, "seat")
    load = []
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Radius - r) < 1e-4:
            c = f.CenterOfMass
            for q in cells():
                x, y = cc(*q)
                if math.hypot(c.x - x, c.y - y) < r:
                    want = {"x": c.x > x, "down": c.y < y, "up": c.y > y}[case]
                    if want:
                        load.append("Face%d" % (k + 1))
    fix = []
    for k, f in enumerate(s.Faces):
        if f.Surface.TypeId != "Part::GeomPlane":
            continue
        bb = f.BoundBox
        if case == "x" and abs(bb.XMin - W) < 1e-6 and abs(bb.XMax - W) < 1e-6:
            fix.append("Face%d" % (k + 1))
        if case == "down" and abs(bb.YMin) < 1e-6 and abs(bb.YMax) < 1e-6:
            fix.append("Face%d" % (k + 1))
        if case == "up" and abs(bb.YMax - bb.YMin) < 1e-6:
            if (abs(bb.YMin - H5) < 1e-6 and bb.XMax <= FP["frame_pad_w"] + 1e-6) or \
                    (abs(bb.YMin - HT) < 1e-6 and bb.XMin >= W - FP["frame_pad_w"] - 1e-6):
                fix.append("Face%d" % (k + 1))
    axis = "x" if case == "x" else "y"
    edge, comp = dir_edge(s, axis)
    want_pos = case in ("x", "up")
    rev = (comp > 0) != want_pos
    n_cells = len(cells())
    Ftot = cell_force(a) / 2 * n_cells          # 两片座平分
    # 每个电芯半圆可能被切成多个面：按电芯平均分配
    per = {}
    for fc in load:
        c = s.Faces[int(fc[4:]) - 1].CenterOfMass
        q = min(cells(), key=lambda q: math.hypot(c.x - cc(*q)[0], c.y - cc(*q)[1]))
        per.setdefault(q, []).append(fc)
    for q, fcs in per.items():
        add_force(doc, an, geo, fcs, cell_force(a) / 2, edge, rev, "Cell_%d_%d" % q)
    add_fixed(doc, an, geo, fix, "Support")
    doc.recompute()
    CTX.clear()
    CTX.update(kind="seat_%s_%gg_lip%.1f" % (case, a, lip), doc=doc, an=an, mesh=mesh, total_N=Ftot)
    return dict(工况=CTX["kind"], 加载电芯数=len(per), 支撑面数=len(fix), 合力N=round(Ftot, 1),
                网格节点=mesh.FemMesh.NodeCount, gmsh=err)


# ------------------------------------------------------------
# 工况 5：压框，整包向上冲击、顶住箱盖
# ------------------------------------------------------------
def pack_mass():
    plastic = sum(x.Volume for x in (make_seat("A"), make_seat("B"), make_cap("A"), make_cap("B")))
    return len(cells()) * P["cell_mass"] + plastic * 1e-9 * FP["rho"] * 0.55 + 0.35


def setup_frame(mass=None, a=None):
    a = a or FP["a_road"]
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
    F = m * FP["g"] * a
    edge, comp = dir_edge(s, "y")
    add_force(doc, an, geo, load, F, edge, comp < 0, "PackUp")
    add_fixed(doc, an, geo, fix, "Lid")
    doc.recompute()
    CTX.clear()
    CTX.update(kind="frame_up_%gg" % a, doc=doc, an=an, mesh=mesh, total_N=F)
    return dict(受压质量kg=round(m, 2), 合力N=round(F, 1), 加载面=len(load), 箱盖面=len(fix),
                网格节点=mesh.FemMesh.NodeCount, gmsh=err)


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
    out = dict(工况=CTX["kind"], 节点数=len(vm),
               vonMises最大MPa=round(srt[-1], 2),
               vonMises_99_9分位MPa=round(srt[int(len(srt) * 0.999)], 2),
               vonMises_99分位MPa=round(srt[int(len(srt) * 0.99)], 2),
               最大应力位置=(round(p.x, 1), round(p.y, 1), round(p.z, 1)),
               最大位移mm=round(max(dl), 4))
    s1 = list(getattr(res, "PrincipalMax", []) or [])
    s3 = list(getattr(res, "PrincipalMin", []) or [])
    if s1:
        ss = sorted(s1)
        out["最大主拉应力MPa"] = round(ss[-1], 2)
        out["主拉应力_99_9分位MPa"] = round(ss[int(len(ss) * 0.999)], 2)
        i1 = max(range(len(s1)), key=lambda i: s1[i])
        q = nodes[nn[i1]]
        out["主拉最大位置"] = (round(q.x, 1), round(q.y, 1), round(q.z, 1))
    if s3:
        out["最大主压应力MPa"] = round(min(s3), 2)
    CTX["res"] = res
    return out
