# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


class Enum:
    group = None

    def __init__(self, label):
        self.label = label

    def __repr__(self):
        return '<%s: %s>' % (self.group, self.label)

    def __str__(self):
        return self.label


class StatusEnum(Enum):
    group = 'Status'

OFFLINE = Enum('Offline')
ONLINE = Enum('Online')
AWAY = Enum('Away')

class OfflineError(Exception):
    """The requested action can't happen while offline."""
