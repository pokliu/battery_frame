# -*- coding: utf-8 -*-
"""无界面批量跑 v3 受力分析，结果写入 FEA/v3_results.json。
用法：freecadcmd fem_run_v3.py            （全部工况）
      环境变量 V3_CASES=axial,lateral,frame 选择工况，V3_LIPS=1.5,2.0,2.5 选择挡边厚。"""
import copy, json, os, time, traceback
W = "/Users/admin/Downloads/battery"
exec(open(os.path.join(W, "battery_holder_v3.py"), encoding="utf-8").read())
exec(open(os.path.join(W, "fem_v3.py"), encoding="utf-8").read())
P0 = copy.deepcopy(P)
cases = os.environ.get("V3_CASES", "axial,lateral,frame").split(",")
lips = [float(x) for x in os.environ.get("V3_LIPS", "1.5,2.0,2.5").split(",")]
lat_lip = float(os.environ.get("V3_LAT_LIP", "1.5"))
path = os.path.join(W, "FEA", "v3_results.json")
out = json.load(open(path)) if os.path.exists(path) else {}


def run(name, setup, *args):
    t = time.time()
    try:
        s = setup(*args)
        print(name, "setup", s, flush=True)
        r = solve()
        r.update(setup=s, sec=round(time.time() - t))
    except Exception:
        r = {"error": traceback.format_exc()[-1200:]}
    out[name] = r
    print(name, r, flush=True)
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)


ends = os.environ.get("V3_ENDS", "A").split(",")
tag = os.environ.get("V3_TAG", "")
if "axial" in cases:
    for lip in lips:
        for e in ends:
            P.clear(); P.update(copy.deepcopy(P0)); P["lip_t"] = lip
            run("座_侧摔50g_挡边%.1f%s_支撑垫%s端" % (lip, tag, e), setup_seat_axial, 50.0, e)
if "lateral" in cases:
    P.clear(); P.update(copy.deepcopy(P0)); P["lip_t"] = lat_lip
    for c in ("x", "down", "up"):
        run("座_%s_5g_挡边%.1f" % (c, lat_lip), setup_seat_lateral, c, 5.0)
if "frame" in cases:
    P.clear(); P.update(copy.deepcopy(P0))
    run("压框_向上5g", setup_frame)
print("DONE", flush=True)
