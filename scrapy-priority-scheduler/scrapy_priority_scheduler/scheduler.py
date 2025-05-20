import logging
from collections import defaultdict
from scrapy.core.scheduler import Scheduler
from scrapy.http import Request
from scrapy.utils.misc import load_object
from twisted.internet.defer import Deferred
from .utils import get_callback_name

logger = logging.getLogger(__name__)

class PriorityScheduler(Scheduler):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.crawler = crawler
        self.branch_requests = defaultdict(list)  # Per-domain branch request queue
        self.leaf_requests = defaultdict(list)   # Per-domain leaf request queue
        self.multiplier = crawler.settings.getfloat("PRIORITY_SCHEDULER_MULTIPLIER", 2.0)
        self.concurrent_requests_per_domain = crawler.settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN", 8)
        self.concurrent_requests = crawler.settings.getint("CONCURRENT_REQUESTS", 16)
        self.active_domains = defaultdict(int)  # Track active requests per domain

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open(self, spider):
        super().open(spider)
        self.spider = spider
        logger.info(f"PriorityScheduler opened for spider: {spider.name}")

    def enqueue_request(self, request):
        domain = self._get_domain(request)
        priority_type = request.meta.get("priority_type")

        if priority_type not in ("branch", "leaf"):
            logger.warning(
                f"Request to {request.url} from callback {get_callback_name(request)} "
                "has no priority_type set in Request.meta. Defaulting to 'leaf'."
            )
            priority_type = "leaf"

        queue = self.branch_requests[domain] if priority_type == "branch" else self.leaf_requests[domain]
        queue.append(request)
        self.active_domains[domain] += 1
        return True

    def next_request(self):
        for domain in self.active_domains:
            if not self._can_schedule_more(domain):
                continue

            # Prioritize branch requests if below threshold
            branch_threshold = self.concurrent_requests_per_domain * self.multiplier
            active_branch_count = sum(1 for req in self.crawler.engine.downloader.active
                                     if req.meta.get("priority_type") == "branch" and self._get_domain(req) == domain)

            if active_branch_count < branch_threshold and self.branch_requests[domain]:
                request = self.branch_requests[domain].pop(0)
                self.active_domains[domain] -= 1
                return request
            elif self.leaf_requests[domain]:
                request = self.leaf_requests[domain].pop(0)
                self.active_domains[domain] -= 1
                return request

        return None

    def _can_schedule_more(self, domain):
        active_count = sum(1 for req in self.crawler.engine.downloader.active
                           if self._get_domain(req) == domain)
        return (active_count < self.concurrent_requests_per_domain and
                len(self.crawler.engine.downloader.active) < self.concurrent_requests)

    def _get_domain(self, request):
        return getattr(self.spider, "name", None) or request.url.split("/")[2]

    def has_pending_requests(self):
        return any(self.branch_requests.values()) or any(self.leaf_requests.values())

    def close(self, reason):
        super().close(reason)
        self.branch_requests.clear()
        self.leaf_requests.clear()
        self.active_domains.clear()
        logger.info(f"PriorityScheduler closed: {reason}")
