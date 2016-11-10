# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple
from enum import Enum
import logging
from .kleedir import KleeDir
from . import verificationtasks

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

VerificationCounterExamples = namedtuple("VerificationCounterExamples", ["task", "failures"])
VerificationInconclusiveResult = namedtuple("VerificationInconclusiveResult", ["task", "early_terminations"])
VerificationWarning = namedtuple("VerificationWarning", ["task", "message_test_tuples"])

class KleeRunnerResult(Enum):
    VALID_KLEE_DIR = 0
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
        reports.append( SummaryType(KleeRunnerResult.OUT_OF_TIME, None) )

    klee_dir = KleeDir(r["klee_dir"])
    if klee_dir.is_valid:
        reports.append( SummaryType(KleeRunnerResult.VALID_KLEE_DIR, None) )
    else:
        reports.append( SummaryType(KleeRunnerResult.INVALID_KLEE_DIR, None) )
    return reports, klee_dir


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
    return _check_against_spec(spec, kleedir)

# Entry point used for testing
def _check_against_spec(spec, kleedir):
    failures = []
    warnings = []
    misc_failures = list(kleedir.misc_errors)
    if len(misc_failures) > 0:
        failures.append(VerificationCounterExamples("no_misc_failures", misc_failures))
    for name, task in sorted(TASKS.items(), key= lambda i: i[0]): # Order tasks by name
        task_failures, task_warnings, inconclusive_tasks = task(spec["verification_tasks"][name], kleedir, name)
        task_failures = list(task_failures)
        task_warnings = list(task_warnings)
        if len(task_failures) > 0:
            failures.append(VerificationCounterExamples(name, task_failures))
        if len(task_warnings) > 0:
            warnings.append(VerificationWarning(name, task_warnings))

        if len(inconclusive_tasks) > 0:
            assert len(task_failures) == 0
            assert len(task_warnings) == 0
            failures.append(VerificationInconclusiveResult(name, inconclusive_tasks))

    return (failures, warnings)

def show_failures_as_string(failures):
    print(failures)
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

def get_klee_verification_results_for_fp_bench(klee_dir):
    verification_results = []
    for task in verificationtasks.fp_bench_tasks:
        result = get_klee_verification_result(
            task,
            klee_dir,
            verificationtasks.get_cex_test_cases_for_fp_bench_task)
        verification_results.append(result)
    return verification_results

KleeResultCorrect = namedtuple("KleeResultCorrect", ["task", "test_cases"])
KleeResultIncorrect = namedtuple("KleeResultIncorrect", ["task", "test_cases"])
KleeResultUnknown = namedtuple("KleeResultUnknown", ["task", "reason", "test_cases"])


def get_klee_dir_verification_summary_across_tasks(verification_results):
    """
        This returns the summarises a set of verification results from
        the same klee directory. Note this is just one possible way of
        interpreting the results.

        This provides a way of summarising the result of attempting
        verifying a set of tasks for the same benchmark.
    """
    assert isinstance(verification_results, list)
    if len(verification_results) == 0:
        raise Exception('Missing results')
    all_correct = [ vr for vr in verification_results if isinstance(vr, KleeResultCorrect)]
    if len(all_correct) == len(verification_results):
        # All tasks were correct
        return KleeResultCorrect("", [])
    all_incorrect = [ vr for vr in verification_results if isinstance(vr, KleeResultIncorrect)]

    if len(all_incorrect) > 0:
        # If at least one task was reported as incorrect report as incorrect
        return KleeResultIncorrect("", [])

    return KleeResultUnknown("", "Could not classify", [])

def get_klee_verification_result(task, klee_dir, task_to_cex_map_fn):
    """
        Given a verification task `task` and a `klee_dir` return
        whether verification with respect to that `task` is shown
        by the `klee_dir`.

        The `task_to_cex_map_fn` is a function that given two arguments
        `task` and `klee_dir` will return a list of KLEE test cases that
        are counter examples to the correctness of that `task`. This exists
        so that this function can be used with any task not just those from
        "fp-bench".

        It will return one of the following types `KleeResultCorrect`,
        `KleeResultIncorrect` or `KleeResultUnknown`.
    """
    assert isinstance(task, str)
    assert isinstance(klee_dir, KleeDir)
    # FIXME: Check `task_to_cex_map_fn`

    if not klee_dir.is_valid:
        return KleeResultUnknown(task, "klee_dir is invalid", [])

    # Get counter examples
    cexs_for_task = task_to_cex_map_fn(task, klee_dir)
    assert isinstance(cexs_for_task, list)

    # Are there counter examples?
    if len(cexs_for_task) > 0:
        # KLEE believes the property doesn't hold.
        return KleeResultIncorrect(task, cexs_for_task)

    # Proving correctness (i.e. verified) is more complicated. It requires
    # that path exploration was exhaustive. This requires that:
    #
    # * There were successful terminations (necessary but not sufficient).
    # * There were no early terminations.
    # * There were no other counter examples for other tasks. This is
    #   problematic because KLEE considers multiple tasks at once. If a
    #   counter example for a different task is observed KLEE stops executing
    #   down that path and therefore we can't conclude if there would counter
    #   examples for the task we actually care about deeper in the program.

    early_terminations = list(klee_dir.early_terminations)
    if len(early_terminations) > 0:
        return KleeResultUnknown(task,
            "Cannot verify because KLEE terminated early on paths",
            early_terminations)

    # Note: Because we already would have exited early with KleeResultIncorrect
    # if there are any counter examples here they should not be for the task
    # we are currently considering.
    assert len(task_to_cex_map_fn(task, klee_dir)) == 0
    cexs_for_all_tasks = list(klee_dir.errors)
    if len(cexs_for_all_tasks) > 0:
        return KleeResultUnknown(task,
            "Cannot verify because KLEE terminated with other counter examples"
            " that block further checking of the task",
            cexs_for_all_tasks)

    # Sanity check. There was at least one successful termination
    successful_terminations = list(klee_dir.successful_terminations)
    if len(successful_terminations) < 1:
        # This shouldn't ever happen. Should we just raise an Exception.
        return KleeResultUnknown(task,
            "Cannot verify because KLEE did not have any successful terminations.",
            successful_terminations)

    # Okay then we have verified the program with respect to the task!
    return KleeResultCorrect(task, successful_terminations)
