# -*- coding: utf-8 -*-
"""用当前参数表复算端盖（最终配置），结果并入 FEA/cap_frame_results.json。"""
import json, os, time, traceback
W = "/Users/admin/Downloads/battery"
exec(open(os.path.join(W, "battery_holder_v2.py"), encoding="utf-8").read())
exec(open(os.path.join(W, "fem_v2.py"), encoding="utf-8").read())
FP["mesh"]["cap"] = (1.8, 0.6)
path = os.path.join(W, "FEA", "cap_frame_results.json")
out = json.load(open(path))
t = time.time()
try:
    s = setup_cap()
    r = solve()
    r.update(螺丝数=s["螺丝压面数"], 合力N=s["合力N"], plate_t=P["plate_t"], sec=round(time.time() - t))
except Exception:
    r = {"error": traceback.format_exc()[-800:]}
out["最终_t%.1f_%d颗" % (P["plate_t"], len(P["screws"]))] = r
print("final", r, flush=True)
json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
