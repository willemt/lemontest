.. code-block::
   :class: ignore

   🍋test /ˈlɛmən tɛst/ Noun.
    1. A test which appears to test a feature, but in fact does not test that feature at all. 
    [us. I reviewed that pull request and found one 🍋test that doesn't test right.]

What?
=====

A unittest runner for detecting 🍋tests.

Why?
====

Good development practice dictates that new features should be accompanied with new tests. Good tests can identify regressions and accidental removal of features.

A 🍋test, is a test which appears to test a feature, but in fact does not test that feature at all. 🍋tests can be considered worse than not having a test at all, because they give the false assumption that your new feature is tested. If a regression occurs, 🍋tests won't let you know. The detection of 🍋tests can identify situations when the feature does not meet your requirements. Detecting 🍋tests helps ensure code quality and feature delivery.

This library identifies 🍋tests. This is done by examining two git branches: the feature, and the merge destination. The algorithm separates business logic from testing code, and then uses Git to revert business logic to it's previous state (the same as the merge destination). A test suite is then run on the reverted business logic with the new tests. Any tests that are successful are marked as 🍋tests.

Testing for 🍋tests is a form of mutation testing. The mutation operation in this case is reverting the business logic to it's previous state before the feature was written.

Quickstart
==========

.. code-block:: bash
   :class: ignore

   pip install lemontest
   manage.py test --testrunner=lemontest.djangorunner.DjangoLemonTestRunner --to-branch=master --from-branch=feature/123

It must be a git repository.
----------------------------
Lemontest needs a git repository to be able to revert business logic.

Algorithm
=========

1. Get source files that have changed (git diff)

2. Identify test source files (use unittest discovery and intersect with step 1)

3. Identify business logic files (set difference between step 1 and step2)

4. Use git to revert business logic code (git checkout)

5. Run tests that have changed

6. Raise an exception for each test that succeeds
