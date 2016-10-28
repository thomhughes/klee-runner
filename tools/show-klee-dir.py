#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Perform verification of a klee-runner result yaml file and associated working
directory.
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
    parser.add_argument("klee_dir", default=None)
    parser.add_argument("--messages",
                        default=False,
                        action="store_true")
    parser.add_argument("--warnings",
                        default=False,
                        action="store_true")
    parser.add_argument("--show-invalid",
                        dest="show_invalid",
                        default=False,
                        action="store_true")
    parser.add_argument("--show-error-locations",
                        dest="show_error_locations",
                        default=False,
                        action="store_true")

    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args)

    if not os.path.exists(args.klee_dir):
        _logger.error("Klee directory \"{}\" does not exist".format(args.klee_dir))
        return 1

    if not os.path.isdir(args.klee_dir):
        _logger.error("\"{}\" is not a directory".format(args.klee_dir))
        return 1

    _logger.info('Reading KLEE directory "{}"'.format(args.klee_dir))
    klee_dir = KleeDir(args.klee_dir)
    _logger.info('Finished reading KLEE directory')

    # Report stuff about the KLEE directory
    if not klee_dir.is_valid:
        if args.show_invalid:
            _logger.warning("\n")
            _logger.warning('KLEE directory is invalid. Showing all available information.')
            _logger.warning("\n")
        else:
            _logger.error('KLEE directory is invalid (use --show-invalid to show anyway)')
            return 1

    _logger.info('Total # of test cases: {}'.format(len(klee_dir.tests)))
    _logger.info('#'*70)

    abort_errors = list(klee_dir.abort_errors)
    _logger.info('# of abort errors: {}'.format(len(abort_errors)))
    show_error_locations(abort_errors, args.show_error_locations)

    assert_errors = list(klee_dir.assertion_errors)
    _logger.info('# of assert errors: {}'.format(len(assert_errors)))
    show_error_locations(assert_errors, args.show_error_locations)

    division_errors = list(klee_dir.division_errors)
    _logger.info('# of division errors: {}'.format(len(division_errors)))
    show_error_locations(division_errors, args.show_error_locations)

    execution_errors = list(klee_dir.execution_errors)
    _logger.info('# of execution errors: {}'.format(len(execution_errors)))
    show_error_locations(execution_errors, args.show_error_locations)

    free_errors = list(klee_dir.free_errors)
    _logger.info('# of free errors: {}'.format(len(free_errors)))
    show_error_locations(free_errors, args.show_error_locations)

    overflow_errors = list(klee_dir.overflow_errors)
    _logger.info('# of overflow errors: {}'.format(len(overflow_errors)))
    show_error_locations(overflow_errors, args.show_error_locations)

    overshift_errors = list(klee_dir.overshift_errors)
    _logger.info('# of overshift errors: {}'.format(len(overshift_errors)))

    ptr_errors = list(klee_dir.ptr_errors)
    _logger.info('# of ptr errors: {}'.format(len(ptr_errors)))

    read_only_errors = list(klee_dir.read_only_errors)
    _logger.info('# of read only errors: {}'.format(len(read_only_errors)))

    user_errors = list(klee_dir.user_errors)
    _logger.info('# of user errors: {}'.format(len(user_errors)))

    misc_errors = list(klee_dir.misc_errors)
    _logger.info('# of misc errors: {}'.format(len(misc_errors)))

    _logger.info('#'*70)
    successful_terminations = list(klee_dir.successful_terminations)
    _logger.info('# of successful terminations: {}'.format(len(successful_terminations)))

    _logger.info('#'*70)

    early_terminations = list(klee_dir.early_terminations)
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
