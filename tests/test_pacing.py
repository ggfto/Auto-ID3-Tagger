import pytest

from autotag.pacing import Pacer


class FakeTime:
    def __init__(self):
        self.now = 100.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)


@pytest.fixture
def time_source():
    return FakeTime()


@pytest.fixture
def pacer(time_source):
    return Pacer(start_interval=5, min_interval=4, max_interval=60, cooldown=30,
                 clock=time_source.clock, sleep=time_source.sleep)


def test_requests_get_consecutive_slots(pacer, time_source):
    pacer.wait()
    pacer.wait()
    pacer.wait()
    assert time_source.slept == [5, 10]


def test_refusal_holds_all_requests_and_widens_the_interval(pacer, time_source):
    pacer.limited()
    assert pacer.interval == 6.25
    pacer.wait()
    assert time_source.slept == [30]


def test_refusals_during_a_cooldown_count_once(pacer, time_source):
    pacer.limited()
    pacer.limited()
    pacer.limited()
    assert pacer.interval == 6.25
    time_source.now += 31
    pacer.limited()
    assert pacer.interval == 7.8125


def test_interval_never_exceeds_the_maximum(pacer, time_source):
    for _ in range(20):
        pacer.limited()
        time_source.now += 31
    assert pacer.interval == 60


def test_success_shrinks_the_interval_down_to_the_minimum(pacer):
    for _ in range(50):
        pacer.succeeded()
    assert pacer.interval == 4
