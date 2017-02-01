# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple
import logging
import pprint
import re

_logger = logging.getLogger(__name__)

# Possibe run outcomes
SuccessfulExecution = namedtuple("SuccessfulExecution", ["msg"])
ASanError = namedtuple("ASanError", ["msg", "type", "stack_trace"])
UBSanError = namedtuple("UBSanError", ["msg", "type", "stack_trace"])
AssertError = namedtuple("AssertError", ["msg", "condition", "stack_trace"])
AbortError = namedtuple("AbortError", ["msg", "stack_trace"])
ArithmeticError = namedtuple("ArithmeticError", ["msg", "stack_trace"])
UnknownError = namedtuple("UnknownError", ["msg", "raw_result_info"])
TimeoutError = namedtuple("TimeoutError", ["msg"])
OutOfMemoryError = namedtuple("OutOfMemoryError", ["msg"])
LibKleeRunTestError = namedtuple("LibKleeRunTestError", ["msg", "type"])

LIB_KLEE_RUN_TEST_ERROR_MSG_RE = re.compile(r"KLEE_RUN_TEST_ERROR: (.+)$")

def get_test_case_run_outcome(r):
    """
        Get an outcome for a run of a test case

        `r` a raw result info dictionary
    """
    assert isinstance(r, dict) # FIXME: Don't use raw form
    _logger.debug('Analysing:\n{}'.format(pprint.pformat(r)))
    invocation_info = r['invocation_info']

    if r['backend_timeout']:
        return TimeoutError(msg='Timeout hit running "{}" with "{}"'.format(
            invocation_info['program'],
            invocation_info['ktest_file']))

    if r['out_of_memory']:
        return OutOfMemoryError(msg='Memory limit hit running "{}" with "{}"'.format(
            invocation_info['program'],
            invocation_info['ktest_file']))

    if r['exit_code'] == 0:
        return SuccessfulExecution(msg='')

    # Look for libkleeruntest errors
    if r['exit_code'] == 1:
        log_file = r['log_file']
        _logger.debug('Opening log file "{}"'.format(log_file))
        with open(log_file, 'r') as f:
            for l in f:
                libkleeruntest_error_match = LIB_KLEE_RUN_TEST_ERROR_MSG_RE.search(l)
                if libkleeruntest_error_match:
                    type = libkleeruntest_error_match.group(1)
                    failure = LibKleeRunTestError(msg=l.strip(), type=type)
                    _logger.debug('Found LibkleeRuntest failure: {}'.format(failure))
                    return failure

    if invocation_info['attach_gdb']:
        return _get_outcome_attached_gdb(r)

    # Try for assert/abort without stacktrace (i.e. gdb was not attached)
    if r['exit_code'] == -6:
        # FIXME: This only works when using PythonPsUtil as the backend
        log_file = r['log_file']
        _logger.debug('Opening log file "{}"'.format(log_file))
        with open(log_file, 'r') as f:
            for l in f:
                assert_match = ASSERT_GDB_RE.search(l)
                if assert_match:
                    # Looks like an assertion failure
                    # FIXME: Parse the stack trace from gdb
                    condition = assert_match.group(1)
                    failure = AssertError(msg=l.strip(), condition=condition, stack_trace=None)
                    _logger.debug('Found assertion failure: {}'.format(failure))
                    return failure

        # Assume it was an abort
        failure = AbortError(msg="most likely an abort", stack_trace=None)
        _logger.debug('Found abort failure: {}'.format(failure))
        return failure

    # Try SIGFPE
    if r['exit_code'] == -8:
        failure = ArithmeticError(msg="Found SIGFPE", stack_trace=None)
        _logger.debug('Found arithmetic failure: {}'.format(failure))
        return failure

    # Try ubsan/asan builds
    if 'misc' in invocation_info:
        if 'bug_replay_build_type' in invocation_info['misc']:
            bug_replay_build_type = invocation_info['misc']['bug_replay_build_type']
            if bug_replay_build_type == 'ubsan':
                return _get_outcome_ubsan(r)
            elif bug_replay_build_type == 'asan':
                return _get_outcome_asan(r)

    # Unknown
    return UnknownError(
        msg='Could not identify exit of program with non-zero exit code',
        raw_result_info=r)

ASSERT_GDB_RE = re.compile(r": Assertion `(.+)' failed.\s*$")
ABORT_GDB_RE = re.compile(r"Program received signal SIGABRT")
SIGFPE_GDB_RE = re.compile(r"Program received signal SIGFPE")

