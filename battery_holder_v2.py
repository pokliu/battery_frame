# -*- coding: utf-8 -*-
"""
32140 16S2P 电池支架 v2 —— 参数化建模脚本（FreeCAD Part 工作台）

运行（FreeCAD Python 控制台 / MCP execute_code）:
    exec(open('/Users/admin/Downloads/battery/battery_holder_v2.py', encoding='utf-8').read())
    build_all()            # 建模 + 校验，返回报告字典
    export_all()           # 导出 STL / STEP 并保存 FCStd

坐标约定：X 沿箱体 220 方向，Y 竖直向上，Z 沿电芯轴向。
原点 = 主体左下角、A 端端面。A 端在 Z<0 一侧，B 端在 Z>body_len 一侧。
只会新建/重建文档「电池支架_v2」，不会碰其它已打开的文档。
"""
import math
import os

import FreeCAD as App
import Part
from FreeCAD import Vector as V

WORKDIR = "/Users/admin/Downloads/battery"
DOC_NAME = "电池支架_v2"
FCSTD_PATH = os.path.join(WORKDIR, "电池支架_v2.FCStd")

# ============================================================
# 参数表（改这里，然后重跑 build_all）
# ============================================================
P = {
    # --- 电芯 ---
    "cell_d": 33.2,            # 电芯名义直径（假体用）
    "cell_len": 140.0,         # 电芯名义长度（假体用），实测 140±0.3
    # --- 排布 ---
    "pitch": 35.0,             # 电芯节距（镍带孔距 34.5）
    "hole_d": 33.6,            # 电芯孔径（以试打块结果为准）
    "wall_out": 4.5,           # 节距边界到外表面的距离 → 外宽 6×35+2×4.5=219
    "cols": 6,
    "rows": 5,                 # 满排层数
    "top_cols": (4, 5),        # 顶层电芯所在列（0 起），靠右
    "top_block_x0": 141.0,     # 顶层电芯块左侧外壁 X
    # --- 箱体 ---
    "box_x": 220.0, "box_y": 275.0, "box_z": 165.0,
    "fit_clear": 0.5,          # 单边装配公差
    # --- 主体 ---
    "body_len": 140.5,         # 电芯腔长（主体长度）
    # --- 端盖 ---
    "end_hole_d": 24.0,        # 点焊开孔
    "plate_t": 2.5,            # 挡板厚（FEA：1.5 在 5 g 轴向冲击下主拉应力 38 MPa，不够；2.5 + 15 颗螺丝约 16 MPa）
    "rim_w": 5.0,              # 外周凸台宽
    "boss_d": 10.0,            # 螺丝加厚凸台直径
    "boss_t": 4.5,             # 螺丝处总厚（自贴合面起）
    "screw_clear_d": 4.5,      # M4 过孔
    "cbore_d": 9.0,            # 螺丝头沉孔（在凸台里时用）
    # 端盖顶边出线槽（X 区间），low = 第 5 层顶边 Y=184，high = 顶层块顶边 Y=219
    "rim_slots_low": ((12.0, 32.0), (42.0, 66.0), (84.0, 104.0), (116.0, 136.0)),
    "rim_slots_high": ((147.0, 170.0), (189.0, 211.0)),
    # --- M4 热熔螺母 ---
    "m4_d": 5.6, "m4_depth": 8.0,
    "edge_off": 6.5,           # 边缘螺母位离外表面距离
    # 螺母位：("star", i, j) 四孔星形；("bottom"/"toplow"/"toptop", k) 横边第 k 与 k+1 列之间；
    #         ("left"/"right", k) 竖边第 k 与 k+1 层之间
    "screws": (
        ("star", 1, 1), ("star", 3, 1), ("star", 1, 3), ("star", 3, 3),
        ("bottom", 0), ("bottom", 4), ("left", 2), ("right", 2),
        ("toplow", 1), ("toptop", 4),
        # FEA 后加的 5 颗：缩短端盖无支撑跨度。避开换层 2×2 镍片中心
        ("star", 2, 0), ("star", 2, 3), ("star", 0, 2), ("star", 4, 1), ("star", 4, 3),
    ),
    # --- 减重/通风孔 ---
    "lighten": True, "lighten_d": 8.0,
    # --- BMS（JK-BD6AxxS-8PD）---
    "bms_l": 136.0, "bms_w": 103.0, "bms_t": 13.6,
    "bms_hole_l": 124.0, "bms_hole_w": 94.0,
    "bms_x0": 19.0,            # BMS 沿 X（103 方向）起点：居中于 0~141，两侧各留约 19 mm 走线
    "bms_z0": 4.0,             # BMS 沿 Z（136 方向）起点：插座端朝 A 端
    "rail_w": 10.0, "rail_h": 7.0,
    "m3_d": 4.0, "m3_depth": 6.0,
    # --- 镍片（参考）---
    "nickel_w": 20.0,          # 焊盘/连接带宽度假设
    "nickel_t": 0.3,
    # --- NTC 探头槽 ---
    "ntc_cell": (2, 2),        # 中心电芯 (列, 层)
    "ntc_dir": 45.0,           # 槽方向（度），朝星形空区
    "ntc_w": 5.5, "ntc_depth": 5.0, "ntc_len": 75.0,
    "ntc_cap_hole_d": 6.0,
    "ntc_probe": (5.0, 5.0, 10.0),
    # --- 顶部压框 ---
    "frame_t": 3.0, "frame_ring_w": 10.0, "frame_ring_t": 4.0, "frame_bar_w": 10.0,
    "frame_dia": 13.0,         # 菱形窗半对角线（45° 自支撑）
    # --- 试打块 ---
    "test_hole_ds": (33.4, 33.6, 33.8), "test_h": 15.0, "test_offset_x": 300.0,
    # --- 导出 ---
    "stl_lin_defl": 0.02, "stl_ang_defl": 0.15,
}


