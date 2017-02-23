# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple
from enum import Enum
import copy
import logging
import os
import pprint
from .kleedir import KleeDir
from .kleedir import KleeDirProxy
from . import verificationtasks

_logger = logging.getLogger(__name__)

# FIXME: This doesn't belong here. But due to the currently
# layout we can't easily import KleeRunner.
def raw_result_info_is_merged(r):
    assert isinstance(r, dict)
    is_merged_result = False
    if 'merged_result' in r and r['merged_result']:
        is_merged_result = True
    return is_merged_result

def get_yaml_load():
    """Acquires the yaml load function"""
    from yaml import load
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader
    return lambda file: load(file, Loader)
yaml_load = get_yaml_load()

class KleeRunnerResult(Enum):
    VALID_KLEE_DIR = 0
    BAD_EXIT = 1
    OUT_OF_MEMORY = 2
    OUT_OF_TIME = 3
    INVALID_KLEE_DIR = 4
    LOST_TEST_CASE = 5
    EXECUTION_ERRORS = 6
    USER_ERRORS = 7
    MISC_ERRORS= 8
    SENTINEL = 100

SummaryType = namedtuple("SummaryType", ["code", "payload"])

def get_run_outcomes(r):
    """
      Return a list of outcomes for the run
    """
    assert isinstance(r, dict) # FIXME: Don't use raw form
    is_merged_result = raw_result_info_is_merged(r)
    reports = [ ]
    hard_out_of_time_found = False

    # Handle exit code
    exit_codes_to_check = []
    if is_merged_result:
        assert isinstance(r["exit_code"], list)
        exit_codes_to_check.extend(r["exit_code"])
    else:
        exit_codes_to_check.append(r["exit_code"])
    for exit_code in exit_codes_to_check:
        if exit_code is not None and exit_code != 0:
            reports.append( SummaryType(KleeRunnerResult.BAD_EXIT, exit_code))

    # Handle out of memory
    out_of_memories_to_check = []
    if is_merged_result:
        assert isinstance(r["out_of_memory"], list)
        out_of_memories_to_check.extend(r["out_of_memory"])
    else:
        out_of_memories_to_check.append(r["out_of_memory"])
    for out_of_memory in out_of_memories_to_check:
        if out_of_memory:
            reports.append( SummaryType(KleeRunnerResult.OUT_OF_MEMORY, None) )

    # Handle backend timeout
    backend_timeouts_to_check = []
    if is_merged_result:
        assert isinstance(r["backend_timeout"], list)
        backend_timeouts_to_check.extend(r["backend_timeout"])
    else:
        backend_timeouts_to_check.append(r["backend_timeout"])
    for backend_timeout in backend_timeouts_to_check:
        if backend_timeout:
            reports.append(
                SummaryType(KleeRunnerResult.OUT_OF_TIME, "backend timeout"))
            hard_out_of_time_found = True

    # Create KleeDir. Create proxy if it is a merged result
    if is_merged_result:
        assert isinstance(r["klee_dir"], list)
        klee_dir = KleeDirProxy(r["klee_dir"])
    else:
        klee_dir = KleeDir(r["klee_dir"])

    if klee_dir.is_valid:
        reports.append( SummaryType(KleeRunnerResult.VALID_KLEE_DIR, None) )
        if klee_dir.lost_test_cases > 0:
            reports.append( SummaryType(KleeRunnerResult.LOST_TEST_CASE, klee_dir.lost_test_cases))

        # Report if paths are explored that should not happen
        execution_errors = list(klee_dir.execution_errors)
        if len(execution_errors) > 0:
            reports.append( SummaryType(KleeRunnerResult.EXECUTION_ERRORS, execution_errors))

        user_errors = list(klee_dir.user_errors)
        if len(user_errors) > 0:
            reports.append( SummaryType(KleeRunnerResult.USER_ERRORS, user_errors))

        misc_errors = list(klee_dir.misc_errors)
        if len(misc_errors) > 0:
            reports.append( SummaryType(KleeRunnerResult.MISC_ERRORS, misc_errors))
    else:
        reports.append( SummaryType(KleeRunnerResult.INVALID_KLEE_DIR, None) )

    # Check for soft timeout
    if not hard_out_of_time_found:
        if klee_dir.halt_timer_invoked:
            reports.append( SummaryType(KleeRunnerResult.OUT_OF_TIME, "soft timeout") )

    return reports, klee_dir

def show_failures_as_string(test_cases):
    msg=""
    for test_case in test_cases:
        msg += "  Test {:06} in {}:{}\n".format(
            test_case.identifier,
            test_case.error.file if hasattr(test_case.error, "file") else "<unknown>",
            test_case.error.line if hasattr(test_case.error, "line") else "<unknown>")
    return msg

