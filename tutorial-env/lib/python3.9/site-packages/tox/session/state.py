from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from tox.config.main import Config
from tox.journal import Journal
from tox.plugin import impl

from .env_select import EnvSelector

if TYPE_CHECKING:
    from tox.config.cli.parse import Options
    from tox.config.cli.parser import ToxParser


class State:
    """Runtime state holder."""

    def __init__(self, options: Options, args: Sequence[str]) -> None:
        self.conf = Config.make(options.parsed, options.pos_args, options.source)
        self._options = options
        self.args = args
        self._journal: Journal = Journal(getattr(options.parsed, "result_json", None) is not None)
        self._selector: EnvSelector | None = None

    @property
    def envs(self) -> EnvSelector:
        """:return: provides access to the tox environments"""
        if self._selector is None:
            self._selector = EnvSelector(self)
        return self._selector


@impl
def tox_add_option(parser: ToxParser) -> None:
    from tox.tox_env.register import REGISTER

    parser.add_argument(
        "--runner",
        dest="default_runner",
        help="the tox run engine to use when not explicitly stated in tox env configuration",
        default=REGISTER.default_env_runner,
        choices=list(REGISTER.env_runners),
    )
