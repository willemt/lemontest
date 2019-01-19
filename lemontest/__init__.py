# -*- encoding: utf-8 -*-

import ast
import collections
import difflib
import inspect
import os
import unittest


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

    def __init__(self, repo=None, to_branch=None, from_branch=None, **kwargs):
        self.repo = repo
        self.to_branch = to_branch
        self.from_branch = from_branch
        super(LemonTestRunner, self).__init__(**kwargs)

    def run(self, suite):
        # Step 1. expected tests
        test_paths = suite2paths(suite)
        self.expected_tests = get_changed_tests(self.repo, self.from_branch, self.to_branch, test_paths)

        # Step 2. get business logic files
        paths = paths_that_changed(self.repo, self.from_branch, self.to_branch)
        business_logic_files = paths - test_paths

        # Step 3. revert business logic code
        for path in business_logic_files:
            self.repo.git.checkout(self.to_branch, path)

        # Step 4. run tests that changed
        new_suite = filter_out_tests(suite, self.expected_tests)

        # TODO: if no tests ran then raise an error (this should be optional via command line option)
        result = super(LemonTestRunner, self).run(new_suite)
        if not result.wasSuccessful():
            self.stream.write("\n")
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

    for test in suite:
        if isinstance(test, suite_class):
            filtered_suite.addTests(filter_out_tests(test, expected_tests))
        else:
            test_fn_name = getattr(test, '_testMethodName', str(test))
            class_name = test.__class__.__name__
            source_file = inspect.getsourcefile(test.__class__).replace(os.getcwd() + '/', '')
            if Test(source_file, class_name, test_fn_name) in expected_tests:
                filtered_suite.addTest(test)

    return filtered_suite


Test = collections.namedtuple('Test', ['path', 'class_name', 'method_name'])


def paths_that_changed(repo, from_branch, to_branch):
    return set(path for path, line_no in file_lines_that_changed(repo.commit(from_branch), repo.commit(to_branch)))


def get_changed_tests(repo, from_branch, to_branch, test_paths):
    expected_tests = set()
    asts_by_path = {}

    for path, line_no in file_lines_that_changed(repo.commit(from_branch), repo.commit(to_branch)):
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
