# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple

_logger = logging.getLogger(__name__)

# Possibe run outcomes
SuccessfulExecution = namedtuple("SuccessfulExecution", ["msg"])
ASanError = namedtuple("ASanError", ["msg", "type", "stack_trace"])
UBSanError = namedtuple("UBSanError", ["msg", "type", "stack_trace"])
AssertError = namedtuple("AssertError", ["msg", "stack_trace"])
AbortError = namedtuple("AssertError", ["msg", "stack_trace"])
UnknownError = namedtuple("UnknownError", ["msg"])
TimeoutError = namedtuple("TimeoutError", ["msg"])
OutOfMemoryError = namedtuple("OutOfMemoryError", ["msg"])

def get_test_case_run_outcomes(r):
    """
        Get a list of outcomes for a run of a test case

        `r` a raw result info dictionary
    """
    assert isinstance(r, dict) # FIXME: Don't use raw form
    raise Exception('TODO')
    return None
