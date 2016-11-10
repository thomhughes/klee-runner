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
from kleeanalysis.analyse import KleeRunnerResult, get_klee_verification_results_for_fp_bench, KleeResultCorrect, KleeResultIncorrect, KleeResultUnknown, get_klee_dir_verification_summary_across_tasks

_logger = logging.getLogger(__name__)


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
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args)

    exitCode = 0
    _logger.info('Reading result infos from {}'.format(args.result_info_file.name))

    # Result counters
    summaryCounters = dict()
    multipleOutcomes = []
    for enum in list(KleeRunnerResult):
        summaryCounters[enum] = 0

    # Verification results map the type to
    # tuple (<identifier>, <result>)
    verification_result_type_to_info = dict() # results on per task basis
    verification_result_type_to_benchmark = dict() #  results on per benchmark basis
    for t in [ KleeResultCorrect, KleeResultIncorrect, KleeResultUnknown]:
        verification_result_type_to_info[t] = []
        verification_result_type_to_benchmark[t] = []

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
            outcomes, klee_dir = kleeanalysis.analyse.get_run_outcomes(result)
            assert isinstance(outcomes, list)
            assert len(outcomes) > 0
            if len(outcomes) > 1:
                _logger.warning('Multiple outcomes for "{}"'.format(identifier))
                multipleOutcomes.append(outcomes)
            for item in outcomes:
                assert isinstance(item, kleeanalysis.analyse.SummaryType)
                summaryCounters[item.code] += 1
                if item.code == KleeRunnerResult.BAD_EXIT:
                    _logger.warning("{} terminated with exit code {}".format(
                        identifier,
                        item.payload))
                elif item.code == KleeRunnerResult.OUT_OF_MEMORY:
                    _logger.warning("{} killed due to running out of memory".format(
                            identifier))
                elif item.code == KleeRunnerResult.OUT_OF_TIME:
                    _logger.warning("{} hit timeout".format(
                            identifier))
                elif item.code == KleeRunnerResult.INVALID_KLEE_DIR:
                    _logger.warning("{} has an invalid klee directory".format(
                        identifier))
                elif item.code == KleeRunnerResult.VALID_KLEE_DIR:
                    # We have a useful klee directory
                    pass
                else:
                    raise Exception("Unhandled KleeRunnerResult")

            # Check what the verification verdicts of KLEE are for
            # the fp-bench tasks.
            verification_results = get_klee_verification_results_for_fp_bench(klee_dir)

            # Update results on per task basis
            for vr in verification_results:
                verification_result_type_to_info[type(vr)].append((identifier, vr))

            # Update results on per benchmark basis
            summary_result = get_klee_dir_verification_summary_across_tasks(verification_results)
            verification_result_type_to_benchmark[type(summary_result)].append(identifier)

                    
    except KeyboardInterrupt:
        _logger.info('Received KeyboardInterrupt')
        exitCode = 1

    print("")
    _logger.info('# of raw results: {}'.format(len(resultInfos["results"])))
    for name , value in sorted(summaryCounters.items(), key=lambda i: i[0].name):
        _logger.info("# of {}: {}".format(name, value))

    if len(multipleOutcomes) > 0:
        _logger.warning('{} benchmark(s) had multiple outcomes'.format(len(multipleOutcomes)))

    print("")
    _logger.info('Verification counts per benchmark')
    for t in [ KleeResultCorrect, KleeResultIncorrect, KleeResultUnknown]:
        _logger.info('# of {}: {}'.format(t,
            len(verification_result_type_to_benchmark[t])))

    print("")
    _logger.info('Verification counts by task')
    for t in [ KleeResultCorrect, KleeResultIncorrect, KleeResultUnknown]:
        _logger.info('# of {}: {}'.format(t,
            len(verification_result_type_to_info[t])))

        # Provide per task break down.
        taskCount = dict()
        for identifier, vr in verification_result_type_to_info[t]:
            try:
                taskCount[vr.task] += 1
            except KeyError:
                taskCount[vr.task] = 1
        for task, count in sorted(taskCount.items(), key=lambda tup: tup[0]):
            _logger.info('# of task {}: {}'.format(task, count))

        # Report counts of the reasons we report unknown
        if t == KleeResultUnknown:
            _logger.info('Reasons for reporting unknown')
            unknownReasonCount = dict()
            for identifier, vr in verification_result_type_to_info[t]:
                count += 1
                try:
                    unknownReasonCount[vr.reason] += 1
                except KeyError:
                    unknownReasonCount[vr.reason] = 1
            for reason, count in sorted(unknownReasonCount.items(), key=lambda tup: tup[0]):
                _logger.info('# because "{}": {}'.format(reason, count))


    return exitCode

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
