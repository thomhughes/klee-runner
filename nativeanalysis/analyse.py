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

# \1 function name
# \2 library
GDB_IN_FROM_STACKFRAME = re.compile(r"#\d+\s+([A-Za-z0-9_]+)\s+\(.*\)\s+from\s+(.+)")
# \1 function name
# \2 source file
# \3 line number
GDB_IN_AT_STACKFRAME = re.compile(r"#\d+\s+([A-Za-z0-9_]+)\s+\(.*\)\s+at\s+(.+):(\d+)")

class StackFrame:
    def __init__(self, fn_name, lib=None, source_file=None, line_number=None):
        assert isinstance(fn_name, str)
        assert len(fn_name) > 0
        if lib is not None:
            assert isinstance(lib, str)
            assert len(lib) > 0
        else:
            assert isinstance(source_file, str)
            assert len(source_file) > 0
            assert isinstance(line_number, int)
            assert line_number > 0
        self.fn_name = fn_name
        self.lib = lib
        self.source_file = source_file
        self.line_number = line_number
    def __str__(self):
        msg = "StrackFrame(\"{}\", ".format(self.fn_name)
        if self.lib:
            msg += "lib=\"{}\")".format(self.lib)
        else:
            msg += "source_file=\"{}\", line_number={})".format(self.source_file, self.line_number)
        return msg
    def __repr__(self):
        return str(self)

def _parse_gdb_stacktrace(f):
    in_stacktrace = False
    stacktrace = None
    for l in f:
        if l.startswith('#0'):
            in_stacktrace = True
            stacktrace = []
        if not in_stacktrace:
            continue
        if not l.startswith('#'):
            in_stacktrace = False
            break
        m = GDB_IN_FROM_STACKFRAME.match(l)
        if m:
            frame = StackFrame(fn_name=m.group(1), lib=m.group(2))
            stacktrace.append(frame)
            continue
        m = GDB_IN_AT_STACKFRAME.match(l)
        if m:
            frame = StackFrame(
                fn_name=m.group(1),
                lib=None,
                source_file=m.group(2),
                line_number=int(m.group(3))
            )
            stacktrace.append(frame)
            continue
        # Failed to parse stack frame
        _logger.error('Failed to parse "{}" from stacktrace'.format(l))
        raise Exception('Failed to parse stacktrace')
        return None

    _logger.debug('Got stacktrace:\n{}'.format(pprint.pformat(stacktrace)))
    return stacktrace

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
                # Looks like an assertion failure. Here's an example trace
                # ```
                # sqrt_klee_bug.x86_64: /home/user/fp-bench/benchmarks/c/imperial/synthetic/sqrt/sqrt.c:80: main: Assertion `almost_equal(x, sqrt_x*sqrt_x)' failed.
                #
                # Program received signal SIGABRT, Aborted.
                # raise () from /usr/lib/libc.so.6
                # #0  raise () from /usr/lib/libc.so.6
                # #1  abort () from /usr/lib/libc.so.6
                # #2  __assert_fail_base () from /usr/lib/libc.so.6
                # #3  __assert_fail () from /usr/lib/libc.so.6
                # #4  main (argc=<optimized out>, argv=<optimized out>) at /home/user/fp-bench/benchmarks/c/imperial/synthetic/sqrt/sqrt.c:80
                # ```
                condition = assert_match.group(1)
                failure = AssertError(msg=l.strip(), condition=condition, stack_trace=_parse_gdb_stacktrace(f))
                _logger.debug('Found assertion failure: {}'.format(failure))
                return failure

            # NOTE: Be careful. assert failures call abort so we are assuming
            # that an assertion error message will come first
            abort_match = ABORT_GDB_RE.search(l)
            if abort_match:
                # Looks like abort() was called. Here's an example trace
                # ```
                # Program received signal SIGABRT, Aborted.
                # raise () from /usr/lib/libc.so.6
                # #0  raise () from /usr/lib/libc.so.6
                # #1  abort () from /usr/lib/libc.so.6
                # #2  __gmp_invalid_operation () at /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/invalid.c:82
                # #3  __gmpf_set_d (r=r@entry=, d=<optimized out>) at /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/mpf/set_d.c:45
                # #4  main (argc=<optimized out>, argv=<optimized out>) at /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/main.c:100
                # ```
                failure = AbortError(msg=l.strip(), stack_trace=_parse_gdb_stacktrace(f))
                _logger.debug('Found abort failure: {}'.format(failure))
                return failure
            sigfpe_match = SIGFPE_GDB_RE.search(l)
            if sigfpe_match:
                failure = ArithmeticError(msg=l.strip(), stack_trace=_parse_gdb_stacktrace(f))
                _logger.debug('Found abort failure: {}'.format(failure))
                return failure

    raise Exception('GDB: unhandled case')

