"""Bounded, read-only bridge to the team's canonical dashboard file contract."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import stat
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT = 2 * 1024 * 1024
MAX_FRAME = 2 * 1024 * 1024
MAX_STATE = 1024 * 1024

class FeedError(ValueError):
    pass

class _SnapshotPath:
    """The unchanged canonical readers consume an already bounded file snapshot."""
    def __init__(self, data):
        self.data = data
    def read_text(self, encoding="utf-8"):
        return self.data.decode(encoding)


def canonical_readers():
    candidates = (ROOT / "great-barrier-defenders/dashboard/server.py",
                  ROOT.parent.parent / "dashboard/server.py", Path("/root/dashboard/server.py"))
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        return None
    try:
        spec = importlib.util.spec_from_file_location("reef_canonical_dashboard_readers", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.read_registry, module.read_decisions
    except (ImportError, OSError, SyntaxError, AttributeError):
        return None


class TeamFeed:
    def __init__(self, run_dir=None, *, readers=None):
        configured = os.environ.get("TEAM_RUN_DIR", "") if run_dir is None else run_dir
        self.root = Path(configured).expanduser().resolve() if configured else None
        self.readers = canonical_readers() if readers is None else readers
        self.last_good = None
        self.lock = threading.Lock()

    def _read(self, name, maximum):
        path = self.root / name
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise FeedError("Source path is outside the configured run directory")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise FeedError("Source exceeds the file bound or is not a regular file")
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        if len(data) > maximum or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise FeedError("Source changed during the read")
        return data, after

    def _frame(self):
        for name in ("frame.png", "frame.jpg", "frame.jpeg"):
            if (self.root / name).exists() or (self.root / name).is_symlink():
                data, info = self._read(name, MAX_FRAME)
                mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if data.startswith(b"\xff\xd8") else None
                if not mime:
                    raise FeedError("Frame is not a PNG or JPEG")
                return data, info, mime
        raise FeedError("Frame unavailable")

    @staticmethod
    def _records(value, maximum):
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise FeedError("Record arrays must contain objects")
        json.dumps(value, allow_nan=False)
        return value[-maximum:]

    def _empty(self, status, error=None):
        return {"ok":False, "configured":bool(self.root), "status":status, "mode":"unconfigured",
                "registry":[], "detections":[], "decisions":[], "registry_updated":None,
                "decisions_updated":None, "frame_updated":None, "frame_synthetic":None,
                "frameUrl":None, "stale":False, "error":error,
                "provenance":{"source":"team_run_files", "parser":"canonical_dashboard", "frameOrigin":"unknown"}}

    def state(self):
        with self.lock:
            if not self.root:
                return 200, self._empty("unconfigured", "TEAM_RUN_DIR is not configured; no sample data substituted")
            if not self.readers:
                return 503, self._empty("unconfigured", "Canonical dashboard readers are unavailable")
            try:
                registry_data, registry_info = self._read("registry.json", MAX_TEXT)
                decisions_data, decisions_info = self._read("decisions.jsonl", MAX_TEXT)
                frame_warning = None
                try:
                    _, frame_info, _ = self._frame()
                except (OSError, ValueError):
                    frame_info = None
                    frame_warning = "Frame unavailable, malformed, or outside bounds; registry and decisions remain readable"
                registry, detections = self.readers[0](_SnapshotPath(registry_data))
                decisions = self.readers[1](_SnapshotPath(decisions_data))
                counts = {"registry":len(registry), "detections":len(detections), "decisions":len(decisions)}
                registry = self._records(registry, 1000)
                detections = self._records(detections, 256)
                decisions = self._records(decisions, 200)
                synthetic = None
                if (self.root / "source.json").exists() or (self.root / "source.json").is_symlink():
                    metadata = json.loads(self._read("source.json", 8192)[0])
                    if not isinstance(metadata, dict) or not isinstance(metadata.get("frameSynthetic"), bool):
                        raise FeedError("Source metadata must explicitly declare frameSynthetic")
                    synthetic = metadata["frameSynthetic"]
                updated = min(registry_info.st_mtime, decisions_info.st_mtime, *([frame_info.st_mtime] if frame_info else []))
                stale = time.time()-updated > 30
                payload = {"ok":True, "configured":True, "status":"stale" if stale else "ready",
                    "mode":"synthetic file source" if synthetic is True else "file source",
                    "registry":registry, "detections":detections, "decisions":decisions,
                    "registry_updated":registry_info.st_mtime, "decisions_updated":decisions_info.st_mtime,
                    "frame_updated":frame_info.st_mtime if frame_info else None, "frame_synthetic":synthetic,
                    "frameUrl":f"/api/lab/team-frame?v={frame_info.st_mtime_ns}" if frame_info else None, "stale":stale,
                    "frameWarning":frame_warning,
                    "sourceAgeSeconds":round(max(0,time.time()-updated),3), "totalRecords":counts,
                    "provenance":{"source":"team_run_files", "parser":"canonical_dashboard",
                        "frameOrigin":"synthetic" if synthetic is True else "camera" if synthetic is False else "unknown",
                        "frameOriginVerified":False, "controlAuthority":False}}
                if len(json.dumps(payload, allow_nan=False, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_STATE-512:
                    raise FeedError("Team state exceeds the response bound")
                self.last_good = payload
                return 200, payload
            except (OSError, ValueError, TypeError, RecursionError, OverflowError):
                payload = dict(self.last_good) if self.last_good else self._empty("error")
                payload.update(ok=False, status="error", stale=True, error="Team run files are missing, malformed, changing, or outside configured bounds; last good view retained")
                return 503, payload

    def frame(self):
        if not self.root or not self.readers:
            raise FeedError("Team frame source is unconfigured")
        try:
            data, _, mime = self._frame()
            return data, mime
        except (OSError, ValueError):
            raise FeedError("Team frame unavailable or invalid") from None
