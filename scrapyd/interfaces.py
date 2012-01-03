from zope.interface import Interface

class IEggStorage(Interface):
    """A component that handles storing and retrieving eggs"""

    def put(eggfile, project, version):
        """Store the egg (passed in the file object) under the given project and
        version"""

    def get(project, version=None):
        """Return a tuple (version, file) with the the egg for the specified
        project and version. If version is None, the latest version is
        returned. If no egg is found for the given project/version (None, None)
        should be returned."""

    def list(project):
        """Return the list of versions which have eggs stored (for the given
        project) in order (the latest version is the currently used)."""

    def delete(project, version=None):
        """Delete the egg stored for the given project and version. If should
        also delete the project if no versions are left"""


class IPoller(Interface):
    """A component that polls for projects that need to run"""

    def poll():
        """Called periodically to poll for projects"""

    def next():
        """Return the next message.

        It should return a Deferred which will get fired when there is a new
        project that needs to run, or already fired if there was a project
        waiting to run already.

        The message is a dict containing (at least):
        * the name of the project to be run in the '_project' key
        * the name of the spider to be run in the '_spider' key
        * a unique identifier for this run in the `_job` key
        This message will be passed later to IEnvironment.get_environment().
        """

    def update_projects():
        """Called when projects may have changed, to refresh the available
        projects"""


class ISpiderQueue(Interface):

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

    def remove(func):
        """Remove all elements from the queue for which func(element) is true,
        and return the number of removed elements.
        """

    def clear():
        """Clear the queue.

        This method can return a deferred. """


class ISpiderScheduler(Interface):
    """A component to schedule spider runs"""

    def schedule(project, spider_name, **spider_args):
        """Schedule a spider for the given project"""

    def list_projects():
        """Return the list of available projects"""

    def update_projects():
        """Called when projects may have changed, to refresh the available
        projects"""


class IEnvironment(Interface):
    """A component to generate the environment of crawler processes"""

    def get_environment(message, slot):
        """Return the environment variables to use for running the process.

        `message` is the message received from the IPoller.next() method
        `slot` is the Launcher slot where the process will be running.
        """
