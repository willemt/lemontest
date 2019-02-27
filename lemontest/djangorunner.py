import functools
import git
import os

from django.test.runner import DiscoverRunner

import lemontest


class DjangoLemonTestRunner(DiscoverRunner):
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
                                             to_branch=self.to_branch)
        super(DjangoLemonTestRunner, self).__init__(*args, **kwargs)

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

    def setup_test_environment(self, **kwargs):
        super(DjangoLemonTestRunner, self).setup_test_environment(**kwargs)

    def teardown_test_environment(self, **kwargs):
        super(DjangoLemonTestRunner, self).teardown_test_environment(**kwargs)

    def suite_result(self, suite, result, **kwargs):
        return len(result.failures) + len(result.errors)
