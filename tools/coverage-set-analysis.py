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

def load_cov_sets_in_dir(dirname, filter_keep_key=None):
    xml_name_to_branch_cov_set = dict()
    dirpath, _, files = next(os.walk(dirname))
    filter_regex = None
    if filter_keep_key is not None:
        filter_regex = re.compile(r'{}'.format(filter_keep_key))
    for f in sorted(files):
        if f.endswith('.xml'):
            if filter_regex is not None:
                if filter_regex.match(f) is None:
                    continue
            _logger.debug('Loading {}'.format(f))
            cov_set = coverage.raw_coverage_xml_to_branch_cov_set(os.path.join(dirpath, f))
            xml_name_to_branch_cov_set[f] = cov_set
    return xml_name_to_branch_cov_set

def merge_cov(a, b):
    assert isinstance(a, dict)
    assert isinstance(b, dict)
    result_cov = {}
    # union keys
    keys = set(a.keys())
    keys.update(b.keys())
    assert len(keys) > 0
    for key in sorted(keys):
        temp = set()
        if key in a:
            temp.update(a[key])
        if key in b:
            temp.update(b[key])
        result_cov[key] = temp
    return result_cov

def load_cov_sets(dirname, do_merge, merge_path_suffix, filter_keep_key):
    s = None
    if not do_merge:
        s = load_cov_sets_in_dir(dirname, filter_keep_key)
    else:
        # Load multiple sets and merge them
        dirpath, dirnames, _ = next(os.walk(dirname))
        for d in sorted([ os.path.join(dirpath, x, merge_path_suffix) for x in dirnames]):
            _logger.info('Loading dir {}'.format(d))
            temp = load_cov_sets_in_dir(d, filter_keep_key)
            assert len(temp.keys()) > 0
            if s is None:
                s = temp
            else:
                _logger.info('Merging in {} for {}'.format(d, dirname))
                s = merge_cov(s, temp)

    _logger.info('{} keys in {}'.format(len(s.keys()), dirname))
    return s

def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first_dir',
        help='First directory',
        default="",
    )
    parser.add_argument('second_dir',
        help='Second directory',
        default="",
    )
    parser.add_argument('--merge-runs',
        default=False,
        dest='merge_runs',
        action='store_true',
    )
    parser.add_argument('--merge-path-suffix',
        default='coverage_files/',
        dest='merge_path_suffix',
    )
    parser.add_argument('--filter-keep-key',
        dest='filter_keep_key',
        default=None,
    )
    parser.add_argument('--dump-branch-cov',
        default=None,
        dest='dump_branch_cov',
        action='store_true',
    )
    parser.add_argument('--dump-first-strict-superset',
        default=None,
        dest='dump_first_strict_superset',
        action='store_true',
    )
    parser.add_argument('--dump-second-strict-superset',
        default=None,
        dest='dump_second_strict_superset',
        action='store_true',
    )
    parser.add_argument('--dump-identical-coverage-set',
        default=None,
        dest='dump_identical_coverage_set',
        action='store_true',
    )
    parser.add_argument('--dump-complementary-coverage-set',
        default=None,
        dest='dump_complementary_coverage_set',
        action='store_true',
    )
    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args(args)
    DriverUtil.handleLoggerArgs(pargs, parser)

    # Load sets
    if not os.path.isdir(pargs.first_dir):
        _logger.error('"{}" is not a directory'.format(pargs.first_dir))
        return 0
    first = load_cov_sets(
        pargs.first_dir,
        pargs.merge_runs,
        pargs.merge_path_suffix,
        pargs.filter_keep_key)
    if not os.path.isdir(pargs.second_dir):
        _logger.error('"{}" is not a directory'.format(pargs.second_dir))
        return 0
    second = load_cov_sets(
        pargs.second_dir,
        pargs.merge_runs,
        pargs.merge_path_suffix,
        pargs.filter_keep_key
    )

    # Create unioned key set (coverage xml file names) so we
    # can handle the case where coverage files aren't present in one
    # of the sets
    keys = set(first.keys())
    keys.update(second.keys())
    print("# of coverage files unioned: {}".format(len(keys)))

    # Will contain keys where the coverage falls into one of these four
    # categories
    first_strict_superset = set()
    second_strict_superset = set()
    same_coverage = set()
    complementary = set() # Nonen of the above

    for key in sorted(keys):
        if key not in first:
            _logger.warning('{} is missing from first'.format(key))
            # empty coverage
            first_cov_set = set()
        else:
            first_cov_set = first[key]
        if key not in second:
            _logger.warning('{} is missing from second'.format(key))
            # empty coverage
            second_cov_set = set()
        else:
            second_cov_set = second[key]
        if pargs.dump_branch_cov:
            print('First cov for {}:\n{}'.format(key, pprint.pformat(first_cov_set)))
            print('Second cov for {}:\n{}'.format(key, pprint.pformat(second_cov_set)))
        # Check sets
        if first_cov_set.issuperset(second_cov_set):
            if first_cov_set.issubset(second_cov_set):
                _logger.info('{} has same coverage'.format(key))
                same_coverage.add(key)
            else:
                _logger.info('{} first is strict superset of second'.format(key))
                first_strict_superset.add(key)
            continue
        if second_cov_set.issuperset(first_cov_set):
            if second_cov_set.issubset(first_cov_set):
                # This is redundant and so should not be reached
                assert False
                _logger.info('{} has same coverage'.format(key))
                same_coverage.add(key)
            else:
                _logger.info('{} second is strict superset of first'.format(key))
                second_strict_superset.add(key)
            continue
        # The sets must be complementary
        _logger.info('{} sets are complementary'.format(key))
        # Check this is the case
        first_cov_only = first_cov_set.difference(second_cov_set)
        second_cov_only = second_cov_set.difference(first_cov_set)
        assert len(first_cov_only) > 0 or len(second_cov_only) > 0
        complementary.add(key)
    print('# first strict superset: {}'.format(len(first_strict_superset)))
    if pargs.dump_first_strict_superset:
        print("{}".format(pprint.pformat(first_strict_superset)))
    print('# second strict superset: {}'.format(len(second_strict_superset)))
    if pargs.dump_second_strict_superset:
        print("{}".format(pprint.pformat(second_strict_superset)))
    print('# same coverage: {}'.format(len(same_coverage)))
    if pargs.dump_identical_coverage_set:
        print("{}".format(pprint.pformat(same_coverage)))
    print('# complementary coverage: {}'.format(len(complementary)))
    if pargs.dump_complementary_coverage_set:
        print("{}".format(pprint.pformat(complementary)))
    print('# Total: {}'.format(
        len(first_strict_superset) +
        len(second_strict_superset) +
        len(same_coverage) +
        len(complementary)))

    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

