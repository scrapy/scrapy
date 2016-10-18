"""
Requirements file parsing
"""

from __future__ import absolute_import

import os
import re
import shlex
import optparse

from pip._vendor.six.moves.urllib import parse as urllib_parse
from pip._vendor.six.moves import filterfalse

import pip
from pip.download import get_file_content
from pip.req.req_install import InstallRequirement
from pip.exceptions import (RequirementsFileParseError)
from pip.utils import normalize_name
from pip import cmdoptions

__all__ = ['parse_requirements']

SCHEME_RE = re.compile(r'^(http|https|file):', re.I)
COMMENT_RE = re.compile(r'(^|\s)+#.*$')

SUPPORTED_OPTIONS = [
    cmdoptions.constraints,
    cmdoptions.editable,
    cmdoptions.requirements,
    cmdoptions.no_index,
    cmdoptions.index_url,
    cmdoptions.find_links,
    cmdoptions.extra_index_url,
    cmdoptions.allow_external,
    cmdoptions.allow_all_external,
    cmdoptions.no_allow_external,
    cmdoptions.allow_unsafe,
    cmdoptions.no_allow_unsafe,
    cmdoptions.use_wheel,
    cmdoptions.no_use_wheel,
    cmdoptions.always_unzip,
    cmdoptions.no_binary,
    cmdoptions.only_binary,
]

# options to be passed to requirements
SUPPORTED_OPTIONS_REQ = [
    cmdoptions.install_options,
    cmdoptions.global_options
]

# the 'dest' string values
SUPPORTED_OPTIONS_REQ_DEST = [o().dest for o in SUPPORTED_OPTIONS_REQ]


def parse_requirements(filename, finder=None, comes_from=None, options=None,
                       session=None, constraint=False, wheel_cache=None):
    """Parse a requirements file and yield InstallRequirement instances.

    :param filename:    Path or url of requirements file.
    :param finder:      Instance of pip.index.PackageFinder.
    :param comes_from:  Origin description of requirements.
    :param options:     Global options.
    :param session:     Instance of pip.download.PipSession.
    :param constraint:  If true, parsing a constraint file rather than
        requirements file.
    :param wheel_cache: Instance of pip.wheel.WheelCache
    """
    if session is None:
        raise TypeError(
            "parse_requirements() missing 1 required keyword argument: "
            "'session'"
        )

    _, content = get_file_content(
        filename, comes_from=comes_from, session=session
    )

    lines = content.splitlines()
    lines = ignore_comments(lines)
    lines = join_lines(lines)
    lines = skip_regex(lines, options)

    for line_number, line in enumerate(lines, 1):
        req_iter = process_line(line, filename, line_number, finder,
                                comes_from, options, session, wheel_cache,
                                constraint=constraint)
        for req in req_iter:
            yield req