# ============================================================
# 派生尺寸与基础几何
# ============================================================
def D():
    p = P
    W = p["cols"] * p["pitch"] + 2 * p["wall_out"]
    H5 = p["rows"] * p["pitch"] + 2 * p["wall_out"]
    HT = H5 + p["pitch"]
    L = p["body_len"]
    CT = (p["box_z"] - 2 * p["fit_clear"] - L) / 2.0
    YT = p["box_y"] - p["fit_clear"]
    return dict(W=W, H5=H5, HT=HT, L=L, CT=CT, YT=YT)


def cc(i, j):
    """电芯 (列 i, 层 j) 中心。"""
    p = P
    return (p["wall_out"] + p["pitch"] / 2 + i * p["pitch"],
            p["wall_out"] + p["pitch"] / 2 + j * p["pitch"])


def cells():
    lst = [(i, j) for j in range(P["rows"]) for i in range(P["cols"])]
    lst += [(c, P["rows"]) for c in P["top_cols"]]
    return lst


def star(i, j):
    p = P
    return (p["wall_out"] + p["pitch"] * (i + 1), p["wall_out"] + p["pitch"] * (j + 1))


def valid_stars():
    cs = set(cells())
    out = []
    for j in range(P["rows"] + 1):
        for i in range(P["cols"] - 1):
            if {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= cs:
                out.append((i, j))
    return out


def screw_xy(spec):
    d = D()
    p = P
    k = spec[0]
    if k == "star":
        return star(spec[1], spec[2])
    x_between = p["wall_out"] + p["pitch"] * (spec[1] + 1)
    if k == "bottom":
        return (x_between, p["edge_off"])
    if k == "toplow":
        return (x_between, d["H5"] - p["edge_off"])
    if k == "toptop":
        return (x_between, d["HT"] - p["edge_off"])
    if k == "left":
        return (p["edge_off"], x_between)
    if k == "right":
        return (d["W"] - p["edge_off"], x_between)
    raise ValueError(spec)


def outline_pts(z=0.0):
    d = D()
    x0 = P["top_block_x0"]
    return [V(0, 0, z), V(d["W"], 0, z), V(d["W"], d["HT"], z), V(x0, d["HT"], z),
            V(x0, d["H5"], z), V(0, d["H5"], z), V(0, 0, z)]


def outline_face(z=0.0):
    return Part.Face(Part.makePolygon(outline_pts(z)))


def cyl(r, z0, z1, x, y):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def radial_box(cx, cy, r0, r1, w, z0, z1, ang):
    b = Part.makeBox(r1 - r0, w, z1 - z0, V(r0, -w / 2, z0))
    b.rotate(V(0, 0, 0), V(0, 0, 1), ang)
    b.translate(V(cx, cy, 0))
    return b


def teardrop_y(x, z, ytop, r, depth):
    """沿 -Y 方向的水滴孔（主体打印方向 +Z，尖角朝 +Z，免支撑）。"""
    y0 = ytop + 0.5
    h = depth + 0.5
    c = Part.makeCylinder(r, h, V(x, y0, z), V(0, -1, 0))
    s = r / math.sqrt(2)
    pts = [V(x, y0, z), V(x + s, y0, z + s), V(x, y0, z + 2 * s), V(x - s, y0, z + s), V(x, y0, z)]
    tri = Part.Face(Part.makePolygon(pts)).extrude(V(0, -h, 0))
    return c.fuse(tri)


def mirror_z(shape):
    return shape.mirror(V(0, 0, D()["L"] / 2), V(0, 0, 1))


def centered_positions(a, b, h, gap=8.0, margin=10.0):
    s = 2 * h + gap
    n = int(math.floor((b - a - 2 * margin - 2 * h) / s)) + 1
    if n < 1:
        return []
    c = (a + b) / 2
    return [c + (k - (n - 1) / 2.0) * s for k in range(n)]


def rect_dist(x, y, r):
    """点到轴对齐矩形 (x0,x1,y0,y1) 的距离（在内部为 0）。"""
    dx = max(r[0] - x, 0, x - r[1])
    dy = max(r[2] - y, 0, y - r[3])
    return math.hypot(dx, dy)


# ============================================================
# 串联分组与镍片
# ============================================================
def groups():
    g = []
    for j in range(P["rows"]):
        pairs = [(0, 1), (2, 3), (4, 5)]
        if j % 2 == 1:
            pairs = pairs[::-1]
        for a, b in pairs:
            g.append([(a, j), (b, j)])
    g.append([(c, P["rows"]) for c in P["top_cols"]])
    return g


def connectors():
    """返回 {'A': [...], 'B': [...]}，每项为 (名称, 电芯列表)。"""
    g = groups()
    n = len(g)
    A, B = [], []
    B.append(("B-（第1组负极）", list(g[0])))
    for k in range(n - 1):  # 连接 k+1 → k+2
        name = "%d→%d" % (k + 1, k + 2)
        (A if k % 2 == 0 else B).append((name, g[k] + g[k + 1]))
    # 第 n 组正极所在端：n 为偶数时 + 在 B 端
    (B if n % 2 == 0 else A).append(("B+（第%d组正极）" % n, list(g[-1])))
    return {"A": A, "B": B}


def nickel_rects(conn_cells):
    w = P["nickel_w"] / 2
    rs = []
    for c in conn_cells:
        x, y = cc(*c)
        rs.append((x - w, x + w, y - w, y + w))
    for a in conn_cells:
        for b in conn_cells:
            if a < b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
                (x1, y1), (x2, y2) = cc(*a), cc(*b)
                rs.append((min(x1, x2) - w, max(x1, x2) + w, min(y1, y2) - w, max(y1, y2) + w))
    # 换层的 2×2 连接常用整块方形镍片，中心也按覆盖处理
    if len(conn_cells) == 4:
        xs = [cc(*c)[0] for c in conn_cells]
        ys = [cc(*c)[1] for c in conn_cells]
        if max(xs) - min(xs) == P["pitch"] and max(ys) - min(ys) == P["pitch"]:
            rs.append((min(xs), max(xs), min(ys), max(ys)))
    return rs


def all_nickel_rects(end):
    out = []
    for _, cs in connectors()[end]:
        out += nickel_rects(cs)
    return out


def nickel_shape(end):
    """镍片占位薄片（参考）。A 端贴在端盖挡板外表面 Z=-plate_t。"""
    pt, nt = P["plate_t"], P["nickel_t"]
    solids = []
    for _, cs in connectors()[end]:
        parts = [box(r[0], r[1], r[2], r[3], -pt - nt, -pt) for r in nickel_rects(cs)]
        s = parts[0].fuse(parts[1:]) if len(parts) > 1 else parts[0]
        solids.append(s.removeSplitter())
    comp = Part.makeCompound(solids)
    if end == "B":
        comp = mirror_z(comp)
    return comp


# ============================================================
# NTC 探头
# ============================================================
def ntc_geom():
    cx, cy = cc(*P["ntc_cell"])
    a = math.radians(P["ntc_dir"])
    rh = P["hole_d"] / 2
    rc = rh + P["ntc_depth"] / 2
    hole_xy = (cx + rc * math.cos(a), cy + rc * math.sin(a))
    # 槽口所在星形
    si = P["ntc_cell"][0] - (0 if math.cos(a) > 0 else 1)
    sj = P["ntc_cell"][1] - (0 if math.sin(a) > 0 else 1)
    return dict(cx=cx, cy=cy, hole_xy=hole_xy, star=(si, sj))


def ntc_end():
    """自动选择出线端：探头过线孔不落在该端镍片上。"""
    g = ntc_geom()
    r = P["ntc_cap_hole_d"] / 2
    for end in ("A", "B"):
        if min(rect_dist(g["hole_xy"][0], g["hole_xy"][1], rr) for rr in all_nickel_rects(end)) >= r:
            return end
    return None


def ntc_slot_solid(end):
    g = ntc_geom()
    rh = P["hole_d"] / 2
    L = D()["L"]
    if end == "A":
        z0, z1 = -1.0, P["ntc_len"]
    else:
        z0, z1 = L - P["ntc_len"], L + 1.0
    return radial_box(g["cx"], g["cy"], rh - 3.0, rh + P["ntc_depth"], P["ntc_w"], z0, z1, P["ntc_dir"])


def ntc_probe_solid(end):
    g = ntc_geom()
    pw, ph, pl = P["ntc_probe"]
    r0 = P["cell_d"] / 2 + 0.1
    if end == "A":
        z1 = P["ntc_len"] - 0.5
    else:
        z1 = D()["L"] - P["ntc_len"] + 0.5 + pl
    return radial_box(g["cx"], g["cy"], r0, r0 + ph, pw, z1 - pl, z1, P["ntc_dir"])


# ============================================================
# 零件
# ============================================================
def screw_points():
    return [screw_xy(s) for s in P["screws"]]


def lighten_stars():
    used = {tuple(round(v, 3) for v in xy) for xy in screw_points()}
    ns = ntc_geom()["star"]
    out = []
    for s in valid_stars():
        xy = star(*s)
        if tuple(round(v, 3) for v in xy) in used or s == ns:
            continue
        out.append(xy)
    return out


def rail_xs():
    off = (P["bms_w"] - P["bms_hole_w"]) / 2
    x1 = P["bms_x0"] + off
    return (x1, x1 + P["bms_hole_w"])


def m3_points():
    off = (P["bms_l"] - P["bms_hole_l"]) / 2
    z1 = P["bms_z0"] + off
    return [(x, z) for x in rail_xs() for z in (z1, z1 + P["bms_hole_l"])]


def make_body():
    d = D()
    L = d["L"]
    body = outline_face(0).extrude(V(0, 0, L))
    # BMS 导轨
    rails = [box(x - P["rail_w"] / 2, x + P["rail_w"] / 2, d["H5"], d["H5"] + P["rail_h"], 0, L)
             for x in rail_xs()]
    body = body.fuse(rails)
    tools = []
    for c in cells():
        x, y = cc(*c)
        tools.append(cyl(P["hole_d"] / 2, -1, L + 1, x, y))
    if P["lighten"]:
        for x, y in lighten_stars():
            tools.append(cyl(P["lighten_d"] / 2, -1, L + 1, x, y))
    for x, y in screw_points():
        tools.append(cyl(P["m4_d"] / 2, -1, P["m4_depth"], x, y))
        tools.append(cyl(P["m4_d"] / 2, L - P["m4_depth"], L + 1, x, y))
    tools.append(ntc_slot_solid(ntc_end()))
    for x, z in m3_points():
        tools.append(teardrop_y(x, z, d["H5"] + P["rail_h"], P["m3_d"] / 2, P["m3_depth"]))
    body = body.cut(tools).removeSplitter()
    return body


def make_cap(end):
    """A 端端盖（Z<0）。end='B' 时生成后镜像到 B 端。"""
    d = D()
    CT, pt = d["CT"], P["plate_t"]
    f = outline_face(0)
    plate = f.extrude(V(0, 0, -pt))
    inner = f.makeOffset2D(-P["rim_w"], 2)
    inner_s = inner.extrude(V(0, 0, -CT - 2))
    inner_s.translate(V(0, 0, 1))
    rim = f.extrude(V(0, 0, -CT)).cut(inner_s)
    bosses = [cyl(P["boss_d"] / 2, -P["boss_t"], 0, x, y) for x, y in screw_points()]
    cap = plate.fuse([rim] + bosses)
    tools = []
    for c in cells():
        x, y = cc(*c)
        tools.append(cyl(P["end_hole_d"] / 2, -CT - 1, 1, x, y))
    if P["lighten"]:
        for x, y in lighten_stars():
            tools.append(cyl(P["lighten_d"] / 2, -CT - 1, 1, x, y))
    for x, y in screw_points():
        tools.append(cyl(P["screw_clear_d"] / 2, -CT - 1, 1, x, y))
        tools.append(cyl(P["cbore_d"] / 2, -CT - 1, -P["boss_t"], x, y))
    rw = P["rim_w"]
    for a, b in P["rim_slots_low"]:
        tools.append(box(a, b, d["H5"] - rw - 1, d["H5"] + 1, -CT - 1, -pt))
    for a, b in P["rim_slots_high"]:
        tools.append(box(a, b, d["HT"] - rw - 1, d["HT"] + 1, -CT - 1, -pt))
    if ntc_end() == end:
        hx, hy = ntc_geom()["hole_xy"]
        tools.append(cyl(P["ntc_cap_hole_d"] / 2, -CT - 1, 1, hx, hy))
    cap = cap.cut(tools).removeSplitter()
    if end == "B":
        cap = mirror_z(cap)
    return cap


def make_frame():
    d = D()
    W, H5, HT, L, CT, YT = d["W"], d["H5"], d["HT"], d["L"], d["CT"], d["YT"]
    t = P["frame_t"]
    z0, z1 = -CT, L + CT
    zm = (z0 + z1) / 2
    x0 = P["top_block_x0"]
    yR = YT - P["frame_ring_t"]
    rw = P["frame_ring_w"]
    front = box(0, W, H5, YT, z0, z0 + t).cut(box(x0, W + 1, H5 - 1, HT, z0 - 1, z0 + t + 1))
    back = front.mirror(V(0, 0, zm), V(0, 0, 1))
    left = box(0, t, H5, YT, z0, z1)
    right = box(W - t, W, HT, YT, z0, z1)
    ring = box(0, W, yR, YT, z0, z1).cut(box(rw, W - rw, yR - 1, YT + 1, z0 + rw, z1 - rw))
    bar = box(0, W, yR, YT, zm - P["frame_bar_w"] / 2, zm + P["frame_bar_w"] / 2)
    frame = front.fuse([back, left, right, ring, bar])
    # 菱形窗（45° 自支撑）
    h = P["frame_dia"]
    yU = (HT + yR) / 2
    yLo = (H5 + HT) / 2
    wins = []

    def dz(xc, yc):  # 穿 Z 向墙
        pts = [V(xc - h, yc, z0 - 1), V(xc, yc - h, z0 - 1), V(xc + h, yc, z0 - 1), V(xc, yc + h, z0 - 1),
               V(xc - h, yc, z0 - 1)]
        return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, z1 - z0 + 2))

    def dx(zc, yc):  # 穿 X 向墙
        pts = [V(-1, yc, zc - h), V(-1, yc - h, zc), V(-1, yc, zc + h), V(-1, yc + h, zc), V(-1, yc, zc - h)]
        return Part.Face(Part.makePolygon(pts)).extrude(V(W + 2, 0, 0))

    for xc in centered_positions(0, W, h):
        wins.append(dz(xc, yU))
    for xc in centered_positions(0, x0, h):
        wins.append(dz(xc, yLo))
    zs = centered_positions(z0 + t, z1 - t, h)
    for zc in zs:
        wins.append(dx(zc, yU))
    # 左墙下排（右墙较矮，只有上排）
    lower_left = []
    for zc in zs:
        pts = [V(-1, yLo, zc - h), V(-1, yLo - h, zc), V(-1, yLo, zc + h), V(-1, yLo + h, zc), V(-1, yLo, zc - h)]
        lower_left.append(Part.Face(Part.makePolygon(pts)).extrude(V(t + 2, 0, 0)))
    frame = frame.cut(wins + lower_left).removeSplitter()
    return frame


