"""
Extensions for batch processing and support.
"""


class Batch:
    """
    Batch which will store information for current batches and provides
    suitable methods to check and update batch info.
    """

    def __init__(self, feed_options):
        self.feed_options = feed_options
        self.batch_item_count = self.feed_options["batch_item_count"]
        # get time duration constraint from feed-settings
        # get file size constraint from feed-settings

        self.current_item_count = 0
        # add time duration parameter here
        # add file size parameter here
        self.batch_id = 0

        self.file = None
        self.updated_once = False
        self.enabled = True
        if not self.batch_item_count:
            self.enabled = False

    def update(self):
        """
        Update batch states parameters.
        """
        self.current_item_count += 1
        # update time duration parameter
        # update file size parameter

        if not self.updated_once:
            self.updated_once = True

    def should_trigger(self):
        """
        Check if any batch state parameter value has crossed its
        specified constraint.
        :return: `True` if parameter value has crossed constraint, else `False`
        :rtype: bool
        """
        if not self.enabled:
            return False

        # add file size and time duration checks
        return self.current_item_count >= self.batch_item_count

    def new_batch(self, file):
        """
        Resets parameter values back to its initial value and increments
        self.batch_id.
        """
        self.file = file
        self.current_item_count = 0
        # reset other parameters as well
        self.updated_once = False
        self.batch_id += 1

    def get_batch_state(self):
        """
        Get current batch state.
        :return: A dictionary containing batch state parameters and its current value.
        :rtype: dict
        """
        state = {
            'itemcount': self.current_item_count,   # add current file size and time elapsed
        }
        return state
