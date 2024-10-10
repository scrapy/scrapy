"""
Scrapy Telnet Console extension

See documentation in docs/topics/telnetconsole.rst
"""

from __future__ import annotations

import binascii
import logging
import os
import pprint
from typing import TYPE_CHECKING, Any

from twisted.internet import protocol
from twisted.internet.tcp import Port

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.decorators import defers
from scrapy.utils.engine import print_engine_status
from scrapy.utils.reactor import listen_tcp
from scrapy.utils.trackref import print_live_refs

if TYPE_CHECKING:
    from twisted.conch import telnet

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)

# signal to update telnet variables
# args: telnet_vars
update_telnet_vars = object()


class TelnetConsole(protocol.ServerFactory):
    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("TELNETCONSOLE_ENABLED"):
            raise NotConfigured

        self.crawler: Crawler = crawler
        self.noisy: bool = False
        self.portrange: list[int] = [
            int(x) for x in crawler.settings.getlist("TELNETCONSOLE_PORT")
        ]
        self.host: str = crawler.settings["TELNETCONSOLE_HOST"]
        self.username: str = crawler.settings["TELNETCONSOLE_USERNAME"]
        self.password: str = crawler.settings["TELNETCONSOLE_PASSWORD"]

        if not self.password:
            self.password = binascii.hexlify(os.urandom(8)).decode("utf8")
            logger.info("Telnet Password: %s", self.password)

        self.crawler.signals.connect(self.start_listening, signals.engine_started)
        self.crawler.signals.connect(self.stop_listening, signals.engine_stopped)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def start_listening(self) -> None:
        self.port: Port = listen_tcp(self.portrange, self.host, self)
        h = self.port.getHost()
        logger.info(
            "Telnet console listening on %(host)s:%(port)d",
            {"host": h.host, "port": h.port},
            extra={"crawler": self.crawler},
        )

    def stop_listening(self) -> None:
        self.port.stopListening()

    def protocol(self) -> telnet.TelnetTransport:  # type: ignore[override]
        # these import twisted.internet.reactor
        from twisted.conch import manhole, telnet
        from twisted.conch.insults import insults

        class Portal:
            """An implementation of IPortal"""

            @defers
            def login(self_, credentials, mind, *interfaces):
                if not (
                    credentials.username == self.username.encode("utf8")
                    and credentials.checkPassword(self.password.encode("utf8"))
                ):
                    raise ValueError("Invalid credentials")

                protocol = telnet.TelnetBootstrapProtocol(
                    insults.ServerProtocol, manhole.Manhole, self._get_telnet_vars()
                )
                return (interfaces[0], protocol, lambda: None)

        return telnet.TelnetTransport(telnet.AuthenticatingTelnetProtocol, Portal())

    def _get_telnet_vars(self) -> dict[str, Any]:
        # Note: if you add entries here also update topics/telnetconsole.rst
        assert self.crawler.engine
        telnet_vars: dict[str, Any] = {
            "engine": self.crawler.engine,
            "spider": self.crawler.engine.spider,
            "slot": self.crawler.engine.slot,
            "crawler": self.crawler,
            "extensions": self.crawler.extensions,
            "stats": self.crawler.stats,
            "settings": self.crawler.settings,
            "est": lambda: print_engine_status(self.crawler.engine),
            "p": pprint.pprint,
            "prefs": print_live_refs,
            "help": "This is Scrapy telnet console. For more info see: "
            "https://docs.scrapy.org/en/latest/topics/telnetconsole.html",
        }
        self.crawler.signals.send_catch_log(update_telnet_vars, telnet_vars=telnet_vars)
        return telnet_vars
