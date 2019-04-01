# -*- encoding: utf-8 -*-

import ast
import collections
import difflib
import inspect
import itertools
import logging
import os
import unittest
import uuid


logger = logging.getLogger(__name__)
logging.disable(logging.NOTSET)
logger.setLevel(os.environ.get('LOGLEVEL', 'WARNING').upper())


__all__ = [
    'LemonTestSuite',
    'LemonTestRunner',
    'LemonTestResult',
    ]


def changed_lines(a, b):
    d = difflib.Differ()
    diffs = d.compare(a.split('\n'), b.split('\n'))
    lineNum = 0
    for line in diffs:
        code = line[:2]
        if code in ("  ", "+ "):
            lineNum += 1
        if code == "+ ":
            yield lineNum, line[2:].strip()


def file_lines_that_changed(head, origin):
    """
    Get the files that changed between these two branches
    Yield (file_path, line_number) tuples
    """

    diff_index = origin.diff(head)

    # FIXME: need to handle creation of new files

    for diff_item in diff_index.iter_change_type('M'):
        a = diff_item.a_blob.data_stream.read().decode('utf-8')
        b = diff_item.b_blob.data_stream.read().decode('utf-8')

        for line in changed_lines(a, b):
            yield diff_item.a_path, line[0]


class VisitorParentRecorder(ast.NodeVisitor):
    """
    Visit all nodes
    Record the parent of the node
    """

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        try:
                            item.parent = node
                        except AttributeError:
                            pass
                        self.visit(item)
            elif isinstance(value, ast.AST):
                try:
                    value.parent = node
                except AttributeError:
                    pass
                self.visit(value)


def get_class_name(node):
    if isinstance(node, ast.ClassDef):
        return node.name
    else:
        return get_class_name(node.parent)


def get_class_and_method_name(node):
    if isinstance(node, ast.FunctionDef):
        return get_class_name(node), node.name
    else:
        return get_class_and_method_name(node.parent)


class LineNumberVisitor(VisitorParentRecorder):
    """
    Only visit these AST nodes that are on these line numbers
    Record a list of (class_name, method_name)
    TODO: rename to test visitor
    """

    def __init__(self, record_linenos=set()):
        self.record_linenos = record_linenos
        self.class_methods = set()

    def generic_visit(self, node):
        if getattr(node, 'lineno', '') in self.record_linenos:
            try:
                class_name, method_name = get_class_and_method_name(node)
            except AttributeError:
                pass
            else:
                self.class_methods.add((class_name, method_name))
        else:
            super(LineNumberVisitor, self).generic_visit(node)


class LemonTestSuite(unittest.TestSuite):
    pass


class LemonTestResult(unittest.TextTestResult):
    """
    Errors/Failures are successes
    Successes are failures
    """

    @unittest.result.failfast
    def addError(self, test, err):
        pass

    @unittest.result.failfast
    def addFailure(self, test, err):
        pass

    def addSuccess(self, test):
        self.failures.append((test, ''))
        self._mirrorOutput = True


