#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Perform verification of a klee-runner result yaml file and associated working
directory.
"""

import argparse
import logging
from load_klee_analysis import add_kleeanalysis_to_module_search_path
add_kleeanalysis_to_module_search_path()
from load_klee_runner import add_KleeRunner_to_module_search_path
add_KleeRunner_to_module_search_path()
from kleeanalysis import Batch
import KleeRunner.ResultInfo

_logger = logging.getLogger(__name__)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--result-info-file",
                        dest="result_info_file",
                        help="result info file. (Default stdin)",
                        type=argparse.FileType('r'),
                        default=sys.stdin)
                
    parser.add_argument("-l","--log-level",type=str, default="info", dest="log_level", choices=['debug','info','warning','error'])

    args = parser.parse_args(args=argv)

    logLevel = getattr(logging, args.log_level.upper(),None)
    if logLevel == logging.DEBUG:
        logFormat = '%(levelname)s:%(threadName)s: %(filename)s:%(lineno)d %(funcName)s()  : %(message)s'
    else:
        logFormat = '%(levelname)s:%(threadName)s: %(message)s'

    logging.basicConfig(level=logLevel, format=logFormat)

    _logger.info('Reading result infos from {}'.format(args.result_info_file.name))
    try:
        resultInfos = KleeRunner.ResultInfo.loadRawResultInfos(args.result_info_file)
        batch = Batch(resultInfos["results"])
        for result in batch.results:
            failure_found = False
            kleedir = result["klee_dir"]
            if result["exit_code"] is not None and result["exit_code"] != 0:
                failure_found = True
                print(kleedir.path, "terminated with exit code", result["exit_code"])
            if result["out_of_memory"]:
                failure_found = True
                print(kleedir.path, "killed due to running out of memory")
            if result["backend_timeout"]:
                failure_found = True
                print(kleedir.path, "killed due to running out allotted time")
            if not kleedir.is_valid:
                failure_found = True
                print(kleedir.path, "is not valid")
            else:
                if len(result["failures"]) > 0:
                    failure_found = True
                    print(kleedir.path, ":", sep="")
                    for fail_task in result["failures"]:
                        print("  Verification failures for task ", fail_task.task, ":", sep="")
                        for fail in fail_task.failures:
                            print("    Test {:06} in {}:{}".format(fail.identifier, fail.error.file, fail.error.line))
            if failure_found:
                print()
    except KeyboardInterrupt:
        _logger.info('Received KeyboardInterrupt')
        return 1
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
