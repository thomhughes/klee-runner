# vim: set sw=4 ts=4 softtabstop=4 expandtab:

class RankReasonStr:
    pass

class RankReason:
    def __init__(self, indices, reason_str):
        assert isinstance(indices, list)
        assert len(indices) > 0
        assert isinstance(reason_str, str)
        self.results = result_infos
        self.reason = reason_str
        for i in self.results:
            assert isinstance(i, int)
            assert i >= 0

def rank(result_infos, bug_replay_infos=None, coverage_replay_infos=None):
    """
        Given a list of `result_infos` compute a ranking. Optionally using
        `bug_replay_infos` and `coverage_replay_infos`.

        Returns a tuple
        (rank_reason_list, unranked_list)

        where

        `rank_reason_list` is a list of `RankReason`s. `RankReasons`s earlier
        in the list are ranked higher (better). `RankReason` contains `results`
        which is a list of indicies (corresponding to `result_infos`) which are
        considered to be ranked the same.

        `unranked_list` is a list of `RanksReasons`s. It represents the
        `result_infos` that could not be ranked.
    """
    assert isinstance(result_infos, list)
    # FIXME: We need support these
    assert bug_replay_infos is None
    assert coverage_replay_infos is None

    # FIXME: We should stop using raw result infos
    for ri in result_infos:
        assert isinstance(ri, dict)
        assert 'invocation_info' in ri

    raise Exception('TODO')
