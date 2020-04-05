import logging

from scrapy.exceptions import NotConfigured
from scrapy import signals
from enum import Enum
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)


class AutoThrottle:

    def __init__(self, crawler):
        self.crawler = crawler
        if not crawler.settings.getbool('AUTOTHROTTLE_ENABLED'):
            raise NotConfigured

        self.debug = crawler.settings.getbool("AUTOTHROTTLE_DEBUG")
        self.target_concurrency = crawler.settings.getfloat("AUTOTHROTTLE_TARGET_CONCURRENCY")
        self.enable_429 = crawler.settings.getbool("AUTOTHROTTLE_HANDLE_API_RATE_LIMIT")
        self.rate_limit_handler = None
        self.rate_limit_status = crawler.settings.getint("AUTOTHROTTLE_RATE_LIMIT_STATUS")
        if self.enable_429:
            self.rate_limit_handler = AutoThrottle429Handler(
                self.target_concurrency)
        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(self._response_downloaded, signal=signals.response_downloaded)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _spider_opened(self, spider):
        self.mindelay = self._min_delay(spider)
        self.maxdelay = self._max_delay(spider)
        spider.download_delay = self._start_delay(spider)

    def _min_delay(self, spider):
        s = self.crawler.settings
        return getattr(spider, 'download_delay', s.getfloat('DOWNLOAD_DELAY'))

    def _max_delay(self, spider):
        return self.crawler.settings.getfloat('AUTOTHROTTLE_MAX_DELAY')

    def _start_delay(self, spider):
        return max(self.mindelay, self.crawler.settings.getfloat('AUTOTHROTTLE_START_DELAY'))

    def _response_downloaded(self, response, request, spider):
        key, slot = self._get_slot(request, spider)
        latency = request.meta.get('download_latency')
        sent_at = request.meta.get('sent_at')
        if self.enable_429:
            self.rate_limit_handler.add_to_history(response, sent_at)
        if latency is None or slot is None:
            return

        olddelay = slot.delay
        self._adjust_delay(slot, sent_at, latency, response)
        if self.debug:
            diff = slot.delay - olddelay
            size = len(response.body)
            conc = len(slot.transferring)
            logger.info(
                "slot: %(slot)s | conc:%(concurrency)2d | "
                "delay:%(delay)5d ms (%(delaydiff)+d) | "
                "latency:%(latency)5d ms | size:%(size)6d bytes",
                {
                    'slot': key, 'concurrency': conc,
                    'delay': slot.delay * 1000, 'delaydiff': diff * 1000,
                    'latency': latency * 1000, 'size': size
                },
                extra={'spider': spider}
            )

    def _get_slot(self, request, spider):
        key = request.meta.get('download_slot')
        return key, self.crawler.engine.downloader.slots.get(key)

    def _adjust_delay(self, slot, sent_at, latency, response):
        """Define delay adjustment policy"""

        # If a server needs `latency` seconds to respond then
        # we should send a request each `latency/N` seconds
        # to have N requests processed in parallel
        target_delay = latency / self.target_concurrency

        # Adjust the delay to make it closer to target_delay
        new_delay = (slot.delay + target_delay) / 2.0

        # If target delay is bigger than old delay, then use it instead of mean.
        # It works better with problematic sites.
        new_delay = max(target_delay, new_delay)

        if response.status == self.rate_limit_status:
            self.rate_limit_handler.increase_min_delay(response, sent_at)
        new_delay = max(new_delay, self.rate_limit_handler.get_min_delay(response))

        # Make sure self.mindelay <= new_delay <= self.max_delay
        new_delay = min(max(self.mindelay, new_delay), self.maxdelay)

        if response.status == self.rate_limit_status:
            # set a special delay on the slot to make it wait until the end of the current time interval
            # before continuing requests.
            slot.rate_limit_special_delay = self.rate_limit_handler.pop_special_delay(response)

        # Dont adjust delay if response status != 200 and new delay is smaller
        # than old one, as error pages (and redirections) are usually small and
        # so tend to reduce latency, thus provoking a positive feedback by
        # reducing delay instead of increase.
        if response.status != 200 and new_delay <= slot.delay:
            return

        slot.delay = new_delay