def make_test_block():
    p = P
    ds = p["test_hole_ds"]
    pitch, w, h = p["pitch"], p["wall_out"], p["test_h"]
    Wt = len(ds) * pitch + 2 * w
    Ht = 2 * pitch + 2 * w
    blk = Part.makeBox(Wt, Ht, h)
    tools = []
    for i, dd in enumerate(ds):
        for j in range(2):
            x, y = w + pitch / 2 + i * pitch, w + pitch / 2 + j * pitch
            if i == 1 and j == 0:  # 挡边样段：底部 1.5 mm + Ø24
                tools.append(cyl(dd / 2, p["plate_t"], h + 1, x, y))
                tools.append(cyl(p["end_hole_d"] / 2, -1, h + 1, x, y))
            else:
                tools.append(cyl(dd / 2, -1, h + 1, x, y))
    # 探头槽样段：中间列上排孔，45°
    x, y = w + pitch / 2 + pitch, w + pitch / 2 + pitch
    rh = ds[1] / 2
    tools.append(radial_box(x, y, rh - 3, rh + p["ntc_depth"], p["ntc_w"], -1, h + 1, p["ntc_dir"]))
    # M4 星形位、M4 边缘位、M3 边缘位（从顶面打入）
    tools.append(cyl(p["m4_d"] / 2, h - p["m4_depth"], h + 1, w + pitch, w + pitch))
    tools.append(cyl(p["m4_d"] / 2, h - p["m4_depth"], h + 1, w + 2 * pitch, p["edge_off"]))
    tools.append(cyl(p["m3_d"] / 2, h - p["m3_depth"], h + 1, w + pitch, Ht - p["edge_off"]))
    # 方向标记：Ø33.4 一侧切角
    tri = Part.Face(Part.makePolygon([V(-1, -1, -1), V(7, -1, -1), V(-1, 7, -1), V(-1, -1, -1)]))
    tools.append(tri.extrude(V(0, 0, h + 2)))
    blk = blk.cut(tools).removeSplitter()
    blk.translate(V(p["test_offset_x"], 0, 0))
    return blk


