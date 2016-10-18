from __future__ import absolute_import

import logging
import tempfile
import os.path

from pip._vendor.six.moves.urllib import parse as urllib_parse
from pip._vendor.six.moves.urllib import request as urllib_request

from pip.utils import display_path, rmtree
from pip.vcs import vcs, VersionControl


urlsplit = urllib_parse.urlsplit
urlunsplit = urllib_parse.urlunsplit


logger = logging.getLogger(__name__)


class Git(VersionControl):
    name = 'git'
    dirname = '.git'
    repo_name = 'clone'
    schemes = (
        'git', 'git+http', 'git+https', 'git+ssh', 'git+git', 'git+file',
    )

    def __init__(self, url=None, *args, **kwargs):

        # Works around an apparent Git bug
        # (see http://article.gmane.org/gmane.comp.version-control.git/146500)
        if url:
            scheme, netloc, path, query, fragment = urlsplit(url)
            if scheme.endswith('file'):
                initial_slashes = path[:-len(path.lstrip('/'))]
                newpath = (
                    initial_slashes +
                    urllib_request.url2pathname(path)
                    .replace('\\', '/').lstrip('/')
                )
                url = urlunsplit((scheme, netloc, newpath, query, fragment))
                after_plus = scheme.find('+') + 1
                url = scheme[:after_plus] + urlunsplit(
                    (scheme[after_plus:], netloc, newpath, query, fragment),
                )

        super(Git, self).__init__(url, *args, **kwargs)

    def export(self, location):
        """Export the Git repository at the url to the destination location"""
        temp_dir = tempfile.mkdtemp('-export', 'pip-')
        self.unpack(temp_dir)
        try:
            if not location.endswith('/'):
                location = location + '/'
            self.run_command(
                ['checkout-index', '-a', '-f', '--prefix', location],
                show_stdout=False, cwd=temp_dir)
        finally:
            rmtree(temp_dir)

    def check_rev_options(self, rev, dest, rev_options):
        """Check the revision options before checkout to compensate that tags
        and branches may need origin/ as a prefix.
        Returns the SHA1 of the branch or tag if found.
        """
        revisions = self.get_refs(dest)

        origin_rev = 'origin/%s' % rev
        if origin_rev in revisions:
            # remote branch
            return [revisions[origin_rev]]
        elif rev in revisions:
            # a local tag or branch name
            return [revisions[rev]]
        else:
            logger.warning(
                "Could not find a tag or branch '%s', assuming commit.", rev,
            )
            return rev_options

    def switch(self, dest, url, rev_options):
        self.run_command(['config', 'remote.origin.url', url], cwd=dest)
        self.run_command(['checkout', '-q'] + rev_options, cwd=dest)

        self.update_submodules(dest)

    def update(self, dest, rev_options):
        # First fetch changes from the default remote
        self.run_command(['fetch', '-q'], cwd=dest)
        # Then reset to wanted revision (maby even origin/master)
        if rev_options:
            rev_options = self.check_rev_options(
                rev_options[0], dest, rev_options,
            )
        self.run_command(['reset', '--hard', '-q'] + rev_options, cwd=dest)
        #: update submodules
        self.update_submodules(dest)

    def obtain(self, dest):
        url, rev = self.get_url_rev()
        if rev:
            rev_options = [rev]
            rev_display = ' (to %s)' % rev
        else:
            rev_options = ['origin/master']
            rev_display = ''
        if self.check_destination(dest, url, rev_options, rev_display):
            logger.info(
                'Cloning %s%s to %s', url, rev_display, display_path(dest),
            )
            self.run_command(['clone', '-q', url, dest])

            if rev:
                rev_options = self.check_rev_options(rev, dest, rev_options)
                # Only do a checkout if rev_options differs from HEAD
                if not self.get_revision(dest).startswith(rev_options[0]):
                    self.run_command(
                        ['checkout', '-q'] + rev_options,
                        cwd=dest,
                    )
            #: repo may contain submodules
            self.update_submodules(dest)

    def get_url(self, location):
        url = self.run_command(
            ['config', 'remote.origin.url'],
            show_stdout=False, cwd=location)
        return url.strip()

    def get_revision(self, location):
        current_rev = self.run_command(
            ['rev-parse', 'HEAD'], show_stdout=False, cwd=location)
        return current_rev.strip()

    def get_refs(self, location):
        """Return map of named refs (branches or tags) to commit hashes."""
        output = self.run_command(['show-ref'],
                                  show_stdout=False, cwd=location)
        rv = {}
        for line in output.strip().splitlines():
            commit, ref = line.split(' ', 1)
            ref = ref.strip()
            ref_name = None
            if ref.startswith('refs/remotes/'):
                ref_name = ref[len('refs/remotes/'):]
            elif ref.startswith('refs/heads/'):
                ref_name = ref[len('refs/heads/'):]
            elif ref.startswith('refs/tags/'):
                ref_name = ref[len('refs/tags/'):]
            if ref_name is not None:
                rv[ref_name] = commit.strip()
        return rv

    def get_src_requirement(self, dist, location, find_tags):
        repo = self.get_url(location)
        if not repo.lower().startswith('git:'):
            repo = 'git+' + repo
        egg_project_name = dist.egg_name().split('-', 1)[0]
        if not repo:
            return None
        current_rev = self.get_revision(location)
        refs = self.get_refs(location)
        # refs maps names to commit hashes; we need the inverse
        # if multiple names map to a single commit, we pick the first one
        # alphabetically
        names_by_commit = {}
        for ref, commit in sorted(refs.items()):
            if commit not in names_by_commit:
                names_by_commit[commit] = ref

        if current_rev in names_by_commit:
            # It's a tag or branch.
            name = names_by_commit[current_rev]
            full_egg_name = (
                '%s-%s' % (egg_project_name, self.translate_egg_surname(name))
            )
        else:
            full_egg_name = '%s-dev' % egg_project_name

        return '%s@%s#egg=%s' % (repo, current_rev, full_egg_name)

    def get_url_rev(self):
        """
        Prefixes stub URLs like 'user@hostname:user/repo.git' with 'ssh://'.
        That's required because although they use SSH they sometimes doesn't
        work with a ssh:// scheme (e.g. Github). But we need a scheme for
        parsing. Hence we remove it again afterwards and return it as a stub.
        """
        if '://' not in self.url:
            assert 'file:' not in self.url
            self.url = self.url.replace('git+', 'git+ssh://')
            url, rev = super(Git, self).get_url_rev()
            url = url.replace('ssh://', '')
        else:
            url, rev = super(Git, self).get_url_rev()

        return url, rev

    def update_submodules(self, location):
        if not os.path.exists(os.path.join(location, '.gitmodules')):
            return
        self.run_command(
            ['submodule', 'update', '--init', '--recursive', '-q'],
            cwd=location,
        )

vcs.register(Git)
