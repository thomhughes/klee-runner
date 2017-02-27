# vim: set sw=4 ts=4 softtabstop=4 expandtab:

import copy
import logging
import os
import math
import pprint
import statistics
from collections import namedtuple
from . import kleedir
from .kleedir import test
from .kleedir import KleeDir, KleeDirProxy
from . import analyse
from enum import Enum

_logger = logging.getLogger(__name__)

RankReason = namedtuple('RankReason', ['rank_reason_type', 'msg'])
BoundType = namedtuple('BoundType', ['lower_bound', 'upper_bound'])

class RankReasonTy(Enum):
    HAS_N_FALSE_POSITIVES = (0, "Has {n} false positives")
    HAS_N_TRUE_POSITIVES = (1, "Has {n} true positives")
    HAS_N_PERCENT_BRANCH_COVERAGE = (2, "Has {n:%} branch coverage")
    HAS_N_CRASHES= (3, "Has {n} crashes")
    HAS_T_SECOND_EXECUTION_TIME = (4, "Has {t} second execution time")
    TIED = (5, "Results are tied")
    # FIXME: These should be removed
    MISSING_COVERAGE_DATA= (6, "Cannot be ranked. Requires coverage data")

    def __init__(self, id, template_msg):
        self.id = id
        self.template_msg = template_msg

    def mk_rank_reason(self, *nargs, **kwargs):
        """
        Make a RankReason from the RankReasonTy.
        The (optional) arguments are used to take
        the `RankReasonTy.template_msg` and do
        any substitutions.
        """
        obj = RankReason(self, self.template_msg.format(*nargs, **kwargs))
        return obj

    def __lt__(self, other):
        return self.id < other.id

class RankPosition:
    def __init__(self, indices, rank_reason):
        assert isinstance(indices, list)
        assert len(indices) > 0
        assert isinstance(rank_reason, RankReason)
        self.indices = indices
        for i in self.indices:
            assert isinstance(i, int)
            assert i >= 0
        self.rank_reason = rank_reason

    def __str__(self):
        msg = None
        if len(self.indices) == 1:
            msg =  "index {} ranked because \"{}\"".format(
                self.indices[0],
                self.rank_reason)
        else:
            msg =  "indices {} ranked same because \"{}\"".format(
                self.indices,
                self.rank_reason)

        msg = "<RankPosition: {}>".format(msg)
        return msg

################################################################################
# Bounding and "average" functions
################################################################################

def get_median_and_range(values):
    assert isinstance(values, list)
    lower_bound = min(values)
    upper_bound = max(values)
    median = statistics.median(values)
    return (lower_bound, median, upper_bound)

def get_arithmetic_mean_and_confidence_intervals(values, confidence_interval_factor):
    assert isinstance(values, list)
    assert confidence_interval_factor > 0
    n = len(values)
    assert n > 1
    mean = statistics.mean(values)
    variance_of_sample = statistics.variance(values)
    standard_error_in_mean_squared = variance_of_sample / n
    standard_error_in_mean = math.sqrt(standard_error_in_mean_squared)
    lower_bound = mean - (standard_error_in_mean * confidence_interval_factor)
    upper_bound = mean + (standard_error_in_mean * confidence_interval_factor)
    return (lower_bound, mean , upper_bound)

def get_arithmetic_mean_and_95_confidence_intervals(values):
    # 95 % confidence
    return get_arithmetic_mean_and_confidence_intervals(values, 1.96)

def get_arithmetic_mean_and_99_confidence_intervals(values):
    # 99.9 % confidence
    return get_arithmetic_mean_and_confidence_intervals(values, 3.27)

__hack_stdev = 0.0
################################################################################
# Ranking
################################################################################