# ============================================================
# 文档与显示
# ============================================================
PALETTE = [(0.90, 0.30, 0.30), (0.95, 0.60, 0.20), (0.95, 0.85, 0.25), (0.60, 0.85, 0.30),
           (0.30, 0.75, 0.40), (0.25, 0.75, 0.70), (0.30, 0.60, 0.90), (0.40, 0.40, 0.90),
           (0.65, 0.40, 0.90), (0.85, 0.40, 0.80), (0.90, 0.45, 0.55), (0.70, 0.55, 0.35),
           (0.55, 0.70, 0.55), (0.45, 0.55, 0.70), (0.75, 0.75, 0.75), (0.35, 0.35, 0.35)]


def get_doc(reset=True):
    for name, doc in App.listDocuments().items():
        if name == DOC_NAME or doc.Label == DOC_NAME or doc.FileName == FCSTD_PATH:
            if reset:
                App.closeDocument(name)
                break
            return doc
    doc = App.newDocument(DOC_NAME)
    doc.Label = DOC_NAME
    return doc


def add(doc, name, label, shape, color=None, transp=0, group=None):
    o = doc.addObject("Part::Feature", name)
    o.Label = label
    o.Shape = shape
    vo = getattr(o, "ViewObject", None)
    if vo is not None:
        if color:
            vo.ShapeColor = color
        vo.Transparency = transp
    if group is not None:
        group.addObject(o)
    return o


