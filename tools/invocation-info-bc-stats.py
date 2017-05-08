#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read an invocation info files and display information
about it.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
add_KleeRunner_to_module_search_path()
from KleeRunner import InvocationInfo

from collections import namedtuple
import argparse
import io
import logging
import os
import pprint
import re
import statistics
import subprocess
import sys
import tempfile
import yaml

_logger = None

class GlobalProgramStats:
    def __init__(self, **kwargs):
        self.min_branches = 0
        if 'min_branches' in kwargs:
            self.min_branches = kwargs['min_branches']
        self.max_branches = None
        if 'max_branches' in kwargs:
            self.max_branches = kwargs['max_branches']
        self.mean_branches = None
        if 'mean_branches' in kwargs:
            self.mean_branches = kwargs['mean_branches']
        self.std_dev_branches = None
        if 'std_dev_branches' is kwargs:
            self.std_dev_branches = kwargs['std_dev_branches']
        self.median_branches = None
        if 'median_branches' in kwargs:
            self.median_branches = kwargs['median_branches']
        
        self.min_sym_bytes = None
        if 'min_sym_bytes' in kwargs:
            self.min_sym_bytes = kwargs['min_sym_bytes']
        self.max_sym_bytes = None
        if 'max_sym_bytes' in kwargs:
            self.max_sym_bytes = kwargs['max_sym_bytes']
        self.mean_sym_bytes = None
        if 'mean_sym_bytes' in kwargs:
            self.mean_sym_bytes = kwargs['mean_sym_bytes']
        if 'std_dev_sym_bytes' is kwargs:
            self.std_dev_sym_bytes = kwargs['std_dev_sym_bytes']
        self.median_sym_bytes = None
        if 'median_sym_bytes' in kwargs:
            self.median_sym_bytes = kwargs['median_sym_bytes']

    def dump(self):
        print("min_branches: {}".format(self.min_branches))
        print("max_branches: {}".format(self.max_branches))
        print("mean_branches: {}".format(self.mean_branches))
        print("std_dev_branches: {}".format(self.std_dev_branches))
        print("median_branches: {}".format(self.median_branches))

        print("min_sym_bytes: {}".format(self.min_sym_bytes))
        print("max_sym_bytes: {}".format(self.max_sym_bytes))
        print("mean_sym_bytes: {}".format(self.mean_sym_bytes))
        print("std_dev_sym_bytes: {}".format(self.std_dev_sym_bytes))
        print("median_sym_bytes: {}".format(self.median_sym_bytes))


def get_stats(program_path, bc_stats_tool):
    num_branches = 0
    estimated_sym_bytes = 0
    with tempfile.TemporaryFile() as f:
        cmd_line = [bc_stats_tool, '-entry-point=main', program_path]
        _logger.debug('Calling {}'.format(cmd_line))
        subprocess.call(cmd_line, stdout=f)
        f.seek(0, io.SEEK_SET)
        data = yaml.load(f)
        num_branches = data['num_branches']
        estimated_sym_bytes = data['estimated_num_symbolic_bytes']

    return num_branches, estimated_sym_bytes

def get_augmented_spec_file(invocation_info):
    augmented_spec_file = invocation_info['misc']['augmented_spec_file']
    with open(augmented_spec_file, 'r') as f:
        data = yaml.load(f)
    return data

def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-l", "--log-level", type=str, default="info",
                        dest="log_level",
                        choices=['debug', 'info', 'warning', 'error'])
    parser.add_argument("--bc-stats",
        dest='bc_stats',
        type=str,
        help='path to bc-stats tool',
        default="bc-stats")
    parser.add_argument("--categories",
        nargs='+',
        default=[],
        help='One of more categories to keep',
    )
    parser.add_argument('invocation_info_file',
                        help='Invocation info file',
                        type=argparse.FileType('r'))

    pargs = parser.parse_args()
    logLevel = getattr(logging, pargs.log_level.upper(), None)
    logging.basicConfig(level=logLevel)
    _logger = logging.getLogger(__name__)

    invocationInfos = InvocationInfo.loadRawInvocationInfos(
        pargs.invocation_info_file)
    print("schema version: {}".format(invocationInfos['schema_version']))
    print("# of jobs: {}".format(len(invocationInfos['jobs'])))

    gs = GlobalProgramStats()
    gs.mean_branches = []
    gs.std_dev_branches = []
    gs.median_branches = []
    gs.mean_sym_bytes = []
    gs.median_sym_bytes = []
    gs.std_dev_sym_bytes = []
    categories = set(pargs.categories)
    drop_count = 0
    keep_count = 0
    for info in invocationInfos['jobs']:
        programPath = info['program']
        if not os.path.exists(programPath):
            _logger.error(
                'Program path "{}" does not exist'.format(programPath))
        if len(categories) > 0:
            augmented_spec_file = get_augmented_spec_file(info)
            infoCategories = set(augmented_spec_file['categories'])
            if infoCategories.issuperset(categories):
                _logger.info('Keeping {} due to being in "{}"'.format(
                    programPath,
                    categories))
            else:
                _logger.info('Dropping {}. "{}" is not superset of "{}"'.format(
                    programPath,
                    infoCategories,
                    categories))
                drop_count += 1
                continue
        keep_count += 1
        num_branches, estimated_sym_bytes = get_stats(programPath, pargs.bc_stats)
        # Partially compute stats using num_branches
        if gs.min_branches == None or gs.min_branches > num_branches:
            gs.min_branches = num_branches
            _logger.info('"{}" had smaller number of branches: {}'.format(
                programPath,
                num_branches))
        if gs.max_branches == None or gs.max_branches < num_branches:
            gs.max_branches = num_branches
            _logger.info('"{}" had larger number of branches: {}'.format(
                programPath,
                num_branches))
        gs.mean_branches.append(num_branches)
        gs.median_branches.append(num_branches)
        gs.std_dev_branches.append(num_branches)
        # Partially compute stats using estimated_sym_bytes
        if gs.min_sym_bytes == None or gs.min_sym_bytes > estimated_sym_bytes:
            gs.min_sym_bytes = estimated_sym_bytes
            _logger.info('"{}" had smaller number of sym bytes: {}'.format(
                programPath,
                estimated_sym_bytes))
        if gs.max_sym_bytes == None or gs.max_sym_bytes < estimated_sym_bytes:
            gs.max_sym_bytes = estimated_sym_bytes
            _logger.info('"{}" had larger number of sym bytes: {}'.format(
                programPath,
                estimated_sym_bytes))
        gs.mean_sym_bytes.append(estimated_sym_bytes)
        gs.median_sym_bytes.append(estimated_sym_bytes)
        gs.std_dev_sym_bytes.append(estimated_sym_bytes)

    # Now compute mean/medians
    gs.mean_branches = statistics.mean(gs.mean_branches)
    gs.std_dev_branches = statistics.stdev(gs.std_dev_branches)
    gs.median_branches = statistics.median(gs.median_branches)
    gs.mean_sym_bytes = statistics.mean(gs.mean_sym_bytes)
    gs.std_dev_sym_bytes = statistics.stdev(gs.std_dev_sym_bytes)
    gs.median_sym_bytes = statistics.median(gs.median_sym_bytes)

    # Output
    print("drop_count: {}".format(drop_count))
    print("keep_count: {}".format(keep_count))
    gs.dump()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