def rank(result_infos, bug_replay_infos=None, coverage_replay_infos=None, coverage_range_fn=get_arithmetic_mean_and_95_confidence_intervals, timing_range_fn=get_arithmetic_mean_and_99_confidence_intervals):
    """
        Given a list of `result_infos` compute a ranking. Optionally using
        `bug_replay_infos` and `coverage_replay_infos`.

        `coverage_range_fn` is the function that should return a tuple (lower_bound, middle_value, upper_bound)
        when applied to a list of coverage values.

        `timing_range_fn` is the function that should return a tuple (lower_bound, middle_value, upper_bound)
        when applied to a list of execution time values.

        Returns `rank_reason_list`.

        where

        `rank_reason_list` is a list of `RankPosition`s. `RankPosition`s earlier
        in the list are ranked higher (better). `RankPosition` contains `results`
        which is a list of indicies (corresponding to `result_infos`) which are
        considered to be ranked the same.
    """
    assert isinstance(result_infos, list)
    global __hack_stdev

    # FIXME: We should stop using raw result infos
    for ri in result_infos:
        assert isinstance(ri, dict)
        assert 'invocation_info' in ri
    assert len(result_infos) > 1

    if coverage_replay_infos:
        assert isinstance(coverage_replay_infos, list)
        assert len(result_infos) == len(coverage_replay_infos)
    if bug_replay_infos:
        assert isinstance(bug_replay_infos, list)
        assert len(result_infos) == len(bug_replay_infos)
    
    reversed_rank = []
    index_to_klee_dir_map = []
    llvm_bc_program_path = None
    llvm_bc_program_path_try = None
    native_program_name = None
    index_to_is_merged_map = []
    index_to_number_of_repeat_runs_map = []
    for index, r in enumerate(result_infos):
        klee_dir_paths = r['klee_dir']
        if isinstance(klee_dir_paths, str):
            # Single result
            klee_dir = KleeDir(r['klee_dir'])
            index_to_is_merged_map.append(False)
        elif isinstance(klee_dir_paths, list):
            # merged result
            klee_dir = KleeDirProxy(klee_dir_paths)
            index_to_is_merged_map.append(True)
            index_to_number_of_repeat_runs_map.append(len(klee_dir_paths))
        else:
            raise Exception('Invalid klee_dir value')
        index_to_klee_dir_map.append(klee_dir)

        # Get the program path
        llvm_bc_program_path_try = result_infos[index]['invocation_info']['program']
        # Sanity check
        if llvm_bc_program_path is None:
            llvm_bc_program_path = llvm_bc_program_path_try
        else:
            if llvm_bc_program_path_try != llvm_bc_program_path:
                raise Exception('Program paths "{}" and "{}" do not match'.format(
                    llvm_bc_program_path,
                    llvm_bc_program_path_try))

    # Sanity check: Make sure results are all single or are all merged
    assert len(index_to_is_merged_map) == len(result_infos)
    all_results_are_merged = all(index_to_is_merged_map)
    all_results_are_single = all(map(lambda x: x is False, index_to_is_merged_map))
    if (not all_results_are_merged) and (not all_results_are_single):
        raise Exception("Can't mix merged and single results when ranking")

    # Compute native_program_name
    # FIXME: this a fp-bench specific hack
    assert llvm_bc_program_path.endswith('.bc')
    native_program_name = os.path.basename(llvm_bc_program_path)
    native_program_name = native_program_name[:-3]

    # Get KLEE verification results
    index_to_klee_verification_results = []
    for klee_dir in index_to_klee_dir_map:
        kvr = analyse.get_klee_verification_results_for_fp_bench(
            klee_dir,
            allow_invalid_klee_dir=True)
        index_to_klee_verification_results.append(kvr)

    # Match against spec to find true positives and false positives.
    # Load spec
    augmented_spec_path = result_infos[0]['invocation_info']['misc']['augmented_spec_file']
    # Sanity check. All result infos should have the same augmented spec file
    for ri in result_infos:
        assert ri['invocation_info']['misc']['augmented_spec_file'] == augmented_spec_path
    raw_spec = analyse.load_spec(augmented_spec_path)

    assert len(index_to_klee_verification_results) == len(result_infos)
    index_to_klee_spec_match = []
    # FIXME: This needs to be factored so we can do this outside of ranking.
    for index, ri in enumerate(result_infos):
        ksms = []
        for kvr in index_to_klee_verification_results[index]:
            ksm = analyse.match_klee_verification_result_against_spec(kvr, raw_spec)
            ksms.append(ksm)
        index_to_klee_spec_match.append(ksms)

    index_to_true_positives = [ ] # Bugs
    index_to_false_positives = [ ] # Reported bugs but are not real bugs

    for index, ksms in enumerate(index_to_klee_spec_match):
        true_positives = []
        false_positives = []
        for ksm_index, ksm in enumerate(ksms):
            expect_correct = ksm.expect_correct
            if isinstance(ksm, analyse.KleeResultMatchSpec):
                assert expect_correct is not None
                if expect_correct is False:
                    # True positive
                    true_positives.extend(ksm.test_cases)
            elif isinstance(ksm, analyse.KleeResultMismatchSpec):
                assert expect_correct is not None
                if expect_correct is True:
                    # False Positive
                    false_positives.extend(ksm.test_cases)
                elif expect_correct is False and ksm.reason == analyse.KleeMatchSpecReason.DISALLOWED_CEX:
                    # Treat a disallowed counter example as a false positive
                    false_positives.extend(ksm.test_cases)

                    # We need to go through the test cases and check if there were any true positives
                    # (i.e. test cases that were in the klee verification result but were not listed as
                    # mismatching the spec)
                    corresponding_kvr = index_to_klee_verification_results[index][ksm_index]
                    assert isinstance(corresponding_kvr, analyse.KleeResultIncorrect)
                    for test_case in corresponding_kvr.test_cases:
                        if test_case in ksm.test_cases:
                            continue
                        _logger.debug('Found test case that is true positive when false positives also occurred. {}'.format(
                            test_case))
                        true_positives.append(test_case)
            else:
                assert isinstance(ksm, analyse.KleeResultUnknownMatchSpec)
                pass
        # If native bug replay information is available use that.
        if bug_replay_infos is not None:
            true_positives, false_positives = _get_bug_replay_corrected_bugs(native_program_name, true_positives, false_positives, bug_replay_infos[index])
        # Strip duplicate bug locations so we only count a location once
        true_positives = strip_duplicate_bug_test_cases(true_positives)
        false_positives = strip_duplicate_bug_test_cases(false_positives)
        _logger.debug('index: {} has {} true positives'.format(
            index,
            len(true_positives))
        )
        index_to_true_positives.append(true_positives)
        _logger.debug('index: {} has {} false positives'.format(
            index,
            len(false_positives))
        )
        index_to_false_positives.append(false_positives)

    available_indices = list(range(len(result_infos)))
    _logger.debug('available_indices: {}'.format(available_indices))

    # Rank results based on false positive count.
    # We treat this as a binary property. If both tools have
    # false positives (no matter how many) they are ranked equally and so
    # go on to the next stage of comparision. If both tools have no false postives
    # then they are also ranked equally. Only if one tools has no false positives and
    # the other has one of more false positives are the tools ranked differently.
    #
    # The motivation behind doing this is that ranking based on the number of false
    # positives implicitly assumes that each false positive is equally important.
    # We cannot make this assumption (e.g. source location of by one, wrong bug type,
    # we cannot say that these are equally important) so instead we consider "has
    # false positives" as a binary property and rank based on that.
    indices_ordered_by_false_positives = sort_and_group(
        available_indices,
        key=lambda i: len(index_to_false_positives[i]) > 0,
        # Reversed so that we process the results with the
        # most false positives first.
        reverse=True
    )
    _logger.debug('indices_ordered_by_false_positives: {}'.format(
        indices_ordered_by_false_positives))
    # To help with debugging
    seen_false_positive_count = None
    for index in available_indices:
        if seen_false_positive_count is not None:
            if seen_false_positive_count != len(index_to_false_positives[index]):
                _logger.warning('index {} has {} false positives but observed {} at other indices'.format(
                    index,
                    len(index_to_false_positives[index]),
                    seen_false_positive_count)
                )
        seen_false_positive_count = len(index_to_false_positives[index])

    indices_least_fp = []
    for index, grouped_list in enumerate(indices_ordered_by_false_positives):
        assert isinstance(grouped_list, list)
        number_of_false_positives = len(index_to_false_positives[grouped_list[0]])
        if index == len(indices_ordered_by_false_positives) -1:
            # This group has the least number of false positives that are
            # the same. So this should go on to the next stage of comparision
            indices_least_fp = grouped_list
            continue
        reversed_rank.append(
            RankPosition(grouped_list.copy(),
                RankReasonTy.HAS_N_FALSE_POSITIVES.mk_rank_reason(n=number_of_false_positives)
            )
        )
    available_indices = indices_least_fp
    _logger.debug('available_indices after processing false positives: {}'.format(
        available_indices))

    def handle_single_result_left(rank_reason_type, fn):
        """
        `fn` is a function that will be passed the
        `rank_reason.mk_rank_reason`. The reason
        for this indirection is so that `fn` is only
        evaluated if there is only a single result left.
        """
        assert isinstance(rank_reason_type, RankReasonTy)
        assert callable(fn)
        if len(available_indices) == 1:
            rank_reason = fn(rank_reason_type.mk_rank_reason)
            assert isinstance(rank_reason, RankReason)
            reversed_rank.append(
                RankPosition(
                    available_indices.copy(),
                    rank_reason
                )
            )
            available_indices.clear()

    handle_single_result_left(
        RankReasonTy.HAS_N_FALSE_POSITIVES,
        lambda mk_rank_reason: mk_rank_reason(n=len(index_to_false_positives[available_indices[0]]))
  )

    # Rank the remaining results based on true positive count.
    # The higher the true positive count the better the ranking.
    if len(available_indices) > 0:
        indices_ordered_by_true_positives = sort_and_group(
            available_indices,
            key=lambda i: len(index_to_true_positives[i]),
            # Not reversed so that we process the results with the
            # least true positives first.
            reverse=False
        )
        indices_most_tp = []
        for index, grouped_list in enumerate(indices_ordered_by_true_positives):
            assert isinstance(grouped_list, list)
            number_of_true_positives = len(index_to_true_positives[grouped_list[0]])
            if index == len(indices_ordered_by_true_positives) -1:
                # This group has the most number of true positives that are
                # the same. So this should go on to the next stage of comparision
                indices_most_tp = grouped_list
                continue
            reversed_rank.append(
                RankPosition(grouped_list.copy(),
                    RankReasonTy.HAS_N_TRUE_POSITIVES.mk_rank_reason(n=number_of_true_positives)
                )
            )
        available_indices = indices_most_tp

    handle_single_result_left(
        RankReasonTy.HAS_N_TRUE_POSITIVES,
        lambda mk_rank_reason: mk_rank_reason(n=len(index_to_true_positives[available_indices[0]]))
    )

    # Rank the remaining the remaining result based on coverage.
    # More is better.
    def get_average_branch_coverage_value(branch_coverage):
        """
            Helper function to handle when working with merged
            coverage.
        """
        if all_results_are_merged:
            # There will be multiple branch coverage results. Take
            # whatever is considered to be the "average".
            assert isinstance(branch_coverage, list)
            _, branch_coverage, _ = coverage_range_fn(branch_coverage)
        return branch_coverage

    if len(available_indices) > 0:
        # FIXME: Should remove this?
        if coverage_replay_infos is None:
            reversed_rank.append(
                RankPosition(available_indices.copy(),
                    RankReasonTy.MISSING_COVERAGE_DATA.mk_rank_reason()
                )
            )
            available_indices = []
        else:
            # Retrieve coverage information
            index_to_coverage_info = _get_index_to_coverage_infos(
                native_program_name,
                index_to_number_of_repeat_runs_map,
                coverage_replay_infos)

            # Now sort remaining results based on coverage
            if all_results_are_single:
                # Single results can be sorted in a simple way
                indices_ordered_by_coverage = sort_and_group(
                    available_indices,
                    key=lambda i: index_to_coverage_info[i]['branch_coverage'],
                    # Not reversed so that we process the results with the
                    # smallest coverage first
                    reverse=False
                )
            elif all_results_are_merged:
                # Do a fuzzy sort based on bounds
                # FIXME: For now assume we are only sorting at most two results.
                assert len(available_indices) <= 2
                _logger.debug('Sorted coverage:')
                _logger.debug('available_indices: {}'.format(available_indices))
                _logger.debug('Coverage values: {}'.format([ index_to_coverage_info[i]['branch_coverage'] for i in available_indices]))
                indices_ordered_by_coverage = fuzzy_sort_and_group(
                    available_indices,
                    coverage_range_fn,
                    key=lambda i: index_to_coverage_info[i]['branch_coverage'],
                    # Not reversed so that we process the results with the
                    # smallest coverage first
                    reverse=False
                )
                _logger.debug('indices_ordered_by_coverage: {}'.format(indices_ordered_by_coverage))
            else:
                raise Exception("Can't sort coverage of merged and single results")
            indices_most_coverage = []
            for index, grouped_list in enumerate(indices_ordered_by_coverage):
                assert isinstance(grouped_list, list)
                branch_coverage = get_average_branch_coverage_value(index_to_coverage_info[grouped_list[0]]['branch_coverage'])
                if index == len(indices_ordered_by_coverage) -1:
                    # This group has the most amount of coverage and so
                    # should go on to the next stage of the comparison
                    indices_most_coverage = grouped_list
                    continue
                reversed_rank.append(
                    RankPosition(grouped_list.copy(),
                        RankReasonTy.HAS_N_PERCENT_BRANCH_COVERAGE.mk_rank_reason(n=branch_coverage))
                )
            # Allow the first tied result to proceed to the next comparison
            available_indices = indices_most_coverage

    handle_single_result_left(
        RankReasonTy.HAS_N_PERCENT_BRANCH_COVERAGE,
        lambda mk_rank_reason: mk_rank_reason(
            n=get_average_branch_coverage_value(index_to_coverage_info[available_indices[0]]['branch_coverage']))
    )

    # Rank based on numbers of crashes.
    # All tools that have 0 crashes go on to the next stage.
    # The tools that have a non-zero amount of crashes are ranked.
    # If there are tools that have an equal (non-zero) amount of crashes
    # they tie but do not go on to the next stage. This is because it is
    # meaningless to compare the execution times of tools if they crashed.
    index_to_number_of_crashes = []
    indices_no_crashes = []
    for result_info in result_infos:
        # FIXME: We might not need to compute for all indices. We should only
        # do for the available_indices.
        index_to_number_of_crashes.append(get_number_of_crashes(result_info))
    indices_ordered_by_crashes = sort_and_group(
        available_indices,
        key=lambda i: index_to_number_of_crashes[i],
        # Reversed so we process the results with the most
        # number of crashes first
        reverse=True
    )
    for index, grouped_list in enumerate(indices_ordered_by_crashes):
        number_of_crashes = index_to_number_of_crashes[grouped_list[0]]
        if index == len(indices_ordered_by_crashes) -1:
            # The indicies with the least amount of crashes.
            # Only if this group has zero crashes should they
            # go on to the next stage of comparison
            if number_of_crashes == 0:
                # Zero crashes
                indices_no_crashes = grouped_list
                continue
        # Otherwise we rank preventing these indices from being
        # consider for the next stage of comparison
        reversed_rank.append(
            RankPosition(grouped_list.copy(),
                RankReasonTy.HAS_N_CRASHES.mk_rank_reason(n=number_of_crashes))
        )
    available_indices = indices_no_crashes
    handle_single_result_left(
        RankReasonTy.HAS_N_CRASHES,
        lambda mk_rank_reason: mk_rank_reason(n=index_to_number_of_crashes[available_indices[0]])
    )


    # Rank remaining results based on execution time
    # Less is better
    def get_average_execution_time_value(execution_time):
        """
            Helper function to handle when working with merged
            execution_times.
        """
        if all_results_are_merged:
            # There will be multiple branch coverage results. Take
            # whatever is considered to be the "average".
            assert isinstance(execution_time, list)
            _, execution_time, _ = timing_range_fn(execution_time)
        return execution_time
    if len(available_indices) > 0:
        index_to_execution_times = _get_index_to_execution_times(result_infos, index_to_number_of_repeat_runs_map)
        assert isinstance(index_to_execution_times, list)
        assert len(index_to_execution_times) == len(result_infos)
        # FIXME: This needs rethinking if a tool crashes it could have a very
        # short execution time which will actually bring down the average
        # execution time of a tool.
        if all_results_are_single:
            indices_ordered_by_execution_time = sort_and_group(
                available_indices,
                key=lambda i: index_to_execution_times[i]['execution_time'],
                # Reversed so that we process the results with the
                # largest execution time first.
                reverse=True
            )
        elif all_results_are_merged:
            # Do a fuzzy sort based on bound
            # FIXME: For now assume we are only sorting at most two results
            assert len(available_indices) <= 2
            _logger.debug('Sorted execution times:')
            _logger.debug('available_indices: {}'.format(available_indices))
            _logger.debug('timing values: {}'.format([ index_to_execution_times[i]['execution_time'] for i in available_indices]))
            indices_ordered_by_execution_time = fuzzy_sort_and_group(
                available_indices,
                timing_range_fn,
                key=lambda i: index_to_execution_times[i]['execution_time'],
                # Reversed so that we process the results with the
                # largest execution time first.
                reverse=True
            )
            _logger.debug('indices_ordered_by_execution_time: {}'.format(indices_ordered_by_execution_time))
            # HACK:
            if len(indices_ordered_by_execution_time) == 2:
                for _i in available_indices:
                    times = index_to_execution_times[_i]['execution_time']
                    stdev = statistics.stdev(times)
                    if stdev > __hack_stdev:
                        __hack_stdev = stdev
                        _logger.warning('LARGEST STDEV: {}'.format(__hack_stdev))
        else:
            raise Exception("Can't sort coverage of merged and single results")
        indices_least_execution_time = []
        for index, grouped_list in enumerate(indices_ordered_by_execution_time):
            assert isinstance(grouped_list, list)
            execution_time = get_average_execution_time_value(index_to_execution_times[grouped_list[0]]['execution_time'])
            if index == len(indices_ordered_by_execution_time) -1:
                # This group has the shortest execution time and so
                # should go on to the next stage of the comparison
                indices_least_execution_time = grouped_list
                continue
            reversed_rank.append(
                RankPosition(grouped_list.copy(),
                    RankReasonTy.HAS_T_SECOND_EXECUTION_TIME.mk_rank_reason(t=execution_time))
            )
        # Allow the first tied result to proceed to the next comparison
        available_indices = indices_least_execution_time

        handle_single_result_left(
            RankReasonTy.HAS_T_SECOND_EXECUTION_TIME,
            lambda mk_rank_reason: mk_rank_reason(
                t=get_average_execution_time_value(index_to_execution_times[available_indices[0]]['execution_time']))
        )

    if len(available_indices) > 0:
        # Remaining results cannot be ranked and are tied
        reversed_rank.append(
            RankPosition(
                available_indices.copy(),
                RankReasonTy.TIED.mk_rank_reason()
            )
        )
        available_indices.clear()


    # Finally re-order ranked results so highest ranked
    # comes first.
    reversed_rank.reverse()
    return reversed_rank


