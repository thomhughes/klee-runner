#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Perform verification of a klee-runner result yaml file and associated working
directory.
"""

import argparse
import logging
# pylint: disable=wrong-import-position
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
add_KleeRunner_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import kleeanalysis.analyse

_logger = logging.getLogger(__name__)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--result-info-file",
                        dest="result_info_file",
                        help="result info file. (Default stdin)",
                        type=argparse.FileType('r'),
                        default=sys.stdin)
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args)

    _logger.info('Reading result infos from {}'.format(args.result_info_file.name))
    successCount = 0
    failCount = 0
    exitCode = 0
    try:
        # FIXME: Don't use raw form
        resultInfos = KleeRunner.ResultInfo.loadRawResultInfos(args.result_info_file)
        for index, result in enumerate(resultInfos["results"]):
            # HACK: Show some sort of progress info
            print('Analysing...{} ({}/{}){}'.format(
                    result["klee_dir"],
                    index + 1,
                    len(resultInfos["results"]),
                    " "*80),
                end='\r', file=sys.stderr, flush=True)
            success = kleeanalysis.analyse.analyse_result(result)
            if success is True:
                successCount += 1
            else:
                failCount += 1
    except KeyboardInterrupt:
        _logger.info('Received KeyboardInterrupt')
        exitCode = 1

    print("")
    _logger.info("# of successes: {}".format(successCount))
    _logger.info("# of failures: {}".format(failCount))
    return exitCode

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
