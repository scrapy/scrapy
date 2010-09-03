from zope.interface import Interface

class ISpiderQueue(Interface):

    def from_settings(settings):
        """Class method to instantiate from settings"""

    def add(name, **spider_args):
        """Add a spider to the queue given its name a some spider arguments.
        
        This method can return a deferred. """

    def pop():
        """Pop the next mesasge from the queue. The messages is a dict
        conaining a key 'name' with the spider name and other keys as spider
        attributes.

        This method can return a deferred. """

    def list():
        """Return a list with the messages in the queue. Each message is a dict
        which must have a 'name' key (with the spider name), and other optional
        keys that will be used as spider arguments, to create the spider.
        
        This method can return a deferred. """

    def count():
        """Return the number of spiders in the queue.
        
        This method can return a deferred. """

    def clear():
        """Clear the queue.

        This method can return a deferred. """