# ============================================================
# 校验
# ============================================================
def vol_common(a, b):
    try:
        return a.common(b).Volume
    except Exception:
        return float("nan")


def checks(objs):
    d = D()
    R = {}
    body, capA, capB, frame = objs["body"], objs["capA"], objs["capB"], objs["frame"]
    cell_shapes = objs["cells"]
    # --- Task 2 ---
    R["主体包围盒"] = tuple(round(v, 2) for v in (body.BoundBox.XLength, body.BoundBox.YLength, body.BoundBox.ZLength))
    R["电芯孔数"] = len(cells())
    R["最小孔间壁"] = round(P["pitch"] - P["hole_d"], 2)
    R["孔到外表面最薄(外圈)"] = round(P["wall_out"] + P["pitch"] / 2 - P["hole_d"] / 2, 2)
    tx, _ = cc(P["top_cols"][0], P["rows"])
    R["顶层块左壁最薄"] = round(tx - P["hole_d"] / 2 - P["top_block_x0"], 2)
    R["主体∩电芯假体"] = round(sum(vol_common(body, c) for c in cell_shapes), 4)
    R["减重孔数"] = len(lighten_stars()) if P["lighten"] else 0
    # --- Task 3 ---
    g = groups()
    R["分组数/每组只数"] = (len(g), sorted({len(x) for x in g}))
    con = connectors()
    bad = []
    for end, lst in con.items():
        for name, cs in lst:
            # 连通性
            seen, todo = {cs[0]}, [cs[0]]
            while todo:
                a = todo.pop()
                for b in cs:
                    if b not in seen and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
                        seen.add(b)
                        todo.append(b)
            if len(seen) != len(cs):
                bad.append((end, name))
    R["镍片连通性异常"] = bad
    R["A端连接"] = [n for n, _ in con["A"]]
    R["B端连接"] = [n for n, _ in con["B"]]
    # --- Task 4 ---
    sm = []
    for spec, (x, y) in zip(P["screws"], screw_points()):
        dh = min(math.hypot(x - cc(*c)[0], y - cc(*c)[1]) - P["hole_d"] / 2 for c in cells()) - P["m4_d"] / 2
        dout = Part.Vertex(V(x, y, 0)).distToShape(Part.makePolygon(outline_pts(0)))[0] - P["m4_d"] / 2
        dniA = min(rect_dist(x, y, r) for r in all_nickel_rects("A")) - P["boss_d"] / 2
        dniB = min(rect_dist(x, y, r) for r in all_nickel_rects("B")) - P["boss_d"] / 2
        dntc = math.hypot(x - ntc_geom()["hole_xy"][0], y - ntc_geom()["hole_xy"][1])
        sm.append(dict(位="%s%s" % (spec[0], spec[1:]), xy=(round(x, 2), round(y, 2)),
                       到电芯孔=round(dh, 2), 到外表面=round(dout, 2),
                       凸台到镍片A=round(dniA, 2), 凸台到镍片B=round(dniB, 2), 到探头孔=round(dntc, 1)))
    R["螺母孔"] = sm
    R["螺母孔余量OK"] = all(s["到电芯孔"] >= 3 and s["到外表面"] >= 3 and s["凸台到镍片A"] >= 0
                         and s["凸台到镍片B"] >= 0 for s in sm)
    # --- Task 5 ---
    end = ntc_end()
    R["探头出线端"] = end
    slot = ntc_slot_solid(end)
    others = [c for c in cells() if c != tuple(P["ntc_cell"])]
    R["探头槽到其他电芯孔最小余量"] = round(min(
        slot.distToShape(cyl(P["hole_d"] / 2, -1, d["L"] + 1, *cc(*c)))[0] for c in others), 2)
    R["探头槽深"] = P["ntc_len"]
    probe = objs["probe"]
    R["探头∩主体"] = round(vol_common(body, probe), 4)
    R["探头∩电芯"] = round(sum(vol_common(probe, c) for c in cell_shapes), 4)
    # --- Task 6 ---
    bms = objs["bms"]
    R["BMS∩主体"] = round(vol_common(body, bms), 4)
    R["BMS顶面Y"] = round(bms.BoundBox.YMax, 2)
    R["BMS到顶层块间隙"] = round(P["top_block_x0"] - bms.BoundBox.XMax, 2)
    R["BMS到左外壁"] = round(bms.BoundBox.XMin, 2)
    # --- Task 7 ---
    allz = [capA.BoundBox.ZMin, capB.BoundBox.ZMax]
    R["轴向总长"] = round(allz[1] - allz[0], 3)
    R["端盖A∩主体"] = round(vol_common(capA, body), 4)
    R["端盖B∩主体"] = round(vol_common(capB, body), 4)
    R["端盖A∩镍片A"] = round(vol_common(capA, objs["niA"]), 4)
    R["端盖B∩镍片B"] = round(vol_common(capB, objs["niB"]), 4)
    R["端盖∩电芯"] = round(sum(vol_common(capA, c) + vol_common(capB, c) for c in cell_shapes), 4)
    # M4 盘头螺丝头顶（M4×12 盘头高约 3.1）相对凸台外沿
    R["螺丝头顶距凸台外沿"] = round(d["CT"] - P["boss_t"] - 3.1, 2)
    R["推荐螺丝"] = "M4×%d 盘头" % int(round(P["boss_t"] + P["m4_depth"] - 0.5))
    # --- Task 8 ---
    R["压框包围盒"] = tuple(round(v, 2) for v in (frame.BoundBox.XLength, frame.BoundBox.YLength, frame.BoundBox.ZLength))
    R["压框∩BMS"] = round(vol_common(frame, bms), 4)
    R["压框∩线束预留"] = round(sum(vol_common(frame, s) for s in objs["wires"]), 4)
    R["压框∩主体/端盖"] = round(vol_common(frame, body) + vol_common(frame, capA) + vol_common(frame, capB), 4)
    # --- Task 9 ---
    parts = [body, capA, capB, frame]
    bb = parts[0].BoundBox
    for s in parts[1:]:
        bb.add(s.BoundBox)
    R["总装包围盒"] = (round(bb.XMin, 2), round(bb.XMax, 2), round(bb.YMin, 2), round(bb.YMax, 2),
                   round(bb.ZMin, 2), round(bb.ZMax, 2))
    R["箱体间隙 X左/X右"] = (round(bb.XMin + (P["box_x"] - d["W"]) / 2, 2),
                         round(d["W"] + (P["box_x"] - d["W"]) / 2 - bb.XMax, 2))
    R["箱体间隙 Z前/Z后"] = (round(bb.ZMin + d["CT"] + P["fit_clear"], 2),
                         round(d["L"] + d["CT"] + P["fit_clear"] - bb.ZMax, 2))
    R["箱体间隙 Y顶"] = round(P["box_y"] - bb.YMax, 2)
    R["零件体积cm3"] = {k: round(objs[k].Volume / 1000, 1) for k in ("body", "capA", "capB", "frame")}
    R["实心质量上限g(PETG 1.27)"] = round(sum(objs[k].Volume for k in ("body", "capA", "capB", "frame")) / 1000 * 1.27)
    return R


