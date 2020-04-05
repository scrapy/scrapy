import unittest
from scrapy.extensions.throttle import TimeIntervalManager,\
    TimeInterval, SlidingWindow, AutoThrottle429Handler
from datetime import datetime, timedelta
from typing import List
from scrapy.http import Response


class TestAutothrottle429(unittest.TestCase):

    def setUp(self) -> None:
        self.handler = AutoThrottle429Handler(1)

    def test_min_delay_calculation(self):
        domain = 'https://test.some-domain.com'
        req_sent_times = TestSlidingWindow._create_reqs(51)
        for sent_at in req_sent_times[:len(req_sent_times) - 1]:
            self.handler.add_to_history(Response(domain),
                                        sent_at)
        bad_res = Response(domain, status=429)
        self.handler.add_to_history(bad_res, req_sent_times[-1])
        self.handler.increase_min_delay(bad_res, req_sent_times[-1])
        assert self.handler.get_min_delay(bad_res) == 1,\
            "{} Estimated min delay is incorrect. Correct is: {}"\
            .format(self.handler.get_min_delay(bad_res), 1)
        self.handler.add_to_history(bad_res, req_sent_times[-1]
                                    + timedelta(seconds=1))
        self.handler.increase_min_delay(bad_res, req_sent_times[-1]
                                        + timedelta(seconds=1))
        self.handler.add_to_history(bad_res, req_sent_times[-1]
                                    + timedelta(seconds=2))
        self.handler.increase_min_delay(bad_res, req_sent_times[-1]
                                        + timedelta(seconds=2))
        self.handler.add_to_history(bad_res, req_sent_times[-1]
                                    + timedelta(seconds=3))
        self.handler.increase_min_delay(bad_res, req_sent_times[-1]
                                        + timedelta(seconds=3))
        assert self.handler.get_delay_interval(domain) == TimeInterval.MINUTE
        min_allowed_delay = 60 / (len(req_sent_times) - 1)
        assert self.handler.get_min_delay(bad_res) >= min_allowed_delay, \
            "{} Estimated min delay is incorrect. Correct is: {}"\
            .format(self.handler.get_min_delay(bad_res),
                    min_allowed_delay)
        assert self.handler.get_min_delay(bad_res) <= min_allowed_delay\
            * 1.1,\
            "{} Forced delay is too long. Should be less than: {}"\
            .format(self.handler.get_min_delay(bad_res),
                    min_allowed_delay * 1.1)


class TestSlidingWindow(unittest.TestCase):

    def test_same_interval_count_second(self):
        reqs = self._create_reqs(5, increment=False)
        window = self._create_history(TimeInterval.SECOND, reqs)
        assert window.current_count == len(reqs)

    def test_same_interval_count_minute_hour_day(self):
        reqs = self._create_reqs(5, second=1)
        self._assert_all_current(TimeInterval.MINUTE, reqs)
        self._assert_all_current(TimeInterval.HOUR, reqs)
        self._assert_all_current(TimeInterval.DAY, reqs)

    def test_next_interval_count_second(self):
        reqs = self._create_reqs(5, second=58)
        window = self._create_history(TimeInterval.SECOND, reqs)
        assert window.current_count == 1
        assert window.previous_count == 1
        window.add_request(reqs[-1] + timedelta(seconds=2))
        assert window.current_count == 1
        assert window.previous_count == 0

    def test_next_interval_count_minute(self):
        reqs = self._create_reqs(5, second=58)
        window = self._create_history(TimeInterval.MINUTE, reqs)
        assert window.current_count == 3
        assert window.previous_count == 2
        window.add_request(reqs[-1] + timedelta(minutes=2))
        assert window.current_count == 1
        assert window.previous_count == 0

    def _assert_all_current(self, interval, reqs):
        window = self._create_history(interval, reqs)
        assert window.current_count == len(reqs), "{} not equal to {}"\
            .format(window.current_count, len(reqs))

    def _create_history(self, interval: TimeInterval, history: List[datetime]):
        window = SlidingWindow(interval, history[0])
        for req in history[1:]:
            window.add_request(req)
        return window

    @staticmethod
    def _create_reqs(length, day=1, hour=10, minute=13,
                     second=5, increment=True) -> List[datetime]:
        return [datetime(year=2020, month=3,
                         day=day, hour=hour, minute=minute,
                         second=second)
                + timedelta(seconds=(i if increment else 0))
                for i in range(length)]


class TestTimeIntervalManager(unittest.TestCase):

    def setUp(self) -> None:
        self._tim = TimeIntervalManager()

    def test_seconds_remaining(self):
        d = datetime(year=2020, month=3, day=5,
                     hour=10, minute=6, second=12)
        assert 1 == self._tim.get_seconds_until_end(d, TimeInterval.SECOND)
        assert 48 == self._tim.get_seconds_until_end(d, TimeInterval.MINUTE)
        assert (53 * 60) + 48 \
            == self._tim.get_seconds_until_end(d, TimeInterval.HOUR)
        assert (13 * 3600) + (53 * 60) + 48 \
            == self._tim.get_seconds_until_end(d, TimeInterval.DAY)