def process_line(line, filename, line_number, finder=None, comes_from=None,
                 options=None, session=None, wheel_cache=None,
                 constraint=False):
    """Process a single requirements line; This can result in creating/yielding
    requirements, or updating the finder.

    For lines that contain requirements, the only options that have an effect
    are from SUPPORTED_OPTIONS_REQ, and they are scoped to the
    requirement. Other options from SUPPORTED_OPTIONS may be present, but are
    ignored.

    For lines that do not contain requirements, the only options that have an
    effect are from SUPPORTED_OPTIONS. Options from SUPPORTED_OPTIONS_REQ may
    be present, but are ignored. These lines may contain multiple options
    (although our docs imply only one is supported), and all our parsed and
    affect the finder.

    :param constraint: If True, parsing a constraints file.
    """
    parser = build_parser()
    defaults = parser.get_default_values()
    defaults.index_url = None
    if finder:
        # `finder.format_control` will be updated during parsing
        defaults.format_control = finder.format_control
    args_str, options_str = break_args_options(line)
    opts, _ = parser.parse_args(shlex.split(options_str), defaults)

    # preserve for the nested code path
    line_comes_from = '%s %s (line %s)' % (
        '-c' if constraint else '-r', filename, line_number)

    # yield a line requirement
    if args_str:
        isolated = options.isolated_mode if options else False
        if options:
            cmdoptions.check_install_build_global(options, opts)
        # get the options that apply to requirements
        req_options = {}
        for dest in SUPPORTED_OPTIONS_REQ_DEST:
            if dest in opts.__dict__ and opts.__dict__[dest]:
                req_options[dest] = opts.__dict__[dest]
        yield InstallRequirement.from_line(
            args_str, line_comes_from, constraint=constraint,
            isolated=isolated, options=req_options, wheel_cache=wheel_cache
        )

    # yield an editable requirement
    elif opts.editables:
        isolated = options.isolated_mode if options else False
        default_vcs = options.default_vcs if options else None
        yield InstallRequirement.from_editable(
            opts.editables[0], comes_from=line_comes_from,
            constraint=constraint, default_vcs=default_vcs, isolated=isolated,
            wheel_cache=wheel_cache
        )

    # parse a nested requirements file
    elif opts.requirements or opts.constraints:
        if opts.requirements:
            req_path = opts.requirements[0]
            nested_constraint = False
        else:
            req_path = opts.constraints[0]
            nested_constraint = True
        # original file is over http
        if SCHEME_RE.search(filename):
            # do a url join so relative paths work
            req_path = urllib_parse.urljoin(filename, req_path)
        # original file and nested file are paths
        elif not SCHEME_RE.search(req_path):
            # do a join so relative paths work
            req_dir = os.path.dirname(filename)
            req_path = os.path.join(os.path.dirname(filename), req_path)
        # TODO: Why not use `comes_from='-r {} (line {})'` here as well?
        parser = parse_requirements(
            req_path, finder, comes_from, options, session,
            constraint=nested_constraint, wheel_cache=wheel_cache
        )
        for req in parser:
            yield req

    # set finder options
    elif finder:
        if opts.index_url:
            finder.index_urls = [opts.index_url]
        if opts.use_wheel is False:
            finder.use_wheel = False
            pip.index.fmt_ctl_no_use_wheel(finder.format_control)
        if opts.no_index is True:
            finder.index_urls = []
        if opts.allow_all_external:
            finder.allow_all_external = opts.allow_all_external
        if opts.extra_index_urls:
            finder.index_urls.extend(opts.extra_index_urls)
        if opts.allow_external:
            finder.allow_external |= set(
                [normalize_name(v).lower() for v in opts.allow_external])
        if opts.allow_unverified:
            # Remove after 7.0
            finder.allow_unverified |= set(
                [normalize_name(v).lower() for v in opts.allow_unverified])
        if opts.find_links:
            # FIXME: it would be nice to keep track of the source
            # of the find_links: support a find-links local path
            # relative to a requirements file.
            value = opts.find_links[0]
            req_dir = os.path.dirname(os.path.abspath(filename))
            relative_to_reqs_file = os.path.join(req_dir, value)
            if os.path.exists(relative_to_reqs_file):
                value = relative_to_reqs_file
            finder.find_links.append(value)


def break_args_options(line):
    """Break up the line into an args and options string.  We only want to shlex
    (and then optparse) the options, not the args.  args can contain markers
    which are corrupted by shlex.
    """
    tokens = line.split(' ')
    args = []
    options = tokens[:]
    for token in tokens:
        if token.startswith('-') or token.startswith('--'):
            break
        else:
            args.append(token)
            options.pop(0)
    return ' '.join(args), ' '.join(options)


def build_parser():
    """
    Return a parser for parsing requirement lines
    """
    parser = optparse.OptionParser(add_help_option=False)

    option_factories = SUPPORTED_OPTIONS + SUPPORTED_OPTIONS_REQ
    for option_factory in option_factories:
        option = option_factory()
        parser.add_option(option)

    # By default optparse sys.exits on parsing errors. We want to wrap
    # that in our own exception.
    def parser_exit(self, msg):
        raise RequirementsFileParseError(msg)
    parser.exit = parser_exit

    return parser


def join_lines(iterator):
    """
    Joins a line ending in '\' with the previous line.
    """
    lines = []
    for line in iterator:
        if not line.endswith('\\'):
            if lines:
                lines.append(line)
                yield ''.join(lines)
                lines = []
            else:
                yield line
        else:
            lines.append(line.strip('\\'))

    # TODO: handle space after '\'.
    # TODO: handle '\' on last line.


def ignore_comments(iterator):
    """
    Strips and filters empty or commented lines.
    """
    for line in iterator:
        line = COMMENT_RE.sub('', line)
        line = line.strip()
        if line:
            yield line


def skip_regex(lines, options):
    """
    Optionally exclude lines that match '--skip-requirements-regex'
    """
    skip_regex = options.skip_requirements_regex if options else None
    if skip_regex:
        lines = filterfalse(re.compile(skip_regex).search, lines)
    return lines
