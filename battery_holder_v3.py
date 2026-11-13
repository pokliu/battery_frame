# -*- coding: utf-8 -*-
"""
32140 16S2P 电池支架 v3 —— 两片电芯座 + 端盖顶箱壁（FreeCAD Part 工作台）

运行（FreeCAD Python 控制台 / MCP execute_code）:
    exec(open('/Users/admin/Downloads/battery/battery_holder_v3.py', encoding='utf-8').read())
    build_all()            # 建模 + 校验，返回报告字典
    export_all()           # 导出 STL/v3、STEP/v3 并保存 电池支架_v3.FCStd

坐标约定：X 沿箱体 220 方向，Y 竖直向上，Z 沿电芯轴向。
原点 = 电芯座底面左下角、A 端电芯腔端面（挡边内表面）。A 端在 Z<0 一侧，B 端在 Z>body_len 一侧。
箱底钢面在 Y=-(liner_t+rubber_t)，支架落在胶条上。
只会新建/重建文档「电池支架_v3」，不会碰其它已打开的文档。
"""
import math
import os

import FreeCAD as App
import Part
from FreeCAD import Vector as V

WORKDIR = "/Users/admin/Downloads/battery"
DOC_NAME = "电池支架_v3"
FCSTD_PATH = os.path.join(WORKDIR, "电池支架_v3.FCStd")

# ============================================================
# 参数表（改这里，然后重跑 build_all）
# ============================================================
P = {
    # --- 电芯 ---
    "cell_d": 33.2,            # 名义直径（假体用）
    "cell_d_max": 33.4,        # 规格书上限（间隙校验用）
    "cell_len": 140.0,         # 140±0.3
    "cell_mass": 0.300,        # kg
    # --- 排布 ---
    "pitch": 35.0,
    "hole_d": 33.6,            # 电芯孔径（以试打块为准）
    "wall_out": 4.0,           # Y 方向（上下）节距边界到外表面；X 方向由箱宽自动推算，见 wall_x()
    "cols": 6, "rows": 5,
    "top_cols": (4, 5),
    # --- 串联顺序（16 组，每组 2 只，(列, 层)）---
    # B−（第 1 组）在左上 (0,4)(1,4)，B+（第 16 组）在顶层块 (4,5)(5,5)：两个端子都在最上面一层，
    # 引线直接从顶边出。程序搜索了所有"相邻组只用直条或 2×2 方片连接、首尾都在顶层"的排法，
    # 只有 4 种（加反向共 8 种），都要 9 块方片；这一种螺栓可用位最均匀。
    #   层5: .. .. .. .. 16 16
    #   层4:  1  1 14 14 15 15
    #   层3:  2  2 13 13 12 12
    #   层2:  3  3  4  4 11 11
    #   层1:  6  6  5  5 10 10
    #   层0:  7  7  8  8  9  9
    "series": (((0, 4), (1, 4)), ((0, 3), (1, 3)), ((0, 2), (1, 2)), ((2, 2), (3, 2)),
               ((2, 1), (3, 1)), ((0, 1), (1, 1)), ((0, 0), (1, 0)), ((2, 0), (3, 0)),
               ((4, 0), (5, 0)), ((4, 1), (5, 1)), ((4, 2), (5, 2)), ((4, 3), (5, 3)),
               ((2, 3), (3, 3)), ((2, 4), (3, 4)), ((4, 4), (5, 4)), ((4, 5), (5, 5))),
    "top_block_wall": 4.2,     # 顶层块左壁厚（top_block_x0 自动推算）
    # --- 箱体（不锈钢箱，给的是外框尺寸）---
    "box_outer": (220.0, 275.0, 165.0),   # X, Y, Z 外框
    "sheet_t": 0.85,           # 板厚 → 内腔 = 外框 − 2×板厚
    "box_inner": None,         # 实测内腔 (X, Y, Z)，有值时优先于上面的推算
    "liner_t": 0.3,            # 青壳纸厚（0.x，待实测），贴四个侧面、两端面、底面
    # 用户要求：只有底部放硅胶条；两侧（Z）只贴青稞纸（即箱壁上的 liner），不放硅胶垫；顶部也不放。
    # 两侧（Z）：卖家要求装配余量 5 mm = 箱内腔长 − 支架两端盖外表面距离（含两侧青稞纸），两端平分。
    # 顶部留 fit_clear（15，让开箱盖紧固螺丝）；前后（X）被 6×35 节距卡死，最多留 gap_x
    "z_clear_total": 5.0,      # Z 向装配余量合计（含两侧青稞纸）
    "fit_clear": 15.0,         # 顶部空隙：压框顶面到箱盖。箱盖用螺丝和箱体紧固，螺丝伸进箱内，留 15 不干涉
    "gap_x": 1.5,              # 前后（X）每边空隙（扣纸后）
    "end_rubber_t": 0.0,       # 端盖外表面硅胶垫厚（两侧），0 = 不放
    "top_rubber_t": 0.0,       # 压框顶环上的硅胶条厚（顶部），0 = 不放
    "rubber_t": 3.0, "rubber_w": 40.0,   # 底部硅胶条 3×40，每端一条
    # --- 电芯座 ---
    "body_len": 140.5,         # 两片挡边内表面之间的距离（电芯腔长）
    "lip_t": 1.5,              # 挡边厚。FEA 侧摔 50 g：2.5→6.6 / 2.0→10.7 / 1.5→16.3 / 1.2→24.6 MPa，取 1.5
    "seat_depth": 24.0,        # 电芯座总深（含挡边）
    "end_hole_d": 24.0,        # 点焊孔
    "lighten_d": 8.0,          # 星形位减重孔
    # --- 贯穿螺栓与定位管 ---
    # M4×150 内六角螺丝（不锯）贯穿 端盖A→座A→定位管→座B→端盖B：头没入端盖 A 的圆沉孔，
    # 沉孔底只留一层薄底（floor_A）压在挡边上；杆末端拧进端盖 B 的 M4×8×6 热熔螺母（从外表面压入）。见 bolt_geom()。
    # 星形位：避开 9 块方片中心（A 端 (0,3)(4,0)(4,2)(2,3)(4,4)，B 端 (0,2)(2,1)(0,0)(4,1)）和探头星形 (2,2)，
    # 剩 11 个可选位；按"截面上任一点到最近螺栓的均方根距离"选 6 颗最优组合（40.3 mm）
    "rods": ((1, 0), (3, 0), (0, 1), (3, 2), (1, 3), (4, 3)),
    "rod_hole_d": 4.6,         # M4 过孔
    "tube_d": 14.0,            # 定位管外径
    "spigot_d": 9.0, "spigot_h": 2.0,         # A 端凸止口
    "socket_d": 9.4, "socket_h": 2.3,         # B 端凹止口
    "bolt_len": 150.0,         # M4×150 杆长（DIN912 长度公差约 ±1.25）
    "bolt_head_d": 6.8, "bolt_head_h": 4.0, "cbore_d": 7.4,     # DIN912 M4 头 Ø6.8×4，沉孔 Ø7.4
    "floor_A": 0.75,           # 端盖 A 沉孔底厚（头下压在挡边上）
    "floor_min": 0.6,          # 沉孔底最小厚度
    # 端盖 B：M4×8×6 热熔螺母（长 8、外径 6），从端盖 B 外表面压入，孔径以试打块为准
    "insert_len": 8.0, "insert_od": 6.0,
    "insert_hole_d": 5.6,
    "insert_recess": 0.3,      # 热熔螺母外端低于端盖 B 外表面
    "insert_relief": 0.4,      # 热熔螺母内端以外的余量（熔料溢出）→ 端盖 B 厚 = 8 + 0.3 + 0.4
    "min_engage": 5.0,         # 螺丝拧进热熔螺母最少长度（1.25D）
    "tip_clear_min": 1.5,      # 杆末端低于端盖 B 外表面最少（吸收螺丝长度公差）
    "capA_inner_min": 3.6,     # 端盖 A 底板以内最小空间高（连接片+青稞纸+采样线）
    # --- 端盖 ---
    "cap_plate_t": 2.5,        # 底板厚（顶箱壁）
    "rim_w": 5.0,
    "pad_d": 12.0,             # 普通支撑垫
    "rod_pad_d": 13.0,         # 螺栓位支撑垫（包住沉孔）
    # 顶边出线槽 X 区间：low = Y=H5 顶边，high = 顶层块顶边 Y=HT（采样线用；引出片槽按引出片位置自动加）
    "slots_low": ((4.5, 12.5), (88.0, 110.0)),
    "slots_high": ((204.0, 213.5),),
    "tab_slot_clear": 1.0,     # 引出片槽每边比引出片宽出
    # 外周凸台菱形通风窗（45° 自支撑，半对角线 h），(端盖A, 端盖B)，0 = 不开。
    # 窗在凸台高度中间，上下各留 rim_win_margin：A 内空间 3.6 → h 1.2（2.4 菱形），B 内空间 6.2 → h 2.5（5 菱形）
    "rim_win_h": (1.2, 2.5),
    "rim_win_margin": 0.6,     # 窗到底板内表面、到挡边的最少实料
    # --- 正负极引出：端子片（铜+镍）向上延伸出端盖顶边槽，在支架顶面以上锡焊 12AWG ---
    "main_wire_d": 4.5,
    "tab_w": 20.0, "tab_above": 22.0,     # 引出片宽、伸出顶面高度
    "main_wire_x": None,       # B− 引出片中心 X；None = 端子片（第 1 组两只电芯）正中间
    "bplus_x": None,           # B+ 引出片中心 X；None = 端子片（第 16 组两只电芯）正中间
    # --- 连接片 ---
    "strip_w": 20.0,
    "cu_t": 0.1, "ni_t": 0.1,
    "current_A": 30.0,
    "cu_rho": 1.72e-8, "ni_rho": 6.99e-8,   # Ω·m
    # --- BMS（JK-BD6AxxS-8PD）---
    "bms_l": 136.0, "bms_w": 103.0, "bms_t": 13.6,
    "bms_hole_l": 124.0, "bms_hole_w": 94.0,
    "bms_x0": None,            # None = 居中于 0~top_block_x0
    "bms_z0": 5.4,             # 136 沿 Z；插座端（A 端）到压框前墙留 ≥10 给插头弯线
    "rail_w": 10.0, "rail_h": 7.0,
    "m3_d": 4.0, "m3_depth": 6.0,
    # --- NTC ---
    "ntc_cell": (2, 2), "ntc_dir": 45.0,
    "ntc_probe": (5.0, 5.0, 10.0),
    "ntc_hole_d": 6.0,
    # --- 顶部压框 ---
    "frame_t": 3.0, "frame_ring_w": 10.0, "frame_ring_t": 4.0, "frame_bar_w": 10.0,
    "frame_dia": 13.0,
    "frame_notch_h": 26.0,
    # --- 压框顶凸台（顶住箱盖，防止整包颠簸时跳起）---
    # 箱盖与箱体在每个侧面的接缝处各有 2 颗螺丝（伸进箱内，用户回忆：长边距两端约 60 或 90，短边约 40）。
    # 凸台放在每条边正中间，宽度按最坏情况避开螺丝：长边螺丝若在距端 90，两颗之间只剩约 38，凸台取 20；
    # 短边两颗相距约 80，凸台取 30。凸台单独打印（顶面朝下），底面 2 个 Ø4 销插进压框顶环的 Ø4.4 孔定位，只受压。
    "boss_w_long": 20.0,       # 长边（沿 X，220 方向）凸台宽
    "boss_w_short": 30.0,      # 短边（沿 Z，165 方向）凸台宽
    "boss_top_gap": 0.5,       # 凸台顶面到箱盖
    "boss_pin_d": 4.0, "boss_pin_h": 3.0, "boss_pin_hole_d": 4.4,
    "boss_pin_inset": 6.0,     # 销中心到顶环外沿（避开下面 3 厚的墙）
    "boss_pin_end": 5.0,       # 销中心到凸台端头
    "lid_screws_long": (60.0, 90.0),    # 长边螺丝距箱内端面的可能位置（校验用，取两种回忆值）
    "lid_screws_short": (40.0,),
    "lid_screw_r": 5.0,        # 螺丝（含螺母）半径按 5 估     # B 端后墙在两个引出片处开缺口（X 范围按引出片 ±12），给焊点和 12AWG 留空间
    # --- 试打块 ---
    "test_hole_ds": (33.4, 33.6, 33.8), "test_lips": (1.5, 2.0, 2.5),
    "test_insert_ds": (5.5, 5.6, 5.7),    # M4×8×6 热熔螺母试孔（深 8.7）
    "test_h": 15.0, "test_offset_x": 300.0,
    # --- 打印/导出 ---
    "printer": 256.0,
    "stl_lin_defl": 0.02, "stl_ang_defl": 0.15,
}


