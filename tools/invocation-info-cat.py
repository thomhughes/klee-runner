#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read one or more invocation info files and concatenate the jobs
specified in them.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
add_KleeRunner_to_module_search_path()
from KleeRunner import InvocationInfo

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
    parser.add_argument('invocation_info_files',
                        help='Invocation info files',
                        nargs='+',
                        type=argparse.FileType('r'))
    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')

    pargs = parser.parse_args()
    logLevel = getattr(logging, pargs.log_level.upper(), None)
    logging.basicConfig(level=logLevel)
    _logger = logging.getLogger(__name__)

    # Collect jobs as strings because dictionary isn't hashable.
    seenJobs = set()
    # Use raw access so we don't add implicit fields
    rawData = []
    for f in pargs.invocation_info_files:
        _logger.info('Loading "{}"'.format(f.name))
        invocationInfos = InvocationInfo.loadRawInvocationInfos(f)
        rawData.append(invocationInfos)

        # Go through jobs
        for j in invocationInfos['jobs']:
            if str(j) in seenJobs:
                _logger.warning('Duplicate job detected:\n{}'.format(j))
            else:
                seenJobs.add(str(j))

    combined = rawData[0]

    for index in range(1, len(rawData)):
        combined['jobs'].extend(rawData[index]['jobs'])

    # Output as YAML
    pargs.output.write('# Automatically generated invocation info\n')
    pargs.output.write(yaml.dump(combined, default_flow_style=False))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
