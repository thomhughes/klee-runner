#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Report simple statistics on a set of KLEE runs
"""

import argparse
import logging
from enum import Enum
import os
import pprint
# pylint: disable=wrong-import-position
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
add_KleeRunner_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import kleeanalysis.analyse
import kleeanalysis.verificationtasks
import kleeanalysis.kleedir
from kleeanalysis.kleedir import KleeDir
from kleeanalysis.analyse import KleeRunnerResult, \
    raw_result_info_is_merged, \
    get_num_merged_results, \
    get_klee_dir_outcomes

_logger = logging.getLogger(__name__)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--result-info-file",
                        dest="result_info_file",
                        help="result info file. (Default stdin)",
                        type=argparse.FileType('r'),
                        default=sys.stdin)
    parser.add_argument("--disallow-invalid-klee-dirs",
        dest="allow_invalid_klee_dir",
        action="store_false",
        default=True
    )
    parser.add_argument("--dump-verified-incorrect-no-assert-fail",
        dest="dump_verified_incorrect_no_assert_fail",
        action="store_true",
        default=False
    )
    parser.add_argument("--ignore-error-runs",
        dest="ignore_error_runs",
        action="store_true",
        default=False,
        help="Carry on report even if failed runs occurred",
    )
    parser.add_argument("--categories",
       nargs='+',
       help='Only analyse results where the bencmark belongs to all specified categories',
       default=[]
    )
    parser.add_argument("--no-normalize",
        dest="no_normalize",
        action='store_true',
        default=False,
        help="Don't normalize merged results"
    )
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args, parser)

    exitCode = 0
    _logger.info('Reading result infos from {}'.format(args.result_info_file.name))

    # Result counters
    summaryCounters = dict()
    multipleOutcomes = []
    for enum in list(KleeRunnerResult):
        summaryCounters[enum] = []

    error_runs = []
    num_raw_results = 0
    is_merged_result = None
    num_runs_in_merged_result = None
    try:
        # FIXME: Don't use raw form
        resultInfos = KleeRunner.ResultInfo.loadRawResultInfos(args.result_info_file)
        for index, result in enumerate(resultInfos["results"]):
            if 'error' in result:
                _logger.error('Found error result :{}'.format(pprint.pformat(result)))
                error_runs.append(result)
                if args.ignore_error_runs:
                    continue
                else:
                    return 1
            identifier = '{}'.format(
                result["invocation_info"]["program"]
            )
            # Load the spec
            spec = kleeanalysis.analyse.load_spec(
                kleeanalysis.analyse.get_augmented_spec_file_path(result))

            if len(args.categories) > 0:
                # FIXME: fp-bench specific
                # Only process the result if the categories of the benchmark
                # are a superset of the requested categories.
                requested_categories = set(args.categories)
                benchmark_categories = set(spec['categories'])
                if not benchmark_categories.issuperset(requested_categories):
                    _logger.warning('Skipping "{}" due to {} not being a superset of {}'.format(
                        identifier,
                        benchmark_categories,
                        requested_categories)
                    )
                    continue
                else:
                    _logger.debug('Keeping "{}" due to {} being a superset of {}'.format(
                        identifier,
                        benchmark_categories,
                        requested_categories)
                    )
            num_raw_results += 1

            if is_merged_result is None:
                is_merged_result = raw_result_info_is_merged(result)
                num_runs_in_merged_result = get_num_merged_results(result)
            elif is_merged_result is False:
                if raw_result_info_is_merged(result):
                    raise Exception('Mixed result types in file')
            else:
                assert is_merged_result is True
                if not raw_result_info_is_merged(result):
                    raise Exception('Mixed result types in file')
                if num_runs_in_merged_result != get_num_merged_results(result):
                    raise Exception('Number of runs mismatch')

            # Get OOM, bad exit, backend timeouts
            outcomes = kleeanalysis.analyse.get_generic_run_outcomes(result)

            # Create KLEE directories
            klee_dirs = []
            if is_merged_result:
                for klee_dir_path in result["klee_dir"]:
                    klee_dirs.append(KleeDir(klee_dir_path))
            else:
                klee_dirs.append(result["klee_dir"])

            klee_dir_outcomes = [ ]
            for klee_dir in klee_dirs:
                temp_outcomes = get_klee_dir_outcomes(klee_dir, check_for_soft_timeout=True)
                check_mixed_timeout(temp_outcomes, outcomes)
                klee_dir_outcomes.extend(temp_outcomes)
            outcomes.extend(klee_dir_outcomes)

            # Add outcomes
            for outcome in outcomes:
                summaryCounters[outcome.code].append(outcome)

            _logger.debug("{}: {}".format(identifier, pprint.pformat(outcomes)))
    except KeyboardInterrupt:
        _logger.info('Received KeyboardInterrupt')
        exitCode = 1

    print("")
    print('# of raw results: {}'.format(num_raw_results))
    for name , outcomes in sorted(summaryCounters.items(), key=lambda i: i[0].name):
        num_outcomes = len(outcomes)
        if is_merged_result:
            if not args.no_normalize:
                num_outcomes = float(num_outcomes) / num_runs_in_merged_result
            else:
                _logger.info('Not normalizing results')
        print("# of {}: {}".format(name, num_outcomes))

    return exitCode

def check_mixed_timeout(klee_dir_outcomes, outcomes):
    # This is a hack to check we don't end up double
    # counting timeouts. This should really ever happen.
    soft_timeout = False
    hard_timeout = False
    for outcome in outcomes:
        if outcome.code == KleeRunnerResult.OUT_OF_TIME:
            hard_timeout = True
            break
    for outcome in klee_dir_outcomes:
        if outcome.code == KleeRunnerResult.OUT_OF_TIME:
            soft_timeout = True
            break
    if soft_timeout and hard_timeout:
        _logger.error('Mixed timeout types\nSimple:{}\nklee dir:{}\n'.format(
            outcomes, klee_dir_outcomes))
        raise Exception('Mixed timeout types!')


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
