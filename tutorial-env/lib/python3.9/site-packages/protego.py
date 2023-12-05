import logging
import re
from collections import namedtuple
from datetime import time
from urllib.parse import ParseResult, quote, urlparse, urlunparse

logger = logging.getLogger(__name__)

_Rule = namedtuple("Rule", ["field", "value"])
RequestRate = namedtuple(
    "RequestRate", ["requests", "seconds", "start_time", "end_time"]
)
VisitTime = namedtuple("VisitTime", ["start_time", "end_time"])

_DISALLOW_DIRECTIVE = {
    "disallow",
    "dissallow",
    "dissalow",
    "disalow",
    "diasllow",
    "disallaw",
}
_ALLOW_DIRECTIVE = {"allow"}
_USER_AGENT_DIRECTIVE = {"user-agent", "useragent", "user agent"}
_SITEMAP_DIRECTIVE = {"sitemap", "sitemaps", "site-map"}
_CRAWL_DELAY_DIRECTIVE = {"crawl-delay", "crawl delay"}
_REQUEST_RATE_DIRECTIVE = {"request-rate", "request rate"}
_VISIT_TIME_DIRECTIVE = {"visit-time", "visit time"}
_HOST_DIRECTIVE = {"host"}

_WILDCARDS = {"*", "$"}

_HEX_DIGITS = set("0123456789ABCDEFabcdef")

__all__ = ["RequestRate", "Protego"]


def _is_valid_directive_field(field):
    return any(
        [
            field in _DISALLOW_DIRECTIVE,
            field in _ALLOW_DIRECTIVE,
            field in _USER_AGENT_DIRECTIVE,
            field in _SITEMAP_DIRECTIVE,
            field in _CRAWL_DELAY_DIRECTIVE,
            field in _REQUEST_RATE_DIRECTIVE,
            field in _HOST_DIRECTIVE,
        ]
    )


class _URLPattern(object):
    """Internal class which represents a URL pattern."""

    def __init__(self, pattern):
        self._pattern = pattern
        self.priority = len(pattern)
        self._contains_asterisk = "*" in self._pattern
        self._contains_dollar = self._pattern.endswith("$")

        if self._contains_asterisk:
            self._pattern_before_asterisk = self._pattern[: self._pattern.find("*")]
        elif self._contains_dollar:
            self._pattern_before_dollar = self._pattern[:-1]

        self._pattern_compiled = False

    def match(self, url):
        """Return True if pattern matches the given URL, otherwise return False."""
        # check if pattern is already compiled
        if self._pattern_compiled:
            return self._pattern.match(url)

        if not self._contains_asterisk:
            if not self._contains_dollar:
                # answer directly for patterns without wildcards
                return url.startswith(self._pattern)

            # pattern only contains $ wildcard.
            return url == self._pattern_before_dollar

        if not url.startswith(self._pattern_before_asterisk):
            return False

        self._pattern = self._prepare_pattern_for_regex(self._pattern)
        self._pattern = re.compile(self._pattern)
        self._pattern_compiled = True
        return self._pattern.match(url)

    def _prepare_pattern_for_regex(self, pattern):
        """Return equivalent regex pattern for the given URL pattern."""
        pattern = re.sub(r"\*+", "*", pattern)
        s = re.split(r"(\*|\$$)", pattern)
        for index, substr in enumerate(s):
            if substr not in _WILDCARDS:
                s[index] = re.escape(substr)
            elif s[index] == "*":
                s[index] = ".*?"
        pattern = "".join(s)
        return pattern


