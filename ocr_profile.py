"""Where the time of one document reading goes, stage by stage (Stage 36.8).

Issue #62 asked why reading a two-page scan took ~40 s in the program when
the OCR engine itself needed ~12 s. A :class:`Profile` records, for one
reading, the twelve stages of that question, with wall time, the reading
thread's CPU time and the number of calls:

 1. source_open              the bytes, their SHA-256, a saved review
 2. pdf_loading              page count, text layer, image coverage
 3. page_rendering           PDF page → pixels → PNG for the engine
 4. image_preprocessing      table rules whitened (``ocr_rules``)
 5. ocr_initialization       engine resolved, image written, process started
 6. ocr_execution            the Tesseract process, start to exit
 7. tsv_parsing              Tesseract TSV → words with boxes
 8. table_reconstruction     answer grids, table rows, matrices
 9. question_reconstruction  numbered items from the lines
10. confidence_assessment    the OCR confidence warning
11. review_model             evidence links, scales, the review the page shows
12. ui_update                Flet renders on the event loop (Python side)

plus, per Tesseract process, its wall time, CPU time and peak memory where
the platform reports them; for the program, its peak memory, I/O bytes and
thread count; and the longest stall of the interface's event loop while the
reading ran (how long the window could not react).

A profile is collected for every reading; it costs a few clock reads. With
``SRA_OCR_PROFILE`` set to a folder, each one is also written there as JSON
(the GUI journeys collect them). Stages run in worker threads: the active
profile travels in a :class:`contextvars.ContextVar`, which
``asyncio.to_thread`` copies into the worker.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import sys
import threading
import time
from pathlib import Path

STAGES = (
    "source_open", "pdf_loading", "page_rendering", "image_preprocessing",
    "ocr_initialization", "ocr_execution", "tsv_parsing", "table_reconstruction",
    "question_reconstruction", "confidence_assessment", "review_model", "ui_update",
)
ENVIRONMENT = "SRA_OCR_PROFILE"

_active: contextvars.ContextVar["Profile | None"] = contextvars.ContextVar(
    "sra_ocr_profile", default=None)


class Profile:
    def __init__(self, label: str = "") -> None:
        self.label = label
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.io_started = process_io()
        self.stages = {name: {"seconds": 0.0, "cpu_seconds": 0.0, "calls": 0} for name in STAGES}
        self.engine_runs: list[dict] = []
        self.events: list[tuple[float, str]] = []
        self.loop_stall_seconds = 0.0
        self.renders = 0
        self.max_threads = threading.active_count()
        self.facts: dict = {}
        self._lock = threading.Lock()

    def add(self, name: str, seconds: float, cpu_seconds: float = 0.0) -> None:
        with self._lock:
            entry = self.stages[name]
            entry["seconds"] += seconds
            entry["cpu_seconds"] += cpu_seconds
            entry["calls"] += 1
            self.max_threads = max(self.max_threads, threading.active_count())

    @contextlib.contextmanager
    def stage(self, name: str):
        wall, cpu = time.perf_counter(), time.thread_time()
        try:
            yield
        finally:
            self.add(name, time.perf_counter() - wall, time.thread_time() - cpu)

    def mark(self, text: str) -> None:
        with self._lock:
            self.events.append((round(time.perf_counter() - self.started, 3), text))

    def engine_run(self, **values) -> None:
        with self._lock:
            self.engine_runs.append(values)

    def result(self) -> dict:
        io_now = process_io()
        total = time.perf_counter() - self.started
        stages = {name: {"seconds": round(v["seconds"], 3), "cpu_seconds": round(v["cpu_seconds"], 3),
                         "calls": v["calls"]} for name, v in self.stages.items()}
        accounted = sum(v["seconds"] for v in self.stages.values())
        return {
            "label": self.label, "total_seconds": round(total, 3),
            "stages": stages,
            # Waiting for the worker, scheduling and anything not wrapped in a stage.
            "unaccounted_seconds": round(max(0.0, total - accounted), 3),
            "process_cpu_seconds": round(time.process_time() - self.cpu_started, 3),
            "peak_memory_bytes": peak_memory(),
            "io_bytes": ({k: io_now[k] - self.io_started.get(k, 0) for k in io_now}
                         if io_now else None),
            "max_threads": self.max_threads,
            "engine_runs": list(self.engine_runs),
            "event_loop_max_stall_seconds": round(self.loop_stall_seconds, 3),
            "renders": self.renders,
            "events": list(self.events),
            "facts": dict(self.facts),
            "platform": sys.platform,
        }

    def write(self) -> Path | None:
        """Write the result to ``$SRA_OCR_PROFILE`` (a folder), if set."""
        folder = os.environ.get(ENVIRONMENT)
        if not folder:
            return None
        try:
            target = Path(folder)
            target.mkdir(parents=True, exist_ok=True)
            index = len(list(target.glob("ocr-profile-*.json"))) + 1
            path = target / f"ocr-profile-{index:02d}.json"
            path.write_text(json.dumps(self.result(), indent=1), encoding="utf-8")
            return path
        except OSError:
            return None


def current() -> Profile | None:
    return _active.get()


@contextlib.contextmanager
def activate(profile: Profile | None):
    token = _active.set(profile)
    try:
        yield profile
    finally:
        _active.reset(token)


def stage(name: str):
    """``with stage("page_rendering"):`` in the active profile, else nothing."""
    profile = _active.get()
    return profile.stage(name) if profile is not None else contextlib.nullcontext()


def mark(text: str) -> None:
    profile = _active.get()
    if profile is not None:
        profile.mark(text)


async def watch_event_loop(profile: Profile, stop: "asyncio.Event", interval: float = 0.05):
    """Record the longest time the event loop could not run a 50 ms timer:
    while it is stalled, the window's clicks and keys wait."""
    import asyncio

    loop = asyncio.get_running_loop()
    while not stop.is_set():
        before = loop.time()
        await asyncio.sleep(interval)
        profile.loop_stall_seconds = max(profile.loop_stall_seconds,
                                         loop.time() - before - interval)