# ============================================================
# 主流程
# ============================================================
LAST = {}


def build_all():
    d = D()
    doc = get_doc(reset=True)
    ref = doc.addObject("App::DocumentObjectGroup", "Ref")
    ref.Label = "参考假体（不打印）"
    prt = doc.addObject("App::DocumentObjectGroup", "Parts")
    prt.Label = "打印零件"

    test = make_test_block()
    add(doc, "TestBlock", "试打块", test, (0.95, 0.75, 0.30))

    body = make_body()
    capA = make_cap("A")
    capB = make_cap("B")
    frame = make_frame()
    add(doc, "Body", "主体", body, (0.85, 0.85, 0.80), 0, prt)
    add(doc, "CapL", "端盖L_A端", capA, (0.30, 0.55, 0.85), 0, prt)
    add(doc, "CapR", "端盖R_B端", capB, (0.30, 0.75, 0.55), 0, prt)
    add(doc, "Frame", "顶部压框", frame, (0.85, 0.50, 0.30), 0, prt)

    # 参考假体
    gidx = {}
    for k, gg in enumerate(groups()):
        for c in gg:
            gidx[c] = k
    z0 = (d["L"] - P["cell_len"]) / 2
    cell_shapes = []
    for c in cells():
        x, y = cc(*c)
        s = cyl(P["cell_d"] / 2, z0, z0 + P["cell_len"], x, y)
        cell_shapes.append(s)
        k = gidx[c]
        add(doc, "Cell_%d_%d" % c, "电芯_第%d组_(%d,%d)" % (k + 1, c[0] + 1, c[1] + 1), s,
            PALETTE[k % len(PALETTE)], 60, ref)
    niA, niB = nickel_shape("A"), nickel_shape("B")
    add(doc, "NickelA", "镍片占位_A端", niA, (0.75, 0.75, 0.78), 0, ref)
    add(doc, "NickelB", "镍片占位_B端", niB, (0.75, 0.75, 0.78), 0, ref)
    end = ntc_end()
    probe = ntc_probe_solid(end)
    add(doc, "NTC", "NTC探头假体", probe, (0.9, 0.1, 0.1), 0, ref)
    bz0 = P["bms_z0"]
    bms = box(P["bms_x0"], P["bms_x0"] + P["bms_w"], d["H5"] + P["rail_h"],
              d["H5"] + P["rail_h"] + P["bms_t"], bz0, bz0 + P["bms_l"])
    add(doc, "BMS", "BMS假体_JK-BD6A", bms, (0.1, 0.4, 0.15), 30, ref)
    # 线束预留区（压框校验用）
    wA = [box(3, 138, d["H5"], d["H5"] + 31, -8.5, -P["plate_t"] - 0.1),
          box(146, 214, d["HT"], d["HT"] + 21, -8.5, -P["plate_t"] - 0.1),
          box(P["frame_t"] + 0.1, P["bms_x0"] - 0.5, d["H5"] + 0.1, d["H5"] + 16, 0, d["L"]),
          box(P["bms_x0"] + P["bms_w"] + 0.5, P["top_block_x0"] - 0.5, d["H5"] + 0.1, d["H5"] + 16, 0, d["L"]),
          box(P["bms_x0"], P["bms_x0"] + P["bms_w"], d["H5"] + P["rail_h"] + P["bms_t"],
              d["H5"] + P["rail_h"] + P["bms_t"] + 12, bz0, bz0 + P["bms_l"]),
          box(P["bms_x0"], P["bms_x0"] + P["bms_w"], d["H5"] + 1, d["H5"] + 25, -8.5, bz0)]
    wires = wA + [mirror_z(w) for w in wA[:2]]
    add(doc, "WireZone", "线束预留区", Part.makeCompound(wires), (1.0, 1.0, 0.0), 85, ref)
    # 箱体内腔（线框显示）
    cav = box(-(P["box_x"] - d["W"]) / 2, d["W"] + (P["box_x"] - d["W"]) / 2, 0, P["box_y"],
              -d["CT"] - P["fit_clear"], d["L"] + d["CT"] + P["fit_clear"])
    o = add(doc, "BoxCavity", "箱体内腔_275x220x165", cav, (0.5, 0.5, 0.5), 90, ref)
    if getattr(o, "ViewObject", None) is not None:
        o.ViewObject.DisplayMode = "Wireframe"

    doc.recompute()
    objs = dict(body=body, capA=capA, capB=capB, frame=frame, cells=cell_shapes, niA=niA, niB=niB,
                probe=probe, bms=bms, wires=wires)
    R = checks(objs)
    # 试打块校验
    R["试打块包围盒"] = tuple(round(v, 2) for v in (test.BoundBox.XLength, test.BoundBox.YLength, test.BoundBox.ZLength))
    R["试打块孔径"] = P["test_hole_ds"]
    LAST.clear()
    LAST.update(objs)
    LAST["test"] = test
    LAST["doc"] = doc
    return R


