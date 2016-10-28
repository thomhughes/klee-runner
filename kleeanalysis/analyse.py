# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple
from enum import Enum
import logging
from .kleedir import KleeDir
from .verificationtasks import TASKS

_logger = logging.getLogger(__name__)

def get_yaml_load():
    """Acquires the yaml load function"""
    from yaml import load
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader
    return lambda file: load(file, Loader)
yaml_load = get_yaml_load()

VerificationFailure = namedtuple("VerificationFailure", ["task", "failures"])

class KleeRunnerResult(Enum):
    OKAY_KLEE_DIR = 0
    BAD_EXIT = 1
    OUT_OF_MEMORY = 2
    OUT_OF_TIME = 3
    INVALID_KLEE_DIR = 4
    SENTINEL = 100

SummaryType = namedtuple("SummaryType", ["code", "payload"])

def get_run_outcomes(r):
    """
      Return a list of outcomes for the run
    """
    assert isinstance(r, dict) # FIXME: Don't use raw form
    reports = [ ]
    if r["exit_code"] is not None and r["exit_code"] != 0:
        reports.append( SummaryType(KleeRunnerResult.BAD_EXIT, r["exit_code"]))
    if r["out_of_memory"]:
        reports.append( SummaryType(KleeRunnerResult.OUT_OF_MEMORY, None) )
    if r["backend_timeout"]:
        reports.append( SummaryType(KleeRunnerResult.OUT_OF_TIME) )

    kleedir = KleeDir(r["klee_dir"])
    if kleedir.is_valid:
        reports.append( SummaryType(KleeRunnerResult.OKAY_KLEE_DIR, kleedir) )
    else:
        reports.append( SummaryType(KleeRunnerResult.INVALID_KLEE_DIR, kleedir) )
    return reports


def check_against_spec(r, kleedir):
    augmentedSpecFilePath = None
    try:
        augmentedSpecFilePath = r["invocation_info"]["misc"]["augmented_spec_file"]
    except KeyError as e:
        _logger.error('Failed to find augmentedSpecFilePath key')
        raise e
    # FIXME: Use the fp-bench infrastructure to load the spec
    spec = None
    with open(augmentedSpecFilePath) as f:
        spec = yaml_load(f)
    failures = []
    misc_failures = list(kleedir.misc_errors)
    if len(misc_failures) > 0:
        failures.append(VerificationFailure("no_misc_failures", misc_failures))
    for name, task in sorted(TASKS.items(), key= lambda i: i[0]): # Order tasks by name
        task_failures = list(task(spec["verification_tasks"][name], kleedir))
        if len(task_failures) > 0:
            failures.append(VerificationFailure(name, task_failures))

    return failures

def show_failures_as_string(failures):
    assert isinstance(failures, list)
    msg=""
    for fail_task in failures:
        msg += "Verification failures for task:{}:\n".format(fail_task.task)
        for fail in fail_task.failures:
            msg += "  Test {:06} in {}:{}\n".format(
                fail.identifier,
                fail.error.file,
                fail.error.line)
    return msg