def fuzzy_sort_and_group(iter, get_range_fn, key=None, reverse=False):
    """
        This function is similar to `sort_and_group` but it meant to be used
        in situations where applying key returns a list of numbers rather than
        a single number (i.e. it used when we have repeated measurements of
        a numeric quanity, e.g. coverage).

        The `get_range_fn` when applied to that list of numbers should return a tuple
        `(min_value, middle_value, max_value)` where `min_value` is some sort of lower
        bound `middle_value` is what the caller would like to use to represent the data set
        (e.g. arithmetic mean) and `max_value` is some soft of upper bound.

        Like `sort_and_group` this function will return a list of lists where each inner
        list is the items from `iter` that are considered the same based on the output of
        `get_range_fn`.

        However unlike `sort_and_group` items from `iter` may be repeated. This is due to
        the nature of the fuzzy sort. For example if we had `[A, B, C]` we might determine
        that `A` and `B` should be considered the same, `B` and `C` should be considered the
        same but `A` and `C` should be considered distinct. Therefore the returned result would
        need to be `[ [A, B], [B, C] ]` where the `B` item is repeated.
    """
    # FIXME: I'm going to be lazy here. Currently I know that `iter` will contain at most two
    # items so I can write a significantly simpler algorithm.
    iter_items = list(iter)

    # No items
    if len(iter_items) == 0:
        return []

    # One item. No sort required
    if len(iter_items) == 1:
        return [ [ ite_items[0] ] ]

    if len(iter_items) != 2:
        raise Exception('Not implemented for more than two items')

    # Compute keys
    keys = []
    for item in iter_items:
        if key:
            keys.append(key(item))
        else:
            keys.append(item)

    # Compute bounds
    ranges = []
    for key in keys:
        lower_bound, middle_value, upper_bound = get_range_fn(key)
        assert lower_bound <= middle_value
        assert middle_value <= upper_bound
        bounds = BoundType(lower_bound=lower_bound, upper_bound=upper_bound)
        _logger.debug('Computed bounds: {}'.format(bounds))
        ranges.append(bounds)

    assert len(ranges) == 2
    # Constructed as if reverse=False
    ret_list = None
    if ranges[0].upper_bound < ranges[1].lower_bound:
        # [ 0 ]  [ 1 ]
        ret_list = [ [iter_items[0]], [iter_items[1]] ]
    elif ranges[1].upper_bound < ranges[0].lower_bound:
        # [ 1 ]  [ 0 ]
        ret_list = [ [iter_items[1]], [iter_items[0]] ]
    else:
        # Considered the same. The bounds overlap in some way
        ret_list = [ [iter_items[0], iter_items[1] ] ]

    if reverse:
        ret_list.reverse()
    return ret_list