def _print_oriented(name):
    """返回按打印方向摆放、落在 Z=0 的形状。"""
    d = D()
    s = LAST[name].copy()
    if name == "capA":            # 贴合面 (Z=0) 朝下
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    elif name == "frame":         # 顶面环朝下
        s.rotate(V(0, 0, 0), V(1, 0, 0), -90)
    bb = s.BoundBox
    s.translate(V(-bb.XMin, -bb.YMin, -bb.ZMin))
    return s


def export_all():
    import MeshPart
    stl_dir = os.path.join(WORKDIR, "STL")
    stp_dir = os.path.join(WORKDIR, "STEP")
    os.makedirs(stl_dir, exist_ok=True)
    os.makedirs(stp_dir, exist_ok=True)
    names = [("body", "主体"), ("capA", "端盖L_A端"), ("capB", "端盖R_B端"), ("frame", "顶部压框"),
             ("test", "试打块")]
    out = {}
    for key, label in names:
        s = _print_oriented(key)
        m = MeshPart.meshFromShape(Shape=s, LinearDeflection=P["stl_lin_defl"],
                                   AngularDeflection=P["stl_ang_defl"], Relative=False)
        sp = os.path.join(stl_dir, label + ".stl")
        m.write(sp)
        LAST[key].exportStep(os.path.join(stp_dir, label + ".step"))
        bb = s.BoundBox
        out[label] = dict(打印包围盒=(round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1)),
                          面片数=m.CountFacets, 封闭=m.isSolid(), STL字节=os.path.getsize(sp))
    LAST["doc"].saveAs(FCSTD_PATH)
    out["FCStd"] = FCSTD_PATH
    return out
