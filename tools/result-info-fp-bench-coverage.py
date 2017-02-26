#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Take two klee-runner output files and report report
on their capability and complementarity on fp-bench.
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
import kleeanalysis.rank
import kleeanalysis.kleedir
from kleeanalysis.kleedir import KleeDir
from kleeanalysis import analyse
import kleeanalysis.verificationtasks
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

def result_info_shows_verified(key, index, result_info):
    klee_dirs = []
    if analyse.raw_result_info_is_merged(result_info):
        # Multiple klee directories. Construct them
        # individually. If any single run managed to
        # verify the benchmark count it.
        for klee_dir in result_info['klee_dir']:
            klee_dirs.append(KleeDir(klee_dir))
    else:
        klee_dirs.append(KleeDir(result_info['klee_dir']))
    # Now go through each KLEE directory. If at least one
    # run verified the benchmark and no runs reported incorrect
    # then count as verified.
    tool_reports_correct = False
    tool_reports_incorrect = False
    for klee_dir in klee_dirs:
        kvrs = analyse.get_klee_verification_results_for_fp_bench(
            klee_dir,
            allow_invalid_klee_dir=True)
        for kvr in kvrs:
            if isinstance(kvr, analyse.KleeResultIncorrect):
                tool_reports_incorrect = True
                _logger.warning('index {} for {} reports incorrect'.format(
                    index,
                    key))
            elif isinstance(kvr, analyse.KleeResultUnknown):
                _logger.warning('index {} for {} reports unknown'.format(
                    index,
                    key))
            else:
                assert isinstance(kvr, analyse.KleeResultCorrect)
                tool_reports_correct = True
    if tool_reports_correct and not tool_reports_incorrect:
        return True
    return False

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_result_info_file",
                        help="First result info fle",
                        type=argparse.FileType('r'))
    parser.add_argument("second_result_info_file",
                        help="Second result info fle",
                        type=argparse.FileType('r'))
    parser.add_argument('-b', "--bug-replay-info",
        dest="bug_replay_info",
        default=[],
        nargs=2,
        help="bug replay info files (first corresponds first result info file)",
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
        key_to_expected_bugs = dict() # Stores benchmark names -> set of error location tuples (i.e. the count is in terms on bugs)
        true_negatives = set() # Stores benchmark names that are expected to bugs
        index_to_found_true_negatives = [] # Stores the true negatives found by a tool
        index_to_found_bugs = [] # Maps to a dictionary mapping benchmark names to found errors
        for key, result_info_list in sorted(key_to_result_infos.items(), key=lambda x:x[0]):
            _logger.info('Processing {}'.format(key))
            assert len(result_infos_list) > 1
            augmented_spec_file_path = analyse.get_augmented_spec_file_path(result_info_list[0])
            spec = analyse.load_spec(augmented_spec_file_path)
            is_correct_benchmark = True
            # Sanity check
            if ( set(spec['verification_tasks'].keys()) !=
                    kleeanalysis.verificationtasks.fp_bench_tasks ):
                raise Exception('tasks missing')
            # Walk through tasks gathering expected bugs
            for task, task_info in spec['verification_tasks'].items():
                assert task_info['correct'] is not None
                if task_info['correct'] is False:
                    is_correct_benchmark = False
                    # Collect expected bugs
                    bug_set = None
                    try:
                        bug_set = key_to_expected_bugs[key]
                    except KeyError:
                        bug_set = set()
                        key_to_expected_bugs[key] = bug_set
                    if 'counter_examples' not in task_info:
                        raise Exception('{} is missing counter examples'.format(key))
                    for counter_example_data in task_info['counter_examples']:
                        for location_data in counter_example_data['locations']:
                            unique_id = (task, location_data['file'], location_data['line'])
                            _logger.debug('Adding bug location {} for {}'.format(unique_id, key))
                            bug_set.add(unique_id)
            # Prepare data structures in not already
            if len(index_to_found_true_negatives) == 0:
                for _ in result_info_list:
                    index_to_found_true_negatives.append(set())
                    index_to_found_bugs.append(dict())

            if is_correct_benchmark:
                true_negatives.add(key)
                _logger.debug('Adding correct benchmark {}'.format(key))

            # Go through tool results and determine how complete each tool's exploration
            # was.
            for index, result_info in enumerate(result_info_list):
                if is_correct_benchmark:
                    if result_info_shows_verified(key, index, result_info):
                        _logger.info('{} reported as correct by {}'.format(
                            key,
                            index))
                        index_to_found_true_negatives[index].add(key)
                else:
                    # TODO
                    pass

        # Dump benchmark info
        print("# of benchmark suite expected true negatives: {}".format(len(true_negatives)))
        expected_bug_count = 0
        for bug_set in key_to_expected_bugs.values():
            expected_bug_count += len(bug_set)
        print("# of benchmark suite expected false positves: {}".format(expected_bug_count))

        # Dump tool info
        for index, _ in enumerate(result_infos_list):
            print("Tool ({}) {}".format(index, index_to_name_fn(index)))
            print("  # of correct: {} / {}".format(
                len(index_to_found_true_negatives[index]),
                len(true_negatives)
                )
            )

        # Dump intersection info
        found_true_negative_intersection = None
        for index, found_true_negatives in enumerate(index_to_found_true_negatives):
            assert isinstance(found_true_negatives, set)
            if found_true_negative_intersection is None:
                found_true_negative_intersection = found_true_negatives.copy()
                continue
            found_true_negative_intersection = found_true_negative_intersection.intersection(
                found_true_negatives)
        print("# of correct intersection: {}".format(len(found_true_negative_intersection)))

        # Dump complement of union info (i.e. what neither tool handled)
        found_true_negative_union = set()
        for index, found_true_negatives in enumerate(index_to_found_true_negatives):
            assert isinstance(found_true_negatives, set)
            found_true_negative_union = found_true_negative_union.union(found_true_negatives)
        found_true_negative_union_complement = true_negatives.difference(found_true_negative_union)
        print("# of correct in union complement (i.e. not found by any tool): {}".format(
            len(found_true_negative_union_complement)))


    except Exception as e:
        _logger.error(e)
        raise e

    return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))