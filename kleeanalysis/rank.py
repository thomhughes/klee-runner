# vim: set sw=4 ts=4 softtabstop=4 expandtab:

import copy
import logging
import os
from collections import namedtuple
from .kleedir import KleeDir
from . import analyse
from enum import Enum

_logger = logging.getLogger(__name__)

RankReason = namedtuple('RankReason', ['rank_reason_type', 'msg'])

class RankReasonTy(Enum):
    HAS_N_FALSE_POSITIVES = (0, "Has {n} false positives")
    HAS_N_TRUE_POSITIVES = (1, "Has {n} true positives")
    HAS_N_PERCENT_BRANCH_COVERAGE = (2, "Has {n:%} branch coverage")
    TIED = (3, "Results are tied")
    # FIXME: These should be removed
    MISSING_COVERAGE_DATA= (4, "Cannot be ranked. Requires coverage data")
    MISSING_TIME_RANK_IMPL= (5, "Cannot be ranked. Requires timing  ranking to be implemented")

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

def rank(result_infos, bug_replay_infos=None, coverage_replay_infos=None):
    """
        Given a list of `result_infos` compute a ranking. Optionally using
        `bug_replay_infos` and `coverage_replay_infos`.

        Returns `rank_reason_list`.

        where

        `rank_reason_list` is a list of `RankPosition`s. `RankPosition`s earlier
        in the list are ranked higher (better). `RankPosition` contains `results`
        which is a list of indicies (corresponding to `result_infos`) which are
        considered to be ranked the same.
    """
    assert isinstance(result_infos, list)
    # FIXME: We need support these
    assert bug_replay_infos is None

    # FIXME: We should stop using raw result infos
    for ri in result_infos:
        assert isinstance(ri, dict)
        assert 'invocation_info' in ri
    assert len(result_infos) > 1

    if coverage_replay_infos:
        assert isinstance(coverage_replay_infos, list)
        assert len(result_infos) == len(coverage_replay_infos)
    
    reversed_rank = []
    index_to_klee_dir_map = []
    for r in result_infos:
        klee_dir = KleeDir(r['klee_dir'])
        index_to_klee_dir_map.append(klee_dir)

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
        # TODO: Correct results based on `bug_replay_infos`
        if bug_replay_infos is not None:
            raise Exception('Not implemented')
        index_to_klee_spec_match.append(ksms)


    index_to_true_positives = [ ] # Bugs
    index_to_false_positives = [ ] # Reported bugs but are not real bugs

    for index, ksms in enumerate(index_to_klee_spec_match):
        true_positives = []
        false_positives = []
        for ksm in ksms:
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
            else:
                assert isinstance(ksm, analyse.KleeResultUnknownMatchSpec)
                pass
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
    # The higher the false positive count the worse the ranking.
    indices_ordered_by_false_positives = sort_and_group(
        available_indices,
        key=lambda i: len(index_to_false_positives[i]),
        # Reversed so that we process the results with the
        # most false positives first.
        reverse=True
    )
    _logger.debug('indices_ordered_by_false_positives: {}'.format(
        indices_ordered_by_false_positives))

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
        lambda mk_rank_reason: mk_rank_reason(n=index_to_false_positives[available_indices[0]])
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
        lambda mk_rank_reason: mk_rank_reason(n=index_to_true_positives[available_indices[0]])
    )

    # Rank the remaining the remaining result based on coverage.
    # More is better.
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
            llvm_bc_program_path = None
            index_to_coverage_info = []
            for index, cri in enumerate(coverage_replay_infos):
                assert isinstance(cri, dict)
                llvm_bc_program_path_try = result_infos[index]['invocation_info']['program']
                if llvm_bc_program_path is None:
                    llvm_bc_program_path = llvm_bc_program_path_try
                else:
                    # Sanity check
                    assert llvm_bc_program_path_try == llvm_bc_program_path

                # FIXME: this a fp-bench specific hack
                assert llvm_bc_program_path.endswith('.bc')
                native_program_name = os.path.basename(llvm_bc_program_path)
                native_program_name = native_program_name[:-3]

                try:
                    coverage_info = cri[native_program_name]
                except KeyError as e:
                    _logger.warning(
                        'Could not find "{}" in coverage info'.format(native_program_name))
                    # Assume zero coverage
                    coverage_info = {
                        'branch_coverage': 0.0,
                        'line_coverage': 0.0,
                        'raw_data': None,
                    }
                index_to_coverage_info.append(coverage_info)

            # Now remaining results based on coverage
            # FIXME: How is this going to work when we have an error bound?
            # we need some sort of fuzzy group and sort.
            indices_ordered_by_coverage = sort_and_group(
                available_indices,
                key=lambda i: index_to_coverage_info[i]['branch_coverage'],
                # Reversed so that we process the results with the
                # smallest coverage first
                reverse=False
            )
            indices_most_coverage = []
            for index, grouped_list in enumerate(indices_ordered_by_coverage):
                assert isinstance(grouped_list, list)
                branch_coverage = index_to_coverage_info[grouped_list[0]]['branch_coverage']
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
            n=index_to_coverage_info[available_indices[0]]['branch_coverage'])
    )

    # Rank remaining results based on execution time
    # Less is better
    if len(available_indices) > 0:
        # FIXME: Implement timing ranking
        reversed_rank.append(
            RankPosition(available_indices.copy(),
                RankReasonTy.MISSING_TIME_RANK_IMPL.mk_rank_reason()
            )
        )
        available_indices.clear()

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
