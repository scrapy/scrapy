from __future__ import absolute_import

import logging
import os
import tempfile
import re

from pip.utils import display_path, rmtree
from pip.vcs import vcs, VersionControl
from pip.download import path_to_url
from pip._vendor.six.moves import configparser


logger = logging.getLogger(__name__)


class Mercurial(VersionControl):
    name = 'hg'
    dirname = '.hg'
    repo_name = 'clone'
    schemes = ('hg', 'hg+http', 'hg+https', 'hg+ssh', 'hg+static-http')

    def export(self, location):
        """Export the Hg repository at the url to the destination location"""
        temp_dir = tempfile.mkdtemp('-export', 'pip-')
        self.unpack(temp_dir)
        try:
            self.run_command(
                ['archive', location], show_stdout=False, cwd=temp_dir)
        finally:
            rmtree(temp_dir)

    def switch(self, dest, url, rev_options):
        repo_config = os.path.join(dest, self.dirname, 'hgrc')
        config = configparser.SafeConfigParser()
        try:
            config.read(repo_config)
            config.set('paths', 'default', url)
            with open(repo_config, 'w') as config_file:
                config.write(config_file)
        except (OSError, configparser.NoSectionError) as exc:
            logger.warning(
                'Could not switch Mercurial repository to %s: %s', url, exc,
            )
        else:
            self.run_command(['update', '-q'] + rev_options, cwd=dest)

    def update(self, dest, rev_options):
        self.run_command(['pull', '-q'], cwd=dest)
        self.run_command(['update', '-q'] + rev_options, cwd=dest)

    def obtain(self, dest):
        url, rev = self.get_url_rev()
        if rev:
            rev_options = [rev]
            rev_display = ' (to revision %s)' % rev
        else:
            rev_options = []
            rev_display = ''
        if self.check_destination(dest, url, rev_options, rev_display):
            logger.info(
                'Cloning hg %s%s to %s',
                url,
                rev_display,
                display_path(dest),
            )
            self.run_command(['clone', '--noupdate', '-q', url, dest])
            self.run_command(['update', '-q'] + rev_options, cwd=dest)

    def get_url(self, location):
        url = self.run_command(
            ['showconfig', 'paths.default'],
            show_stdout=False, cwd=location).strip()
        if self._is_local_repository(url):
            url = path_to_url(url)
        return url.strip()

    def get_tag_revs(self, location):
        tags = self.run_command(['tags'], show_stdout=False, cwd=location)
        tag_revs = []
        for line in tags.splitlines():
            tags_match = re.search(r'([\w\d\.-]+)\s*([\d]+):.*$', line)
            if tags_match:
                tag = tags_match.group(1)
                rev = tags_match.group(2)
                if "tip" != tag:
                    tag_revs.append((rev.strip(), tag.strip()))
        return dict(tag_revs)

    def get_branch_revs(self, location):
        branches = self.run_command(
            ['branches'], show_stdout=False, cwd=location)
        branch_revs = []
        for line in branches.splitlines():
            branches_match = re.search(r'([\w\d\.-]+)\s*([\d]+):.*$', line)
            if branches_match:
                branch = branches_match.group(1)
                rev = branches_match.group(2)
                if "default" != branch:
                    branch_revs.append((rev.strip(), branch.strip()))
        return dict(branch_revs)

    def get_revision(self, location):
        current_revision = self.run_command(
            ['parents', '--template={rev}'],
            show_stdout=False, cwd=location).strip()
        return current_revision

    def get_revision_hash(self, location):
        current_rev_hash = self.run_command(
            ['parents', '--template={node}'],
            show_stdout=False, cwd=location).strip()
        return current_rev_hash

    def get_src_requirement(self, dist, location, find_tags):
        repo = self.get_url(location)
        if not repo.lower().startswith('hg:'):
            repo = 'hg+' + repo
        egg_project_name = dist.egg_name().split('-', 1)[0]
        if not repo:
            return None
        current_rev = self.get_revision(location)
        current_rev_hash = self.get_revision_hash(location)
        tag_revs = self.get_tag_revs(location)
        branch_revs = self.get_branch_revs(location)
        if current_rev in tag_revs:
            # It's a tag
            full_egg_name = '%s-%s' % (egg_project_name, tag_revs[current_rev])
        elif current_rev in branch_revs:
            # It's the tip of a branch
            full_egg_name = '%s-%s' % (
                egg_project_name,
                branch_revs[current_rev],
            )
        else:
            full_egg_name = '%s-dev' % egg_project_name
        return '%s@%s#egg=%s' % (repo, current_rev_hash, full_egg_name)

vcs.register(Mercurial)