# ============================================================
# 派生尺寸与基础几何
# ============================================================
def box_inner():
    if P["box_inner"]:
        return tuple(P["box_inner"])
    return tuple(v - 2 * P["sheet_t"] for v in P["box_outer"])


def wall_x():
    """X 方向节距边界到外表面：箱内宽 − 2×(纸+间隙) − 6×节距，两侧平分。"""
    bx = box_inner()[0]
    W = bx - 2 * (P["liner_t"] + P["gap_x"])
    return (W - P["cols"] * P["pitch"]) / 2.0


def top_block_x0():
    return cc(P["top_cols"][0], P["rows"])[0] - P["hole_d"] / 2 - P["top_block_wall"]


def bms_x0():
    return P["bms_x0"] if P["bms_x0"] is not None else (top_block_x0() - P["bms_w"]) / 2.0


def D():
    p = P
    bi = box_inner()
    W = p["cols"] * p["pitch"] + 2 * wall_x()
    H5 = p["rows"] * p["pitch"] + 2 * p["wall_out"]
    HT = H5 + p["pitch"]
    L = p["body_len"]
    lip = p["lip_t"]
    gap = p["z_clear_total"] / 2.0               # Z 每端：纸 + 空隙（硅胶垫 end_rubber_t 也算在里面）
    tot_z = bi[2] - 2 * gap                      # 两端盖外表面距离
    capB_t = p["insert_len"] + p["insert_recess"] + p["insert_relief"]
    capA_t = tot_z - L - 2 * lip - capB_t        # 端盖 A 用剩下的
    cap_t = min(capA_t, capB_t)
    zA = -lip - capA_t                           # 端盖 A 外表面
    zB = L + lip + capB_t
    zBm = -lip - capB_t                          # 端盖 B 外表面在 A 端坐标（镜像前）里的位置
    y_floor = -(p["liner_t"] + p["rubber_t"])    # 箱底钢面
    YT = y_floor + bi[1] - p["fit_clear"] - p["top_rubber_t"]   # 压框顶面（顶部硅胶条 0，箱盖内侧不贴纸）
    seat_in = p["seat_depth"] - lip              # 电芯座内端面 Z（A 座）
    return dict(W=W, H5=H5, HT=HT, L=L, lip=lip, cap_t=cap_t, capA_t=capA_t, capB_t=capB_t, zA=zA, zB=zB,
                zBm=zBm, y_floor=y_floor,
                YT=YT, seat_in=seat_in, zm=L / 2.0, gap=gap, gap_x=p["liner_t"] + p["gap_x"],
                plate_in=zA + p["cap_plate_t"],
                box=(-(bi[0] - W) / 2, W + (bi[0] - W) / 2, y_floor, y_floor + bi[1],
                     zA - gap, zB + gap))


def cc(i, j):
    p = P
    return (wall_x() + p["pitch"] / 2 + i * p["pitch"],
            p["wall_out"] + p["pitch"] / 2 + j * p["pitch"])


def cells():
    lst = [(i, j) for j in range(P["rows"]) for i in range(P["cols"])]
    lst += [(c, P["rows"]) for c in P["top_cols"]]
    return lst


def star(i, j):
    p = P
    return (wall_x() + p["pitch"] * (i + 1), p["wall_out"] + p["pitch"] * (j + 1))


def valid_stars():
    cs = set(cells())
    out = []
    for j in range(P["rows"] + 1):
        for i in range(P["cols"] - 1):
            if {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= cs:
                out.append((i, j))
    return out


def ntc_star():
    i, j = P["ntc_cell"]
    a = math.radians(P["ntc_dir"])
    return (i - (0 if math.cos(a) > 0 else 1), j - (0 if math.sin(a) > 0 else 1))


def outline_pts(z=0.0):
    d = D()
    x0 = top_block_x0()
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


def hex_prism(x, y, af, z0, z1):
    r = af / math.sqrt(3)
    pts = [V(x + r * math.cos(math.radians(30 + 60 * k)), y + r * math.sin(math.radians(30 + 60 * k)), z0)
           for k in range(7)]
    return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, z1 - z0))


def teardrop_y(x, z, ytop, r, depth, up=1):
    """沿 -Y 的水滴孔，尖角朝 up*Z（打印方向向上）。"""
    y0 = ytop + 0.5
    h = depth + 0.5
    c = Part.makeCylinder(r, h, V(x, y0, z), V(0, -1, 0))
    s = r / math.sqrt(2)
    pts = [V(x, y0, z), V(x + s, y0, z + up * s), V(x, y0, z + up * 2 * s), V(x - s, y0, z + up * s), V(x, y0, z)]
    tri = Part.Face(Part.makePolygon(pts)).extrude(V(0, -h, 0))
    return c.fuse(tri)


def mirror_z(shape):
    return shape.mirror(V(0, 0, D()["zm"]), V(0, 0, 1))


def centered_positions(a, b, h, gap=8.0, margin=10.0):
    s = 2 * h + gap
    n = int(math.floor((b - a - 2 * margin - 2 * h) / s)) + 1
    if n < 1:
        return []
    c = (a + b) / 2
    return [c + (k - (n - 1) / 2.0) * s for k in range(n)]


def rect_dist(x, y, r):
    dx = max(r[0] - x, 0, x - r[1])
    dy = max(r[2] - y, 0, y - r[3])
    return math.hypot(dx, dy)


# ============================================================
# 串联分组与连接片（层内直条 + 换层 2×2 方片）
# ============================================================
def groups():
    return [list(g) for g in P["series"]]


def connectors():
    """返回列表：dict(name, end, kind, cells, segs, ga, gb)。
    segs 为 (电芯a, 电芯b) 端点对，每段是一条宽 strip_w 的直条，沿行或沿列。"""
    g = groups()
    n = len(g)
    out = [dict(name="B-（第1组负极）", end="B", kind="terminal", cells=list(g[0]),
                segs=[(g[0][0], g[0][1])], ga=None, gb=None)]
    for k in range(n - 1):
        ga, gb = sorted(g[k]), sorted(g[k + 1])
        end = "A" if k % 2 == 0 else "B"
        name = "%d→%d" % (k + 1, k + 2)
        cs = sorted(ga + gb)
        xs, ys = {c[0] for c in cs}, {c[1] for c in cs}
        segs = [(cs[0], cs[-1])]
        if (len(ys) == 1 and max(xs) - min(xs) == 3) or (len(xs) == 1 and max(ys) - min(ys) == 3):
            kind = "straight"               # 一条 4 只直条
        elif len(xs) == 2 and len(ys) == 2 and max(xs) - min(xs) == 1 and max(ys) - min(ys) == 1:
            kind = "square"                 # 2×2 整块方片（宽铜片自裁，不挖中心孔）
        else:
            raise ValueError("第 %s 处连接既不是直条也不是 2×2 方片: %s" % (name, cs))
        out.append(dict(name=name, end=end, kind=kind, cells=ga + gb, segs=segs, ga=ga, gb=gb))
    last = sorted(g[-1])
    out.append(dict(name="B+（第%d组正极）" % n, end="B" if n % 2 == 0 else "A", kind="terminal",
                    cells=last, segs=[(last[0], last[1])], ga=None, gb=None))
    return out


