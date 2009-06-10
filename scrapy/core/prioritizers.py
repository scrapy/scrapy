"""
The Prioritizer is a class which receives a list of elements and prioritizes
it. It's used for defining the order in which domains are to be scraped. 

A Prioritizer basically consists of a class which receives a list of elements
in its constructs and contains only one method: get_priority() which returns
the priority of the given element. The element passed to get_priority() must
exists in the list of elements passed in the constructor.

This module contains several basic prioritizers.

For more advanced prioritizers see: scrapy.contrib.prioritizers
"""
import random

class NullPrioritizer(object):
    """
    This prioritizer always return the same priority (1)
    """
    def get_priority(self, element):
        return 1

class RandomPrioritizer(object):
    """
    This prioritizer always return a random priority
    """
    def get_priority(self, element):
        return random.randrange(0, 1000)