def sort_and_group(iter, key=None, reverse=False):
    sorted_iter = sorted(iter, key=key, reverse=reverse)
    grouped = []
    for index, value in enumerate(sorted_iter):
        if index == 0:
            grouped.append([value])
            continue
        # Get list at the head of the list
        head_list = grouped[-1]
        assert isinstance(head_list, list)
        if key(head_list[0]) == key(value):
            # Same to sort by so group together
            head_list.append(value)
        else:
            # Different sorting value so add new value
            grouped.append([value])
    return grouped

def _get_index_to_coverage_infos(native_program_name, index_to_number_of_repeat_runs_map, coverage_replay_infos):
    index_to_coverage_info = []
    for index, cri in enumerate(coverage_replay_infos):
        try:
            coverage_info = cri[native_program_name]
        except KeyError as e:
            _logger.warning(
                'Could not find "{}" in coverage info'.format(native_program_name))
            # Assume zero coverage
            if len(index_to_number_of_repeat_runs_map) == 0:
                # We are handling single runs
                coverage_info = {
                    'branch_coverage': 0.0,
                    'line_coverage': 0.0,
                    'raw_data': None,
                }
            else:
                # We are handling repeat runs
                number_of_repeat_runs = index_to_number_of_repeat_runs_map[index]
                assert number_of_repeat_runs > 1
                coverage_info = {
                    'branch_coverage': [ 0.0 for _ in range(0, number_of_repeat_runs) ],
                    'line_coverage': [ 0.0 for _ in range(0, number_of_repeat_runs) ],
                    'raw_data': None,
                }
        index_to_coverage_info.append(coverage_info)
    return index_to_coverage_info

