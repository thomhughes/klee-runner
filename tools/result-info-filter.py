#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info files and filter based on a predicate
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
add_KleeRunner_to_module_search_path()
from KleeRunner import ResultInfo

import argparse
import logging
import os
import pprint
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
    parser.add_argument('result_info_file',
                        help='Invocation info file',
                        type=argparse.FileType('r'))
    parser.add_argument('predicate',
                        type=str,
                        help="python expression to evaluate on result 'r'")
    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')

    pargs = parser.parse_args()
    logLevel = getattr(logging, pargs.log_level.upper(), None)
    logging.basicConfig(level=logLevel)
    _logger = logging.getLogger(__name__)

    resultInfos = ResultInfo.loadRawResultInfos(pargs.result_info_file)
    # Make shallow copy
    newResultInfos = resultInfos.copy()
    newResultInfos['results'] = []

    # FIXME: Should we try sanity check the predicate? The user
    # could specify literaly anything and could be dangerous to
    # execute.
    _logger.info('Compiling predicate "{}"'.format(pargs.predicate))
    predicate = eval('lambda r: {}'.format(pargs.predicate))

    # filter out non matching jobs by only copying over results that
    # match the predicate
    keepCount = 0
    for r in resultInfos['results']:
        if predicate(r):
            _logger.debug('Keeping result "{}"'.format(r))
            newResultInfos['results'].append(r)
            keepCount += 1
        else:
            _logger.debug('Removing result "{}"'.format(r))

    # Output as YAML
    pargs.output.write('# Automatically generated result info\n')
    pargs.output.write(yaml.dump(newResultInfos, default_flow_style=False))

    _logger.info('# kept: {}'.format(keepCount))
    _logger.info('# removed: {}'.format(
        len(resultInfos['results']) - keepCount))

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
