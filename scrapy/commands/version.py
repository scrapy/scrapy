import argparse
import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.utils.versions import scrapy_components_versions


class Command(ScrapyCommand):
    """Command to print the current Scrapy version and related component details."""

    default_settings = {"LOG_ENABLED": False, "SPIDER_LOADER_WARN_ONLY": True}

    def syntax(self) -> str:
        """Return the syntax for the command.

        Returns:
            str: The syntax string.
        """
        return "[-v]"

    def short_desc(self) -> str:
        """Return a short description of the command.

        Returns:
            str: A brief description.
        """
        return "Print Scrapy version"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        """Add the `--verbose` option for detailed output.

        Args:
            parser (argparse.ArgumentParser): The argument parser instance.
        """
        super().add_options(parser)
        parser.add_argument(
            "--verbose",
            "-v",
            dest="verbose",
            action="store_true",
            help="Display detailed information about Twisted, Python, and platform (useful for bug reports).",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Execute the command to print version information.

        Args:
            args (list[str]): Command line arguments.
            opts (argparse.Namespace): Parsed command-line options.
        """
        if opts.verbose:
            versions = scrapy_components_versions()
            width = max(len(n) for (n, _) in versions)
            for name, version in versions:
                print(f"{name:<{width}} : {version}")
        else:
            print(f"Scrapy {scrapy.__version__}")
