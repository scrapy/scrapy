from enum import Enum

try:
    from enum_tools.documentation import document_enum
except ImportError:

    def document_enum(func):  # type: ignore[misc]
        return func
else:
    # https://github.com/domdfcoding/enum_tools/issues/29
    import enum_tools.documentation

    enum_tools.documentation.INTERACTIVE = True


@document_enum
class SeedingPolicy(Enum):
    front_load = "front_load"
    """The crawl does not start until all seed requests have been scheduled.

    Aims to give the :ref:`scheduler <topics-scheduler>` full control over
    request order from the start. Some custom schedulers may require this
    seeding policy to work as designed.
    """

    greedy = "greedy"
    """Iterating seeds takes priority over processing scheduled requests.

    Every time a seed request is iterated, it is scheduled, and then the next
    request from the scheduler is sent.

    .. note:: That request sent may not be the scheduled seed request
        depending on the priority of scheduled requests, on the configured
        :setting:`SCHEDULER` and on certain scheduler settings (e.g.
        :setting:`SCHEDULER_MEMORY_QUEUE`).

    Best used when prioritizing seed requests is important.
    """

    idle = "idle"
    """A single seed is read only when there are neither scheduled nor on-going
    requests.

    That is, a new seed is not read until all requests triggered by the
    previous seed, directly or indirectly, have been processed.

    Unlike :py:enum:mem:`lazy`, resource savings are prioritized over crawl
    speed.

    It is functionally equivalent to running a spider multiple times in a row,
    one per seed request.
    """

    lazy = "lazy"
    """Processing scheduled requests takes priority over iterating seeds.

    Aims to minimize the number of requests in the scheduler at any given time,
    to minimize resource usage (memory or disk, depending on
    :setting:`JOBDIR`).

    It is best used when seed request priority is not important.

    Switching to :py:enum:mem:`idle` may lower resource usage further at the
    cost of also lowering crawl speed.
    """
