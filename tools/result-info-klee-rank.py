#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Take two klee-runner output files and rank their results
in terms of bug finding.
"""

import argparse
import logging
import pprint
import os
import sys
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import KleeRunner.ResultInfoUtil
import kleeanalysis
import kleeanalysis.analyse
import kleeanalysis.rank
_logger = logging.getLogger(__name__)

def handle_rejected_result_infos(rejected_result_infos, index_to_name_fn):
    assert len(rejected_result_infos) == 2
    assert isinstance(rejected_result_infos, list)
    had_rejected_result_infos = False
    for index, rejected_result_infos_list in enumerate(rejected_result_infos):
        name = index_to_name_fn(index)
        assert(isinstance(rejected_result_infos_list, list))
        for result_info in rejected_result_infos_list:
            had_rejected_result_infos = True
            _logger.warning('"{}" was rejected from "{}"'.format(
                KleeRunner.ResultInfoUtil.get_result_info_key(result_info),
                name))
    return had_rejected_result_infos

def report_missing_result_infos(key_to_result_infos, index_to_name_fn):
    assert isinstance(key_to_result_infos, dict)
    had_missing_result_infos = False
    for key, result_infos in key_to_result_infos.items():
        assert(isinstance(result_infos, list))
        for index, result_info in enumerate(result_infos):
            if result_info is None:
                had_missing_result_infos = True
                name = index_to_name_fn(index)
                _logger.warning('"{}" is missing from "{}"'.format(
                    key,
                    name))
    return had_missing_result_infos

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_result_info_file",
                        help="First result info fle",
                        type=argparse.FileType('r'))
    parser.add_argument("second_result_info_file",
                        help="Second result info fle",
                        type=argparse.FileType('r'))
    parser.add_argument('-c', "--coverage-info",
        dest="coverage_info",
        default=[],
        nargs=2,
        help="coverage info files (first corresponds first result info file)",
    )
    parser.add_argument('-b', "--bug-replay-info",
        dest="bug_replay_info",
        default=[],
        nargs=2,
        help="bug replay info files (first corresponds first result info file)",
    )
    parser.add_argument("--categories",
       nargs='+',
       help='Only analyse results where the bencmark belongs to all specified categories',
       default=[]
    )
    parser.add_argument("--max-exec-time",
        dest='max_exec_time',
        default=None,
        type=float,
        help="Inform ranking algorithm of max time above which is considered a timeout",
    )
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args, parser)

    key_to_result_infos = None
    rejected_result_infos = None
    try:
        # FIXME: Don't use raw form
        if args.first_result_info_file.name == args.second_result_info_file.name:
            _logger.error("First and second result-infos file cannot be the same")
            return 1

        _logger.info('Loading "{}"'.format(args.first_result_info_file.name))
        firstResultInfos = KleeRunner.ResultInfo.loadRawResultInfos(
            args.first_result_info_file)
        _logger.info('Loading "{}"'.format(args.second_result_info_file.name))
        secondResultInfos = KleeRunner.ResultInfo.loadRawResultInfos(
            args.second_result_info_file)

        result_infos_list = [ firstResultInfos, secondResultInfos ]
        key_to_result_infos, rejected_result_infos = (
            KleeRunner.ResultInfoUtil.group_result_infos_by(result_infos_list)
        )
        def index_to_name_fn(index):
            if index == 0:
                return args.first_result_info_file.name
            elif index == 1:
                return args.second_result_info_file.name
            else:
                raise Exception('Unhandled index "{}"'.format(index))
        had_rejected_result_infos = handle_rejected_result_infos(
            rejected_result_infos,
            index_to_name_fn
        )

        if had_rejected_result_infos:
            _logger.error('Rejected ResultInfo(s) where found.')
            return 1

        if len(key_to_result_infos) == 0:
            _logger.error('No accepeted result infos')
            return 1
        had_missing_result_infos = report_missing_result_infos(
            key_to_result_infos,
            index_to_name_fn)
        if had_missing_result_infos:
            _logger.error('Some result infos were missing')
            return 1

        coverage_replay_infos = None
        if args.coverage_info:
            # Open coverage files
            coverage_replay_infos = []
            assert len(args.coverage_info) == 2
            for cov_info_file_path in args.coverage_info:
                if not os.path.exists(cov_info_file_path):
                    _logger.error('"{}" does not exist'.format(cov_info_file_path))
                    return 1
                with open(cov_info_file_path, 'r') as f:
                    _logger.info('Loading coverage info file {}'.format(cov_info_file_path))
                    coverage_replay_infos.append(KleeRunner.util.loadYaml(f))
        bug_replay_infos = None
        if args.bug_replay_info:
            # Open bug replay files
            bug_replay_infos = []
            assert len(args.bug_replay_info) == 2
            for bug_replay_info_file_path in args.bug_replay_info:
                if not os.path.exists(bug_replay_info_file_path):
                    _logger.error('"{}" does not exist'.format(bug_replay_info_file_path))
                    return 1
                with open(bug_replay_info_file_path, 'r') as f:
                    _logger.info('Loading bug replay info file {}'.format(bug_replay_info_file_path))
                    bug_replay_infos.append(KleeRunner.util.loadYaml(f))


        # Now do rank
        key_to_RankResult_list_map = dict()
        key_to_first_wins_map = dict()
        key_to_second_wins_map = dict()
        key_to_ties_map = dict()
        for key, result_info_list in sorted(key_to_result_infos.items(), key=lambda x:x[0]):
            # Skip benchmarks not in requested categories
            if len(args.categories) > 0:
                # FIXME: fp-bench specific
                # Only process the result if the categories of the benchmark
                # are a superset of the requested categories.
                augmented_spec_file_path = kleeanalysis.analyse.get_augmented_spec_file_path(result_info_list[0])
                __spec = kleeanalysis.analyse.load_spec(augmented_spec_file_path)
                requested_categories = set(args.categories)
                benchmark_categories = set(__spec['categories'])
                if not benchmark_categories.issuperset(requested_categories):
                    _logger.warning('Skipping "{}" due to {} not being a superset of {}'.format(
                        __spec["name"],
                        benchmark_categories,
                        requested_categories)
                    )
                    continue
                else:
                    _logger.debug('Keeping "{}" due to {} being a superset of {}'.format(
                        __spec["name"],
                        benchmark_categories,
                        requested_categories)
                    )
                del __spec

            _logger.info('Ranking "{}"'.format(key))
            ranking = kleeanalysis.rank.rank(
                result_info_list,
                bug_replay_infos=bug_replay_infos,
                coverage_replay_infos=coverage_replay_infos,
                max_exec_time=args.max_exec_time)
            assert isinstance(ranking, list)
            key_to_RankResult_list_map[key] = ranking
            if len(ranking) == 1:
                # Must be a tie
                assert isinstance(ranking[0], kleeanalysis.rank.RankPosition)
                key_to_ties_map[key] = ranking[0]
                _logger.info('"{}" ranks {}'.format(key, ranking[0]))
            elif len(ranking) == 2:
                _logger.info('"{}" ranks.\n First:{}\nSecond:{}'.format(
                    key,
                    ranking[0],
                    ranking[1]))
                assert len(ranking[0].indices) == 1
                if ranking[0].indices[0] == 0:
                    key_to_first_wins_map[key] = ranking[0]
                else:
                    assert ranking[0].indices[0] == 1
                    key_to_second_wins_map[key] = ranking[0]
            else:
                raise Exception('Unexpected rank result')

        # Print stats about ranking
        def print_reasons(key_to_map):
            reason_to_count_map = dict()
            for _, rank_position in key_to_map.items():
                count = 0
                try:
                    count = reason_to_count_map[rank_position.rank_reason.rank_reason_type]
                except KeyError:
                    count = 0
                reason_to_count_map[rank_position.rank_reason.rank_reason_type] = count + 1
            for reason, count in sorted(reason_to_count_map.items(), key=lambda k:k[0]):
                print("  # of {}: {}".format(reason, count))
        def print_info_about(key_to_map, index):
            print("# of wins for \"{}\": {}".format(
                index_to_name_fn(index),
                len(key_to_map))
            )
            print_reasons(key_to_map)

        print_info_about(key_to_first_wins_map, 0)
        print_info_about(key_to_second_wins_map, 1)

        # Print information about ties
        print("# of ties: {}".format(len(key_to_ties_map)))
        print_reasons(key_to_ties_map)
    except Exception as e:
        _logger.error(e)
        raise e

    return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
