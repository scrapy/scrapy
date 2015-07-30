class PeriodicStatsObserver(object):
    """
    Class that monitors a stats value and decides to show it or not across intervals
    """
    def __init__(self, key, use_re_key=False, use_partial_values=False,
                 export_key=None, export_interval=1,
                 only_export_on_change=False, only_export_on_close=False):
        self.key = key
        self.use_re_key = use_re_key
        self._export_interval = export_interval
        self._use_partial_values = use_partial_values
        self._export_key = export_key
        self._only_export_on_change = only_export_on_change
        self._only_export_on_close = only_export_on_close
        self._value = None
        self._last_value = None
        self._interval_counter = 0

    @property
    def export_key(self):
        return self._export_key or self.key

    def get_interval_stats(self, force=False):
        """
        Returns the stats for the current interval
        """
        interval_value, reason = self._get_interval_value(force)
        #print '%s[%d] value: %s reason: %s' % \
        #      (self.export_key, self._interval_counter, interval_value, reason)
        if interval_value is not None:
            if self._use_partial_values:
                self._value = 0
            self._last_value = interval_value

        self._interval_counter += 1
        return self.export_key, interval_value

    def set_value(self, value, spider=None):
        self._value = value

    def inc_value(self, count=1, start=0):
        if self._value is None:
            self._value = start
        self._value += count

    def _get_interval_value(self, force):
        """
        Returns the stat value for the current interval
        """
        if force:
            return self._value, 'forced'
        if self._only_export_on_close:
            return None, 'not close'
        if self._is_in_interval():
            self._interval_counter = 0
            if not self._only_export_on_change:
                return self._value, 'always'
            elif self._value_changed():
                return self._value, 'changed'
            else:
                return None, 'not changed'
        return None, 'not in interval'

    def _value_changed(self):
        return self._last_value != self._value

    def _is_in_interval(self):
        return self._interval_counter == 0 or \
               self._interval_counter >= self._export_interval
