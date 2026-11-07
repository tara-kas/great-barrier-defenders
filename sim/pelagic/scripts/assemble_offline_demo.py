#!/usr/bin/env python3
"""Join completed, validated mission and inspection movies without streaming."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate,codec_name",
        "-show_entries", "format=duration,size", "-show_chapters", "-of", "json", str(path)]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", type=Path, default=ROOT / "outputs/contact-graft-pip")
    parser.add_argument("--inspection", type=Path, default=ROOT / "outputs/reef-inspection-lighting")
    parser.add_argument("--details", type=Path,
                        help="Use the current/tissue detail reel as the first chapter")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "outputs/pelagic-scuba-demo/pelagic-complete.mp4")
    args = parser.parse_args()
    directories = ([args.details, args.mission] if args.details else [args.mission, args.inspection])
    sources = ([args.details / "pelagic-reef-details.mp4", args.mission / "pelagic-pip.mp4"]
               if args.details else [args.mission / "pelagic-pip.mp4", args.inspection / "pelagic-inspection.mp4"])
    validations = [json.loads((directory / "validation.json").read_text())
                   for directory in directories]
    assert all(v["result"] == "PASS" for v in validations), "Both input recordings must pass validation"
    assert args.output.resolve() not in [p.resolve() for p in sources]
    media = [probe(source) for source in sources]
    streams = [m["streams"][0] for m in media]
    for stream in streams:
        assert (stream["width"], stream["height"], stream["r_frame_rate"], stream["codec_name"]) == (
            1600, 900, "24/1", "h264"), "Inputs must use the common offline recording format"
    frames = [int(s["nb_read_frames"]) for s in streams]
    for observed, validated in zip(frames, validations):
        assert observed == int(validated["video"]["streams"][0]["nb_read_frames"])
    titles = (["Current, living tissue and robot lights", "Natural-branch coral contact mission"]
              if args.details else ["Same-genet coral contact mission", "White, blue and UV inspection cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pelagic-join-") as temporary:
        directory = Path(temporary)
        # ffconcat uses single quotes, with embedded quotes escaped outside them.
        quoted = [str(p.resolve()).replace("'", "'\\''") for p in sources]
        (directory / "inputs.txt").write_text("".join(f"file '{p}'\n" for p in quoted))
        metadata = ";FFMETADATA1\ntitle=PELAGIC — offline reef demonstration\n"
        start = 0
        for title, count in zip(titles, frames):
            metadata += f"[CHAPTER]\nTIMEBASE=1/24\nSTART={start}\nEND={start+count}\ntitle={title}\n"
            start += count
        (directory / "chapters.txt").write_text(metadata)
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(directory / "inputs.txt"),
            "-i", str(directory / "chapters.txt"), "-map", "0:v:0", "-map_metadata", "1",
            "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", str(args.output)], check=True)
    result = probe(args.output)
    assert int(result["streams"][0]["nb_read_frames"]) == sum(frames)
    assert abs(float(result["format"]["duration"]) - sum(frames)/24) < .1
    assert len(result["chapters"]) == 2
    evidence = {"result": "PASS", "server_started": False, "sources": [str(p.resolve()) for p in sources],
                "source_sha256": [hashlib.sha256(p.read_bytes()).hexdigest() for p in sources],
                "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "chapters": titles, "reencoded": False, "video": result,
                "interpretation": "Mechanical contact and illustrative RGB response; biological recovery unmodelled"}
    args.output.with_suffix(".validation.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps({"result": "PASS", "movie": str(args.output),
                      "frames": sum(frames), "duration_seconds": sum(frames)/24}, indent=2))


if __name__ == "__main__":
    main()
