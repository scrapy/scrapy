"""
The Domain Scheduler keeps track of next domains to scrape. They must implement
the following methods:

* next_domain()
  return next domain to scrape and remove it from pending queue

* add_domain(domain)
  add domain to pending queue

* remove_pending_domain(domain)
  remove (all occurrences) of domain from pending queue, do nothing if not
  pending

* has_pending_domain(domain)
  Return ``True`` if the domain is pending to scrape, ``False`` otherwise

"""

class FifoDomainScheduler(object):
    """Basic domain scheduler based on a FIFO queue"""

    def __init__(self):
        self.pending_domains = []

    def next_domain(self) :
        if self.pending_domains:
            return self.pending_domains.pop(0)

    def add_domain(self, domain):
        self.pending_domains.append(domain)

    def remove_pending_domain(self, domain):
        self.pending_domains = [d for d in self.pending_domains if d != domain]

    def has_pending_domain(self, domain):
        return domain in self.pending_domains
