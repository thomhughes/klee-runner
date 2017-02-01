#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info YAML file from a run of `batch-runner.py`
and report on the KLEE test cases.
"""

import argparse
from enum import Enum
import logging
import os
# pylint: disable=wrong-import-position
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
add_KleeRunner_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
from kleeanalysis.kleedir.kleedir import KleeDir

_logger = logging.getLogger(__name__)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_info_file',
                        help='Result info file',
                        type=argparse.FileType('r'))
    parser.add_argument("--messages",
                        default=False,
                        action="store_true")
    parser.add_argument("--warnings",
                        default=False,
                        action="store_true")
    parser.add_argument("--no-count--invalid",
                        dest="no_count_invalid",
                        default=False,
                        action="store_true")
    parser.add_argument("--show-error-locations",
                        dest="show_error_locations",
                        default=False,
                        action="store_true")

    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args, parser)

    resultInfos = KleeRunner.ResultInfo.loadRawResultInfos(args.result_info_file)
    abort_errors = []
    assert_errors = []
    division_errors = []
    execution_errors = []
    free_errors = []
    overflow_errors = []
    overshift_errors = []
    ptr_errors = []
    read_only_errors = []
    misc_errors = []
    user_errors = []
    successful_terminations = []
    early_terminations = []
    test_case_count = 0
    invalid_klee_dir_count = 0
    klee_dir_counted = 0
    error_run_count = 0
    for index, r in enumerate(resultInfos['results']):
        if 'klee_dir' not in r and 'error' in r:
            _logger.warning('Found error result. Skipping')
            error_run_count += 1
            continue
        klee_dir_path = r['klee_dir']

        if not os.path.exists(klee_dir_path):
            _logger.error("Klee directory \"{}\" does not exist".format(klee_dir_path))
            return 1

        if not os.path.isdir(klee_dir_path):
            _logger.error("\"{}\" is not a directory".format(klee_dir_path))
            return 1

        _logger.debug('Reading KLEE directory "{}"'.format(klee_dir_path))
        klee_dir = KleeDir(klee_dir_path)
        _logger.debug('Finished reading KLEE directory')

        # Report stuff about the KLEE directory
        if not klee_dir.is_valid:
            _logger.warning('Invalid klee dir "{}"'.format(klee_dir_path))
            if args.no_count_invalid:
                _logger.waring('Skipping invalid klee dir "{}"'.format(klee_dir_path))
                continue
            invalid_klee_dir_count += 1

        klee_dir_counted += 1

        test_case_count += len(klee_dir.tests)
        abort_errors.extend(list(klee_dir.abort_errors))
        assert_errors.extend(list(klee_dir.assertion_errors))
        division_errors.extend(list(klee_dir.division_errors))
        execution_errors.extend(list(klee_dir.execution_errors))
        free_errors.extend(list(klee_dir.free_errors))
        overflow_errors.extend(list(klee_dir.overflow_errors))
        overshift_errors.extend(list(klee_dir.overshift_errors))
        ptr_errors.extend(list(klee_dir.ptr_errors))
        read_only_errors.extend(list(klee_dir.read_only_errors))
        user_errors.extend(list(klee_dir.user_errors))
        misc_errors.extend(list(klee_dir.misc_errors))
        successful_terminations.extend(list(klee_dir.successful_terminations))
        early_terminations.extend(list(klee_dir.early_terminations))

    if error_run_count > 0:
        _logger.warning('#'*70)
        _logger.warning('Found {} error runs!'.format(error_run_count))
        _logger.warning('#'*70)

    _logger.info('# Counted klee dirs: {}'.format(klee_dir_counted))
    _logger.info('# of invalid klee directories: {}'.format(invalid_klee_dir_count))
    _logger.info('Total # of test cases: {}'.format(test_case_count))
    _logger.info('#'*70)

    _logger.info('# of abort errors: {}'.format(len(abort_errors)))
    show_error_locations(abort_errors, args.show_error_locations)

    _logger.info('# of assert errors: {}'.format(len(assert_errors)))
    show_error_locations(assert_errors, args.show_error_locations)

    _logger.info('# of division errors: {}'.format(len(division_errors)))
    show_error_locations(division_errors, args.show_error_locations)

    _logger.info('# of execution errors: {}'.format(len(execution_errors)))
    show_error_locations(execution_errors, args.show_error_locations)

    _logger.info('# of free errors: {}'.format(len(free_errors)))
    show_error_locations(free_errors, args.show_error_locations)

    _logger.info('# of overflow errors: {}'.format(len(overflow_errors)))
    show_error_locations(overflow_errors, args.show_error_locations)

    _logger.info('# of overshift errors: {}'.format(len(overshift_errors)))
    show_error_locations(overshift_errors, args.show_error_locations)

    _logger.info('# of ptr errors: {}'.format(len(ptr_errors)))
    show_error_locations(ptr_errors, args.show_error_locations)

    _logger.info('# of read only errors: {}'.format(len(read_only_errors)))
    show_error_locations(read_only_errors, args.show_error_locations)

    _logger.info('# of user errors: {}'.format(len(user_errors)))
    show_error_locations(user_errors, args.show_error_locations)

    _logger.info('# of misc errors: {}'.format(len(misc_errors)))
    show_error_locations(misc_errors, args.show_error_locations)

    _logger.info('#'*70)
    _logger.info('# of successful terminations: {}'.format(len(successful_terminations)))
    _logger.info('#'*70)
    _logger.info('# of early terminations: {}'.format(len(early_terminations)))
    # Show the reason for early termination by count
    reasonCounts = dict()
    for t in early_terminations:
        msg = ' '.join(t.early.message).strip()
        if msg not in reasonCounts:
            reasonCounts[msg] = 1
        else:
            reasonCounts[msg] += 1
    for reason, count in sorted(reasonCounts.items(), key=lambda i: i[0]):
        _logger.info("\"{}\": {}".format(reason, count))

    if args.messages:
        _logger.info('#'*70)
        msgs = ''.join(klee_dir.messages)
        _logger.info('KLEE messages:\n{}'.format(msgs))
    if args.warnings:
        _logger.info('#'*70)
        warnings = ''.join(klee_dir.warnings)
        _logger.info('KLEE warnings:\n{}'.format(warnings))

def show_error_locations(tests, enabled):
    assert isinstance(tests, list)
    if not enabled:
        return
    for test in tests:
        error = test.error
        msg = "{msg}: {file}:{line}\n".format(
            file=error.file,
            line=error.line,
            msg=error.message)
        msg += "assembly line: {}\n".format(error.assembly_line)
        if len(error.stack) > 0:
            msg += "stack:\n"
        for l in error.stack:
            msg += l
        _logger.info(msg)

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
