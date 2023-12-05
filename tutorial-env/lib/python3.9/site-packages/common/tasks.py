# -*- coding: utf-8 -*-
"""
Read the Docs common tasks.

This is used from a repository that uses the common repository. You can see what
tasks are available with::

    invoke -l

To get more info on tasks::

    invoke -h setup-labels
"""

import glob
import os
import textwrap
from collections import namedtuple

from configparser import RawConfigParser, NoSectionError
from invoke import task, Exit


REPO_PATH = os.path.dirname(os.path.dirname(__file__))
SETUP_SECTION = 'tool:release'

# Label class used below for setup-labels
Label = namedtuple('Label', ['name', 'color', 'desc', 'transpose'])


@task
def prepare(ctx, version, path=REPO_PATH, since=None):
    """
    Prepare the next release version by updating files.

    This will stage a few updates for manual review and commit:

    * Prepend the most recent PRs and issues that were closed to CHANGELOG.rst.
    * Update the setup.cfg version

    Changelog uses the file modification date to track the last time it was
    updated.  New entries will end up at the top of the file, under a heading
    for the new version.
    """

    try:
        from dateutil.parser import parse
    except ImportError:
        print('You need to install `python-dateutil` package: "pip install python-dateutil"')
        raise Exit(1)

    print('Updating release version in setup.cfg')
    setupcfg_path = os.path.join(path, 'setup.cfg')
    config = RawConfigParser()
    config.read(setupcfg_path)

    release_config = get_config(config)
    if release_config['github_private'] and 'GITHUB_TOKEN' not in os.environ.keys():
        print('\n'.join(textwrap.wrap(
            'In order to grab pull request information from a private repository '
            'you will need to set the GITHUB_TOKEN env variable with a personal '
            'access token from GitHub.'
        )))
        return False

    # Set the release number
    # config.set('metadata', 'version', version)
    # with open(setupcfg_path, 'w') as configfile:
    #     config.write(configfile)

    # Install and run
    print('Installing github-changelog')
    ctx.run('npm install --no-package-lock git+https://github.com/agjohnson/github-changelog.git')
    if not since:
        # Get last modified date from Git instead of assuming the file metadata is
        # correct. This can change depending on git reset, etc.
        git_log = ctx.run('git log -1 --format="%ad" -- CHANGELOG.rst')
        since = parse(git_log.stdout.strip()).strftime('%Y-%m-%d')
    changelog_path = os.path.join(path, 'CHANGELOG.rst')
    template_path = os.path.join(
        path,
        'common',
        'changelog.hbs',
    )
    bin_path = os.path.join(path, 'node_modules', '.bin')
    cmd = (
        '{bin_path}/gh-changelog '
        '-o {owner} -r {repository} '
        '--file {changelog_path} '
        '--since {since} '
        '--template {template_path} '
        '--header "Version {version}" '
        '--merged '
    ).format(
        bin_path=bin_path,
        owner='readthedocs',
        repository='sphinx-notfound-page',
        version=version,
        template_path=template_path,
        changelog_path=changelog_path,
        since=since,
    )  # yapf: disable
    try:
        token = os.environ['GITHUB_TOKEN']
        cmd += '--token ' + token + ' '
    except KeyError:
        print('')
        print(
            '\n'.join(
                textwrap.wrap(
                    'In order to avoid rate limiting on the GitHub API, you can specify '
                    'an environment variable `GITHUB_TOKEN` with a personal access token. '
                    'There is no need for the token to have any permissions unless the '
                    'repoistory is private.')))
        print('')
    print(cmd)
    print('Updating changelog')
    ctx.run(cmd)


@task
def release(ctx, version):
    """
    Tag release of Read the Docs.

    Do this after prepare task and manual cleanup/commit
    """
    # Ensure we're on the master branch first
    git_rev_parse = ctx.run('git rev-parse --abbrev-ref HEAD', hide=True)
    current_branch = git_rev_parse.stdout.strip()
    if current_branch != 'master':
        print('You must be on master branch!')
        raise Exit(1)
    ctx.run(
        ('git tag {version} && '
         'git push --tags').format(version=version))


def get_config(config=None):
    release_config = {
        'github_owner': 'rtfd',
        'github_private': False,
    }

    if config is None:
        config = RawConfigParser()

        setupcfg_path = os.path.join(REPO_PATH, 'setup.cfg')
        if not os.path.exists(setupcfg_path):
            print(
                'Missing setup.cfg! '
                'Make sure you are running invoke from your repository path.'
            )
            return False
        config.read(setupcfg_path)

    try:
        release_config.update(config.items(SETUP_SECTION))
    except NoSectionError:
        pass

    return release_config


