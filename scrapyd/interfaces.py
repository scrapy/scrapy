from zope.interface import Interface

class IEggStorage(Interface):
    """A component that handles storing and retrieving eggs"""

    def put(eggfile, project, version):
        """Store the egg (passed in the file object) under the given project and
        version"""

    def get(project, version=None):
        """Return a tuple (version, file) with the the egg for the specified
        project and version. If version is None, the latest version is
        returned."""

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

        The message is a dict containing (at least) the name of the project to
        be run in the 'project' key. This message will be passed later to
        IEnvironment.get_environment().
        """

    def update_projects():
        """Called when projects may have changed, to refresh the available
        projects"""


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

        `message` is the message received from the IPoller.next()
        `slot` is the Launcher slot where the process will be running.
        """