def seg_rect(seg):
    w = P["strip_w"] / 2
    (x1, y1), (x2, y2) = cc(*seg[0]), cc(*seg[1])
    return (min(x1, x2) - w, max(x1, x2) + w, min(y1, y2) - w, max(y1, y2) + w)


def seg_cells(seg):
    (i1, j1), (i2, j2) = seg
    if i1 == i2:
        return [(i1, j) for j in range(min(j1, j2), max(j1, j2) + 1)]
    if j1 == j2:
        return [(i, j1) for i in range(min(i1, i2), max(i1, i2) + 1)]
    # 方片：两角点围成的矩形内全部电芯
    return [(i, j) for j in range(min(j1, j2), max(j1, j2) + 1) for i in range(min(i1, i2), max(i1, i2) + 1)]


def seg_edges(seg):
    """方片/直条覆盖的相邻电芯对（导电桥）。"""
    sc = set(seg_cells(seg))
    return [(a, b) for a in sc for b in sc if a < b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1]


def square_stars(end):
    """该端方片中心所在星形位（被方片盖住，不能放支撑垫/螺栓）。"""
    out = []
    for c in connectors():
        if c["end"] == end and c["kind"] == "square":
            out.append(min(c["cells"]))
    return out


def strip_rects(end):
    return [seg_rect(s) for c in connectors() if c["end"] == end for s in c["segs"]]


def strip_shape(end, kind=None):
    """连接片占位（铜+镍叠层），贴在挡边外表面。"""
    d = D()
    t = P["cu_t"] + P["ni_t"]
    solids = []
    for c in connectors():
        if c["end"] != end or (kind and c["kind"] != kind):
            continue
        parts = [box(r[0], r[1], r[2], r[3], -d["lip"] - t, -d["lip"]) for r in map(seg_rect, c["segs"])]
        s = parts[0].fuse(parts[1:]).removeSplitter() if len(parts) > 1 else parts[0]
        solids.append(s)
    if not solids:
        return None
    comp = Part.makeCompound(solids)
    return mirror_z(comp) if end == "B" else comp


# ============================================================
# 零件
# ============================================================
def rod_pts():
    return [star(*s) for s in P["rods"]]


def pad_stars(end):
    ban = set(square_stars(end))
    if end == "A":
        ban.add(ntc_star())
    return [s for s in valid_stars() if s not in ban]


def lighten_stars():
    used = set(P["rods"]) | {ntc_star()}
    return [s for s in valid_stars() if s not in used]


def rail_xs():
    off = (P["bms_w"] - P["bms_hole_w"]) / 2
    x1 = bms_x0() + off
    return (x1, x1 + P["bms_hole_w"])


def m3_zs():
    off = (P["bms_l"] - P["bms_hole_l"]) / 2
    z1 = P["bms_z0"] + off
    return (z1, z1 + P["bms_hole_l"])


def seat_core():
    """A 座（不含止口），Z 从 -lip 到 seat_in，定位管伸到 zm。"""
    d = D()
    lip, zi, zm = d["lip"], d["seat_in"], d["zm"]
    s = outline_face(-lip).extrude(V(0, 0, P["seat_depth"]))
    adds = [box(x - P["rail_w"] / 2, x + P["rail_w"] / 2, d["H5"], d["H5"] + P["rail_h"], -lip, zi)
            for x in rail_xs()]
    adds += [cyl(P["tube_d"] / 2, zi - 0.5, zm, x, y) for x, y in rod_pts()]
    s = s.fuse(adds)
    tools = []
    for c in cells():
        x, y = cc(*c)
        tools.append(cyl(P["hole_d"] / 2, 0, zi + 1, x, y))
        tools.append(cyl(P["end_hole_d"] / 2, -lip - 1, 1, x, y))
    for st in lighten_stars():
        tools.append(cyl(P["lighten_d"] / 2, -lip - 1, zi + 1, *star(*st)))
    for x, y in rod_pts():
        tools.append(cyl(P["rod_hole_d"] / 2, -lip - 1, zm + 1, x, y))
    tools.append(cyl(P["ntc_hole_d"] / 2, -lip - 1, zi + 1, *star(*ntc_star())))
    z1 = m3_zs()[0]
    for x in rail_xs():
        tools.append(teardrop_y(x, z1, d["H5"] + P["rail_h"], P["m3_d"] / 2, P["m3_depth"], up=1))
    return s.cut(tools)


def make_seat(end):
    d = D()
    zm = d["zm"]
    core = seat_core()
    if end == "A":
        sp = [cyl(P["spigot_d"] / 2, zm - 0.1, zm + P["spigot_h"], x, y) for x, y in rod_pts()]
        s = core.fuse(sp)
        s = s.cut([cyl(P["rod_hole_d"] / 2, zm - 1, zm + P["spigot_h"] + 1, x, y) for x, y in rod_pts()])
    else:
        s = mirror_z(core)
        s = s.cut([cyl(P["socket_d"] / 2, zm - 0.01, zm + P["socket_h"], x, y) for x, y in rod_pts()])
    return s.removeSplitter()


def make_cap(end):
    """端盖。先按 A 端坐标建模（外表面 Z=zA 或 zBm），B 端镜像。A、B 厚度不同。"""
    d = D()
    lip = d["lip"]
    ct = d["capA_t"] if end == "A" else d["capB_t"]
    zA = -lip - ct
    pin = zA + P["cap_plate_t"]
    f = outline_face(zA)
    plate = f.extrude(V(0, 0, P["cap_plate_t"]))
    inner = f.makeOffset2D(-P["rim_w"], 2)
    inner_s = inner.extrude(V(0, 0, ct + 2))
    inner_s.translate(V(0, 0, -1))
    rim = f.extrude(V(0, 0, ct)).cut(inner_s)
    pads = []
    for st in pad_stars(end):
        x, y = star(*st)
        dd = P["rod_pad_d"] if st in P["rods"] else P["pad_d"]
        pads.append(cyl(dd / 2, pin - 0.1, -lip, x, y))
    cap = plate.fuse([rim] + pads)
    tools = []
    cb = bolt_geom()["cbore_depth"]
    for x, y in rod_pts():
        tools.append(cyl(P["rod_hole_d"] / 2, zA - 1, -lip + 1, x, y))
        if end == "A":     # 螺丝头圆沉孔
            tools.append(cyl(P["cbore_d"] / 2, zA - 1, zA + cb, x, y))
        else:              # 热熔螺母孔，从外表面压入
            tools.append(cyl(P["insert_hole_d"] / 2, zA - 1, zA + insert_hole_depth(), x, y))
    rw = P["rim_w"]
    lo, hi = cap_slots()
    for a, b in lo:
        tools.append(box(a, b, d["H5"] - rw - 1, d["H5"] + 1, pin, -lip + 1))
    for a, b in hi:
        tools.append(box(a, b, d["HT"] - rw - 1, d["HT"] + 1, pin, -lip + 1))
    tools += rim_windows(pin, end)
    cap = cap.cut(tools).removeSplitter()
    return mirror_z(cap) if end == "B" else cap


def terminal_mid_x(g):
    """端子片（一组两只电芯）正中间的 X。"""
    return sum(cc(*c)[0] for c in g) / len(g)


def tab_xs():
    """B−、B+ 引出片中心 X：默认在端子片正中间。"""
    xm = P["main_wire_x"] if P["main_wire_x"] is not None else terminal_mid_x(P["series"][0])
    xp = P["bplus_x"] if P["bplus_x"] is not None else terminal_mid_x(P["series"][-1])
    return xm, xp


def cap_slots():
    """端盖顶边出线槽 (low, high)：采样线槽 + 引出片槽（宽 tab_w + 2×tab_slot_clear）。"""
    xm, xp = tab_xs()
    h = P["tab_w"] / 2 + P["tab_slot_clear"]
    lo = sorted(list(P["slots_low"]) + [(xm - h, xm + h)])
    hi = sorted(list(P["slots_high"]) + [(xp - h, xp + h)])
    return lo, hi


def insert_hole_depth():
    """热熔螺母孔深（自端盖 B 外表面）= 端盖 B 厚，即打穿到挡边。"""
    return P["insert_len"] + P["insert_recess"] + P["insert_relief"]


def bolt_geom():
    """贯穿螺栓（装配坐标）：头座面在端盖 A 里，离挡边外表面 floor_A；杆末端在端盖 B 的热熔螺母里。"""
    d = D()
    floor = P["floor_A"]
    cb = d["capA_t"] - floor                       # 头沉孔深（自外表面）
    head_seat = d["zA"] + cb
    ins_out = d["zB"] - P["insert_recess"]         # 热熔螺母外端
    ins_in = ins_out - P["insert_len"]             # 热熔螺母内端
    bolt_end = head_seat + P["bolt_len"]
    return dict(floor=floor, cbore_depth=cb, head_recess=cb - P["bolt_head_h"], head_seat=head_seat,
                insert_in=ins_in, insert_out=ins_out, bolt_end=bolt_end,
                engage=min(bolt_end, ins_out) - ins_in, tip_below_face=d["zB"] - bolt_end)


def rim_win_h(end):
    return P["rim_win_h"][0 if end == "A" else 1]