# --- process measurements (best effort; None where the platform has none) ---

def peak_memory() -> int | None:
    """Peak working set (Windows) or maximum resident size (POSIX), bytes."""
    try:
        if os.name == "nt":
            counters = _windows_memory(_current_process())
            return int(counters.PeakWorkingSetSize) if counters else None
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)
    except Exception:
        return None


def process_io() -> dict:
    """Bytes read and written by this process so far."""
    try:
        if os.name == "nt":
            return _windows_io(_current_process()) or {}
        with open("/proc/self/io", encoding="ascii") as handle:
            fields = dict(line.split(": ") for line in handle.read().splitlines())
        return {"read_bytes": int(fields["read_bytes"]), "write_bytes": int(fields["write_bytes"])}
    except Exception:
        return {}


def child_usage(process) -> dict:
    """CPU seconds, peak memory and I/O of a finished ``subprocess.Popen``
    (Windows: from its process handle; POSIX: not available per child)."""
    if os.name != "nt":
        return {}
    handle = getattr(process, "_handle", None)
    if handle is None:
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        creation, exit_, kernel, user = (wintypes.FILETIME() for _ in range(4))
        ok = ctypes.windll.kernel32.GetProcessTimes(
            wintypes.HANDLE(int(handle)), ctypes.byref(creation), ctypes.byref(exit_),
            ctypes.byref(kernel), ctypes.byref(user))
        usage = {}
        if ok:
            def seconds(value):
                return ((value.dwHighDateTime << 32) + value.dwLowDateTime) / 1e7
            usage["cpu_seconds"] = round(seconds(kernel) + seconds(user), 3)
        counters = _windows_memory(int(handle))
        if counters:
            usage["peak_memory_bytes"] = int(counters.PeakWorkingSetSize)
        io = _windows_io(int(handle))
        if io:
            usage["io_bytes"] = io
        return usage
    except Exception:
        return {}


def _current_process():
    import ctypes

    return ctypes.windll.kernel32.GetCurrentProcess()


def _windows_memory(handle):
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    psapi = ctypes.WinDLL("psapi")
    if psapi.GetProcessMemoryInfo(wintypes.HANDLE(handle), ctypes.byref(counters), counters.cb):
        return counters
    return None


def _windows_io(handle) -> dict | None:
    import ctypes
    from ctypes import wintypes

    class Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    io = Io()
    if ctypes.windll.kernel32.GetProcessIoCounters(wintypes.HANDLE(handle), ctypes.byref(io)):
        return {"read_bytes": int(io.ReadTransferCount), "write_bytes": int(io.WriteTransferCount)}
    return None