class _RuleSet(object):
    """Internal class which stores rules for a user agent."""

    def __init__(self, parser_instance):
        self.user_agent = None
        self._rules = []
        self._crawl_delay = None
        self._req_rate = None
        self._visit_time = None
        self._parser_instance = parser_instance

    def applies_to(self, robotname):
        """Return matching score."""
        robotname = robotname.strip().lower()
        if self.user_agent == "*":
            return 1
        if self.user_agent in robotname:
            return len(self.user_agent)
        return 0

    def _unquote(self, url, ignore="", errors="replace"):
        """Replace %xy escapes by their single-character equivalent."""
        if "%" not in url:
            return url

        def hex_to_byte(h):
            """Replaces a %xx escape with equivalent binary sequence."""
            return bytes.fromhex(h)

        # ignore contains %xy escapes for characters that are not
        # meant to be converted back.
        ignore = {"{ord_c:02X}".format(ord_c=ord(c)) for c in ignore}

        parts = url.split("%")
        parts[0] = parts[0].encode("utf-8")

        for i in range(1, len(parts)):
            if len(parts[i]) >= 2:
                # %xy is a valid escape only if x and y are hexadecimal digits.
                if set(parts[i][:2]).issubset(_HEX_DIGITS):
                    # make sure that all %xy escapes are in uppercase.
                    hexcode = parts[i][:2].upper()
                    leftover = parts[i][2:]
                    if hexcode not in ignore:
                        parts[i] = hex_to_byte(hexcode) + leftover.encode("utf-8")
                        continue
                    else:
                        parts[i] = hexcode + leftover

            # add back the '%' we removed during splitting.
            parts[i] = b"%" + parts[i].encode("utf-8")

        return b"".join(parts).decode("utf-8", errors)

    def hexescape(self, char):
        """Escape char as RFC 2396 specifies"""
        hex_repr = hex(ord(char))[2:].upper()
        if len(hex_repr) == 1:
            hex_repr = "0%s" % hex_repr
        return "%" + hex_repr

    def _quote_path(self, path):
        """Return percent encoded path."""
        parts = urlparse(path)
        path = self._unquote(parts.path, ignore="/%")
        path = quote(path, safe="/%")

        parts = ParseResult("", "", path, parts.params, parts.query, parts.fragment)
        path = urlunparse(parts)
        return path or "/"

    def _quote_pattern(self, pattern):
        if pattern.startswith("https://") or pattern.startswith("http://"):
            pattern = "/" + pattern

        # Corner case for query only (e.g. '/abc?') and param only (e.g. '/abc;') URLs.
        # Save the last character otherwise, urlparse will kill it.
        last_char = ""
        if pattern[-1] == "?" or pattern[-1] == ";" or pattern[-1] == "$":
            last_char = pattern[-1]
            pattern = pattern[:-1]

        parts = urlparse(pattern)
        pattern = self._unquote(parts.path, ignore="/*$%")
        pattern = quote(pattern, safe="/*%")

        parts = ParseResult(
            "", "", pattern + last_char, parts.params, parts.query, parts.fragment
        )
        pattern = urlunparse(parts)
        return pattern

    def allow(self, pattern):
        if "$" in pattern:
            self.allow(pattern.replace("$", self.hexescape("$")))

        pattern = self._quote_pattern(pattern)
        if not pattern:
            return
        self._rules.append(_Rule(field="allow", value=_URLPattern(pattern)))

        # If index.html is allowed, we interpret this as / being allowed too.
        if pattern.endswith("/index.html"):
            self.allow(pattern[:-10] + "$")

    def disallow(self, pattern):
        if "$" in pattern:
            self.disallow(pattern.replace("$", self.hexescape("$")))

        pattern = self._quote_pattern(pattern)
        if not pattern:
            return
        self._rules.append(_Rule(field="disallow", value=_URLPattern(pattern)))

    def finalize_rules(self):
        self._rules.sort(
            key=lambda r: (r.value.priority, r.field == "allow"), reverse=True
        )

    def can_fetch(self, url):
        """Return if the url can be fetched."""
        url = self._quote_path(url)
        allowed = True
        for rule in self._rules:
            if rule.value.match(url):
                if rule.field == "disallow":
                    allowed = False
                break
        return allowed

    @property
    def crawl_delay(self):
        """Get & set crawl delay for the rule set."""
        return self._crawl_delay

    @crawl_delay.setter
    def crawl_delay(self, delay):
        try:
            delay = float(delay)
        except ValueError:
            # Value is malformed, do nothing.
            logger.debug(
                "Malformed rule at line {line_seen} : cannot set crawl delay to '{delay}'. "
                "Ignoring this rule.".format(
                    line_seen=self._parser_instance._total_line_seen, delay=delay
                )
            )
            return

        self._crawl_delay = delay

    @property
    def request_rate(self):
        """Get & set request rate for the rule set."""
        return self._req_rate

    @request_rate.setter
    def request_rate(self, value):
        try:
            parts = value.split()
            if len(parts) == 2:
                rate, time_period = parts
            else:
                rate, time_period = parts[0], ""

            requests, seconds = rate.split("/")
            time_unit = seconds[-1].lower()
            requests, seconds = int(requests), int(seconds[:-1])

            if time_unit == "m":
                seconds *= 60
            elif time_unit == "h":
                seconds *= 3600
            elif time_unit == "d":
                seconds *= 86400

            start_time = None
            end_time = None
            if time_period:
                start_time, end_time = self._parse_time_period(time_period)
        except Exception:
            # Value is malformed, do nothing.
            logger.debug(
                "Malformed rule at line {line_seen} : cannot set request rate using '{value}'. "
                "Ignoring this rule.".format(
                    line_seen=self._parser_instance._total_line_seen, value=value
                )
            )
            return

        self._req_rate = RequestRate(requests, seconds, start_time, end_time)

    def _parse_time_period(self, time_period, separator="-"):
        """Parse a string with a time period into a tuple of start and end times."""
        start_time, end_time = time_period.split(separator)
        start_time = time(int(start_time[:2]), int(start_time[-2:]))
        end_time = time(int(end_time[:2]), int(end_time[-2:]))
        return start_time, end_time

    @property
    def visit_time(self):
        """Get & set visit time for the rule set."""
        return self._visit_time

    @visit_time.setter
    def visit_time(self, value):
        try:
            start_time, end_time = self._parse_time_period(value, separator=" ")
        except Exception:
            logger.debug(
                "Malformed rule at line {line_seen} : cannot set visit time using '{value}'. "
                "Ignoring this rule.".format(
                    line_seen=self._parser_instance._total_line_seen, value=value
                )
            )
            return
        self._visit_time = VisitTime(start_time, end_time)


