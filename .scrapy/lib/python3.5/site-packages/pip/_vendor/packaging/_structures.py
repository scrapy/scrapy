# Copyright 2014 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function


class Infinity(object):

    def __repr__(self):
        return "Infinity"

    def __hash__(self):
        return hash(repr(self))

    def __lt__(self, other):
        return False

    def __le__(self, other):
        return False

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not isinstance(other, self.__class__)

    def __gt__(self, other):
        return True

    def __ge__(self, other):
        return True

    def __neg__(self):
        return NegativeInfinity

Infinity = Infinity()


class NegativeInfinity(object):

    def __repr__(self):
        return "-Infinity"

    def __hash__(self):
        return hash(repr(self))

    def __lt__(self, other):
        return True

    def __le__(self, other):
        return True

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not isinstance(other, self.__class__)

    def __gt__(self, other):
        return False

    def __ge__(self, other):
        return False

    def __neg__(self):
        return Infinity

NegativeInfinity = NegativeInfinity()
