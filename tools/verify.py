#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Perform verification of a klee-runner result yaml file and associated working
directory.
"""

import argparse
import logging
from enum import Enum
# pylint: disable=wrong-import-position
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
add_KleeRunner_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import kleeanalysis.analyse
from kleeanalysis.analyse import KleeRunnerResult

_logger = logging.getLogger(__name__)

# FIXME: No way to extend enums...
class VerificationResult(Enum):
    OKAY_KLEE_DIR = KleeRunnerResult.OKAY_KLEE_DIR.value
    BAD_EXIT = KleeRunnerResult.BAD_EXIT.value
    OUT_OF_MEMORY = KleeRunnerResult.OUT_OF_MEMORY.value
    OUT_OF_TIME = KleeRunnerResult.OUT_OF_TIME.value
    INVALID_KLEE_DIR = KleeRunnerResult.INVALID_KLEE_DIR.value
    VERIFICATION_SUCCESS = KleeRunnerResult.SENTINEL.value + 1
    VERIFICATION_FAILURE = KleeRunnerResult.SENTINEL.value + 2
    FAIL_TO_CLASSIFY = KleeRunnerResult.SENTINEL.value + 3

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--result-info-file",
                        dest="result_info_file",
                        help="result info file. (Default stdin)",
                        type=argparse.FileType('r'),
                        default=sys.stdin)
    parser.add_argument("--no-progress",
                        dest="no_progress",
                        default=False,
                        action="store_true",
                        help="Don't show progress on stdout")
    parser.add_argument("--ignore-invalid-klee-dirs",
                        dest="ignore_invalid_klee_dirs",
                        help="Don't try to find counter examples in invalid klee directories",
                        default=False,
                        action="store_true")
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args)

    exitCode = 0
    _logger.info('Reading result infos from {}'.format(args.result_info_file.name))

    # Result counters
    summaryCounters = dict()
    multipleOutcomes = []
    verificationWarnings = []
    for enum in list(VerificationResult):
        summaryCounters[enum] = 0
    try:
        # FIXME: Don't use raw form
        resultInfos = KleeRunner.ResultInfo.loadRawResultInfos(args.result_info_file)
        for index, result in enumerate(resultInfos["results"]):
            identifier = result["klee_dir"]
            if not args.no_progress:
                # HACK: Show some sort of progress info
                print('Analysing...{} ({}/{}){}'.format(
                        identifier,
                        index + 1,
                        len(resultInfos["results"]),
                        " "*20),
                    end='\r', file=sys.stdout, flush=True)
            outcomes = kleeanalysis.analyse.get_run_outcomes(result)
            assert isinstance(outcomes, list)
            assert len(outcomes) > 0
            if len(outcomes) > 1:
                _logger.warning('Multiple outcomes for "{}"'.format(identifier))
                multipleOutcomes.append(outcomes)
            for item in outcomes:
                assert isinstance(item, kleeanalysis.analyse.SummaryType)
                if item.code == KleeRunnerResult.BAD_EXIT:
                    _logger.warning("{} terminated with exit code {}".format(
                        identifier,
                        item.payload))
                    summaryCounters[VerificationResult.BAD_EXIT] += 1
                elif item.code == KleeRunnerResult.OUT_OF_MEMORY:
                    _logger.warning("{} killed due to running out of memory".format(
                            identifier))
                    summaryCounters[VerificationResult.OUT_OF_MEMORY] += 1
                elif item.code == KleeRunnerResult.OUT_OF_TIME:
                    _logger.warning("{} hit timeout".format(
                            identifier))
                    summaryCounters[VerificationResult.OUT_OF_TIME] += 1
                elif item.code == KleeRunnerResult.INVALID_KLEE_DIR:
                    _logger.warning("{} has an invalid klee directory".format(
                        identifier))
                    summaryCounters[VerificationResult.INVALID_KLEE_DIR] += 1
                    if not args.ignore_invalid_klee_dirs:
                        failures, warnings = kleeanalysis.analyse.check_against_spec(result, item.payload)
                        # 0 failures doesn't mean verified here as an invalid KLEE directory
                        # likely means something went wrong during KLEE's execution which
                        # probably means execution was
                        if len(failures) > 0:
                            msg = '{} failed to verify (note: using invalid klee directory)\n'.format(
                                identifier)
                            msg += kleeanalysis.analyse.show_failures_as_string(failures)
                            assert isinstance(msg, str) and len(msg) > 0
                            _logger.warning(msg)
                            summaryCounters[VerificationResult.VERIFICATION_FAILURE] += 1
                        if len(warnings) > 0:
                            for verification_warning in warnings:
                                verificationWarnings.append(verification_warning)
                                _logger.warning(
                                    'An issue occured verifying the "{}" task'.format(verification_warning.task))
                                for msg, test_case in verification_warning.message_test_tuples:
                                    _logger.warning('{}\nTest case:{}\n'.format(msg, test_case))
                elif item.code == KleeRunnerResult.OKAY_KLEE_DIR:
                    # We have a useful klee directory check against
                    # the benchmark specification.
                    failures, warnings = kleeanalysis.analyse.check_against_spec(result, item.payload)
                    assert isinstance(failures, list)
                    if len(failures) == 0:
                        _logger.info('{} performed successful verification'.format(
                            identifier))
                        summaryCounters[VerificationResult.VERIFICATION_SUCCESS] += 1
                    else:
                        msg = '{} failed to verify\n'.format(
                            identifier)
                        msg += kleeanalysis.analyse.show_failures_as_string(failures)
                        assert isinstance(msg, str) and len(msg) > 0
                        _logger.warning(msg)
                        summaryCounters[VerificationResult.VERIFICATION_FAILURE] += 1

                    if len(warnings) > 0:
                        for verification_warning in warnings:
                            verificationWarnings.append(verification_warning)
                            _logger.warning(
                                'An issue occured verifying the "{}" task'.format(verification_warning.task))
                            for msg, test_case in verification_warning.message_test_tuples:
                                _logger.warning('{}\nTest case:{}\n'.format(msg, test_case))
                else:
                    raise Exception("Unhandled KleeRunnerResult")

    except KeyboardInterrupt:
        _logger.info('Received KeyboardInterrupt')
        exitCode = 1

    print("")
    _logger.info('# of raw results: {}'.format(len(resultInfos["results"])))
    for name , value in sorted(summaryCounters.items(), key=lambda i: i[0].name):
        _logger.info("# of {}: {}".format(name, value))

    if len(multipleOutcomes) > 0:
        _logger.warning('{} benchmark(s) had multiple outcomes'.format(len(multipleOutcomes)))
    if len(verificationWarnings) > 0:
        _logger.warning('There were {} verification warnings'.format(len(verificationWarnings)))

    return exitCode

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
