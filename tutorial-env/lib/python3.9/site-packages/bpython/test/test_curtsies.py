import unittest

from collections import namedtuple
from bpython.curtsies import combined_events
from bpython.test import FixLanguageTestCase as TestCase

import curtsies.events


ScheduledEvent = namedtuple("ScheduledEvent", ["when", "event"])


class EventGenerator:
    def __init__(self, initial_events=(), scheduled_events=()):
        self._events = []
        self._current_tick = 0
        for e in initial_events:
            self.schedule_event(e, 0)
        for e, w in scheduled_events:
            self.schedule_event(e, w)

    def schedule_event(self, event, when):
        self._events.append(ScheduledEvent(when, event))
        self._events.sort()

    def send(self, timeout=None):
        if timeout not in [None, 0]:
            raise ValueError("timeout value %r not supported" % timeout)
        if not self._events:
            return None
        if self._events[0].when <= self._current_tick:
            return self._events.pop(0).event

        if timeout == 0:
            return None
        elif timeout is None:
            e = self._events.pop(0)
            self._current_tick = e.when
            return e.event
        else:
            raise ValueError("timeout value %r not supported" % timeout)

    def tick(self, dt=1):
        self._current_tick += dt
        return self._current_tick


class TestCurtsiesPasteDetection(TestCase):
    def test_paste_threshold(self):
        eg = EventGenerator(list("abc"))
        cb = combined_events(eg, paste_threshold=3)
        e = next(cb)
        self.assertIsInstance(e, curtsies.events.PasteEvent)
        self.assertEqual(e.events, list("abc"))
        self.assertEqual(next(cb), None)

        eg = EventGenerator(list("abc"))
        cb = combined_events(eg, paste_threshold=4)
        self.assertEqual(next(cb), "a")
        self.assertEqual(next(cb), "b")
        self.assertEqual(next(cb), "c")
        self.assertEqual(next(cb), None)

    def test_set_timeout(self):
        eg = EventGenerator("a", zip("bcdefg", [1, 2, 3, 3, 3, 4]))
        eg.schedule_event(curtsies.events.SigIntEvent(), 5)
        eg.schedule_event("h", 6)
        cb = combined_events(eg, paste_threshold=3)
        self.assertEqual(next(cb), "a")
        self.assertEqual(cb.send(0), None)
        self.assertEqual(next(cb), "b")
        self.assertEqual(cb.send(0), None)
        eg.tick()
        self.assertEqual(cb.send(0), "c")
        self.assertEqual(cb.send(0), None)
        eg.tick()
        self.assertIsInstance(cb.send(0), curtsies.events.PasteEvent)
        self.assertEqual(cb.send(0), None)
        self.assertEqual(cb.send(None), "g")
        self.assertEqual(cb.send(0), None)
        eg.tick(1)
        self.assertIsInstance(cb.send(0), curtsies.events.SigIntEvent)
        self.assertEqual(cb.send(0), None)
        self.assertEqual(cb.send(None), "h")
        self.assertEqual(cb.send(None), None)


if __name__ == "__main__":
    unittest.main()