class TimeInterval(Enum):
    SECOND = "%Y/%m/%d %H:%M:%S", 1, 1000000
    MINUTE = "%Y/%m/%d %H:%M", 60, 60
    HOUR = "%Y/%m/%d %H", 3600, 60
    DAY = "%Y/%m/%d", 86400, 24

    @staticmethod
    def get_index(interval):
        return list(TimeInterval).index(interval)


class TimeIntervalManager:

    def __init__(self):
        self.time_interval_next_map = {TimeInterval.SECOND: TimeInterval.MINUTE, TimeInterval.MINUTE: TimeInterval.HOUR,
                                       TimeInterval.HOUR: TimeInterval.DAY}
        self.time_interval_attr = {TimeInterval.SECOND: 'microsecond', TimeInterval.MINUTE: 'second',
                                   TimeInterval.HOUR: 'minute', TimeInterval.DAY: 'hour'}

    def get_next_interval(self, degree: TimeInterval):
        return self.time_interval_next_map.get(degree, TimeInterval.DAY)

    def get_time_part(self, time_stamp: datetime, degree: TimeInterval):
        return time_stamp.__getattribute__(self.time_interval_attr[degree])

    def get_seconds_until_end(self, time_stamp: datetime, interval: TimeInterval) -> int:
        # if interval is seconds, return 1.
        # if interval is minutes, return:  get_seconds(1 minute) - current second
        # if interval is hour, return:  get_seconds(1 hour) - (get_seconds(1 minute) * (60 minutes - current_minutes)
        #                           + (60 seconds - current second))
        # if interval is day, return:  get_seconds(1 day) - (get_seconds(1 hour) * (24 hours - current hour) +
        #                          (get_seconds(1 min) * (60 minutes - current_minutes) + (60 seconds - current second))
        spent_time = 0
        if interval == TimeInterval.SECOND:
            return self.get_seconds(interval) - spent_time
        spent_time += time_stamp.second
        if interval == TimeInterval.MINUTE:
            return self.get_seconds(interval) - spent_time
        spent_time += time_stamp.minute * self.get_seconds(TimeInterval.MINUTE)
        if interval == TimeInterval.HOUR:
            return self.get_seconds(interval) - spent_time
        spent_time += time_stamp.hour * self.get_seconds(TimeInterval.HOUR)
        return self.get_seconds(interval) - spent_time

    @staticmethod
    def get_timestamp_key(t: datetime, degree: TimeInterval):
        return t.strftime(degree.value[0])

    @staticmethod
    def get_delta(degree: TimeInterval):
        return timedelta(seconds=TimeIntervalManager.get_seconds(degree))

    @staticmethod
    def get_parts(degree: TimeInterval):
        return degree.value[2]

    @staticmethod
    def get_seconds(degree: TimeInterval):
        return degree.value[1]


class SlidingWindow:

    """
    This structure implements keeps track of the number of requests over the previous and current time intervals.
    """

    def __init__(self, interval: TimeInterval, current: datetime, current_count=1, previous_count=0):
        self.interval = interval
        self.current = current
        self.current_count = current_count
        self.previous_count = previous_count
        self._tim = TimeIntervalManager()

    def add_request(self, sent_at: datetime):
        label = self.get_key(sent_at)
        if label != self.get_key(self.current):
            # slide window
            # case 1. next window. case 2, previous window was blank. (no requests in the last interval).
            if self.is_next_window(label):
                self.reset_window(sent_at, self.current_count)
            else:
                self.reset_window(sent_at, 0)
        else:
            self.current_count += 1

    def reset_window(self, new_current, new_previous_count, set_blank=False):
        self.current = new_current
        self.current_count = 0 if set_blank else 1
        self.previous_count = new_previous_count

    def is_next_window(self, label: str):
        return self.get_key(self.current + self._tim.get_delta(self.interval)) == label

    def get_key(self, _datetime):
        return self._tim.get_timestamp_key(_datetime, self.interval)

    def __repr__(self):
        return "SlidingWindow: {}\n Current Window: {}\n Current Count{}\n Previous Count{}" \
            .format(self.interval, self._tim.get_timestamp_key(self.current, self.interval),
                    self.current_count,
                    self.previous_count)


