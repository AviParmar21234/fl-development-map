from scraper import http


def test_throttle_sleeps_within_delay():
    slept = []
    http._last_request.clear()
    http._throttle("example.com", now=lambda: 100.0, sleep=slept.append)
    assert slept == []  # first hit, no sleep
    http._throttle("example.com", now=lambda: 100.1, sleep=slept.append)
    assert len(slept) == 1 and abs(slept[0] - 0.4) < 1e-6


def test_throttle_no_sleep_after_delay():
    slept = []
    http._last_request.clear()
    http._throttle("example.com", now=lambda: 100.0, sleep=slept.append)
    http._throttle("example.com", now=lambda: 101.0, sleep=slept.append)
    assert slept == []
