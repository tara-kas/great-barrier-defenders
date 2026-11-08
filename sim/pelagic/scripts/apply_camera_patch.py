#!/usr/bin/env python3
"""Replace indexed frames with audited fresh Isaac captures, preserving timing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import cv2


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dir', type=Path, required=True)
    parser.add_argument('--patch-dir', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    base, patch = args.base_dir, args.patch_dir
    info = json.loads((patch/'patch-manifest.json').read_text())
    schedule = json.loads((base/'schedule.json').read_text())
    other = json.loads((patch/'schedule.json').read_text())
    assert schedule['ticks'] == other['ticks'] and schedule['fps'] == other['fps']
    assert info['trace_sha256'] == digest(args.trace)
    assert info['geometry_validation']['passed'] and info['linkage_validation']['passed']
    indices = set(info['patch_indices'])
    count, fps = schedule['frame_count'], schedule['fps']
    assert indices and min(indices) >= 0 and max(indices) < count
    assert len(indices) == info['rendered_frame_count']
    for index in indices:
        assert (patch/f'patch-{index:05d}.png').is_file()
    original = base/'reef-rescue-mission.mp4'
    backup = base/'reef-rescue-mission-before-camera-fix.mp4'
    assert not backup.exists(), 'Already applied; retain the original capture provenance'
    source_hash = digest(original)
    capture = cv2.VideoCapture(str(original))
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == count
    assert abs(capture.get(cv2.CAP_PROP_FPS)-fps) < .001
    result = base/'reef-rescue-mission-patched.mp4'
    encoder = subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','bgr24',
        '-s','1600x900','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
        '-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(result)],stdin=subprocess.PIPE)
    try:
        for index in range(count):
            ok, frame = capture.read()
            assert ok, f'Missing source frame {index}'
            if index in indices:
                frame = cv2.imread(str(patch/f'patch-{index:05d}.png'))
            assert frame is not None and frame.shape == (900,1600,3)
            encoder.stdin.write(frame.tobytes())
        encoder.stdin.close()
        assert encoder.wait() == 0
    finally:
        capture.release()
        if encoder.poll() is None:
            encoder.terminate(); encoder.wait()
    subprocess.run(['ffmpeg','-v','error','-i',str(result),'-f','null','-'],check=True)
    original.rename(backup)
    result.rename(original)
    report = {'mode':'camera-only replacement with fresh audited Isaac captures',
              'original_sha256':source_hash,'sha256':digest(original),'frames':count,'fps':fps,
              'patch_indices':sorted(indices),'trace_sha256':info['trace_sha256'],
              'geometry_checks':info['geometry_validation']['checks'],
              'linkage_checks':len(info['linkage_validation']['checks']),
              'frame_timing_unchanged':True,'interpolated_frames':False,'decode_passed':True}
    (base/'camera-patch-validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='patch_indices'}))


if __name__ == '__main__':
    main()