@task
def setup_labels(ctx, repo, dry_run=False):
    """Setup shared repository labels

    You can specify ``--dry-run/-d`` in order to avoid making changes
    immediately. Note that the actual actions will differ on a live run as the
    list of labels is polled twice.
    """
    try:
        from github import Github, GithubException
    except ImportError:
        print('Python package PyGithub is missing.')
        return False

    if 'GITHUB_TOKEN' not in os.environ.keys():
        print('\n'.join(textwrap.wrap(
            'GITHUB_TOKEN env variable is required. Set up a personal token here:\n'
            'https://github.com/settings/tokens'
        )))
        return False

    # Current base for labels across repos
    labels = [
        Label('Accepted', '10ff91', 'Accepted issue on our roadmap', []),
        Label('Bug', 'FF666E', 'A bug', ['bug']),
        Label('Design', 'e10c02', 'Design or UX/UI related', []),
        Label('Feature', '5319e7', 'New feature', ['Feature Overview']),
        Label('Good First Issue', 'bfe5bf', 'Good for new contributors', ['good first issue']),

        Label('Improvement', 'e2419d', 'Minor improvement to code', ['enhancement', 'Enhancement']),

        Label('Needed: design decision', '54473F', 'A core team decision is required', []),
        Label('Needed: documentation', '54473F', 'Documentation is required', []),
        Label('Needed: more information', '54473F', 'A reply from issue author is required', []),
        Label('Needed: patch', '54473F', 'A pull request is required', []),
        Label('Needed: replication', '54473F', 'Bug replication is required', []),
        Label('Needed: tests', '54473F', 'Tests are required', []),

        Label('Operations', '0052cc', 'Operations or server issue', []),

        Label('PR: hotfix', 'fbca04', 'Pull request applied as hotfix to release', []),
        Label('PR: work in progress', 'F0EDF9', 'Pull request is not ready for full review', []),

        Label('Priority: high', 'e11d21', 'High priority', ['High Priority', 'Priority: High']),
        Label('Priority: low', '4464d6', 'Low priority', ['Priority: Low']),

        Label('Sprintable', 'fef2c0', 'Small enough to sprint on', []),

        Label('Status: blocked', 'd0d0c0', 'Issue is blocked on another issue', []),
        Label('Status: stale', 'd0d0c0', 'Issue will be considered inactive soon', []),

        Label('Support', '5494E8', 'Support question', ['question', 'Question']),
    ]

    # Labels we determined we don't use
    delete_labels = [
        'duplicate',
        'help wanted',
        'invalid',
        'wontfix',
        'PR: ready for review',
        'Status: duplicate',
        'Status: invalid',
        'Status: rejected',
    ]

    api = Github(os.environ.get('GITHUB_TOKEN'))
    repo = api.get_repo(repo)

    # First pass: create expected labels, try to repurpose old labels if
    # possible first.
    try:
        existing_labels = list(repo.get_labels())
    except GithubException:
        print('Repository not found, check that `repo` argument is correct')
        return False
    for label in labels:
        found = None

        for existing_label in existing_labels:
            if label.name == existing_label.name:
                found = existing_label
                break
        if not found:
            for existing_label in existing_labels:
                if existing_label.name in label.transpose:
                    found = existing_label
                    break

        # Modify or create a new label. We can't detect changes here as
        # description is never available on the label object
        if found:
            print('Updating label: {0}'.format(found.name))
            if not dry_run:
                found.edit(label.name, label.color, label.desc)
        else:
            print('Creating label: {0}'.format(label.name))
            if not dry_run:
                repo.create_label(label.name, label.color, label.desc)

    # Second pass, we:
    #
    # * Labels that should be deleted
    # * Labels that can't be transpose directly, issues need to be moved
    # * Notes unknown labels
    untouched = set()
    for label in repo.get_labels():
        if label.name in delete_labels:
            print('Deleting label: {0}'.format(label.name))
            if not dry_run:
                label.delete()
        elif label.name in [l.name for l in labels]:
            pass
        else:
            transpose = False
            for our_label in labels:
                if label.name in our_label.transpose:
                    for issue in repo.get_issues(labels=[label]):
                        print('Adding label for issue: issue={0} label={1}'.format(
                            issue,
                            our_label.name,
                        ))
                        if not dry_run:
                            issue.add_to_labels(our_label.name)
                    print('Deleting label: {0}'.format(label.name))
                    if not dry_run:
                        label.delete()
                    transpose = True
                    break

            if not transpose:
                untouched.add(label)

    if untouched:
        print('Did not do anything with the following labels:')
        for label in untouched:
            print(' - {0}'.format(label.name))


@task(name='upgrade')
def upgrade_all_packages(ctx, skip=False, patch=False, packages=None):
    """
    Upgrade all the packages listed in all ``requirements/*.txt`` files.

    This task only upgrades the versions of the packages in the text files, but
    do not perform the action to effectively upgrade them in the system.

    The task is used to keep Read the Docs updated and find potential
    incompatibilities with newer versions and take advantage of the latest
    securities releases.
    """
    try:
        import pur
    except ImportError:
        print('You need to install `pur` package: "pip install pur"')
        raise Exit(1)

    if patch and not skip:
        method = '--patch'
    elif skip and not patch:
        method = '--skip'
    elif not skip and not patch:
        # default
        method = '--skip'
    else:
        print("You can't use --patch and --skip together.")
        raise Exit(1)

    command_template = 'pur {method} {packages} --requirement {reqfile}'

    # We only upgrade these packages for the patch version of them because we
    # found there are some incompatibilities with the following versions. See
    # each .txt file to know the reasons.
    if packages is None:
        packages = (
            'redis',
            'commonmark',
            'django',
            'docker',
            'celery',
            'gitpython',
            'elasticsearch',
            'pyelasticsearch',
            'mercurial',
        )
        packages = ','.join(packages)

    for reqfile in glob.glob('requirements/*.txt'):
        cmd = command_template.format(packages=packages, reqfile=reqfile, method=method)
        print('Running: {}'.format(cmd))
        ctx.run(cmd)
