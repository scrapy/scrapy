class GroupFilter(dict):
    """Filter groups of keys"""
    def open(self, group):
        self[group] = set()

    def close(self, group):
        del self[group]

    def add(self, group, key):
        """Add a key to the group if an equivalent key has not already been added.
        This method will return true if the key was added and false otherwise.
        """
        if key not in self[group]:
            self[group].add(key)
            return True
        return False

    def has(self, group, key):
        return key in self[group]