def _get_outcome_attached_gdb(r):
    assert isinstance(r, dict) # FIXME: Don't use raw form
    invocation_info = r['invocation_info']
    assert invocation_info['attach_gdb']
    assert r['exit_code'] != 0

    # For now assume we are looking for abort and assertion failures
    log_file = r['log_file']
    _logger.debug('Opening log file "{}"'.format(log_file))
    with open(log_file, 'r') as f:
        # Walk through the lines trying to find assertion message
        # e.g.
        # non_terminating_klee_bug.x86_64: /home/user/fp-bench/benchmarks/c/imperial/synthetic/non-terminating/non-terminating.c:65: main: Assertion `false' failed.
        for l in f:
            assert_match = ASSERT_GDB_RE.search(l)
            if assert_match:
                # Looks like an assertion failure
                # FIXME: Parse the stack trace from gdb
                condition = assert_match.group(1)
                failure = AssertError(msg=l.strip(), condition=condition, stack_trace=None)
                _logger.debug('Found assertion failure: {}'.format(failure))
                return failure

            # NOTE: Be careful. assert failures call abort so we are assuming
            # that an assertion error message will come first
            abort_match = ABORT_GDB_RE.search(l)
            if abort_match:
                # Looks like abort() was called
                # FIXME: Parse the stack trace from gdb
                failure = AbortError(msg=l.strip(), stack_trace=None)
                _logger.debug('Found abort failure: {}'.format(failure))
                return failure
            sigfpe_match = SIGFPE_GDB_RE.search(l)
            if sigfpe_match:
                # FIXME: Parse the stack trace from gdb
                failure = ArithmeticError(msg=l.strip(), stack_trace=None)
                _logger.debug('Found abort failure: {}'.format(failure))
                return failure

    raise Exception('GDB: unhandled case')

UBSAN_EXIT_CODE_RE = re.compile(r"exitcode=(\d+)")
UBSAN_RUNTIME_ERROR_RE = re.compile(r"runtime error: (.+)$")
def _get_outcome_ubsan(r):
    assert isinstance(r, dict) # FIXME: Don't use raw form
    assert r['exit_code'] != 0
    invocation_info = r['invocation_info']

    # Parse out the excepted exit code
    expected_exit_code = None
    if 'UBSAN_OPTIONS' in invocation_info['environment_variables']:
        ubsan_options = invocation_info['environment_variables']['UBSAN_OPTIONS']
        exit_code_match = UBSAN_EXIT_CODE_RE.search(ubsan_options)
        if exit_code_match:
            expected_exit_code = int(exit_code_match.group(1))
            if expected_exit_code != r['exit_code']:
                raise Exception('UBSan: Unhandled case')

    # Look for runtime error
    log_file = r['log_file']
    _logger.debug('Opening log file "{}"'.format(log_file))
    with open(log_file, 'r') as f:
        for l in f:
            runtime_error_match = UBSAN_RUNTIME_ERROR_RE.search(l)
            if runtime_error_match:
                type = runtime_error_match.group(1)
                # FIXME: parse out stack trace
                failure = UBSanError(msg=l.strip(), type=type, stack_trace=None)
                _logger.debug('Found ubsan failure: {}'.format(failure))
                return failure

    raise Exception('UBSan: Unhandled case')


ASAN_EXIT_CODE_RE = re.compile(r"exitcode=(\d+)")
ASAN_ERROR_MSG_RE = re.compile(r"AddressSanitizer: ([a-zA-z-]+)")

def _get_outcome_asan(r):
    assert isinstance(r, dict) # FIXME: Don't use raw form
    assert r['exit_code'] != 0
    invocation_info = r['invocation_info']

    # Parse out the excepted exit code
    expected_exit_code = None
    if 'ASAN_OPTIONS' in invocation_info['environment_variables']:
        asan_options = invocation_info['environment_variables']['ASAN_OPTIONS']
        exit_code_match = ASAN_EXIT_CODE_RE.search(asan_options)
        if exit_code_match:
            expected_exit_code = int(exit_code_match.group(1))
            if expected_exit_code != r['exit_code']:
                raise Exception('ASan: Unhandled case')
    # Look for ASan error message. E.g.
    # AddressSanitizer: stack-buffer-overflow on address
    log_file = r['log_file']
    _logger.debug('Opening log file "{}"'.format(log_file))
    with open(log_file, 'r') as f:
        for l in f:
            asan_error_msg_match = ASAN_ERROR_MSG_RE.search(l)
            if asan_error_msg_match:
                type = asan_error_msg_match.group(1)
                # FIXME: parse out stack trace
                failure = ASanError(msg=l.strip(), type=type, stack_trace=None)
                _logger.debug('Found asan failure: {}'.format(failure))
                return failure
    raise Exception('ASan: Unhandled case')
