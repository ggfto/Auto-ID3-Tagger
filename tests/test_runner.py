import threading
import time

import pytest

from autotag import report, runner, tagging
from autotag.identify import RateLimited


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "retry_delay", lambda attempt: 0.2)
    folder = tmp_path / "music"
    folder.mkdir()
    for name in ("a.mp3", "b.mp3", "c.mp3", "d.m4a", "ignored.wav", "._hidden.mp3"):
        (folder / name).write_bytes(b"x")
    return str(folder), str(tmp_path / "state")


def fake_process(behavior):
    def process(path, acoustid_key, state_dir):
        return behavior(path) or {"path": path, "status": "tagged"}
    return process


def statuses(state):
    return {key.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]: row["status"] for key, row in report.load(state).items()}


def test_only_supported_files_are_processed(library, monkeypatch):
    folder, state = library
    monkeypatch.setattr(tagging, "process_file", fake_process(lambda path: None))

    runner.run(folder, None, state, workers=2)

    assert statuses(state) == {name: "tagged" for name in ("a.mp3", "b.mp3", "c.mp3", "d.m4a")}


def test_never_more_threads_than_the_limit(library, monkeypatch):
    folder, state = library
    lock = threading.Lock()
    active = [0]
    peak = [0]

    def behavior(path):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=2)

    assert peak[0] == 2


def test_file_waiting_for_retry_does_not_hold_the_queue(library, monkeypatch):
    folder, state = library
    finished = []
    tries = {}

    def behavior(path):
        name = path[-5:]
        tries[name] = tries.get(name, 0) + 1
        if name == "a.mp3" and tries[name] == 1:
            raise ConnectionError("rate limited")
        finished.append(name)

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=1)  # One thread: a sleeping retry would block everything.

    assert finished == ["b.mp3", "c.mp3", "d.m4a", "a.mp3"]
    assert statuses(state)["a.mp3"] == "tagged"


def test_file_that_keeps_failing_becomes_an_error(library, monkeypatch):
    folder, state = library
    tries = []

    def behavior(path):
        if path.endswith("a.mp3"):
            tries.append(path)
            raise ConnectionError("down")

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=2)

    assert len(tries) == runner.MAX_ATTEMPTS
    assert statuses(state)["a.mp3"] == "error"


def test_rate_limit_does_not_use_up_attempts(library, monkeypatch):
    folder, state = library
    tries = []

    def behavior(path):
        if path.endswith("a.mp3"):
            tries.append(path)
            if len(tries) <= runner.MAX_ATTEMPTS + 2:
                raise RateLimited("Shazam")

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=1)

    assert statuses(state)["a.mp3"] == "tagged"


def test_run_stops_when_the_service_keeps_refusing(library, monkeypatch):
    folder, state = library
    monkeypatch.setattr(runner, "MAX_CONSECUTIVE_LIMITS", 3)

    def refuse(path):
        raise RateLimited("Shazam")

    monkeypatch.setattr(tagging, "process_file", fake_process(refuse))
    runner.run(folder, None, state, workers=1)

    assert report.load(state) == {}


def test_cloud_file_is_released_once_after_its_last_try(library, monkeypatch):
    folder, state = library
    released = []
    tries = {}
    monkeypatch.setattr(runner.audiofile, "is_cloud_only", lambda path: True)
    monkeypatch.setattr(runner.audiofile, "free_local_copy", released.append)

    def behavior(path):
        tries[path] = tries.get(path, 0) + 1
        if path.endswith("a.mp3") and tries[path] == 1:
            raise ConnectionError("down")

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=1)

    assert sorted(path[-5:] for path in released) == ["a.mp3", "b.mp3", "c.mp3", "d.m4a"]


def test_problem_in_the_file_is_not_retried(library, monkeypatch):
    folder, state = library
    tries = []

    def behavior(path):
        if path.endswith("a.mp3"):
            tries.append(path)
            raise ValueError("invalid tag")

    monkeypatch.setattr(tagging, "process_file", fake_process(behavior))
    runner.run(folder, None, state, workers=2)

    assert len(tries) == 1


def test_run_stops_after_many_errors_in_a_row_and_continues_later(library, monkeypatch):
    folder, state = library
    monkeypatch.setattr(runner, "MAX_CONSECUTIVE_ERRORS", 2)
    monkeypatch.setattr(runner, "MAX_ATTEMPTS", 1)

    def fail(path):
        raise ConnectionError("down")

    monkeypatch.setattr(tagging, "process_file", fake_process(fail))
    runner.run(folder, None, state, workers=1)
    assert len(statuses(state)) == 2

    monkeypatch.setattr(tagging, "process_file", fake_process(lambda path: None))
    runner.run(folder, None, state, workers=1)
    assert set(statuses(state).values()) == {"tagged"}
    assert len(statuses(state)) == 4


def test_finished_files_are_skipped_by_the_next_run(library, monkeypatch):
    folder, state = library
    monkeypatch.setattr(tagging, "process_file", fake_process(lambda path: None))
    runner.run(folder, None, state, workers=2)

    def must_not_run(path):
        raise AssertionError("processed again")

    monkeypatch.setattr(tagging, "process_file", fake_process(must_not_run))
    assert runner.run(folder, None, state, workers=2) == {}