def rim_window_positions(end="A"):
    """返回 [(方向, 边坐标, 沿边位置列表)]。方向 'y'：穿 Y 向墙（顶边）；'x'：穿 X 向墙（左右侧）。"""
    d = D()
    h = rim_win_h(end)
    if h <= 0:
        return []
    gap, margin = 6.0, 8.0

    def free(lo, hi, slots):
        ps = centered_positions(lo, hi, h, gap, margin)
        return [p for p in ps if all(p + h + 1.0 <= a or p - h - 1.0 >= b for a, b in slots)]

    lo, hi = cap_slots()
    return [("y", d["H5"], free(0, top_block_x0(), lo)),
            ("y", d["HT"], free(top_block_x0(), d["W"], hi)),
            ("x", 0.0, free(0, d["H5"], ())),
            ("x", d["W"], free(0, d["HT"], ()))]


def rim_windows(pin=None, end="A"):
    d = D()
    h, rw = rim_win_h(end), P["rim_w"]
    zc = ((d["plate_in"] if pin is None else pin) + (-d["lip"])) / 2
    out = []
    for kind, e, ps in rim_window_positions(end):
        for p in ps:
            if kind == "y":
                pts = [V(p - h, 0, zc), V(p, 0, zc - h), V(p + h, 0, zc), V(p, 0, zc + h), V(p - h, 0, zc)]
                s = Part.Face(Part.makePolygon(pts)).extrude(V(0, rw + 1.5, 0))
                s.translate(V(0, e - rw - 0.5, 0))
            else:
                pts = [V(0, p - h, zc), V(0, p, zc - h), V(0, p + h, zc), V(0, p, zc + h), V(0, p - h, zc)]
                s = Part.Face(Part.makePolygon(pts)).extrude(V(rw + 1.5, 0, 0))
                s.translate(V(-1.0 if e == 0 else e - rw - 0.5, 0, 0))
            out.append(s)
    return out


def make_frame():
    d = D()
    W, H5, HT, YT = d["W"], d["H5"], d["HT"], d["YT"]
    t = P["frame_t"]
    z0, z1, zm = d["zA"], d["zB"], d["zm"]
    x0 = top_block_x0()
    yR = YT - P["frame_ring_t"]
    rw = P["frame_ring_w"]
    front = box(0, W, H5, YT, z0, z0 + t).cut(box(x0, W + 1, H5 - 1, HT, z0 - 1, z0 + t + 1))
    back = box(0, W, H5, YT, z1 - t, z1).cut(box(x0, W + 1, H5 - 1, HT, z1 - t - 1, z1 + 1))
    # B 端后墙在两个引出片处开缺口，给焊点和 12AWG 让位
    back = back.cut([box(a, b, y0 - 1, y0 + P["frame_notch_h"], z1 - t - 1, z1 + 1) for a, b, y0 in notch_ranges()])
    left = box(0, t, H5, YT, z0, z1)
    right = box(W - t, W, HT, YT, z0, z1)
    ring = box(0, W, yR, YT, z0, z1).cut(box(rw, W - rw, yR - 1, YT + 1, z0 + rw, z1 - rw))
    frame = front.fuse([back, left, right, ring] + frame_bars())
    h = P["frame_dia"]
    yU = (HT + yR) / 2
    yLo = (H5 + HT) / 2

    def dz(xc, yc):
        pts = [V(xc - h, yc, z0 - 1), V(xc, yc - h, z0 - 1), V(xc + h, yc, z0 - 1), V(xc, yc + h, z0 - 1),
               V(xc - h, yc, z0 - 1)]
        return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, z1 - z0 + 2))

    def dx(zc, yc, x1):
        pts = [V(-1, yc, zc - h), V(-1, yc - h, zc), V(-1, yc, zc + h), V(-1, yc + h, zc), V(-1, yc, zc - h)]
        return Part.Face(Part.makePolygon(pts)).extrude(V(x1 + 1, 0, 0))

    wins = [dz(xc, yU) for xc in centered_positions(0, W, h)]
    wins += [dz(xc, yLo) for xc in centered_positions(0, x0, h)]
    zs = centered_positions(z0 + t, z1 - t, h)
    wins += [dx(zc, yU, W + 1) for zc in zs]
    wins += [dx(zc, yLo, t + 1) for zc in zs]
    return frame.cut(wins + boss_pin_holes()).removeSplitter()


def frame_bars(grow=0.0):
    """压框顶环的两条对角支撑条（X 形，角到角），宽 frame_bar_w（+2×grow），装配坐标。
    原来是沿 X 的正中一条，用户要在正中线上打孔，改成对角。"""
    d = D()
    W, z0, z1 = d["W"], d["zA"], d["zB"]
    YT = d["YT"]
    yR = YT - P["frame_ring_t"]
    hw = P["frame_bar_w"] / 2 + grow
    out = []
    for (xa, za), (xb, zb) in (((0.0, z0), (W, z1)), ((0.0, z1), (W, z0))):
        L = math.hypot(xb - xa, zb - za)
        ux, uz = (xb - xa) / L, (zb - za) / L
        nx, nz = -uz * hw, ux * hw
        e = 20.0                                 # 两头多伸出，再和外框求交
        pa = (xa - ux * e, za - uz * e)
        pb = (xb + ux * e, zb + uz * e)
        pts = [V(pa[0] + nx, yR - grow, pa[1] + nz), V(pb[0] + nx, yR - grow, pb[1] + nz),
               V(pb[0] - nx, yR - grow, pb[1] - nz), V(pa[0] - nx, yR - grow, pa[1] - nz)]
        f = Part.Face(Part.makePolygon(pts + [pts[0]]))
        bar = f.extrude(V(0, YT - yR + 2 * grow, 0)).common(box(0, W, yR - grow, YT + grow, z0, z1))
        out.append(bar)
    return out


def boss_specs():
    """压框顶凸台：[(名称, (x0,x1,z0,z1), 两个销的 (x,z))]，装配坐标。"""
    d = D()
    W, rw, ins, e = d["W"], P["frame_ring_w"], P["boss_pin_inset"], P["boss_pin_end"]
    z0, z1 = d["zA"], d["zB"]
    bx = d["box"]
    xc = (bx[0] + bx[1]) / 2                    # 以箱内腔中线为准（螺丝位置是相对箱子量的）
    zc = (bx[4] + bx[5]) / 2
    hl, hs = P["boss_w_long"] / 2, P["boss_w_short"] / 2
    out = []
    for name, zr, zp in (("长边A", (z0, z0 + rw), z0 + ins), ("长边B", (z1 - rw, z1), z1 - ins)):
        out.append((name, (xc - hl, xc + hl) + zr, [(xc - hl + e, zp), (xc + hl - e, zp)]))
    for name, xr, xp in (("短边左", (0.0, rw), ins), ("短边右", (W - rw, W), W - ins)):
        out.append((name, xr + (zc - hs, zc + hs), [(xp, zc - hs + e), (xp, zc + hs - e)]))
    return out


def boss_height():
    d = D()
    return d["box"][3] - P["boss_top_gap"] - d["YT"]


def make_bosses():
    d = D()
    YT, h = d["YT"], boss_height()
    out = []
    for _, (x0, x1, z0, z1), pins in boss_specs():
        b = box(x0, x1, YT, YT + h, z0, z1)
        b = b.fuse([Part.makeCylinder(P["boss_pin_d"] / 2, P["boss_pin_h"] + 0.1, V(x, YT + 0.1, z), V(0, -1, 0))
                    for x, z in pins])
        out.append(b.removeSplitter())
    return out


def boss_pin_holes():
    d = D()
    YT = d["YT"]
    return [Part.makeCylinder(P["boss_pin_hole_d"] / 2, P["frame_ring_t"] + 2, V(x, YT + 1, z), V(0, -1, 0))
            for _, _, pins in boss_specs() for x, z in pins]


def lid_screw_solids():
    """箱盖紧固螺丝假体（按回忆的两种位置都画，伸进箱内 15 高范围），只用于校验凸台避让。"""
    d = D()
    bx = d["box"]
    r = P["lid_screw_r"]
    y0, y1 = d["YT"], bx[3]
    out = []
    for a in P["lid_screws_long"]:            # 长边：在 Z 两端箱壁上，沿 X 距两端 a
        for x in (bx[0] + a, bx[1] - a):
            for z0, z1 in ((bx[4], bx[4] + 15), (bx[5] - 15, bx[5])):
                out.append(box(x - r, x + r, y0, y1, z0, z1))
    for a in P["lid_screws_short"]:           # 短边：在 X 两侧箱壁上，沿 Z 距两端 a
        for z in (bx[4] + a, bx[5] - a):
            for x0, x1 in ((bx[0], bx[0] + 15), (bx[1] - 15, bx[1])):
                out.append(box(x0, x1, y0, y1, z - r, z + r))
    return out


