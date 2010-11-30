from twisted.application.service import Application
from twisted.application.internet import TimerService, TCPServer
from twisted.web import server

from .interfaces import IEggStorage, IPoller, ISpiderScheduler, IEnvironment
from .launcher import Launcher
from .eggstorage import FilesystemEggStorage
from .scheduler import SpiderScheduler
from .poller import QueuePoller
from .environ import Environment
from .website import Root
from .config import Config

def application():
    app = Application("Scrapyd")
    config = Config()
    http_port = config.getint('http_port', 6800)

    poller = QueuePoller(config)
    eggstorage = FilesystemEggStorage(config)
    scheduler = SpiderScheduler(config)
    environment = Environment(config)

    app.setComponent(IPoller, poller)
    app.setComponent(IEggStorage, eggstorage)
    app.setComponent(ISpiderScheduler, scheduler)
    app.setComponent(IEnvironment, environment)

    launcher = Launcher(config, app)
    timer = TimerService(5, poller.poll)
    webservice = TCPServer(http_port, server.Site(Root(config, app)))

    launcher.setServiceParent(app)
    timer.setServiceParent(app)
    webservice.setServiceParent(app)

    return app
