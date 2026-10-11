"""Name-based helpers for live sessions: resolve track/device indices right before every call
(the user edits the set while scripts run), set parameters by their display value, measure peaks.

Meter calibration (Live raw meter scale, linear in dB near the top): 0.01317 per dB, 0.881 = -3.1 dBFS."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_call import call  # noqa: E402

CAL, CEIL_RAW, CEIL_DB = 0.01317, 0.881, -3.1


def ok(reply, what):
    if reply.get("status") != "success":
        raise SystemExit(what + " FAILED: " + str(reply.get("message")))
    return reply.get("result", {})


def track(name):
    for t in ok(call("get_session_snapshot", {"include_notes": False, "include_params": False}), "snap")["tracks"]:
        if t["name"] == name or (name == "*-Group" and t["name"].endswith("-Group")):
            return t["index"]
    raise SystemExit("track not found: " + name)


def device(tname, dname, which="last"):
    ti = track(tname)
    idx = [d["index"] for d in ok(call("get_track_info", {"track_index": ti}), "info")["devices"] if d["name"] == dname]
    if not idx:
        raise SystemExit("%s not on %s" % (dname, tname))
    return ti, (idx[0] if which == "first" else idx[-1])


def param(tname, dname, pname, which="last"):
    ti, di = device(tname, dname, which)
    ps = ok(call("get_device_parameters", {"track_index": ti, "device_index": di}), "params")["device"]["parameters"]
    return ti, di, [p for p in ps if p["name"] == pname][0]


def num(display):
    x = float(re.search(r"[-−]?\d+(\.\d+)?", display).group(0).replace("−", "-"))
    return x * 1000 if "kHz" in display else x


def set_raw(tname, dname, pname, value, which="last"):
    ti, di, p = param(tname, dname, pname, which)
    ok(call("set_device_parameter", {"track_index": ti, "device_index": di, "parameter_index": p["index"], "value": value}), pname)
    return p["display"], param(tname, dname, pname, which)[2]["display"]


def set_display(tname, dname, pname, target, which="last"):
    """Bisect a monotonic parameter until its display number reads `target` (dB, Hz…)."""
    ti, di, p = param(tname, dname, pname, which)
    before, lo, hi = p["display"], p["min"], p["max"]
    for _ in range(28):
        mid = (lo + hi) / 2
        ok(call("set_device_parameter", {"track_index": ti, "device_index": di, "parameter_index": p["index"], "value": mid}), pname)
        cur = [q for q in ok(call("get_device_parameters", {"track_index": ti, "device_index": di}), "p")["device"]["parameters"]
               if q["index"] == p["index"]][0]
        if num(cur["display"]) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-4:
            break
    return before, param(tname, dname, pname, which)[2]["display"]


def peak(tname, at):
    t = -1 if tname == "MASTER" else track(tname)
    ok(call("set_current_song_time", {"time": at}), "seek")
    time.sleep(2.5)
    raw = ok(call("measure_peak", {"track_index": t, "duration": 2.5}), "peak")["peak_hold"]
    return (raw - CEIL_RAW) / CAL + CEIL_DB