def _get_index_to_execution_times(result_infos, index_to_number_of_repeat_runs_map):
    index_to_execution_times = []
    user_and_sys_time_available = True
    timing_info_template = {
        # 'execution_time': 0.0,
    }
    for index, result_info in enumerate(result_infos):
        user_time = result_info['user_cpu_time']
        sys_time = result_info['sys_cpu_time']
        if len(index_to_number_of_repeat_runs_map) == 0:
            # Individual result
            if user_time is None or sys_time is None:
                user_and_sys_time_available = False
                break
            # More accurate timings available
            timing_info = timing_info_template.copy()
            timing_info['execution_time'] = user_time + sys_time
        else:
            # Merged result
            assert isinstance(user_time, list)
            assert isinstance(sys_time, list)
            _logger.debug('user_time: {}'.format(user_time))
            _logger.debug('sys_time: {}'.format(sys_time))
            if len(list(filter(lambda t: t is None, user_time))) > 0 or len(list(filter(lambda t: t is None, sys_time))) > 0:
                user_and_sys_time_available = False
                break
            timing_info = timing_info_template.copy()
            timing_info['execution_time'] = list(map(lambda t: t[0] + t[1], zip(user_time, sys_time)))
        index_to_execution_times.append(timing_info)

    if user_and_sys_time_available:
        # Every result info had accurate timings so use those
        return index_to_execution_times

    _logger.warning('Accurate execution time unavailable. Falling back to wallclock time for {}'.format(
        result_infos[0]['invocation_info']['program']))
    # We don't have accurate timings for every result info
    # fall back to wallclock time instead.
    index_to_execution_times.clear()
    for index, result_info in enumerate(result_infos):
        timing_info = timing_info_template.copy()
        timing_info['execution_time'] = result_info['wallclock_time']
        index_to_execution_times.append(timing_info)
    return index_to_execution_times