def get_klee_verification_results_for_fp_bench(klee_dir, allow_invalid_klee_dir=False):
    verification_results = []
    for task in verificationtasks.fp_bench_tasks:
        result = get_klee_verification_result(
            task,
            klee_dir,
            verificationtasks.get_cex_test_cases_for_fp_bench_task,
            allow_invalid_klee_dir)
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

class KleeResultUnknownReason:
    INVALID_KLEE_DIR = "klee_dir is invalid"
    EARLY_TERMINATION = "Cannot verify because KLEE terminated early on paths"
    CEX_BLOCK_TASK = ("Cannot verify because KLEE terminated with other"
        " counter examples that block further checking of the task")
    NO_TEST_CASES = "KLEE produced no test cases"

def get_klee_verification_result(task, klee_dir, task_to_cex_map_fn, allow_invalid_klee_dir=False):
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

        WARNING: This logic assumes that KLEE is told to check for
        overshift and division by zero. If those checks are disabled
        then a result of `KleeResultCorrect` cannot be trusted.
    """
    assert isinstance(task, str)
    assert isinstance(klee_dir, KleeDir)
    # FIXME: Check `task_to_cex_map_fn`

    # Fail early without considering test cases if requested
    if (not klee_dir.is_valid) and (not allow_invalid_klee_dir):
        return KleeResultUnknown(
            task,
            KleeResultUnknownReason.INVALID_KLEE_DIR,
            [])

    # Sanity check
    if len(klee_dir.tests) == 0:
        # KLEE directory has not tests at all so we can't conclude
        # anything!
        return KleeResultUnknown(
            task,
            KleeResultUnknownReason.NO_TEST_CASES,
            [])

    # Get counter examples
    cexs_for_task = task_to_cex_map_fn(task, klee_dir)
    assert isinstance(cexs_for_task, list)

    # Are there counter examples?
    if len(cexs_for_task) > 0:
        # KLEE believes the property doesn't hold.
        return KleeResultIncorrect(task, cexs_for_task)

    if not klee_dir.is_valid:
        return KleeResultUnknown(
            task,
            KleeResultUnknownReason.INVALID_KLEE_DIR,
            [])

    # Proving correctness (i.e. verified) is more complicated. It requires
    # that path exploration was exhaustive. This requires that:
    #
    # * There were no early terminations.
    # * There were no other counter examples for other tasks that could be
    #   non-terminating (i.e. undefined behaviour).
    #   This is problematic because KLEE considers multiple tasks at once. If a
    #   counter example for a different task is observed, KLEE stops executing
    #   down that path and therefore we can't conclude if there would counter
    #   examples for the task we actually care about deeper in the program.
    #   (unless all counter examples are terminating, i.e. assert() and abort()).
    #
    # Note it is not actually necessary for there to be successful terminations
    # for a benchmark to be correct w.r.t a particular verification task. For
    # example consider a benchmark with a single path that has an assertion
    # that always fails. For the `no_assert_fail` task the result will be
    # KleeResultIncorrect but for the `no_overshift` task we can conclude
    # KleeResultCorrect even though there were no successful terminations
    # (there is just one test with an assertion failure).

    early_terminations = list(klee_dir.early_terminations)
    if len(early_terminations) > 0:
        return KleeResultUnknown(task,
            KleeResultUnknownReason.EARLY_TERMINATION,
            early_terminations)

    # Note: Because we already would have exited early with KleeResultIncorrect
    # if there are any counter examples here they should not be for the task
    # we are currently considering.
    assert len(task_to_cex_map_fn(task, klee_dir)) == 0

    # Compute the set of cexs that might not cause termination.
    cexs_for_all_tasks = list(klee_dir.errors)
    non_terminating_cexs = []
    terminating_cexs = []
    assertion_errors = list(klee_dir.assertion_errors)
    abort_errors = list(klee_dir.abort_errors)
    non_terminating_cexs = []
    for cex in cexs_for_all_tasks:
        if cex in assertion_errors:
            terminating_cexs.append(cex)
            continue
        if cex in abort_errors:
            terminating_cexs.append(cex)
            continue
        non_terminating_cexs.append(cex)

    if len(non_terminating_cexs) > 0:
        return KleeResultUnknown(
            task,
            KleeResultUnknownReason.CEX_BLOCK_TASK,
            non_terminating_cexs)

    successful_terminations = list(klee_dir.successful_terminations)


    # Okay then we have verified the program with respect to the task!
    # We need to add terminating cexs here because they are relevant
    # for coverage. It is a little bit confusing because those terminating
    # counter examples are bugs but they are bugs for different verification
    # tasks, not this one!
    relevant_test_cases = successful_terminations + terminating_cexs
    assert(len(relevant_test_cases) > 0)
    return KleeResultCorrect(task, relevant_test_cases)


KleeResultMatchSpec = namedtuple("KleeResultMatchSpec",
    ["task", "expect_correct", "test_cases", "warnings"])
KleeResultMismatchSpec = namedtuple("KleeResultMismatchSpec",
    ["task", "reason", "test_cases", "expect_correct"])
KleeResultUnknownMatchSpec = namedtuple("KleeResultUnknownMatchSpec",
    ["task", "reason", "klee_verification_result", "expect_correct"])

def get_augmented_spec_file_path(raw_result):
    augmented_spec_file_path = None
    try:
        augmented_spec_file = raw_result["invocation_info"]["misc"]["augmented_spec_file"]
    except KeyError as e:
        _logger.error('Failed to find augmented_spec_file key')
        raise e
    if not os.path.exists(augmented_spec_file):
        raise Exception('"{}" does not exist'.format(augmented_spec_file))
    return augmented_spec_file

def load_spec(spec_file_path):
    # FIXME: We should be using fp-bench's infrastructure to do this
    spec = None
    with open(spec_file_path) as f:
        spec = yaml_load(f)
    _logger.debug('Loaded spec "{}"'.format(spec_file_path))
    return spec

class KleeMatchSpecReason:
    SPEC_PROVIDES_NO_CORRECTNESS = "spec provides no correctness"
    KLEE_COULD_NOT_DETERMINE_CORRECTNESS = "KLEE could not determine correctness"
    EXPECT_CORRECT_KLEE_REPORTS_INCORRECT = (
        "expect correct but KLEE reports incorrect")
    EXPECT_INCORRECT_KLEE_REPORTS_CORRECT = (
        "Expect incorrect but KLEE reports correct")
    DISALLOWED_CEX = (
        "Expected incorrect and KLEE reported this but observed disallowed "
        "counter example(s)")

class KleeMatchSpecWarnings:
    CEX_NOT_IN_SPEC = "Observed counter examples not listed in spec"
    NOT_ALL_CEX_OBSERVED = "Observed counter examples do not cover all listed for this task in spec"

def match_klee_verification_result_against_spec(klee_verification_result, spec):
    task = klee_verification_result.task
    assert isinstance(task, str)
    assert (
        isinstance(klee_verification_result, KleeResultCorrect) or
        isinstance(klee_verification_result, KleeResultIncorrect) or
        isinstance(klee_verification_result, KleeResultUnknown)
    )
    assert isinstance(spec, dict)

    verification_tasks = spec["verification_tasks"]
    task_info = verification_tasks[task]
    expect_correct = task_info["correct"]
    assert isinstance(expect_correct, bool) or expect_correct == None

    if expect_correct is None:
        # The spec provides no useful information so we can't perform a match.
        return KleeResultUnknownMatchSpec(
            task,
            KleeMatchSpecReason.SPEC_PROVIDES_NO_CORRECTNESS,
            klee_verification_result,
            None
        )

    if isinstance(klee_verification_result, KleeResultUnknown):
        # The KLEE verification result provides no useful answer so we
        # can't compare
        return KleeResultUnknownMatchSpec(
            task,
            KleeMatchSpecReason.KLEE_COULD_NOT_DETERMINE_CORRECTNESS,
            klee_verification_result,
            expect_correct
        )

    if expect_correct is True:
        # The spec expects the benchmark to be correct with respect to `task`
        if isinstance(klee_verification_result, KleeResultCorrect):
            # The spec expects correct and KLEE reports the same
            return KleeResultMatchSpec(
                task=task,
                expect_correct=True,
                test_cases=klee_verification_result.test_cases,
                warnings=[])
        else:
            # KLEE reports the benchmark is incorrect. This is a mismatch
            assert isinstance(klee_verification_result, KleeResultIncorrect)
            return KleeResultMismatchSpec(
                task=task,
                reason=KleeMatchSpecReason.EXPECT_CORRECT_KLEE_REPORTS_INCORRECT,
                test_cases=klee_verification_result.test_cases,
                expect_correct=expect_correct)

    # The benchmark is expected to be incorrect with respect to the task
    assert expect_correct is False
    counter_examples_are_exhaustive = task_info['exhaustive_counter_examples']
    assert isinstance(counter_examples_are_exhaustive, bool)

    if isinstance(klee_verification_result, KleeResultCorrect):
        # KLEE thinks the benchmarks is correct w.r.t the verification
        # task but we expect incorrect.
        return KleeResultMismatchSpec(
            task=task,
            reason=KleeMatchSpecReason.EXPECT_INCORRECT_KLEE_REPORTS_CORRECT,
            test_cases=klee_verification_result.test_cases,
            expect_correct=expect_correct
        )

    # Now we should be only considering the case where the benchmark
    # is expected to be incorrect w.r.t to the task and KLEE also
    # reports this.
    assert isinstance(klee_verification_result, KleeResultIncorrect)

    # Collect the counter examples that are expected from the spec.
    # Map <file_name> -> set of source lines.
    allowed_cexs = dict()
    if "counter_examples" in task_info:
        for cex in task_info["counter_examples"]:
            for loc in cex["locations"]:
                if loc["file"] not in allowed_cexs:
                    allowed_cexs[loc["file"]] = set()
                allowed_cexs[loc["file"]].add(int(loc["line"]))
        _logger.debug('Allowed failures for task {}: {}'.format(
            task,
            pprint.pformat(allowed_cexs)))

    # Go through the counter examples found by KLEE and compare
    # them to allowed_cexs.
    unexpected_cexs = []
    expected_cexs = []
    unobserved_cexs = copy.deepcopy(allowed_cexs)
    for test_case in klee_verification_result.test_cases:
        _logger.debug('Considering test case:\n{}\n'.format(test_case))
        assert test_case.error is not None
        # FIXME:
        # The file path in failure is absolute (e.g. `/path/to/file.c`) where
        # as the spec will have `file.c` so we need to check if `/file.c` is a
        # suffix of the error path.
        #
        # This isn't quite right as we could accidently match is a files happen
        # to have the same name but are actually in completly different
        # directories.
        assert os.path.isabs(test_case.error.file)
        test_case_file = None
        for acf in allowed_cexs.keys():
            assert not acf.startswith('/')
            suffix = '/{}'.format(acf)
            if test_case.error.file.endswith(suffix):
                test_case_file = acf
                break

        if test_case_file is None:
            # This test case doesn't match any expected counter example.
            _logger.debug(('"{}" is not in allowed_cexs. This is not a '
                'failure that the spec expects').format(test_case.error.file))
            unexpected_cexs.append(test_case)
            continue
        if test_case.error.line not in allowed_cexs[test_case_file]:
            _logger.debug(('"{}" is in allowed failures. But the error line for'
                ' this failure ({}) is not expected by the spec'
                '(expected lines:{})').format(
                    test_case.error.file,
                    test_case.error.line,
                    allowed_cexs[test_case_file]))
            unexpected_cexs.append(test_case)
            continue

        # This counter example is expected
        _logger.debug('{}:{} appears to be an allowed failure'.format(
            test_case.error.file,
            test_case.error.line))
        expected_cexs.append(test_case)

        # Remove this cex from the set of unobserved counter examples
        try:
            unobserved_cexs[test_case_file].remove(test_case.error.line)
            if len(unobserved_cexs[test_case_file]) == 0:
                # Remove the test_case_file as a key
                unobserved_cexs.pop(test_case_file)
        except KeyError:
            # Already removed
            pass

    if len(unexpected_cexs) == 0:
        warnings = []
        if len(unobserved_cexs) > 0:
            # Some counter examples in the spec were not observed.
            warnings.append(
                (KleeMatchSpecWarnings.NOT_ALL_CEX_OBSERVED, unobserved_cexs)
            )
            _logger.debug('Match spec but some counter examples were not observed: {}'.format(
                unobserved_cexs))

        # KLEE reported no unexpected counter examples
        assert len(expected_cexs) > 0
        return KleeResultMatchSpec(
            task=task,
            expect_correct=False,
            test_cases=expected_cexs,
            warnings=warnings)

    assert len(unexpected_cexs) > 0
    if counter_examples_are_exhaustive:
        # Having unexpected counter examples is a mismatch if the counter examples
        # provided by the spec are exhaustive.
        return KleeResultMismatchSpec(
            task=task,
            reason=KleeMatchSpecReason.DISALLOWED_CEX,
            test_cases=unexpected_cexs,
            expect_correct=expect_correct,
        )

    # The counter examples are not exhaustive so this is not an mismatch but we
    # should emit warnings about the unexpected counter examples
    return KleeResultMatchSpec(
        task=task,
        expect_correct=False,
        test_cases=expected_cexs + unexpected_cexs,
        warnings=[
            (KleeMatchSpecWarnings.CEX_NOT_IN_SPEC, unexpected_cexs)
        ]
    )


