#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:

from argparse import ArgumentParser
from load_klee_analysis import add_kleeanalysis_to_module_search_path
add_kleeanalysis_to_module_search_path()
from kleeanalysis import Batch
import logging

_logger = logging.getLogger(__name__)

def main(argv):
    parser = ArgumentParser(description="Perform verification of a klee-runner result yaml file and associated working directory")
    parser.add_argument("path", help="path to the .yml file")
    parser.add_argument("-l","--log-level",type=str, default="info", dest="log_level", choices=['debug','info','warning','error'])

    args = parser.parse_args(args=argv)

    logLevel = getattr(logging, args.log_level.upper(),None)
    if logLevel == logging.DEBUG:
        logFormat = '%(levelname)s:%(threadName)s: %(filename)s:%(lineno)d %(funcName)s()  : %(message)s'
    else:
        logFormat = '%(levelname)s:%(threadName)s: %(message)s'

    logging.basicConfig(level=logLevel, format=logFormat)
    batch = Batch(args.path)
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

if __name__ == '__main__':
    import sys
    main(sys.argv[1:])