def _get_bug_replay_corrected_bugs(native_program_name, _true_positives, _false_positives, bug_replay_info):
    if len(_true_positives) == 0 and len(_false_positives) == 0:
        return _true_positives, _false_positives

    true_positives = []
    false_positives = []
    made_changes = False
    try:
        bug_replay_info_for_program = bug_replay_info[native_program_name]
    except KeyError as e:
        _logger.error('Could not find "{}" in bug replay info'.format(native_program_name))
        raise e
    replayed_test_cases = bug_replay_info_for_program['test_cases']
    assert isinstance(replayed_test_cases, dict)

    for test_case in _true_positives:
        ktest_file_path = test_case.ktest_file
        _logger.debug('Confirming {}'.format(ktest_file_path))
        try:
            replay_info = replayed_test_cases[ktest_file_path]
        except KeyError as e:
            _logger.error('Could not find "{}" ktest file in replayed bug info'.format(ktest_file_path))
            raise e
        assert isinstance(replay_info, dict)
        if replay_info['confirmed'] is True:
            true_positives.append(test_case)
        else:
            assert replay_info['confirmed'] is False
            _logger.warning('Bug replay for "{}" with "{}" was not confirmed. TREATING AS FALSE POSITIVE!'.format(
                native_program_name,
                ktest_file_path))
            made_changes = True
            false_positives.append(test_case)

    for test_case in _false_positives:
        ktest_file_path = test_case.ktest_file
        _logger.debug('Confirming {}'.format(ktest_file_path))
        try:
            replay_info = replayed_test_cases[ktest_file_path]
        except KeyError as e:
            _logger.error('Could not find "{}" ktest file in replayed bug info'.format(ktest_file_path))
            raise e
        assert isinstance(replay_info, dict)
        if replay_info['confirmed'] is False:
            false_positives.append(test_case)
        else:
            assert replay_info['confirmed'] is True
            _logger.warning('Bug replay for "{}" with "{}" was confirmed. TREATING AS TRUE POSITIVE!'.format(
                native_program_name,
                ktest_file_path,
                ))
            made_changes = True
            true_positives.append(test_case)

    if made_changes:
        _logger.debug('True positives:\n{}\nreplaced with\n{}'.format(pprint.pformat(_true_positives), pprint.pformat(true_positives)))
        _logger.debug('False positives:\n{}\nreplaced with\n{}'.format(pprint.pformat(_false_positives), pprint.pformat(false_positives)))
    return true_positives, false_positives

