#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
    Script to run a program
"""
import argparse
import logging
import os
import pprint
import traceback
import sys
import magic
from KleeRunner import InvocationInfo
from KleeRunner import RunnerFactory
from KleeRunner import DriverUtil
from KleeRunner import ResultInfo
from KleeRunner import RunnerContext


def entryPoint(args):
    # pylint: disable=too-many-branches,too-many-statements
    parser = argparse.ArgumentParser(description=__doc__)
    DriverUtil.parserAddLoggerArg(parser)
    parser.add_argument("--dry", action='store_true',
                        help="Stop after initialising runners")
    parser.add_argument("-k", "--ktest-file", dest="ktest_file",
                        default=None, help="KTest file to pass to the runner")
    parser.add_argument("--attach-gdb",
                        dest="attach_gdb",
                        action='store_true',
                        default=False, help="Attach gdb when running")
    parser.add_argument("--coverage-dir",
        dest="coverage_dir",
        default=None,
        help="Coverage directory to give to pass to runner")
    parser.add_argument("config_file", help="YAML configuration file")
    parser.add_argument("working_dir", help="Working directory")
    parser.add_argument("yaml_output", help="path to write YAML output to")
    parser.add_argument("program", help="Program to run")
    # `program_args` is a dummy argument so we get the right usage message from
    # argparse.  We parse `programs_args` ourselves
    parser.add_argument("program_args", nargs="*",
                        help="Arguments to pass to program")

    # Determine where the `program` argument is so
    # we split the arguments into to lists. One to give
    # to argparse and the other to use in an instance of InvocationInfo.
    # FIXME: We need a better heuristic.
    index = 0
    with magic.Magic(flags=magic.MAGIC_MIME_TYPE) as m:
        while index < (len(args) - 1):
            # HACK: Try to determine which argument is the program
            if args[index].endswith('.bc'):  # This is such a hack!
                break
            if os.path.exists(args[index]):
                if m.id_filename(args[index]) == 'application/x-executable':
                    # Yet another hack!
                    break
            index += 1

    argParseArgs = args[:index + 1]
    programArgs = []
    if len(args) >= index + 2:
        programArgs = args[index + 1:]

    pargs = parser.parse_args(argParseArgs)

    DriverUtil.handleLoggerArgs(pargs, parser)
    _logger = logging.getLogger(__name__)

    # Check if output file already exists
    yamlOutputFile = os.path.abspath(pargs.yaml_output)
    if os.path.exists(yamlOutputFile):
        _logger.error(
            'yaml_output file ("{}") already exists'.format(yamlOutputFile))
        return 1

    # Load runner configuration
    config, success = DriverUtil.loadRunnerConfig(pargs.config_file)
    if not success:
        return 1

    # Get schema version that will be put into result info
    schemaVersion = ResultInfo.getSchema()['__version__']

    # Create invocation info
    invocationInfoRepr = {
        'program': os.path.abspath(pargs.program),
        'command_line_arguments': programArgs,
        'environment_variables': {},
        'extra_klee_arguments': [],
        'attach_gdb': pargs.attach_gdb,
    }
    if pargs.ktest_file:
        kTestFile = os.path.abspath(pargs.ktest_file)
        if not os.path.exists(kTestFile):
            _logger.error('KTest file "{}" does not exist'.format(kTestFile))
            return 1
        invocationInfoRepr['ktest_file'] = kTestFile
    if pargs.coverage_dir:
        coverage_dir = os.path.abspath(pargs.coverage_dir)
        coverage_dir, success = DriverUtil.setupWorkingDirectory(coverage_dir)
        if not success:
            _logger.error('Failed to setup coverage directory')
            return 1
        invocationInfoRepr['coverage_dir'] = coverage_dir

    _logger.info('Invocation info:\n{}'.format(
        pprint.pformat(invocationInfoRepr)))
    invocationInfo = InvocationInfo.InvocationInfo(invocationInfoRepr)

    # Setup the working directory
    workDir, success = DriverUtil.setupWorkingDirectory(pargs.working_dir)
    if not success:
        return 1

    # Get Runner class to use
    runner_ctx = RunnerContext.RunnerContext(num_parallel_jobs=1)
    RunnerClass = RunnerFactory.getRunnerClass(config['runner'])
    runner = RunnerClass(invocationInfo, workDir, config['runner_config'], runner_ctx)

    if pargs.dry:
        _logger.info('Not running runner')
        return 0

    # Run the runner
    reports = []
    exitCode = 0
    try:
        runner.run()
        reports.append(runner.getResults())
    except KeyboardInterrupt:
        _logger.error('Keyboard interrupt')
    except Exception: # pylint: disable=broad-except
        _logger.error("Error handling:{}".format(invocationInfoRepr))
        _logger.error(traceback.format_exc())

        # Attempt to add the error to the report
        errorLog = {}
        errorLog['invocation_info'] = runner.InvocationInfo
        errorLog['error'] = traceback.format_exc()
        reports.append(errorLog)
        exitCode = 1

    # Write result to YAML file
    outputData = {
        'schema_version': schemaVersion,
        'results': reports
    }

    DriverUtil.writeYAMLOutputFile(yamlOutputFile, outputData)
    return exitCode

if __name__ == '__main__':
    sys.exit(entryPoint(sys.argv[1:]))