class Protego(object):
    def __init__(self):
        # A dict mapping user agents (specified in robots.txt) to rule sets.
        self._user_agents = {}

        # Preferred host specified in the robots.txt
        self._host = None

        # A list of sitemaps specified in the robots.txt
        self._sitemap_list = []

        # A memoization table mapping user agents (used in queries) to matched rule sets.
        self._matched_rule_set = {}

        self._total_line_seen = 0
        self._invalid_directive_seen = 0
        self._total_directive_seen = 0

    @classmethod
    def parse(cls, content):
        o = cls()
        if not isinstance(content, str):
            raise ValueError(f"Protego.parse expects str, got {type(content).__name__}")
        o._parse_robotstxt(content)
        return o

    def _parse_robotstxt(self, content):
        lines = content.splitlines()

        # A list containing rule sets corresponding to user
        # agents of the current record group.
        current_rule_sets = []

        # Last encountered rule irrespective of whether it was valid or not.
        previous_rule_field = None

        for line in lines:
            self._total_line_seen += 1

            # Remove the comment portion of the line
            hash_pos = line.find("#")
            if hash_pos != -1:
                line = line[0:hash_pos].strip()

            # Whitespace at the beginning and at the end of the line is ignored.
            line = line.strip()
            if not line:
                continue

            # Format for a valid robots.txt rule is "<field>:<value>"
            if line.find(":") != -1:
                field, value = line.split(":", 1)
            else:
                # We will be generous here and give it a second chance.
                parts = line.split(" ")
                if len(parts) < 2:
                    continue

                possible_filed = parts[0]
                for i in range(1, len(parts)):
                    if _is_valid_directive_field(possible_filed):
                        field, value = possible_filed, " ".join(parts[i:])
                        break
                    possible_filed += " " + parts[i]
                else:
                    continue

            field = field.strip().lower()
            value = value.strip()

            # Ignore rules with no value part (e.g. "Disallow: ", "Allow: ").
            if not value:
                previous_rule_field = field
                continue

            # Ignore rules without a corresponding user agent.
            if (
                not current_rule_sets
                and field not in _USER_AGENT_DIRECTIVE
                and field not in _SITEMAP_DIRECTIVE
            ):
                logger.debug(
                    "Rule at line {line_seen} without any user agent to enforce it on.".format(
                        line_seen=self._total_line_seen
                    )
                )
                continue

            self._total_directive_seen += 1

            if field in _USER_AGENT_DIRECTIVE:
                if (
                    previous_rule_field
                    and previous_rule_field not in _USER_AGENT_DIRECTIVE
                ):
                    current_rule_sets = []

                # Wildcards are not supported in the user agent values.
                # We will be generous here and remove all the wildcards.
                user_agent = value.strip().lower()
                user_agent_without_asterisk = None
                if user_agent != "*" and "*" in user_agent:
                    user_agent_without_asterisk = user_agent.replace("*", "")

                user_agents = [user_agent, user_agent_without_asterisk]
                for user_agent in user_agents:
                    if not user_agent:
                        continue
                    # See if this user agent is encountered before, if so merge these rules into it.
                    rule_set = self._user_agents.get(user_agent, None)
                    if rule_set and rule_set not in current_rule_sets:
                        current_rule_sets.append(rule_set)

                    if not rule_set:
                        rule_set = _RuleSet(self)
                        rule_set.user_agent = user_agent
                        self._user_agents[user_agent] = rule_set
                        current_rule_sets.append(rule_set)

            elif field in _ALLOW_DIRECTIVE:
                for rule_set in current_rule_sets:
                    rule_set.allow(value)

            elif field in _DISALLOW_DIRECTIVE:
                for rule_set in current_rule_sets:
                    rule_set.disallow(value)

            elif field in _SITEMAP_DIRECTIVE:
                self._sitemap_list.append(value)

            elif field in _CRAWL_DELAY_DIRECTIVE:
                for rule_set in current_rule_sets:
                    rule_set.crawl_delay = value

            elif field in _REQUEST_RATE_DIRECTIVE:
                for rule_set in current_rule_sets:
                    rule_set.request_rate = value

            elif field in _HOST_DIRECTIVE:
                self._host = value

            elif field in _VISIT_TIME_DIRECTIVE:
                for rule_set in current_rule_sets:
                    rule_set.visit_time = value

            else:
                self._invalid_directive_seen += 1

            previous_rule_field = field

        for user_agent in self._user_agents.values():
            user_agent.finalize_rules()

    def _get_matching_rule_set(self, user_agent):
        """Return the rule set with highest matching score."""
        if not self._user_agents:
            return None

        if user_agent in self._matched_rule_set:
            return self._matched_rule_set[user_agent]
        score_rule_set_pairs = (
            (rs.applies_to(user_agent), rs) for rs in self._user_agents.values()
        )
        match_score, matched_rule_set = max(score_rule_set_pairs, key=lambda p: p[0])

        if not match_score:
            self._matched_rule_set[user_agent] = None
            return None
        self._matched_rule_set[user_agent] = matched_rule_set
        return matched_rule_set

    def can_fetch(self, url, user_agent):
        """Return True if the user agent can fetch the URL, otherwise return False."""
        matched_rule_set = self._get_matching_rule_set(user_agent)
        if not matched_rule_set:
            return True
        return matched_rule_set.can_fetch(url)

    def crawl_delay(self, user_agent):
        """Return the crawl delay specified for the user agent as a float.
        If nothing is specified, return None.
        """
        matched_rule_set = self._get_matching_rule_set(user_agent)
        if not matched_rule_set:
            return None
        return matched_rule_set.crawl_delay

    def request_rate(self, user_agent):
        """Return the request rate specified for the user agent as a named tuple
        RequestRate(requests, seconds, start_time, end_time). If nothing is
        specified, return None.
        """
        matched_rule_set = self._get_matching_rule_set(user_agent)
        if not matched_rule_set:
            return None
        return matched_rule_set.request_rate

    def visit_time(self, user_agent):
        """Return the visit time specified for the user agent as a named tuple
        VisitTime(start_time, end_time). If nothing is specified, return None.
        """
        matched_rule_set = self._get_matching_rule_set(user_agent)
        if not matched_rule_set:
            return None
        return matched_rule_set.visit_time

    @property
    def sitemaps(self):
        """Get an iterator containing links to sitemaps specified."""
        return iter(self._sitemap_list)

    @property
    def preferred_host(self):
        """Get the preferred host."""
        return self._host

    @property
    def _valid_directive_seen(self):
        return self._total_directive_seen - self._invalid_directive_seen