def make_test_block():
    """试打块：上排 3 孔 Ø33.4/33.6/33.8 贯通；下排 Ø33.6 带挡边 1.5/2.0/2.5 + Ø24；
    星形位 1：Ø4.6 过孔 + 顶面凹止口；星形位 2：定位管段 + 凸止口；M3 试孔；
    -Y 侧试孔条：M4×8×6 热熔螺母孔 Ø5.5/5.6/5.7（有缺口标记的是 5.5）。
    打印：底面（挡边面）朝下。"""
    p = P
    pitch, w, h = p["pitch"], p["wall_out"], p["test_h"]
    Wt = 3 * pitch + 2 * w
    Ht = 2 * pitch + 2 * w
    blk = Part.makeBox(Wt, Ht, h)
    s1 = (w + pitch, w + pitch)
    s2 = (w + 2 * pitch, w + pitch)
    blk = blk.fuse(cyl(p["tube_d"] / 2, h - 0.1, h + 10, *s2))
    blk = blk.fuse(cyl(p["spigot_d"] / 2, h + 9.9, h + 10 + p["spigot_h"], *s2))
    tools = []
    for i in range(3):
        x = w + pitch / 2 + i * pitch
        tools.append(cyl(p["test_hole_ds"][i] / 2, -1, h + 1, x, w + pitch * 1.5))
        lip = p["test_lips"][i]
        tools.append(cyl(p["hole_d"] / 2, lip, h + 1, x, w + pitch / 2))
        tools.append(cyl(p["end_hole_d"] / 2, -1, h + 1, x, w + pitch / 2))
    tools.append(cyl(p["rod_hole_d"] / 2, -1, h + 12 + 1, *s1))
    tools.append(cyl(p["socket_d"] / 2, h - p["socket_h"], h + 1, *s1))
    tools.append(cyl(p["rod_hole_d"] / 2, -1, h + 13, *s2))
    tools.append(cyl(p["m3_d"] / 2, h - p["m3_depth"], h + 1, w + pitch, 5.0))     # M3 热熔螺母试孔
    tri = Part.Face(Part.makePolygon([V(-1, -1, -1), V(7, -1, -1), V(-1, 7, -1), V(-1, -1, -1)]))
    tools.append(tri.extrude(V(0, 0, h + 2)))
    # 热熔螺母试孔条（-Y 侧），3 个梯度，从顶面打下去（端盖 B 实际是从打印床那面压入，孔是竖直的，一样）
    bar_w = 12.0
    blk = blk.fuse(box(0, Wt, -bar_w, 0.1, 0, h))
    for k, dd in enumerate(p["test_insert_ds"]):
        x = Wt * (k + 1) / 4.0
        tools.append(cyl(dd / 2, h - insert_hole_depth(), h + 1, x, -bar_w / 2))
        tools.append(cyl(p["rod_hole_d"] / 2, -1, h + 1, x, -bar_w / 2))
    tools.append(box(Wt * 0.25 - 6, Wt * 0.25 + 6, -bar_w - 1, -bar_w + 0.8, h - 0.6, h + 1))   # 小缺口标记 = 最小孔
    blk = blk.cut(tools).removeSplitter()
    blk.translate(V(p["test_offset_x"], 0, 0))
    return blk


# ============================================================
# 参考假体
# ============================================================
def ntc_probe_solid():
    cx, cy = cc(*P["ntc_cell"])
    pw, ph, pl = P["ntc_probe"]
    r0 = P["cell_d_max"] / 2 + 0.1
    zc = D()["zm"]
    return radial_box(cx, cy, r0, r0 + ph, pw, zc - pl / 2, zc + pl / 2, P["ntc_dir"])


def bms_solid():
    d = D()
    y0 = d["H5"] + P["rail_h"]
    return box(bms_x0(), bms_x0() + P["bms_w"], y0, y0 + P["bms_t"], P["bms_z0"], P["bms_z0"] + P["bms_l"])


def notch_ranges():
    """B 端压框后墙缺口：[(x0, x1, 墙底 Y)]，对准两个引出片。"""
    d = D()
    h = P["tab_w"] / 2 + 2.0
    xm, xp = tab_xs()
    return [(xm - h, xm + h, d["H5"]), (xp - h, xp + h, d["HT"])]


def main_wire_solids():
    """正负极引出（都在 B 端最上面一层）。先按 A 端坐标建，再镜像到 B 端。返回 dict：
    tabs：B−、B+ 端子片向上延伸的引出片（铜+镍，宽 tab_w），穿过端盖顶边槽，伸出支架顶面 tab_above；
    joints：在支架顶面以上把 12AWG 锡焊到引出片上的空间（引出片外侧，压框后墙在这里开缺口）；
    routes：B− 线越过 BMS 顶面到 BMS 的 B− 端子；B+ 线向内弯进出线区；
    outlet：总正负出线区（B+ 和 BMS 的 P−），在压框顶环开口以内一直到箱盖。"""
    d = D()
    H5, HT, YT, lip = d["H5"], d["HT"], d["YT"], d["lip"]
    t = P["cu_t"] + P["ni_t"]
    hw = P["tab_w"] / 2
    by1 = H5 + P["rail_h"] + P["bms_t"]
    bx0 = bms_x0()
    zo = d["zBm"]                                # 端盖 B 外表面（A 坐标）
    zw = zo + P["frame_t"] + 0.1                 # 压框后墙内侧（A 坐标）
    zi = d["seat_in"]
    xm, xp = tab_xs()
    ym = cc(*P["series"][0][0])[1]
    yp = cc(*P["series"][-1][0])[1]
    tab_m = box(xm - hw, xm + hw, ym, H5 + P["tab_above"], -lip - t, -lip)
    tab_p = box(xp - hw, xp + hw, yp, HT + P["tab_above"], -lip - t, -lip)
    jz0, jz1 = zo + 0.3, -lip - t - 0.05        # 引出片外侧、端盖外表面以内
    joint_m = box(xm - hw - 1, xm + hw + 1, H5 + 3, H5 + P["tab_above"] + 3, jz0, jz1)
    joint_p = box(xp - hw - 1, xp + hw + 1, HT + 3, HT + P["tab_above"] + 3, jz0, jz1)
    route_m = box(bx0 + 2, xm + hw + 1, by1 + 0.1, by1 + P["main_wire_d"] + 2, zw, zi - 10)
    route_p = box(xp - hw - 1, xp + hw + 1, HT + 5, HT + 25, zw, zi)
    out = box(100.0, d["W"] - P["frame_ring_w"] - 0.5, HT + 0.5, YT,
              zo + P["frame_ring_w"] + 0.5, zi)
    m = mirror_z
    # 出线区让开压框对角支撑条（线从支撑条旁边的开口上去）
    outlet = m(out).cut(frame_bars(grow=0.5))
    return dict(tab_m=m(tab_m), tab_p=m(tab_p), joint_m=m(joint_m), joint_p=m(joint_p),
                route_m=m(route_m), route_p=m(route_p), outlet=outlet)


def wire_zones():
    """线束预留区（不打印，校验用）。"""
    d = D()
    H5, HT, lip = d["H5"], d["HT"], d["lip"]
    bx0, bx1 = bms_x0(), bms_x0() + P["bms_w"]
    by1 = H5 + P["rail_h"] + P["bms_t"]

    def end_zones(zo):                         # zo = 该端端盖外表面（A 坐标）
        zi = zo + P["frame_t"] + 0.1           # 压框前（后）墙内侧
        return [box(14.0, 138, H5 + 0.1, H5 + 31, zi, -lip - 0.1),                    # 端盖上方采样线
                box(top_block_x0() + 5.5, d["W"] - P["frame_t"] - 0.1, HT + 0.1, HT + 21, zi, -lip - 0.1),
                box(bx0, bx1, H5 + P["rail_h"], by1 + 10, zi, P["bms_z0"]),          # BMS 插座插头/弯线
                box(cc(5, 0)[0] + P["strip_w"] / 2 + 0.5, d["W"] - P["rim_w"] - 0.3, 10.0, HT - 0.1,
                    zo + P["cap_plate_t"] + 0.1, -lip - 0.3)]                        # 右侧竖向采样线通道
    A = end_zones(d["zA"])
    Bm = end_zones(d["zBm"])
    both = [box(P["frame_t"] + 0.1, bx0 - 0.5, H5 + 0.1, H5 + 16, d["seat_in"] + 0.1, d["L"] - d["seat_in"] - 0.1),
            box(bx1 + 0.5, top_block_x0() - 0.5, H5 + 0.1, H5 + 16, d["seat_in"] + 0.1,
                d["L"] - d["seat_in"] - 0.1),
            box(bx0, bx1, by1, by1 + 12, P["bms_z0"], P["bms_z0"] + P["bms_l"])]
    return A + [mirror_z(z) for z in Bm] + both


def liner_solids():
    d = D()
    bx = d["box"]
    t = P["liner_t"]
    return [box(bx[0], bx[0] + t, bx[2], bx[3], bx[4], bx[5]), box(bx[1] - t, bx[1], bx[2], bx[3], bx[4], bx[5]),
            box(bx[0] + t, bx[1] - t, bx[2], bx[2] + t, bx[4], bx[5]),
            box(bx[0] + t, bx[1] - t, bx[2] + t, bx[3], bx[4], bx[4] + t),
            box(bx[0] + t, bx[1] - t, bx[2] + t, bx[3], bx[5] - t, bx[5])]


def rubber_solids():
    d = D()
    y1 = d["y_floor"] + P["liner_t"]
    a = box(0, d["W"], y1, y1 + P["rubber_t"], d["zA"], d["zA"] + P["rubber_w"])
    b = box(0, d["W"], y1, y1 + P["rubber_t"], d["zB"] - P["rubber_w"], d["zB"])
    return [a, b]


def end_rubber_solids():
    """两侧硅胶垫：贴在端盖外表面，外形同端盖。"""
    d = D()
    t = P["end_rubber_t"]
    if t <= 0:
        return []
    return [outline_face(d["zA"] - t).extrude(V(0, 0, t)), outline_face(d["zB"]).extrude(V(0, 0, t))]


def top_rubber_solids():
    """顶部硅胶条：贴在压框顶环上（环宽 frame_ring_w）。"""
    d = D()
    y0, t, rw = d["YT"], P["top_rubber_t"], P["frame_ring_w"]
    if t <= 0:
        return []
    ring = box(0, d["W"], y0, y0 + t, d["zA"], d["zB"]).cut(
        box(rw, d["W"] - rw, y0 - 1, y0 + t + 1, d["zA"] + rw, d["zB"] - rw))
    return [ring]


def rod_solids():
    """贯穿螺栓假体：杆 Ø4 + 头 Ø6.8×4（热熔螺母另见 insert_solids）。"""
    b = bolt_geom()
    out = []
    for x, y in rod_pts():
        s = cyl(2.0, b["head_seat"], b["bolt_end"], x, y)
        s = s.fuse(cyl(P["bolt_head_d"] / 2, b["head_seat"] - P["bolt_head_h"], b["head_seat"], x, y))
        out.append(s)
    return out


