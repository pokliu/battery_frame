# -*- coding: utf-8 -*-
"""无界面跑端盖方案对比 + 压框工况，结果写入 FEA/cap_frame_results.json。"""
import copy, json, os, time, traceback
W = "/Users/admin/Downloads/battery"
exec(open(os.path.join(W, "battery_holder_v2.py"), encoding="utf-8").read())
exec(open(os.path.join(W, "fem_v2.py"), encoding="utf-8").read())
FP["mesh"]["cap"] = (1.8, 0.6)
FP["mesh"]["frame"] = (2.5, 0.8)
P0 = copy.deepcopy(P)
extra = (("star", 2, 0), ("star", 2, 3), ("star", 0, 2), ("star", 4, 2), ("star", 4, 4))
variants = [
    ("t1.5_10颗(当前)", dict()),
    ("t3.0_10颗", dict(plate_t=3.0)),
    ("t3.0_15颗", dict(plate_t=3.0, screws=P0["screws"] + extra)),
    ("t2.5_15颗", dict(plate_t=2.5, screws=P0["screws"] + extra)),
    ("t2.0_15颗", dict(plate_t=2.0, screws=P0["screws"] + extra)),
    ("t1.5_15颗", dict(plate_t=1.5, screws=P0["screws"] + extra)),
]
path = os.path.join(W, "FEA", "cap_frame_results.json")
out = json.load(open(path)) if os.path.exists(path) else {}
out.pop("压框_向上冲击", None)
variants = [v for v in variants if v[0] not in out]
for name, kw in variants:
    P.clear(); P.update(copy.deepcopy(P0)); P.update(kw)
    t = time.time()
    try:
        s = setup_cap()
        r = solve()
        r.update(螺丝数=s["螺丝压面数"], 合力N=s["合力N"], sec=round(time.time() - t))
    except Exception:
        r = {"error": traceback.format_exc()[-800:]}
    out[name] = r
    print(name, r, flush=True)
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
P.clear(); P.update(P0)
t = time.time()
try:
    s = setup_frame()
    r = solve()
    r.update(setup=s, sec=round(time.time() - t))
except Exception:
    r = {"error": traceback.format_exc()[-800:]}
out["压框_向上冲击"] = r
print("frame", r, flush=True)
json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
print("DONE", flush=True)
