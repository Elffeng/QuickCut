#!/usr/bin/env python3
"""Validate the next-stage contract fixture, without media or model runtimes.

This deliberately is not a complete production schema validator. It exercises
cross-document, provenance and timing invariants that six teams share.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path, PurePosixPath


KINDS = {
    "Brief", "AssetManifest", "RetrievalRequest", "CandidateSet",
    "StoryPlan", "VoicePackage", "EditTimeline", "ExportManifest",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(records, key):
    result = {}
    for record in records:
        value = record[key]
        require(isinstance(value, str) and value and value not in result, f"Duplicate/empty {key}: {value}")
        result[value] = record
    return result


def interval(value, label, maximum=None):
    begin, end = value["begin"], value["end"]
    require(type(begin) is int and type(end) is int, f"{label}: times must be integer microseconds")
    require(0 <= begin < end, f"{label}: expected nonempty [begin,end)")
    if maximum is not None:
        require(end <= maximum, f"{label}: exceeds duration {maximum}")
    return begin, end


def safe_uri(value):
    require(isinstance(value, str) and value, "Asset URI must be a nonempty relative path")
    p = PurePosixPath(value)
    require(not p.is_absolute() and ".." not in p.parts and "\\" not in value and ":" not in value,
            f"Asset URI escapes the project root or is not portable: {value}")


def rate(value, label):
    n, d = value["numerator"], value["denominator"]
    require(type(n) is int and type(d) is int and n > 0 and d > 0, f"{label}: invalid rational rate")
    return n, d


def validate(bundle):
    require(bundle["schema_version"] == "0.1.0" and bundle["fixtures_only"] is True,
            "This checker expects an explicitly labeled 0.1.0 fixture")
    docs = unique(bundle["documents"], "kind")
    require(set(docs) == KINDS, "Expected exactly the eight agreed document kinds")
    unique(bundle["documents"], "document_id")
    project_id = docs["Brief"]["project_id"]
    for kind, doc in docs.items():
        require(doc["schema_version"] == "0.1.0" and doc["fixtures_only"] is True, f"{kind}: fixture/version missing")
        require(doc["project_id"] == project_id, f"{kind}: project mismatch")
        require(type(doc["revision"]) is int and doc["revision"] > 0, f"{kind}: bad revision")
        for link in doc["inputs"]:
            target = docs.get(link["kind"])
            require(target is not None, f"{kind}: unknown input kind")
            require(link["document_id"] == target["document_id"] and link["revision"] == target["revision"],
                    f"{kind}: stale input revision or document ID")
    manifest, story, voice, timeline = (docs[k] for k in ("AssetManifest", "StoryPlan", "VoicePackage", "EditTimeline"))
    assets = unique(manifest["assets"] + voice["assets"], "asset_id")
    for asset in assets.values():
        safe_uri(asset["uri"])
        if asset.get("proxy_uri"):
            safe_uri(asset["proxy_uri"])
        require(type(asset["duration_us"]) is int and asset["duration_us"] > 0, "Bad asset duration")
        require(asset["origin"] in {"user", "external", "generated"}, "Unknown asset origin")
        if asset["media_kind"] == "video":
            rate(asset["video"]["fps"], "source fps")
    segments = unique(manifest["segments"], "segment_id")
    for segment in segments.values():
        asset = assets[segment["asset_id"]]
        require(segment["asset_revision"] == asset["revision"], "Stale segment asset revision")
        begin, end = interval(segment["source_range_us"], "segment source", asset["duration_us"])
        for frame in segment["keyframes"]:
            safe_uri(frame["uri"])
            require(begin <= frame["source_time_us"] < end, "Keyframe lies outside its segment")
    queries = unique(docs["RetrievalRequest"]["queries"], "query_id")
    results = unique(docs["CandidateSet"]["results"], "query_id")
    require(set(results) == set(queries), "Candidate results must explicitly cover each retrieval query")
    candidates = unique([c for result in results.values() for c in result["candidates"]], "candidate_id")
    for query_id, result in results.items():
        for candidate in result["candidates"]:
            segment = segments[candidate["segment_id"]]
            asset = assets[segment["asset_id"]]
            require(candidate["asset_revision"] == asset["revision"], "Candidate asset revision mismatch")
            require(asset["origin"] in queries[query_id]["allowed_origins"], "Candidate violates allowed origins")
    beats = unique(story["beats"], "beat_id")
    story_cues = unique(story["narration_cues"], "cue_id")
    selected = set()
    require(not story["unresolved_gaps"], "Ready-for-edit fixture has unresolved story gaps")
    for beat in beats.values():
        require(all(c in story_cues for c in beat["cue_ids"]), "Beat references unknown narration cue")
        for shot in beat["shots"]:
            candidate = candidates[shot["candidate_id"]]
            require(shot["segment_id"] == candidate["segment_id"], "Story selection does not match candidate")
            selected.add(shot["segment_id"])
    for cue in story_cues.values():
        require(cue["beat_id"] in beats and cue["cue_id"] in beats[cue["beat_id"]]["cue_ids"], "Narration/beat mismatch")
        require(set(cue["evidence_segment_ids"]) <= selected, "Narration cites an unselected segment")
    voices = unique(voice["cues"], "cue_id")
    require(set(voices) == set(story_cues), "Voice package omits or adds narration cues")
    for cue_id, cue in voices.items():
        require(cue["text"] == story_cues[cue_id]["text"], "TTS changed approved narration text")
        require(cue["duration_us"] == assets[cue["asset_id"]]["duration_us"], "Voice duration does not match audio asset")
        require(cue["fit_status"] == "fits" and not cue["needs_retime"], "Ready timeline uses unresolved TTS timing")
        require(cue["duration_us"] <= cue["duration_budget_us"], "Voice exceeds its declared budget")
        for local in cue["local_subtitles"]:
            interval(local["range_us"], "local subtitle", cue["duration_us"])
        require("".join(c["text"] for c in cue["local_subtitles"]) == cue["text"], "Local subtitle/voice text mismatch")
    duration = timeline["duration_us"]
    require(duration <= docs["Brief"]["requirements"]["target_duration_us"], "Timeline exceeds brief duration")
    tracks = unique(timeline["tracks"], "track_id")
    rate(timeline["output"]["fps"], "output fps")
    clips = unique([clip for track in tracks.values() for clip in track.get("clips", [])], "clip_id")
    narrator_clips = {}
    for track in tracks.values():
        records = track.get("clips", track.get("cues", []))
        previous_end = 0
        for record in records:
            begin, end = interval(record["timeline_range_us"], "timeline clip", duration)
            require(begin >= previous_end, "Unexpected overlap or out-of-order clip in one track")
            previous_end = end
            if "asset_id" not in record:
                continue
            asset = assets[record["asset_id"]]
            require(record["asset_revision"] == asset["revision"], "Timeline references stale asset")
            sb, se = interval(record["source_range_us"], "clip source", asset["duration_us"])
            n, d = rate(record["playback_rate"], "playback rate")
            require((se - sb) * d == (end - begin) * n, "Source/output duration or playback rate mismatch")
            if track["kind"] == "video":
                segment = segments[record["segment_id"]]
                require(segment["asset_id"] == record["asset_id"] and record["segment_id"] in selected,
                        "Picture clip is not a selected source segment")
                lo, hi = interval(segment["source_range_us"], "selected source")
                require(lo <= sb < se <= hi, "Fine cut exceeds declared candidate interval")
                require(record["beat_id"] in beats, "Unknown beat")
            elif track["kind"] == "source_audio":
                linked = clips[record["linked_video_clip_id"]]
                require(asset["audio"]["present"], "Original track cites media without audio")
                require(all(record[k] == linked[k] for k in ("asset_id", "source_range_us", "timeline_range_us", "playback_rate")),
                        "Original soundtrack is no longer aligned with its picture clip")
            elif track["kind"] == "narration":
                require(record["cue_id"] not in narrator_clips, "Narration cue repeated")
                narrator_clips[record["cue_id"]] = record
                require(record["asset_id"] == voices[record["cue_id"]]["asset_id"], "Wrong voice asset")
    require(set(narrator_clips) == set(voices), "Timeline narration coverage does not match voice package")
    subtitles = [cue for track in tracks.values() if track["kind"] == "subtitle" for cue in track["cues"]]
    unique(subtitles, "subtitle_id")
    require({s["cue_id"] for s in subtitles} == set(voices), "Missing/extra subtitle cues")
    for cue in subtitles:
        require(cue["text"] == voices[cue["cue_id"]]["text"], "Subtitle text differs from spoken text")
        require(cue["timeline_range_us"] == narrator_clips[cue["cue_id"]]["timeline_range_us"], "Subtitle/voice timing differs")
    pictures = [c for t in tracks.values() if t["kind"] == "video" for c in t["clips"]]
    require(pictures[0]["timeline_range_us"]["begin"] == 0 and pictures[-1]["timeline_range_us"]["end"] == duration,
            "Fixture picture does not cover the full timeline")
    require(all(a["timeline_range_us"]["end"] == b["timeline_range_us"]["begin"] for a, b in zip(pictures, pictures[1:])),
            "Fixture contains an unintended picture gap")
    export = docs["ExportManifest"]
    require(export["status"] == "not_exported" and export["import_verification"]["performed"] is False,
            "Fixture must not claim an actual editor export/import")
    safe_uri(export["package_root"])
    for entry in export["planned_files"]:
        safe_uri(entry["uri"])
    return project_id


def self_test(bundle):
    mutations = [
        ("stale revision", lambda d: d["StoryPlan"]["inputs"][0].update(revision=999)),
        ("unsafe media path", lambda d: d["AssetManifest"]["assets"][0].update(uri="../outside.mp4")),
        ("out-of-bounds source", lambda d: d["EditTimeline"]["tracks"][0]["clips"][0]["source_range_us"].update(end=999999999)),
        ("subtitle text mismatch", lambda d: d["EditTimeline"]["tracks"][3]["cues"][0].update(text="并未播出的台词")),
        ("false export claim", lambda d: d["ExportManifest"].update(status="verified_import")),
    ]
    for name, mutate in mutations:
        altered = copy.deepcopy(bundle)
        mutate({d["kind"]: d for d in altered["documents"]})
        try:
            validate(altered)
        except (ValueError, KeyError, TypeError):
            continue
        raise ValueError(f"Negative control was not rejected: {name}")
    print(f"PASS: {len(mutations)} invalid-fixture negative controls rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=Path(__file__).with_name("bundle.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        project_id = validate(bundle)
        print(f"PASS: contract fixture {project_id}; 8 documents; no media/model execution")
        if args.self_test:
            self_test(bundle)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