def insert_solids():
    """热熔螺母假体（按孔径画，压入后外圈嵌进塑料，所以不参与干涉校验）。"""
    b = bolt_geom()
    return [cyl(P["insert_hole_d"] / 2, b["insert_in"], b["insert_out"], x, y).cut(
        cyl(2.0, b["insert_in"] - 1, b["insert_out"] + 1, x, y)) for x, y in rod_pts()]


# ============================================================
# 文档与显示
# ============================================================
PALETTE = [(0.90, 0.30, 0.30), (0.95, 0.60, 0.20), (0.95, 0.85, 0.25), (0.60, 0.85, 0.30),
           (0.30, 0.75, 0.40), (0.25, 0.75, 0.70), (0.30, 0.60, 0.90), (0.40, 0.40, 0.90),
           (0.65, 0.40, 0.90), (0.85, 0.40, 0.80), (0.90, 0.45, 0.55), (0.70, 0.55, 0.35),
           (0.55, 0.70, 0.55), (0.45, 0.55, 0.70), (0.75, 0.75, 0.75), (0.35, 0.35, 0.35)]


# 打印零件颜色（只影响 FCStd 和带色 STEP 的显示；无界面运行时 FCStd 里没有颜色）
COLORS = {"seatA": (0.16, 0.40, 0.72), "seatB": (0.16, 0.52, 0.62), "capA": (0.95, 0.55, 0.15),
          "capB": (0.92, 0.72, 0.18), "frame": (0.32, 0.34, 0.40), "test": (0.95, 0.75, 0.30),
          "bosses": (0.20, 0.65, 0.35)}
OBJ_NAMES = {"seatA": "SeatA", "seatB": "SeatB", "capA": "CapA", "capB": "CapB", "frame": "Frame",
             "bosses": "Bosses",
             "test": "TestBlock"}


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
    if a is None or b is None:
        return 0.0
    try:
        return a.common(b).Volume
    except Exception:
        return float("nan")


def vsum(a, lst):
    return round(sum(vol_common(a, b) for b in lst), 4)


def check_strips():
    R = {}
    g = groups()
    gid = {c: k for k, gg in enumerate(g) for c in gg}
    con = connectors()
    R["分组数/每组只数"] = (len(g), sorted({len(x) for x in g}))
    R["A端连接"] = ["%s(%s)" % (c["name"], c["kind"]) for c in con if c["end"] == "A"]
    R["B端连接"] = ["%s(%s)" % (c["name"], c["kind"]) for c in con if c["end"] == "B"]
    bad, bridges, square = [], {}, []
    for c in con:
        covered = set()
        edges = []
        for s in c["segs"]:
            sc = seg_cells(s)
            covered |= set(sc)
            edges += seg_edges(s)
            r = seg_rect(s)
            if min(r[1] - r[0], r[3] - r[2]) > P["strip_w"] + 1e-6:
                square.append(c["name"])
                if c["kind"] != "square":
                    bad.append((c["name"], "非方片却出现宽于 strip_w 的片"))
        if not set(c["cells"]) <= covered or not covered <= set(c["cells"]):
            bad.append((c["name"], "覆盖电芯不符"))
        seen, todo = {c["cells"][0]}, [c["cells"][0]]
        while todo:
            a = todo.pop()
            for e in edges:
                for x, y in (e, e[::-1]):
                    if x == a and y not in seen:
                        seen.add(y)
                        todo.append(y)
        if seen != set(c["cells"]):
            bad.append((c["name"], "不连通"))
        if c["ga"]:
            ga, gb = set(c["ga"]), set(c["gb"])
            bridges[c["name"]] = sum(1 for a, b in set(edges) if (a in ga and b in gb) or (a in gb and b in ga))
    R["连接片异常"] = bad
    R["每处连接桥数"] = bridges
    kinds = {c["name"]: c["kind"] for c in con}
    R["桥数符合(直条1/方片2)"] = all(v == (1 if kinds[k] == "straight" else 2) for k, v in bridges.items())
    R["2x2方片"] = square
    R["直条/方片/端子数"] = tuple(sum(1 for c in con if c["kind"] == k) for k in ("straight", "square", "terminal"))
    R["方片中心星形 A/B"] = (square_stars("A"), square_stars("B"))
    R["螺栓压在方片中心上"] = [s for s in P["rods"] if s in set(square_stars("A")) | set(square_stars("B"))]
    pos = [c for c in con if c["kind"] == "terminal"]
    R["B±所在端"] = [(c["name"], c["end"]) for c in pos]
    # 每组恰好在 A、B 两端各出现一次（一端是正极、另一端是负极）
    cnt = {}
    for c in con:
        for e in set(c["cells"]):
            cnt.setdefault(gid[e], []).append(c["end"])
    R["每组两端各接一次"] = all(sorted(v) == ["A", "A", "B", "B"] for v in cnt.values())
    w = P["strip_w"]
    a_cu = P["cu_t"] * w
    a_ni = P["ni_t"] * w
    a_eq = a_cu + a_ni * P["cu_rho"] / P["ni_rho"]
    I = P["current_A"]
    seg_len = P["pitch"] - 20.0   # 焊点间桥长度按 15 mm
    r_bridge = seg_len * 1e-3 / (1 / (P["cu_rho"] / (a_cu * 1e-6)) + 1 / (P["ni_rho"] / (a_ni * 1e-6)))
    R["桥截面铜当量mm2"] = round(a_eq, 2)
    R["桥电流密度A/mm2 直条/方片"] = (round(I / a_eq, 1), round(I / a_eq / 2, 1))
    R["每段桥发热W(30A)"] = round(I * I * r_bridge, 3)
    return R


