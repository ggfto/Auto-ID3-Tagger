"""Runs the library through a pool of threads, with failed files retried later."""
import heapq
import itertools
import os
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass

from . import audiofile, backup, report, tagging
from .identify import RateLimited

MAX_ATTEMPTS = 5
MAX_CONSECUTIVE_ERRORS = 10
# The pacer waits at least a minute per refusal at its slowest, so this is about an hour.
MAX_CONSECUTIVE_LIMITS = 60
RETRY_BASE_SECONDS = 15


@dataclass
class Task:
    path: str
    attempt: int = 0
    was_cloud_only: bool | None = None


def retry_delay(attempt):
    """Seconds before the next try: about 15, 30, 60 and 120, spread out so files do not retry together."""
    return RETRY_BASE_SECONDS * 2 ** (attempt - 1) + random.uniform(0, 5)


def iter_files(folder, done):
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            if audiofile.is_audio_file(name) and report.path_key(path) not in done:
                yield path


def attempt_file(task, acoustid_key, state_dir):
    """One try at a file. Runs in a worker thread."""
    if task.was_cloud_only is None:
        task.was_cloud_only = audiofile.is_cloud_only(task.path)
    return tagging.process_file(task.path, acoustid_key, state_dir)


def _release(task):
    """The file stays local between tries, so a retry does not download it again."""
    if task.was_cloud_only:
        audiofile.free_local_copy(task.path)


def _next_task(waiting, files, now):
    if waiting and waiting[0][0] <= now:
        return heapq.heappop(waiting)[2]
    path = next(files, None)
    return Task(path) if path else None


def run(folder, acoustid_key, state_dir, workers):
    done = {key for key, row in report.load(state_dir).items() if row["status"] not in report.RETRY_STATUSES}
    files = iter_files(folder, done)
    log = report.Report(state_dir)
    counts = {}
    waiting = []  # (ready time, tie breaker, task): failed files waiting for their next try
    order = itertools.count()
    running = {}
    consecutive_errors = 0
    consecutive_limits = 0
    stopping = False

    print(f"Scanning recursively: {folder} ({workers} threads)")
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while True:
            while not stopping and len(running) < workers:
                task = _next_task(waiting, files, time.monotonic())
                if not task:
                    break
                running[pool.submit(attempt_file, task, acoustid_key, state_dir)] = task

            if not running:
                if stopping or not waiting:
                    break
                time.sleep(max(0.0, waiting[0][0] - time.monotonic()))
                continue

            timeout = None
            if waiting and not stopping:
                timeout = max(0.0, waiting[0][0] - time.monotonic())
            finished, _ = wait(running, timeout=timeout, return_when=FIRST_COMPLETED)

            for future in finished:
                task = running.pop(future)
                try:
                    row = future.result()
                except RateLimited as e:
                    # Says nothing about the file, so it does not use up an attempt.
                    consecutive_limits += 1
                    print(f"Rate limited by {e}, slowing down: {task.path}")
                    heapq.heappush(waiting, (time.monotonic(), next(order), task))
                    if consecutive_limits >= MAX_CONSECUTIVE_LIMITS and not stopping:
                        stopping = True
                        print("Stopping: the service keeps refusing requests. "
                              "Run the same command later to continue.")
                    continue
                except Exception as e:
                    task.attempt += 1
                    # ValueError means the file itself is the problem, so trying again cannot help.
                    if not isinstance(e, ValueError) and task.attempt < MAX_ATTEMPTS:
                        delay = retry_delay(task.attempt)
                        print(f"Will retry in {delay:.0f}s (attempt {task.attempt}): {task.path}: {e!r}")
                        heapq.heappush(waiting, (time.monotonic() + delay, next(order), task))
                        continue
                    row = {"path": task.path, "status": "error", "detail": repr(e)}

                consecutive_limits = 0
                log.add(row)
                _release(task)
                counts[row["status"]] = counts.get(row["status"], 0) + 1
                print(f"{row['status']}: {task.path} -> {row.get('new_artist')} - {row.get('new_title')}")

                consecutive_errors = consecutive_errors + 1 if row["status"] == "error" else 0
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS and not stopping:
                    stopping = True
                    print(f"Stopping after {MAX_CONSECUTIVE_ERRORS} errors in a row. "
                          "Run the same command later to continue.")
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for task in [entry[2] for entry in waiting] + list(running.values()):
            _release(task)
        log.close()
        print(f"Summary: {counts}")
        print(f"Report: {report.report_path(state_dir)}")
    return counts


def restore(folder, state_dir):
    """Puts back the original tags of the files changed under folder."""
    rows = report.load(state_dir)
    log = report.Report(state_dir)
    restored = 0
    try:
        for row in rows.values():
            if row["status"] not in report.CHANGED_STATUSES or not report.is_under(row["path"], folder):
                continue
            try:
                was_cloud_only = audiofile.is_cloud_only(row["path"])
                backup.restore_tag(row["path"], state_dir)
                if was_cloud_only:
                    audiofile.free_local_copy(row["path"])
                log.add({"path": row["path"], "status": "restored"})
                restored += 1
            except Exception as e:
                print(f"Could not restore {row['path']}: {e}")
    finally:
        log.close()
    print(f"Restored {restored} file(s)")
    return restored
