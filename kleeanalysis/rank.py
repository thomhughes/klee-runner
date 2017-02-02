# vim: set sw=4 ts=4 softtabstop=4 expandtab:

import logging
from .kleedir import KleeDir
from . import analyse

_logger = logging.getLogger(__name__)

class RankReasonStr:
    HAS_N_FALSE_POSITIVES = "Has {n} false positives"
    HAS_N_TRUE_POSITIVES = "Has {n} true positives"
    HAS_N_PERCENT_COVERAGE = "Has {}% coverage"
    TIED = "Results are tied"
    # FIXME: These should be removed
    MISSING_COVERAGE_RANK_IMPL="Cannot be ranked. Requires coverage ranking to be implemented"
    MISSING_TIME_RANK_IMPL="Cannot be ranked. Requires timing  ranking to be implemented"

class RankReason:
    def __init__(self, indices, reason_str):
        assert isinstance(indices, list)
        assert len(indices) > 0
        assert isinstance(reason_str, str)
        self.indices = indices
        self.reason = reason_str
        for i in self.indices:
            assert isinstance(i, int)
            assert i >= 0

    def __str__(self):
        msg = None
        if len(self.indices) == 1:
            msg =  "index {} ranked because \"{}\"".format(
                self.indices[0],
                self.reason)
        else:
            msg =  "indices {} ranked same because \"{}\"".format(
                self.indices,
                self.reason)

        msg = "<RankReason: {}>".format(msg)
        return msg

def rank(result_infos, bug_replay_infos=None, coverage_replay_infos=None):
    """
        Given a list of `result_infos` compute a ranking. Optionally using
        `bug_replay_infos` and `coverage_replay_infos`.

        Returns `rank_reason_list`.

        where

        `rank_reason_list` is a list of `RankReason`s. `RankReasons`s earlier
        in the list are ranked higher (better). `RankReason` contains `results`
        which is a list of indicies (corresponding to `result_infos`) which are
        considered to be ranked the same.
    """
    assert isinstance(result_infos, list)
    # FIXME: We need support these
    assert bug_replay_infos is None
    assert coverage_replay_infos is None

    # FIXME: We should stop using raw result infos
    for ri in result_infos:
        assert isinstance(ri, dict)
        assert 'invocation_info' in ri
    assert len(result_infos) > 1
    
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
            RankReason(grouped_list.copy(),
                RankReasonStr.HAS_N_FALSE_POSITIVES.format(n=number_of_false_positives)
            )
        )
    available_indices = indices_least_fp
    _logger.debug('available_indices after processing false positives: {}'.format(
        available_indices))

    def handle_single_result_left(reason_str):
        if len(available_indices) == 1:
            reversed_rank.append(
                RankReason(
                    available_indices.copy(),
                    reason_str
                )
            )
            available_indices.clear()

    handle_single_result_left(RankReasonStr.HAS_N_FALSE_POSITIVES)

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
                RankReason(grouped_list.copy(),
                    RankReasonStr.HAS_N_TRUE_POSITIVES.format(n=number_of_true_positives)
                )
            )
        available_indices = indices_most_tp

    handle_single_result_left(RankReasonStr.HAS_N_TRUE_POSITIVES)

    # Rank the remaining the remaining result based on coverage.
    # More is better.
    if len(available_indices) > 0:
        # FIXME: Implement coverage ranking
        reversed_rank.append(
            RankReason(available_indices.copy(),
                RankReasonStr.MISSING_COVERAGE_RANK_IMPL
            )
        )
        available_indices = []

    handle_single_result_left(RankReasonStr.HAS_N_PERCENT_COVERAGE)

    # Rank remaining results based on execution time
    # Less is better
    if len(available_indices) > 0:
        # FIXME: Implement timing ranking
        reversed_rank.append(
            RankReason(available_indices.copy(),
                RankReasonStr.MISSING_TIME_RANK_IMPL
            )
        )
        available_indices = []

    if len(available_indices) > 0:
        # Remaining results cannot be ranked and are tied
        reversed_rank.append(
            RankReason(
                available_indices.copy(),
                RankReasonStr.TIED
            )
        )
        available_indices = []


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
