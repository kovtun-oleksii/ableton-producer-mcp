"""Write real Arrangement (track-lane) automation through a Session "carrier" clip.

Live's API refuses to create envelopes in Arrangement clips, but when a Session
clip that carries an automation envelope is duplicated into the Arrangement,
Live converts the envelope into track automation over that clip's span and
leaves the rest of the lane untouched. So, per affected Arrangement block:

  1. copy the block's notes (from the Session clip it was made from) into a
     spare Session slot,
  2. write the curve segment for that block into the carrier's envelope,
  3. duplicate the carrier onto the block's position (replacing it with an
     identical-notes clip), and restore the block's name.

Usage:
    python scripts/arrangement_automation.py plan.json
where plan.json is a list of jobs:
    {"track_index": 0, "carrier_slot": 3,
     "target": {"type": "device", "device_index": 1, "parameter_index": 1},
     "points": [{"time": 32, "value": 0.45}, ...],      # absolute Arrangement beats
     "blocks": [32, 48, 64],                               # start beats of blocks to rewrite
     "fallback_source_slot": 2}                            # optional; otherwise such blocks reuse their own notes
Several parameters in the same blocks go in one job as
    "targets": [{"target": {...}, "points": [...]}, ...]
instead of "target"/"points": rebuilding a block replaces the clip, so curves
written in separate passes over the same block could overwrite each other.
Give each curve explicit values for every rebuilt block (use "step" points
to hold the baseline), since a curve holds its end values outside its points.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_call import call  # noqa: E402


def _ok(reply, what):
    if reply.get("status") != "success":
        raise RuntimeError(what + ": " + str(reply.get("message")))
    return reply.get("result", {})


def _session_sources(track_index):
    info = _ok(call("get_track_info", {"track_index": track_index}), "get_track_info")
    return {s["clip"]["name"]: s["index"] for s in info["clip_slots"] if s.get("has_clip")}


def _notes(track_index, slot):
    notes = _ok(call("get_clip_notes", {"track_index": track_index, "clip_index": slot}), "get_clip_notes")["notes"]
    return [{k: n[k] for k in ("pitch", "start_time", "duration", "velocity", "mute")} for n in notes]


def _arrangement_notes(track_index, block_start):
    snap = _ok(call("get_session_snapshot", {"include_notes": True, "include_params": False}), "get_session_snapshot")
    clips = snap["tracks"][track_index]["arrangement_clips"]
    clip = next(c for c in clips if abs(c["start_time"] - block_start) < 1e-6)
    return [{k: n[k] for k in ("pitch", "start_time", "duration", "velocity", "mute")} for n in clip.get("notes", [])]


def automate_blocks(job):
    track = job["track_index"]
    carrier = job["carrier_slot"]
    sources = _session_sources(track)
    carrier_names = [name for name, slot in sources.items() if slot == carrier]
    if carrier_names and carrier_names[0] != "__automation_carrier__":
        raise RuntimeError("carrier slot %d on track %d holds '%s'" % (carrier, track, carrier_names[0]))
    arrangement = _ok(call("get_arrangement_clips", {"track_index": track}), "get_arrangement_clips")["clips"]
    note_cache = {}
    done = []
    for block_start in job["blocks"]:
        block = next((c for c in arrangement if abs(c["start_time"] - block_start) < 1e-6), None)
        if block is None:
            raise RuntimeError("no Arrangement clip starts at beat %s on track %d" % (block_start, track))
        source = sources.get(block["name"], job.get("fallback_source_slot"))
        if source is None:
            # No Session clip of that name (edited or one-off blocks): copy the
            # Arrangement clip's own notes instead.
            source = ("arrangement", block_start)
            name = block["name"]
            note_cache[source] = _arrangement_notes(track, block_start)
        else:
            # Unnamed blocks (e.g. left by an earlier carrier) take their source's name.
            name = block["name"] or next(n for n, s in sources.items() if s == source)
        if source not in note_cache:
            note_cache[source] = _notes(track, source)

        info = _ok(call("get_track_info", {"track_index": track}), "get_track_info")
        if info["clip_slots"][carrier]["has_clip"]:
            _ok(call("delete_clip", {"track_index": track, "clip_index": carrier}), "delete carrier")
        _ok(call("create_clip", {"track_index": track, "clip_index": carrier, "length": block["length"]}), "create carrier")
        _ok(call("set_clip_name", {"track_index": track, "clip_index": carrier, "name": "__automation_carrier__"}), "name carrier")
        if note_cache[source]:
            _ok(call("add_notes_to_clip", {"track_index": track, "clip_index": carrier, "notes": note_cache[source]}), "copy notes")
        # A rebuilt block replaces the clip, so every curve that should live in
        # it goes into the same carrier ("targets"), not into separate passes.
        curves = job.get("targets") or [{"target": job["target"], "points": job["points"]}]
        for curve in curves:
            local_points = [dict(p, time=p["time"] - block_start) for p in curve["points"]]
            _ok(call("set_clip_automation", {
                "track_index": track, "clip_view": "session", "clip_index": carrier,
                "target": curve["target"], "points": local_points,
                "resolution": job.get("resolution", 0.25), "clear_existing": True,
            }), "write envelope")
        _ok(call("duplicate_session_clip_to_arrangement", {
            "track_index": track, "clip_index": carrier, "destination_time": block_start,
        }), "duplicate carrier")

        arrangement = _ok(call("get_arrangement_clips", {"track_index": track}), "get_arrangement_clips")["clips"]
        index = next(i for i, c in enumerate(arrangement) if abs(c["start_time"] - block_start) < 1e-6)
        _ok(call("set_arrangement_clip_name", {"track_index": track, "clip_index": index, "name": name}), "restore name")
        done.append(block_start)

    info = _ok(call("get_track_info", {"track_index": track}), "get_track_info")
    if info["clip_slots"][carrier]["has_clip"]:
        _ok(call("delete_clip", {"track_index": track, "clip_index": carrier}), "delete carrier")
    return done


if __name__ == "__main__":
    for job in json.load(open(sys.argv[1])):
        blocks = automate_blocks(job)
        print("track %d: rewrote blocks at beats %s" % (job["track_index"], blocks))
