#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info describing a set of KLEE test case replays.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_native_analysis import add_nativeanalysis_to_module_search_path
add_KleeRunner_to_module_search_path()
add_kleeanalysis_to_module_search_path()
add_nativeanalysis_to_module_search_path()
from KleeRunner import ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import KleeRunner.InvocationInfo
import KleeRunner.util
import nativeanalysis.analyse

import argparse
import logging
import os
import pprint
import subprocess
import sys
import yaml

_logger = logging.getLogger(__name__)

def main(args):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_info_file',
                        help='Result info file',
                        type=argparse.FileType('r'))
    parser.add_argument('--dump-unknowns',
        dest='dump_unknowns',
        action='store_true')
    parser.add_argument('--dump-timeouts',
        dest='dump_timeouts',
        action='store_true')

    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args()
    DriverUtil.handleLoggerArgs(pargs, parser)

    _logger.info('Loading "{}"...'.format(pargs.result_info_file.name))
    resultInfos, resultInfoMisc  = ResultInfo.loadResultInfos(pargs.result_info_file)
    _logger.info('Loading complete')

    # Check the misc data
    if resultInfoMisc is None:
        _logger.error('Expected result info to have misc data')
        return 1
    if resultInfoMisc['runner'] != 'NativeReplay':
        _logger.error('Expected runner to have been NativeReplay but was "{}"'.format(
            resultInfoMisc['runner']))
        return 1

    errorTypeToErrorListMap = dict()
    multipeOutcomeList = []
    for result_index, r in enumerate(resultInfos):
        _logger.info('Processing {}/{}'.format(result_index + 1, len(resultInfos)))
        raw_result = r.GetInternalRepr()
        program_path = r.RawInvocationInfo['program']
        outcome = nativeanalysis.analyse.get_test_case_run_outcome(raw_result)
        error_list = None
        try:
            error_list = errorTypeToErrorListMap[type(outcome)]
        except KeyError:
            error_list = []
            errorTypeToErrorListMap[type(outcome)] = error_list
        error_list.append(outcome)

    # Print report
    print('#'*70)
    print("# of test cases with multiple outcomes: {}".format(len(multipeOutcomeList)))
    for ty, error_list in errorTypeToErrorListMap.items():
        print("# of {}: {}".format(ty, len(error_list)))
        if ty == nativeanalysis.analyse.UnknownError and pargs.dump_unknowns:
            for error in error_list:
                print(error)
        if ty == nativeanalysis.analyse.TimeoutError and pargs.dump_timeouts:
            for error in error_list:
                print(error)


    # Now emit as YAML
    #as_yaml = yaml.dump(program_to_coverage_info, default_flow_style=False)
    #pargs.output_yaml.write(as_yaml)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