def strip_duplicate_bug_test_cases(test_cases):
    """
    Given a list of test cases return a list of test cases
    where each error location is only reported once.
    """
    assert isinstance(test_cases, list)
    # Set of tuples (<file_name>, <line_number>)
    seen_locations = set()
    test_cases_to_keep = []
    for index, test_case in enumerate(test_cases):
        assert isinstance(test_case, kleedir.test.Test)
        file_name = test_case.error.file
        line_number = test_case.error.line
        identifier = (file_name, line_number)
        if identifier in seen_locations:
            _logger.debug('At index {} already seen {} . Skipping'.format(
                index,
                identifier))
            continue
        _logger.debug('At index {} adding test case {}'.format(
            index,
            identifier))
        test_cases_to_keep.append(test_case)
        seen_locations.add(identifier)
    return test_cases_to_keep

def get_number_of_crashes(result_info):
    """
        Here we consider a crash to be a non zero exit code or
        an out of memory termination. Although these two things
        are distinct we don't consider any one to be better than
        the other in terms of ranking.
    """
    assert isinstance(result_info, dict)
    # FIXME: We can't use analyse.get_generic_run_outcomes()
    # because we can't distinguish between a crash and an out
    # of memory situation properly
    #reports = analyse.get_generic_run_outcomes(result_info)
    is_merged_result = analyse.raw_result_info_is_merged(result_info)
    non_zero_exit_code_count = 0 # Only counted if it wasn't an out of memory run
    out_of_memory_count = 0
    if is_merged_result:
        assert isinstance(result_info['out_of_memory'], list)
        assert isinstance(result_info['exit_code'], list)
        assert len(result_info['out_of_memory']) == len(result_info['exit_code'])
        for index, oom in enumerate(result_info['out_of_memory']):
            corresponding_exit_code = result_info['exit_code'][index]
            if oom is True:
                out_of_memory_count += 1
            elif corresponding_exit_code is not None and corresponding_exit_code != 0:
                non_zero_exit_code_count += 1
    else:
        if result_info['out_of_memory'] is True:
            out_of_memory_count += 1
        elif result_info['exit_code'] is not None and result_info['exit_code'] != 0:
            non_zero_exit_code_count += 1
    return non_zero_exit_code_count + out_of_memory_count