class LemonTestRunner(unittest.TextTestRunner):
    resultclass = LemonTestResult

    def __init__(self, repo=None, to_branch=None, from_branch=None, original_from_branch=None, **kwargs):
        self.repo = repo
        self.to_branch = to_branch
        self.from_branch = from_branch
        self.original_from_branch = original_from_branch

        # FIXME: should respect --top-level-directory
        # Change directory so that git path's match test runner's path
        os.chdir(self.repo.working_tree_dir)

        super(LemonTestRunner, self).__init__(**kwargs)

    @staticmethod
    def merge_and_checkout(repo, from_branch, to_branch):
        """
        Merge these branches together and checkout the resulting branch
        """
        to_commit = repo.commit(to_branch)

        # We need to merge the "to" branch into the "from" branch to ensure
        # the diff works properly and scopes the correct tests
        repo.git.checkout(from_branch)
        new_branch = repo.create_head(str(uuid.uuid4()), from_branch)
        new_branch.checkout()

        # merge "to" into "from"^
        merge_base = repo.merge_base(new_branch, to_commit)
        repo.index.merge_tree(to_commit, base=merge_base)
        from_commit = repo.index.commit(
            "Merge",
            parent_commits=(new_branch.commit, to_commit))
        repo.git.checkout(from_commit)

        # For some reason there's still some dirty files
        repo.head.reset(index=True, working_tree=True)

        # Use this as our NEW "from" branch
        return str(from_commit)

    def run(self, suite):
        self.stream.writeln('Running Lemon test')
        self.stream.writeln('-' * 70)

        # Step 1. relevant tests
        test_paths = suite2paths(suite)
        self.expected_tests = get_changed_tests(
            self.repo, self.from_branch, self.to_branch, test_paths)
        if self.verbosity >= 3:
            print('Tests detected in paths:\n  {}'.format('\n  '.join(sorted(test_paths))))
            print('Expected tests:\n  {}'.format('\n  '.join(sorted(self.expected_tests))))

        # Step 2. get business logic files
        paths = paths_that_changed(self.repo, self.from_branch, self.to_branch)
        paths = set(filter(lambda x: x.endswith('.py'), paths))
        business_logic_files = sorted(paths - test_paths)

        # Step 3. revert business logic code
        for path in business_logic_files:
            self.repo.git.checkout(self.to_branch, path)

        # Step 4. run tests that changed
        new_suite, inscope_tests = filter_out_tests(suite, self.expected_tests)

        # Step 5. remove new branch (clean up)
        # TODO

        # Diagnostics
        self.stream.writeln('To commit:\n  {}'.format(str(self.repo.commit(self.to_branch))))
        self.stream.writeln('')

        self.stream.writeln('From commit:\n  {}'.format(str(self.repo.commit(self.original_from_branch))))
        self.stream.writeln('')

        self.stream.writeln('Changed files:\n  {}'.format('\n  '.join(paths)))
        self.stream.writeln('')

        self.stream.writeln('Relevant tests:')
        sorted_tests = sorted(inscope_tests, key=lambda x: (x.path, x.class_name, x.method_name))
        for path, tests in itertools.groupby(sorted_tests, key=lambda x: x.path):
            self.stream.writeln('  {}:'.format(path))
            for class_name, _tests in itertools.groupby(tests, key=lambda x: x.class_name):
                self.stream.writeln('    {}:'.format(class_name))
                for test in _tests:
                    self.stream.writeln('      {}'.format(test.method_name))
        self.stream.writeln('')

        self.stream.writeln('Business logic:\n  {}'.format('\n  '.join(business_logic_files)))
        self.stream.writeln('')

        # TODO: if no tests ran then raise an error (this should be optional via command line option)
        result = super(LemonTestRunner, self).run(new_suite)
        if not result.wasSuccessful():
            self.stream.write("🍋 test(s) detected:\n")
            self.stream.write("""
    This test runner has detected 🍋 test(s). The test runner has reverted
    the "business logic" within this branch via "git checkout" and has run the
    test suite again. Test(s) were detected as having passed successfully,
    whereas this test runner had expected them to fail (because the business
    logic has been reverted).

    Recommendation: update the test so that it fails as if the business logic
    has never been written (ie. red/green/refactor).\n
""")
        return result


def suite2paths(suite):
    suite_class = type(suite)
    paths = set()
    for test in suite:
        if isinstance(test, suite_class):
            paths = paths.intersect(suite2paths(test))
        else:
            source_file = inspect.getsourcefile(test.__class__).replace(os.getcwd() + '/', '')
            paths.add(source_file)
    return paths


def filter_out_tests(suite, expected_tests):
    """
    Filter out the tests that aren't within expected_tests
    """
    suite_class = type(suite)
    filtered_suite = suite_class()
    inscope_tests = set()

    for test in suite:
        if isinstance(test, suite_class):
            suite, _inscope_tests = filter_out_tests(test, expected_tests)
            inscope_tests = inscope_tests | _inscope_tests
            filtered_suite.addTests(suite)
        else:
            test_fn_name = getattr(test, '_testMethodName', str(test))
            class_name = test.__class__.__name__
            source_file = inspect.getsourcefile(test.__class__).replace(os.getcwd() + '/', '')
            test_test = Test(source_file, class_name, test_fn_name)
            if test_test in expected_tests:
                inscope_tests.add(test_test)
                filtered_suite.addTest(test)

    return filtered_suite, inscope_tests


class Test(collections.namedtuple('Test', ['path', 'class_name', 'method_name'])):
    __slots__ = ()

    def __str__(self):
        return '{}:{}.{}'.format(self.path, self.class_name, self.method_name)


def paths_that_changed(repo, from_branch, to_branch):
    return set(path for path, line_no in file_lines_that_changed(repo.commit(from_branch), repo.commit(to_branch)))


def get_changed_tests(repo, from_branch, to_branch, test_paths):
    expected_tests = set()
    asts_by_path = {}

    head = repo.commit(from_branch)
    origin = repo.commit(to_branch)

    for path, line_no in file_lines_that_changed(head, origin):
        if path.endswith('.py') and path in test_paths:
            try:
                module_ast = asts_by_path[path]
            except KeyError:
                module_ast = ast.parse(open(path, 'r').read(), filename=path, mode='exec')
                asts_by_path[path] = module_ast

            v = LineNumberVisitor(record_linenos=set([line_no]))
            v.visit(module_ast)

            for class_name, method_name in v.class_methods:
                expected_tests.add(Test(path, class_name, method_name))

    return expected_tests
