# -*- coding: utf-8 -*-
"""无界面批量跑主体切片工况（freecadcmd），结果写入 FEA/slice_results.json。"""
import json, os, sys, time, traceback
W = "/Users/admin/Downloads/battery"
exec(open(os.path.join(W, "battery_holder_v2.py"), encoding="utf-8").read())
exec(open(os.path.join(W, "fem_v2.py"), encoding="utf-8").read())
FP["mesh"]["slice"] = (1.2, 0.4)
os.makedirs(os.path.join(W, "FEA"), exist_ok=True)
res = {}
for case in ("down", "up"):
    t = time.time()
    try:
        s = setup_slice(case)
        print(case, "setup", s, round(time.time() - t), flush=True)
        r = solve()
        r["setup"] = s
        r["sec"] = round(time.time() - t)
        res[case] = r
        print(case, r, flush=True)
    except Exception:
        res[case] = {"error": traceback.format_exc()[-800:]}
        print(res[case], flush=True)
json.dump(res, open(os.path.join(W, "FEA", "slice_results.json"), "w"), ensure_ascii=False, indent=1)