def checks(o):
    d = D()
    R = {}
    W, H5, HT, lip = d["W"], d["H5"], d["HT"], d["lip"]
    seatA, seatB, capA, capB, frame = o["seatA"], o["seatB"], o["capA"], o["capB"], o["frame"]
    cs = o["cells"]
    stA, stB = o["stripA"], o["stripB"]
    # --- 箱体预算 ---
    bi = box_inner()
    R["箱内腔 X/Y/Z"] = tuple(round(v, 2) for v in bi)
    R["X 宽/预算"] = (round(W, 2), round(bi[0] - 2 * d["gap_x"], 2))
    R["Z 总长/预算"] = (round(d["zB"] - d["zA"], 2), round(bi[2] - 2 * d["gap"], 2))
    R["Z 装配余量合计(含纸)"] = round(bi[2] - (d["zB"] - d["zA"]), 2)
    R["端盖厚 A/B"] = (round(d["capA_t"], 3), round(d["capB_t"], 3))
    R["端盖A内空间高 ≥ capA_inner_min"] = (round(d["capA_t"] - P["cap_plate_t"], 2),
                                       d["capA_t"] - P["cap_plate_t"] >= P["capA_inner_min"] - 1e-9)
    R["支架底面Y/箱底钢面Y"] = (0.0, d["y_floor"])
    # --- 连接片 ---
    R.update(check_strips())
    # --- 电芯座 ---
    R["孔间壁"] = round(P["pitch"] - P["hole_d"], 2)
    R["孔到外表面最薄 X/Y"] = (round(wall_x() + P["pitch"] / 2 - P["hole_d"] / 2, 2),
                          round(P["wall_out"] + P["pitch"] / 2 - P["hole_d"] / 2, 2))
    tx, _ = cc(P["top_cols"][0], P["rows"])
    R["顶层块左壁"] = round(tx - P["hole_d"] / 2 - top_block_x0(), 2)
    R["座A∩电芯"] = vsum(seatA, cs)
    R["座B∩电芯"] = vsum(seatB, cs)
    R["座∩连接片"] = round(vol_common(seatA, stA) + vol_common(seatB, stB), 4)
    R["座A∩座B(止口)"] = round(vol_common(seatA, seatB), 4)
    rs = P["cell_d_max"] / 2
    R["定位管到电芯上限外径"] = round(min(math.hypot(x - cc(*c)[0], y - cc(*c)[1]) - rs - P["tube_d"] / 2
                                    for x, y in rod_pts() for c in cells()), 2)
    R["止口凸/凹单边间隙"] = round((P["socket_d"] - P["spigot_d"]) / 2, 2)
    R["止口轴向余量"] = round(P["socket_h"] - P["spigot_h"], 2)
    # 管对接：两片管端都在 zm
    R["中间敞开段长"] = round(d["L"] - 2 * d["seat_in"], 2)
    hx, hy = star(*ntc_star())
    R["探头孔到连接片A"] = round(min(rect_dist(hx, hy, r) for r in strip_rects("A")) - P["ntc_hole_d"] / 2, 2)
    R["探头∩座/电芯"] = round(vol_common(o["probe"], seatA) + vol_common(o["probe"], seatB) + vsum(o["probe"], cs), 4)
    R["探头∩定位管"] = round(vol_common(o["probe"], seatA) + vol_common(o["probe"], seatB), 4)
    R["减重孔数"] = len(lighten_stars())
    # --- 端盖 ---
    R["端盖A∩连接片A"] = round(vol_common(capA, stA), 4)
    R["端盖B∩连接片B"] = round(vol_common(capB, stB), 4)
    R["端盖∩座"] = round(vol_common(capA, seatA) + vol_common(capB, seatB), 4)
    R["端盖∩电芯"] = round(sum(vol_common(capA, c) + vol_common(capB, c) for c in cs), 4)
    pad_cl = {}
    for end in ("A", "B"):
        rects = strip_rects(end)
        m = 1e9
        for st in pad_stars(end):
            x, y = star(*st)
            dd = P["rod_pad_d"] if st in P["rods"] else P["pad_d"]
            m = min(m, min(rect_dist(x, y, r) for r in rects) - dd / 2)
        pad_cl[end] = round(m, 2)
    R["支撑垫到连接片最小"] = pad_cl
    # 边缘凸台到连接片
    rim_in = outline_face(0).makeOffset2D(-P["rim_w"], 2)
    m = 1e9
    for end in ("A", "B"):
        for r in strip_rects(end):
            f = Part.Face(Part.makePolygon([V(r[0], r[2], 0), V(r[1], r[2], 0), V(r[1], r[3], 0), V(r[0], r[3], 0),
                                            V(r[0], r[2], 0)]))
            m = min(m, rim_in.Wires[0].distToShape(f.Wires[0])[0])
    R["凸台内沿到连接片最小"] = round(m, 2)
    bg = bolt_geom()
    R["热熔螺母孔到垫外沿(≥3)"] = round((P["rod_pad_d"] - P["insert_hole_d"]) / 2, 2)
    R["螺丝头沉孔到垫外沿"] = round((P["rod_pad_d"] - P["cbore_d"]) / 2, 2)
    R["螺栓都有支撑垫(A,B)"] = (all(s in pad_stars("A") for s in P["rods"]), all(s in pad_stars("B") for s in P["rods"]))
    R["螺丝杆长"] = P["bolt_len"]
    R["头沉孔深(端盖A)"] = round(bg["cbore_depth"], 2)
    R["沉孔底厚(头下压在挡边上)"] = round(bg["floor"], 2)
    R["螺丝头顶低于端盖A外表面"] = round(bg["head_recess"], 2)
    R["热熔孔深/端盖B厚"] = (round(insert_hole_depth(), 2), round(d["capB_t"], 2))
    R["热熔螺母Z范围"] = (round(bg["insert_in"], 2), round(bg["insert_out"], 2))
    R["螺丝拧入热熔螺母长度"] = round(bg["engage"], 2)
    R["杆末端低于端盖B外表面"] = round(bg["tip_below_face"], 2)
    hole_vol = sum(vol_common(capB, cyl(P["insert_hole_d"] / 2 - 0.05, bg["insert_in"], bg["insert_out"], x, y))
                   for x, y in rod_pts())
    R["热熔孔内塑料体积"] = round(hole_vol, 4)
    R["螺栓尺寸OK"] = (bg["floor"] >= P["floor_min"] and bg["head_recess"] >= 0.3
                    and bg["engage"] >= P["min_engage"] and bg["tip_below_face"] >= P["tip_clear_min"]
                    and bg["bolt_end"] <= bg["insert_out"] and insert_hole_depth() <= d["capB_t"] + 1e-9
                    and (P["rod_pad_d"] - P["insert_hole_d"]) / 2 >= 3.0 and hole_vol < 1e-6)
    pa = []
    for end in ("A", "B"):
        ps = pad_stars(end)
        a = sum(math.pi * ((P["rod_pad_d"] if st in P["rods"] else P["pad_d"]) ** 2) / 4 for st in ps)
        a -= len(P["rods"]) * math.pi * P["rod_hole_d"] ** 2 / 4          # 螺栓孔
        a -= sum(1 for s in lighten_stars() if s in ps) * math.pi * P["lighten_d"] ** 2 / 4   # 座上减重孔落在垫中间
        a += outline_face(0).Area - rim_in.Area                          # 外周凸台
        pa.append(round(a))
    R["端盖承压面积mm2(A,B)"] = tuple(pa)
    F50 = len(cells()) * P["cell_mass"] * 9.81 * 50
    R["50g轴向合力N"] = round(F50)
    R["50g端盖平均压应力MPa"] = round(F50 / min(pa), 2)
    # --- 主线 ---
    mws = o["main_wires"]
    labs = (("tab_m", "B−引出片"), ("tab_p", "B+引出片"), ("joint_m", "B−焊点区"), ("joint_p", "B+焊点区"),
            ("route_m", "B−走线"), ("route_p", "B+走线"), ("outlet", "总正负出线区"))
    for k, lab in labs:
        s = mws[k]
        R[lab + "∩端盖B/座B/压框/BMS/电芯"] = tuple(round(vol_common(s, x), 4) for x in
                                              (capB, seatB, frame, bms_solid())) + (vsum(s, cs),)
    for k, lab in (("joint_m", "B−焊点区"), ("joint_p", "B+焊点区"), ("route_m", "B−走线"), ("route_p", "B+走线")):
        R[lab + "∩连接片B"] = round(vol_common(mws[k], stB), 4)
    R["引出片伸出支架顶面"] = P["tab_above"]
    xm, xp = tab_xs()
    R["引出片中心偏离端子片中间 B−/B+"] = (round(xm - terminal_mid_x(P["series"][0]), 3),
                                    round(xp - terminal_mid_x(P["series"][-1]), 3))
    R["引出片X范围 B−/B+"] = tuple(tuple(round(v, 2) for v in (mws[k].BoundBox.XMin, mws[k].BoundBox.XMax))
                              for k in ("tab_m", "tab_p"))
    R["焊点区Z深(放12AWG)"] = round(mws["joint_m"].BoundBox.ZLength, 2)
    R["引出片到BMS端面"] = round(mws["tab_m"].BoundBox.ZMin - (P["bms_z0"] + P["bms_l"]), 2)
    R["出线区(箱盖下方) X/Z范围"] = (tuple(round(v, 1) for v in (mws["outlet"].BoundBox.XMin, mws["outlet"].BoundBox.XMax)),
                              tuple(round(v, 1) for v in (mws["outlet"].BoundBox.ZMin, mws["outlet"].BoundBox.ZMax)))
    R["端盖内空间高 A/B(连接片+青稞纸+采样线)"] = (round(d["capA_t"] - P["cap_plate_t"], 2),
                                          round(d["capB_t"] - P["cap_plate_t"], 2))
    R["边框通风窗数 A/B"] = tuple(sum(len(p) for _, _, p in rim_window_positions(e)) for e in ("A", "B"))
    R["通风窗菱形高 A/B"] = (2 * rim_win_h("A"), 2 * rim_win_h("B"))
    R["通风窗到底板/挡边余量 A/B"] = tuple(round(((d["capA_t"] if e == "A" else d["capB_t"]) - P["cap_plate_t"]) / 2
                                          - rim_win_h(e), 2) for e in ("A", "B"))
    R["通风窗余量OK"] = all(v >= P["rim_win_margin"] - 1e-9 for v in R["通风窗到底板/挡边余量 A/B"])
    R["出线区面积(让开支撑条后, 顶环开口内) mm2"] = round(mws["outlet"].common(
        box(0, d["W"], d["YT"] - 0.2, d["YT"], d["zA"], d["zB"])).Volume / 0.2)
    # --- BMS ---
    bms = o["bms"]
    R["BMS∩座/端盖/电芯"] = round(vol_common(bms, seatA) + vol_common(bms, seatB) + vol_common(bms, capA)
                               + vol_common(bms, capB) + vsum(bms, cs), 4)
    R["BMS顶面Y/HT"] = (round(bms.BoundBox.YMax, 2), HT)
    R["BMS到顶层块间隙"] = round(top_block_x0() - bms.BoundBox.XMax, 2)
    R["BMS插座端空间"] = round(P["bms_z0"] - (d["zA"] + P["frame_t"]), 2)
    zs = m3_zs()
    R["M3孔Z / 所在座Z范围"] = (tuple(round(z, 2) for z in zs), (-lip, d["seat_in"]),
                             (d["L"] - d["seat_in"], d["L"] + lip))
    R["M3孔到座端面余量"] = round(min(zs[0] - P["m3_d"] / 2 + lip, d["seat_in"] - zs[0] - P["m3_d"] / 2,
                                  zs[1] - P["m3_d"] / 2 - (d["L"] - d["seat_in"]),
                                  d["L"] + lip - zs[1] - P["m3_d"] / 2), 2)
    R["M3孔到导轨侧面"] = round((P["rail_w"] - P["m3_d"]) / 2, 2)
    # --- 压框 ---
    R["压框∩BMS"] = round(vol_common(frame, bms), 4)
    R["压框∩线束预留"] = vsum(frame, o["wires"])
    R["压框∩座/端盖"] = round(vol_common(frame, seatA) + vol_common(frame, seatB) + vol_common(frame, capA)
                          + vol_common(frame, capB), 4)
    R["线束预留∩座/端盖"] = round(sum(vol_common(z, s) for z in o["wires"] for s in (seatA, seatB, capA, capB)), 4)
    # --- 总装/箱体 ---
    parts = [seatA, seatB, capA, capB, frame]
    bb = parts[0].BoundBox
    for s in parts[1:]:
        bb.add(s.BoundBox)
    bx = d["box"]
    t = P["liner_t"]
    R["总装包围盒"] = tuple(round(v, 2) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax))
    R["前后X 空隙(扣纸) 左/右"] = (round(bb.XMin - (bx[0] + t), 2), round(bx[1] - t - bb.XMax, 2))
    R["两侧Z 端盖到纸 A/B"] = (round(bb.ZMin - (bx[4] + t), 2), round(bx[5] - t - bb.ZMax, 2))
    R["两侧Z 硅胶垫外空隙 A/B"] = (round(bb.ZMin - P["end_rubber_t"] - (bx[4] + t), 2),
                             round(bx[5] - t - bb.ZMax - P["end_rubber_t"], 2))
    R["顶部 压框顶面到箱盖"] = round(bx[3] - bb.YMax, 2)
    bos = o["bosses"]
    R["凸台高/顶面到箱盖"] = (round(boss_height(), 2), round(bx[3] - max(b.BoundBox.YMax for b in bos), 2))
    R["凸台∩压框/座/端盖"] = round(sum(vol_common(b, s) for b in bos for s in parts), 4)
    R["凸台∩青稞纸/出线区/线束/引出片焊点区"] = round(sum(vol_common(b, s) for b in bos for s in
                                            o["liner"] + o["wires"] + [o["main_wires"][k] for k in o["main_wires"]]), 4)
    R["凸台∩箱盖螺丝(长边60/90、短边40 两种都算)"] = round(sum(vol_common(b, s) for b in bos for s in o["lid_screws"]), 4)
    R["凸台到箱盖螺丝最近(沿边)"] = round(min(b.distToShape(s)[0] for b in bos for s in o["lid_screws"]), 2)
    R["凸台销插入深/顶环厚"] = (P["boss_pin_h"], P["frame_ring_t"])
    R["凸台承压面积mm2 / 5g向上压应力MPa"] = (
        round(sum(b.BoundBox.XLength * b.BoundBox.ZLength for b in bos)),
        round((P["cell_mass"] * len(cells()) + 1.5) * 9.81 * 5 / sum(b.BoundBox.XLength * b.BoundBox.ZLength for b in bos), 3))
    R["底部 纸+胶条"] = round(bb.YMin - bx[2], 2)
    R["零件∩青壳纸/胶条"] = round(sum(vol_common(s, l) for s in parts for l in o["liner"] + o["rubber"]), 4)
    R["零件∩螺栓/螺母"] = round(sum(vol_common(s, r) for s in parts for r in o["rods"]), 4)
    R["螺栓∩电芯/连接片"] = round(sum(vol_common(r, c) for r in o["rods"] for c in cs + [stA, stB]), 4)
    R["螺栓头/杆末端凸出端盖外表面"] = round(max(max(r.BoundBox.ZMax for r in o["rods"]) - d["zB"],
                                       d["zA"] - min(r.BoundBox.ZMin for r in o["rods"])), 2)
    # --- 体积 ---
    vol = {k: round(o[k].Volume / 1000, 1) for k in ("seatA", "seatB", "capA", "capB", "frame")}
    vol["bosses"] = round(sum(b.Volume for b in bos) / 1000, 1)
    R["零件体积cm3"] = vol
    R["实体合计cm3"] = round(sum(vol.values()), 1)
    R["实心质量上限g(PETG 1.27)"] = round(sum(vol.values()) * 1.27)
    rub = (P["cell_mass"] * len(cells()) + sum(vol.values()) * 1.27e-3 * 0.55 + 0.35) * 9.81
    R["胶条静压MPa / 5g"] = (round(rub / (2 * P["rubber_w"] * W), 4), round(rub * 5 / (2 * P["rubber_w"] * W), 4))
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
    add(doc, "TestBlock", "试打块", test, COLORS["test"])
    seatA, seatB = make_seat("A"), make_seat("B")
    capA, capB = make_cap("A"), make_cap("B")
    frame = make_frame()
    add(doc, "SeatA", "电芯座A", seatA, COLORS["seatA"], 0, prt)
    add(doc, "SeatB", "电芯座B", seatB, COLORS["seatB"], 0, prt)
    add(doc, "CapA", "端盖A", capA, COLORS["capA"], 0, prt)
    add(doc, "CapB", "端盖B", capB, COLORS["capB"], 0, prt)
    add(doc, "Frame", "顶部压框", frame, COLORS["frame"], 0, prt)
    bosses = make_bosses()
    add(doc, "Bosses", "压框顶凸台x4", Part.makeCompound(bosses), COLORS["bosses"], 0, prt)
    lid_screws = lid_screw_solids()
    add(doc, "LidScrews", "箱盖紧固螺丝假体(两种回忆位置)", Part.makeCompound(lid_screws), (0.7, 0.1, 0.1), 50, ref)

    gidx = {c: k for k, gg in enumerate(groups()) for c in gg}
    z0 = (d["L"] - P["cell_len"]) / 2
    cell_shapes = []
    for c in cells():
        x, y = cc(*c)
        s = cyl(P["cell_d"] / 2, z0, z0 + P["cell_len"], x, y)
        cell_shapes.append(s)
        k = gidx[c]
        add(doc, "Cell_%d_%d" % c, "电芯_第%d组_(%d,%d)" % (k + 1, c[0] + 1, c[1] + 1), s,
            PALETTE[k % len(PALETTE)], 60, ref)
    stA, stB = strip_shape("A"), strip_shape("B")
    for end in ("A", "B"):
        for kind, col in (("straight", (0.75, 0.75, 0.78)), ("square", (0.85, 0.50, 0.25)), ("terminal", (0.9, 0.2, 0.2))):
            s = strip_shape(end, kind)
            if s is not None:
                add(doc, "Strip%s_%s" % (end, kind), "连接片_%s端_%s" % (end, kind), s, col, 0, ref)
    probe = ntc_probe_solid()
    add(doc, "NTC", "NTC探头假体", probe, (0.9, 0.1, 0.1), 0, ref)
    bms = bms_solid()
    add(doc, "BMS", "BMS假体_JK-BD6A", bms, (0.1, 0.4, 0.15), 30, ref)
    mws = main_wire_solids()
    add(doc, "TabMinus", "B−引出片(顶层,向上)", mws["tab_m"], (0.1, 0.1, 0.9), 0, ref)
    add(doc, "TabPlus", "B+引出片(顶层,向上)", mws["tab_p"], (0.9, 0.1, 0.1), 0, ref)
    add(doc, "LeadZone", "12AWG焊点与走线区",
        Part.makeCompound([mws[k] for k in ("joint_m", "joint_p", "route_m", "route_p")]), (1.0, 0.5, 0.0), 70, ref)
    add(doc, "Outlet", "总正负出线区_到箱盖", mws["outlet"], (1.0, 0.4, 0.4), 80, ref)
    wires = wire_zones()
    add(doc, "WireZone", "线束预留区", Part.makeCompound(wires), (1.0, 1.0, 0.0), 85, ref)
    rods = rod_solids()
    add(doc, "Bolts", "M4x150贯穿螺栓", Part.makeCompound(rods), (0.6, 0.6, 0.65), 0, ref)
    add(doc, "Inserts", "M4x8x6热熔螺母(端盖B)", Part.makeCompound(insert_solids()), (0.85, 0.70, 0.30), 0, ref)
    liner = liner_solids()
    add(doc, "Liner", "青壳纸", Part.makeCompound(liner), (0.55, 0.35, 0.2), 80, ref)
    rubber = rubber_solids()
    add(doc, "Rubber", "底部硅胶条3x40", Part.makeCompound(rubber), (0.2, 0.2, 0.2), 0, ref)
    erub = end_rubber_solids()
    if erub:
        add(doc, "EndRubber", "两侧硅胶垫(端盖外)", Part.makeCompound(erub), (0.25, 0.25, 0.25), 40, ref)
    trub = top_rubber_solids()
    if trub:
        add(doc, "TopRubber", "顶部硅胶条(压框顶环)", Part.makeCompound(trub), (0.25, 0.25, 0.25), 40, ref)
    rubber = rubber + erub + trub
    bx = d["box"]
    cav = box(*bx)
    o = add(doc, "BoxCavity", "箱体内腔_275x220x165", cav, (0.5, 0.5, 0.5), 90, ref)
    if getattr(o, "ViewObject", None) is not None:
        o.ViewObject.DisplayMode = "Wireframe"
    doc.recompute()
    objs = dict(seatA=seatA, seatB=seatB, capA=capA, capB=capB, frame=frame, cells=cell_shapes, stripA=stA,
                stripB=stB, probe=probe, bms=bms, wires=wires, main_wires=mws, rods=rods, liner=liner, rubber=rubber,
                bosses=bosses, lid_screws=lid_screws)
    R = checks(objs)
    R["试打块包围盒"] = tuple(round(v, 2) for v in (test.BoundBox.XLength, test.BoundBox.YLength, test.BoundBox.ZLength))
    LAST.clear()
    LAST.update(objs)
    LAST["test"] = test
    LAST["doc"] = doc
    return R