# FIXME: The stacktrace for ASan and UBSan are the same
# we probably ought to use the same parser
UBSAN_START_STACKTRACE = re.compile(r"\s*#0")
UBSAN_FRAME_STACKTRACE = re.compile(r"\s*#\d+")
# \1 function name
# \2 source file
# \3 line number
UBSAN_FRAME_SOURCE_STACKTRACE = re.compile(r"^\s*#\d+\s+.+\s+in\s+([A-Za-z0-9_]+)\s+(.+):(\d+)")
# \1 function name
# \2 library
UBSAN_FRAME_LIB_STACKTRACE = re.compile(r"^\s*#\d+\s+.+\s+in\s+([A-Za-z0-9_]+)\s+\((.+)\+.+\)")
def _parse_ubsan_stacktrace(f):
    """
    Example stacktrace:
    ```
    /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/errno.c:53:19: runtime error: division by zero
        #0 0x409a9c in __gmp_exception /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/errno.c:53
        #1 0x409aad in __gmp_sqrt_of_negative /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/errno.c:64
        #2 0x402364 in __gmpf_sqrt /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/gmp-6.1.1/mpf/sqrt.c:76
        #3 0x401eab in main /home/user/fp-bench/benchmarks/c/aachen/real/gmp/benchmarks/main.c:96
        #4 0x7fa818130290 in __libc_start_main (/usr/lib/libc.so.6+0x20290)
        #5 0x401ed9 in _start (/home/dsl11/dev/klee-afr/fp-bench/replay_ubsan_build/benchmarks/c/aachen/real/gmp/gmp_klee_inv_arg.x86_64+0x401ed9)
    ```
    """
    in_stacktrace = False
    stacktrace = None
    for l in f:
        _logger.debug('Examining "{}"'.format(l))
        if not in_stacktrace and UBSAN_START_STACKTRACE.match(l):
            in_stacktrace = True
            stacktrace = []
        if not in_stacktrace:
            _logger.debug('Not in stacktrace')
            continue
        if not UBSAN_FRAME_STACKTRACE.match(l):
            in_stacktrace = False
            break
        m = UBSAN_FRAME_LIB_STACKTRACE.match(l)
        if m:
            frame = StackFrame(fn_name=m.group(1), lib=m.group(2))
            stacktrace.append(frame)
            continue
        m = UBSAN_FRAME_SOURCE_STACKTRACE.match(l)
        if m:
            frame = StackFrame(
                fn_name=m.group(1),
                lib=None,
                source_file=m.group(2),
                line_number=int(m.group(3))
            )
            stacktrace.append(frame)
            continue
        # Failed to parse stack frame
        _logger.error('Failed to parse "{}" from stacktrace'.format(l))
        raise Exception('Failed to parse stacktrace')
        return None

    _logger.debug('Got stacktrace:\n{}'.format(pprint.pformat(stacktrace)))
    return stacktrace

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
                failure = UBSanError(msg=l.strip(), type=type, stack_trace=_parse_ubsan_stacktrace(f))
                _logger.debug('Found ubsan failure: {}'.format(failure))
                return failure

    raise Exception('UBSan: Unhandled case')

# FIXME: The stacktrace for ASan and UBSan are the same
# we probably ought to use the same parser
ASAN_START_STACKTRACE = re.compile(r"^\s*#0")
ASAN_FRAME_STACKTRACE = re.compile(r"^\s*#\d+")
# \1 function name
# \2 source file
# \3 line number
ASAN_FRAME_SOURCE_STACKTRACE = re.compile(r"^\s*#\d+\s+.+\s+in\s+([A-Za-z0-9_]+)\s+(.+):(\d+)")
# \1 function name
# \2 library
ASAN_FRAME_LIB_STACKTRACE = re.compile(r"^\s*#\d+\s+.+\s+in\s+([A-Za-z0-9_]+)\s+\((.+)\+.+\)")
def _parse_asan_stacktrace(f):
    """
    Example trace
    ```
    =================================================================
    ==8223==ERROR: AddressSanitizer: stack-buffer-overflow on address 0x7fffdc76cf24 at pc 0x000000400c1d bp 0x7fffdc76cee0 sp 0x7fffdc76ced0
    READ of size 4 at 0x7fffdc76cf24 thread T0
        #0 0x400c1c in sum2 /home/user/fp-bench/benchmarks/c/imperial/synthetic/sum_is_commutative/sum_is_commutative.c:51
        #1 0x400c1c in main /home/user/fp-bench/benchmarks/c/imperial/synthetic/sum_is_commutative/sum_is_commutative.c:72
        #2 0x7f00accb1290 in __libc_start_main (/usr/lib/libc.so.6+0x20290)
        #3 0x400c89 in _start (/home/dsl11/dev/klee-afr/fp-bench/replay_asan_build/benchmarks/c/imperial/synthetic/sum_is_commutative_klee_float_bug.x86_64+0x400c89)

    Address 0x7fffdc76cf24 is located in stack of thread T0 at offset 52 in frame
        #0 0x4009bf in main /home/user/fp-bench/benchmarks/c/imperial/synthetic/sum_is_commutative/sum_is_commutative.c:59
    ```
    """
    in_stacktrace = False
    stacktrace = None
    for l in f:
        _logger.debug('Examining "{}"'.format(l))
        if not in_stacktrace and ASAN_START_STACKTRACE.match(l):
            in_stacktrace = True
            stacktrace = []
        if not in_stacktrace:
            _logger.debug('Not in stacktrace')
            continue
        if not ASAN_FRAME_STACKTRACE.match(l):
            in_stacktrace = False
            break
        m = ASAN_FRAME_LIB_STACKTRACE.match(l)
        if m:
            frame = StackFrame(fn_name=m.group(1), lib=m.group(2))
            stacktrace.append(frame)
            continue
        m = ASAN_FRAME_SOURCE_STACKTRACE.match(l)
        if m:
            frame = StackFrame(
                fn_name=m.group(1),
                lib=None,
                source_file=m.group(2),
                line_number=int(m.group(3))
            )
            stacktrace.append(frame)
            continue
        # Failed to parse stack frame
        _logger.error('Failed to parse "{}" from stacktrace'.format(l))
        raise Exception('Failed to parse stacktrace')
        return None

    _logger.debug('Got stacktrace:\n{}'.format(pprint.pformat(stacktrace)))
    return stacktrace

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
                failure = ASanError(msg=l.strip(), type=type, stack_trace=_parse_asan_stacktrace(f))
                _logger.debug('Found asan failure: {}'.format(failure))
                return failure
    raise Exception('ASan: Unhandled case')
