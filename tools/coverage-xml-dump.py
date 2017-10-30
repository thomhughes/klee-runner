#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
from load_native_analysis import add_nativeanalysis_to_module_search_path
add_KleeRunner_to_module_search_path()
add_nativeanalysis_to_module_search_path()
from KleeRunner import ResultInfo
import KleeRunner.DriverUtil as DriverUtil
from nativeanalysis import coverage

import argparse
import logging
import os
import pprint
import re
import sys

_logger = logging.getLogger(__name__)

def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coverage_xml_file',
                        help='Coverage XML file',
                        type=argparse.FileType('r'))
    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args(args)
    DriverUtil.handleLoggerArgs(pargs, parser)

    branch_cov = coverage.raw_coverage_xml_to_branch_cov_set(pargs.coverage_xml_file)
    print('Branch coverage set:\n{}'.format(pprint.pformat(branch_cov)))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