class AutoThrottle429Handler:

    def __init__(self, target_concurrency):
        self.__initial_failover_lives__ = max(3, target_concurrency + 2)  # Allows for simultaneous requests to fail
        self._tim = TimeIntervalManager()
        self.delay_intervals = {}
        self.delay = {}
        self.failover_lives = {}  # for each domain, keep track of the number of times the current time slot has failed.
        self.rate_limit_reset_delay = {}
        self.request_history = {}

    def increase_min_delay(self, response, sent_at):
        domain = self._get_domain(response)
        time_slot = self.get_delay_interval(domain)

        if self.failover_lives.get(domain, self.__initial_failover_lives__) <= 0:
            # when failover lives reaches 0, increase the time interval from eg: n req per second -> x req per minute.
            time_slot = self._increase_time_slot(domain, time_slot)
        self.delay[domain] = self._compute_delay(sent_at, time_slot, self.request_history[domain])

        # Then, because any more requests this time slot are likely to still be blocked...
        self._set_special_delay(domain, sent_at, time_slot)
        # reduce failover lives
        self.failover_lives[domain] = self.failover_lives.get(domain, self.__initial_failover_lives__) - 1
        logger.log(logging.INFO, "Decreasing request rate due to rate limit.\n"
                   + "New rate: {}, {}".format(self.delay.get(domain), time_slot.name))

    def get_min_delay(self, response):
        return self.delay.get(self._get_domain(response), 0)

    def _compute_delay(self, sent_at, time_slot, history: List[SlidingWindow]) -> float:
        window = history[TimeInterval.get_index(time_slot)]
        # 1. estimate the request rate -1.
        # the sliding window formula makes an estimation assuming constant rate of requests in previous time slot
        # for example 20 requests were made in the previous minute, 7 requests made in the current minute
        # and we are 20 seconds into the current minute.
        # so the estimation will be 20 * ((60 - 20) / 60)  = 20  * 2/3 = 13.2
        # to this we add the number of requests made in the current minute.
        # 13.2 + 7 => 20.2 requests per minute.
        # We subtract 1 because the last request threw a rate limit error and we want to be below that rate.
        wanted_rate = (window.previous_count
                       * ((self._tim.get_parts(time_slot)
                           - self._tim.get_time_part(sent_at, time_slot))
                          / self._tim.get_parts(time_slot))) \
            + window.current_count - 1

        # 2. calculate delay required to achieve that rate.
        return self._tim.get_seconds(time_slot) / wanted_rate

    def _increase_time_slot(self, domain, current_time_slot) -> TimeInterval:
        # get the next logical time slot
        new_time_slot = self._tim.get_next_interval(current_time_slot)
        self.delay_intervals[domain] = new_time_slot
        # reset failover lives.
        self.failover_lives[domain] = self.__initial_failover_lives__
        return new_time_slot

    def add_to_history(self, response, sent_at):
        domain = self._get_domain(response)

        if response.status == 200:  # only keep track of good requests because this works better.
            if domain not in self.request_history.keys():
                self.request_history[domain] = [SlidingWindow(interval, sent_at)
                                                for interval in list(TimeInterval)]
            else:
                for struct in self.request_history[domain]:
                    struct.add_request(sent_at)

        return self.request_history[domain]

    def _set_special_delay(self, domain, sent_at: datetime, time_slot: TimeInterval):
        self.rate_limit_reset_delay[domain] = self._tim\
            . get_seconds_until_end(sent_at, time_slot)

    def pop_special_delay(self, response):
        return self.rate_limit_reset_delay.pop(self._get_domain(response), 0)

    def get_delay_interval(self, domain):
        return self.delay_intervals.get(domain, TimeInterval.SECOND)

    @staticmethod
    def _get_domain(response):
        # is 1 api = 1 domain a fair assumption? Seems iffy. TODO:
        return '/'.join(response.url.split('/')[:3])
