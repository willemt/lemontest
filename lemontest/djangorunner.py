import functools
import git
import lemontest
import os
import subprocess
import sys

from django.test.runner import DiscoverRunner


class DjangoLemonTestRunner(DiscoverRunner):
    def __init__(self, from_branch=None, to_branch=None, repo_path=None, *args, **kwargs):
        self.to_branch = to_branch
        self.from_branch = from_branch

        repo_path = repo_path or os.getcwd()

        try:
            self.repo = git.Repo(repo_path or os.getcwd())
        except git.exc.InvalidGitRepositoryError:
            self.repo = git.Repo(os.path.join(repo_path, '..'))

        lemontest.LemonTestRunner.merge_and_checkout(
            self.repo, from_branch, to_branch)

        # The merge and checkout probably affected code we need. We could have
        # tried to reload all the code that could've been touched in this repo
        # but it's safer and simpler to just re-run the test suite
        cmds = list(sys.argv)
        cmds.insert(0, sys.executable)
        cmds.append('--testrunner=lemontest.djangorunner._DjangoLemonTestRunner')
        r = subprocess.call(cmds)
        exit(r)

    @classmethod
    def add_arguments(cls, parser):
        DiscoverRunner.add_arguments(parser)
        parser.add_argument(
            '-F', '--from-branch', action='store', default=None,
            help='The branch to test',
        )
        parser.add_argument(
            '-T', '--to-branch', action='store', default=None,
            help='The target branch to merge to',
        )
        parser.add_argument(
            '-R', '--repo-path', action='store', default=None,
            help='Path that the git repository is in',
        )
        parser.add_argument(
            '-Y', '--fail-if-no-tests-executed', action='store', default=None,
            help='Fail if no tests were executed',
        )

    def suite_result(self, suite, result, **kwargs):
        return len(result.failures) + len(result.errors)


class _DjangoLemonTestRunner(DjangoLemonTestRunner):
    def __init__(self, from_branch=None, to_branch=None, repo_path=None, *args, **kwargs):
        self.to_branch = to_branch
        self.from_branch = from_branch

        repo_path = repo_path or os.getcwd()

        try:
            self.repo = git.Repo(repo_path or os.getcwd())
        except git.exc.InvalidGitRepositoryError:
            self.repo = git.Repo(os.path.join(repo_path, '..'))

        self.test_runner = functools.partial(lemontest.LemonTestRunner,
                                             repo=self.repo,
                                             from_branch=self.from_branch,
                                             to_branch=self.to_branch,
                                             original_from_branch=self.from_branch)

        super(DjangoLemonTestRunner, self).__init__(*args, **kwargs)
