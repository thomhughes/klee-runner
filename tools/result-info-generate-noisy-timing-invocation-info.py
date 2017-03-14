#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a merged klee-runner result info file and output a new invocation info
that is a subset of the programs in the merged klee-runner.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
from load_klee_analysis import add_kleeanalysis_to_module_search_path
add_KleeRunner_to_module_search_path()
add_kleeanalysis_to_module_search_path()
from KleeRunner import InvocationInfo
from KleeRunner import ResultInfo
from kleeanalysis import analyse
from kleeanalysis import rank

import argparse
import logging
import os
import pprint
import random
import re
import sys
import yaml

_logger = None


def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-l", "--log-level", type=str, default="info",
                        dest="log_level",
                        choices=['debug', 'info', 'warning', 'error'])
    parser.add_argument("--check-program-path", dest="check_program_path",
                        default=False, action='store_true')
    parser.add_argument('merged_result_info_file',
                        help='Merged result info file',
                        type=argparse.FileType('r'))
    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')
    parser.add_argument('--max-noisy-programs',
        dest='max_noisy_programs',
        default=0,
        type=int,
        help='The maximum number of programs to output where the execution time is noisy')
    parser.add_argument('--max-not-noisy-programs',
        dest='max_not_noisy_programs',
        default=0,
        type=int,
        help='The maximum number of programs to output where the execution time is not noisy')
    parser.add_argument('--noisy-abs-bound-threshold',
        dest='noisy_abs_bound_threshold',
        default=5,
        type=int
    )
    parser.add_argument('--randomize-order',
        dest='randomize_order',
        default=False,
        action='store_true'
    )

    pargs = parser.parse_args()
    logLevel = getattr(logging, pargs.log_level.upper(), None)
    logging.basicConfig(level=logLevel)
    _logger = logging.getLogger(__name__)

    resultInfo =  ResultInfo.loadRawResultInfos(pargs.merged_result_info_file)

    # Find runs where the execution time is very noisy
    ii_diff_above_threshold_tuples = []
    ii_diff_below_threshold_tuples = []
    for index, r in enumerate(resultInfo['results']):
        if not analyse.raw_result_info_is_merged(r):
            _logger.error('result info must be a merged result info')
            return 1
        execution_times = get_execution_times(r)
        lower_bound, _, upper_bound = rank.get_arithmetic_mean_and_99_confidence_intervals(
            execution_times)

        diff = upper_bound - lower_bound
        if diff > pargs.noisy_abs_bound_threshold:
            _logger.debug('bound {} larger than {} for {}'.format(
                diff,
                pargs.noisy_abs_bound_threshold,
                r['invocation_info']['program']
            ))
            ii_diff_above_threshold_tuples.append((r['invocation_info'], diff))
        else:
            ii_diff_below_threshold_tuples.append((r['invocation_info'], diff))

    # Sort by execution time (longest running first)
    ii_diff_above_threshold_tuples = sorted(
        ii_diff_above_threshold_tuples,
        key=lambda t: t[1],
        reverse=True)
    ii_diff_below_threshold_tuples = sorted(
        ii_diff_below_threshold_tuples,
        key=lambda t: t[1],
        reverse=True)

    new_ii_jobs = []
    above_counter = 0
    for (ii, diff) in ii_diff_above_threshold_tuples:
        if above_counter >= pargs.max_noisy_programs:
            _logger.info('Reached max noisy program limit of {}'.format(
                pargs.max_noisy_programs))
            break
        _logger.info('Adding noisy program {} with diff of {}'.format(
            ii['program'],
            diff))
        new_ii_jobs.append(ii)
        above_counter += 1
    below_counter = 0
    for (ii, diff) in ii_diff_below_threshold_tuples:
        if below_counter >= pargs.max_not_noisy_programs:
            _logger.info('Reached max not noisy program limit of {}'.format(
                pargs.max_not_noisy_programs))
            break
        _logger.info('Adding not noisy program {} with diff of {}'.format(
            ii['program'],
            diff))
        new_ii_jobs.append(ii)
        below_counter += 1

    if pargs.randomize_order:
        _logger.info('Randomizing order')
        random.shuffle(new_ii_jobs)

    _logger.info('Kept {} jobs'.format(len(new_ii_jobs)))
    invocationInfos = dict()
    invocationInfos['jobs'] = new_ii_jobs
    invocationInfos['schema_version'] = InvocationInfo.getSchema()['__version__']
    as_yaml = yaml.dump(invocationInfos, default_flow_style=False)
    pargs.output.write(as_yaml)
    return 0

def get_execution_times(r):
    # HACK: Use internal function to get the execution time that is
    # used for ranking.
    assert isinstance(r, dict)
    result_infos = [r]
    number_of_repeat_runs = 1
    if isinstance(r['wallclock_time'], list):
        number_of_repeat_runs = len(r['wallclock_time'])
    index_to_number_of_repeat_runs_map = [ number_of_repeat_runs ]
    execution_times = rank._get_index_to_execution_times(
        result_infos,
        index_to_number_of_repeat_runs_map
    )
    assert isinstance(execution_times, list)
    return execution_times[0]['execution_time']

if __name__ == '__main__':
    sys.exit(main(sys.argv))
