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

# FIXME: This is fp-bench specific and should be moved into fp-bench's infrastructure.

fp_bench_tasks = {
    "no_assert_fail",
    "no_integer_division_by_zero",
    "no_invalid_deref",
    "no_invalid_free",
    "no_overshift",
    "no_reach_error_function",
}

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


