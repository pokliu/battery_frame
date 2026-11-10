# -*- coding: utf-8 -*-
import json, os, time, traceback
W = "/Users/admin/Downloads/battery"
exec(open(os.path.join(W, "battery_holder_v2.py"), encoding="utf-8").read())
exec(open(os.path.join(W, "fem_v2.py"), encoding="utf-8").read())
FP["mesh"]["frame"] = (1.5, 0.6)
path = os.path.join(W, "FEA", "cap_frame_results.json")
out = json.load(open(path))
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