def _print_oriented(name):
    s = LAST[name].copy()
    if name in ("seatB", "capB"):          # 挡边/底板在 +Z 侧 → 翻过来朝下
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    elif name == "bosses":                  # 凸台顶面朝下，销朝上
        s = Part.makeCompound(LAST["bosses"])
        s.rotate(V(0, 0, 0), V(1, 0, 0), -90)
    elif name == "frame":                   # 顶环朝下
        s.rotate(V(0, 0, 0), V(1, 0, 0), -90)
    bb = s.BoundBox
    s.translate(V(-bb.XMin, -bb.YMin, -bb.ZMin))
    return s


EXPORT_NAMES = [("seatA", "电芯座A"), ("seatB", "电芯座B"), ("capA", "端盖A"), ("capB", "端盖B"),
                ("frame", "顶部压框"), ("bosses", "压框顶凸台x4"), ("test", "试打块")]


def print_bboxes():
    out = {}
    for key, label in EXPORT_NAMES:
        bb = _print_oriented(key).BoundBox
        out[label] = (round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1))
    out["OK(≤打印机-5)"] = all(max(v) <= P["printer"] - 5 for v in out.values())
    return out


def export_all():
    import MeshPart
    stl_dir = os.path.join(WORKDIR, "STL")
    stp_dir = os.path.join(WORKDIR, "STEP")
    os.makedirs(stl_dir, exist_ok=True)
    os.makedirs(stp_dir, exist_ok=True)
    out = {}
    for key, label in EXPORT_NAMES:
        s = _print_oriented(key)
        m = MeshPart.meshFromShape(Shape=s, LinearDeflection=P["stl_lin_defl"],
                                   AngularDeflection=P["stl_ang_defl"], Relative=False)
        sp = os.path.join(stl_dir, label + ".stl")
        m.write(sp)
        stp = os.path.join(stp_dir, label + ".step")
        if App.GuiUp:          # 界面下用 ImportGui 导出，STEP 里带颜色
            import ImportGui
            ImportGui.export([LAST["doc"].getObject(OBJ_NAMES[key])], stp)
        else:
            LAST[key].exportStep(stp)
        bb = s.BoundBox
        out[label] = dict(打印包围盒=(round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1)),
                          面片数=m.CountFacets, 封闭=m.isSolid(), STL字节=os.path.getsize(sp))
    LAST["doc"].saveAs(FCSTD_PATH)
    out["FCStd"] = FCSTD_PATH
    return out
