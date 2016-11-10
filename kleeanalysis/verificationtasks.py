# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Implementations for the various verification tasks.
"""
from collections import namedtuple
import logging
import os
import pprint

from .kleedir.kleedir import KleeDir

_logger = logging.getLogger(__name__)


def _fail_generator(spec: "A failure specification", failures: "An iterable list of failures", task_name, early_terminations):
    if failures is None:
        raise Exception("Hell")
    # FIXME: Handle missing counter example and exhaustive keyword
    expectCorrect = spec["correct"]
    assert expectCorrect == True or expectCorrect == False
    counterExamplesAreExhaustive = False
    if 'exhaustive_counter_examples' in spec and spec['exhaustive_counter_examples'] is True:
        counterExamplesAreExhaustive = True

    allowed_failures = {}
    if "counter_examples" in spec:
        for cex in spec["counter_examples"]:
            for loc in cex["locations"]:
                if loc["file"] not in allowed_failures:
                    allowed_failures[loc["file"]] = set()
                allowed_failures[loc["file"]].add(int(loc["line"]))
    _logger.debug('Allowed failures for task {}: {}'.format(
        task_name,
        pprint.pformat(allowed_failures)))
    if expectCorrect and len(allowed_failures) > 0:
        raise Exception("A failure that must not happen, but has counterexamples makes no sense")

    actual_failures = [] # Mismatches against the spec
    warnings = [] # List of tuples (<warning message>, <test>)
    inconclusive_tests = []

    for fail in failures:
        _logger.debug('Considering failure:\n{}\n'.format(fail))
        # The file path in failure is absolute (e.g. `/path/to/file.c`) where
        # as the spec will have `file.c` so we need to check if `/file.c` is a
        # suffix of the error path.
        assert os.path.isabs(fail.error.file)
        allowed_failure_file = None
        for af in allowed_failures.keys():
            assert not af.startswith('/')
            suffix = '/{}'.format(af)
            if fail.error.file.endswith(suffix):
                allowed_failure_file = af
                break

        # Logic for handling mismatch is a nested function
        # so we can re-use the logic
        def handleMisMatchAgainstCounterExample():
            if expectCorrect:
                _logger.debug(
                    'The benchmark is expected to be correct so this is '
                    'a real failure')
                actual_failures.append(fail)
            else:
                # FIXME: Is this the right way to handle this!?
                # The benchmark is expected to be incorrect but the test
                # showing incorrectness doesn't match any counter example we
                # know about.
                assert expectCorrect is False
                if counterExamplesAreExhaustive:
                    # This is kind of weird. It's a different sort of failure.
                    _logger.debug('The list of counter examples are supposed'
                        ' to be exhaustive but another has been found so treat'
                        ' this as a failure')
                    actual_failures.append(fail)
                else:
                    warning_msg = ('An expected failure for task "{}" was'
                        ' observed but the test case does not match any known'
                        ' counter examples.').format(task_name)
                    _logger.warning(warning_msg)
                    warnings.append( (warning_msg, fail) )

        if allowed_failure_file is None:
            _logger.debug(('"{}" is not in allowed failures. This is not a '
                'failure that the spec expects').format(fail.error.file))
            handleMisMatchAgainstCounterExample()
            continue
        if fail.error.line not in allowed_failures[allowed_failure_file]:
            _logger.debug(('"{}" is in allowed failures. But the error line for'
                ' this failure ({}) is not expected by the spec'
                '(expected lines:{})').format(
                    fail.error.file,
                    fail.error.line,
                    allowed_failures[allowed_failure_file]))
            handleMisMatchAgainstCounterExample()
            continue
        # Appears to be an allowed failure
        _logger.debug('{}:{} appears to be an allowed failure'.format(
            fail.error.file,
            fail.error.line))

    # FIXME: This sucks and is confusing we need to separate the logic
    # of knowing if a benchmark is correct w.r.t a property and whether or
    # not that matches the spec.
    # Handle early terminations. If they exist and there are no actual
    # failures or expected failures then we can't conclude that the results
    # match the spec. This matte
    #
    # - Have early terminations, spec expected correct but no counter examples
    # - Have early terminations, spec expecte
    early_terminations_list = list(early_terminations)
    if len(early_terminations_list) > 0:
        if len(actual_failures) == 0 and len(warnings) == 0:
            inconclusive_tests = early_terminations_list

    return actual_failures, warnings, inconclusive_tests

# FIXME: Verifying the spec and getting the relevant KLEE test cases shouldn't be coupled together. We should
# be able to gather the relevant tests for a verification task and then separately report if they match the spec
# or not.
TASKS = {
    "no_assert_fail": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.assertion_errors, task_name, kleedir.early_terminations),
    "no_integer_division_by_zero": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.division_errors, task_name, kleedir.early_terminations),
    "no_invalid_deref": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.ptr_errors, task_name, kleedir.early_terminations),
    "no_invalid_free": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.free_errors, task_name, kleedir.early_terminations),
    "no_overshift": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.overshift_errors, task_name, kleedir.early_terminations),
    "no_reach_error_function": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.abort_errors, task_name, kleedir.early_terminations)
}


# All of the above needs to die. What's below is the new code
# that will replace it.

fp_bench_tasks = {
    "no_assert_fail",
    "no_integer_division_by_zero",
    "no_invalid_deref",
    "no_invalid_free",
    "no_overshift",
    "no_reach_error_function",
}

# FIXME: This is fp-bench specific and should be moved into fp-bench's infrastructure.
def get_cex_test_cases_for_fp_bench_task(task, klee_dir):
    """
        Returns a list of test cases that are counter examples
        to fp-bench verification tasks being correct.
    """
    assert isinstance(task, str)
    assert isinstance(klee_dir, KleeDir)
    test_cases = []
    if task == "no_assert_fail":
        test_cases.extend(klee_dir.assertion_errors)
    elif task == "no_integer_division_by_zero":
        test_cases.extend(klee_dir.division_errors)
    elif task == "no_invalid_deref":
        test_cases.extend(klee_dir.ptr_errors)
    elif task == "no_invalid_free":
        test_cases.extend(klee_dir.free_errors)
    elif task == "no_overshift":
        test_cases.extend(klee_dir.overshift_errors)
    elif task == "no_reach_error_function":
        test_cases.extend(klee_dir.abort_errors)
    else:
        raise Exception('Unknown task "{}"'.format(task))
    return test_cases


