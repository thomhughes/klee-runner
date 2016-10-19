#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
    Script to run a Runner over a set of programs.
"""
import argparse
import datetime
import logging
import os
import traceback
import signal
import sys
from KleeRunner import RunnerFactory
from KleeRunner import InvocationInfo
from KleeRunner import DriverUtil
from KleeRunner import ResultInfo

_logger = None
futureToRunner = None


def handleInterrupt(signum, frame):
    # pylint: disable=unused-argument
    logging.info('Received signal {}'.format(signum))
    if futureToRunner != None:
        cancel(futureToRunner)


def cancel(futureToRunnerMap):
    _logger.warning('Cancelling futures')
    # Cancel all futures first. If we tried
    # to kill the runner at the same time then
    # other futures would start which we don't want
    for future in futureToRunnerMap.keys():
        future.cancel()
    # Then we can kill the runners if required
    for runner in futureToRunnerMap.values():
        runner.kill()


def entryPoint(args):
    # pylint: disable=global-statement,too-many-branches,too-many-statements
    # pylint: disable=too-many-return-statements
    global _logger, futureToRunner
    parser = argparse.ArgumentParser(description=__doc__)
    DriverUtil.parserAddLoggerArg(parser)
    parser.add_argument("--dry", action='store_true',
                        help="Stop after initialising runners")
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default="1",
        help="Number of jobs to run in parallel (Default %(default)s)")
    parser.add_argument("config_file", help="YAML configuration file")
    parser.add_argument("invocation_info", help="Invocation info file")
    parser.add_argument("working_dirs_root",
                        help="Directory to create working directories inside")
    parser.add_argument("yaml_output", help="path to write YAML output to")

    pargs = parser.parse_args(args)

    DriverUtil.handleLoggerArgs(pargs)
    _logger = logging.getLogger(__name__)

    if pargs.jobs <= 0:
        _logger.error('jobs must be <= 0')
        return 1

    # Load runner configuration
    config, success = DriverUtil.loadRunnerConfig(pargs.config_file)
    if not success:
        return 1

    # Get schema version that will be put into result info
    schemaVersion = ResultInfo.getSchema()['__version__']

    # Load Invocation objects
    invocationInfoObjects = None
    try:
        with open(pargs.invocation_info, 'r') as f:
            invocationInfoObjects = InvocationInfo.loadInvocationInfos(f)
    except Exception as e: # pylint: disable=broad-except
        _logger.error(e)
        _logger.debug(traceback.format_exc())
        return 1

    if len(invocationInfoObjects) < 1:
        logging.error('List of jobs cannot be empty')
        return 1

    yamlOutputFile = os.path.abspath(pargs.yaml_output)

    if os.path.exists(yamlOutputFile):
        _logger.error(
            'yaml_output file ("{}") already exists'.format(yamlOutputFile))
        return 1

    # Setup the directory to hold working directories
    workDirsRoot = os.path.abspath(pargs.working_dirs_root)
    if os.path.exists(workDirsRoot):
        # Check its a directory and its empty
        if not os.path.isdir(workDirsRoot):
            _logger.error(
                '"{}" exists but is not a directory'.format(workDirsRoot))
            return 1

        workDirsRootContents = next(os.walk(workDirsRoot, topdown=True))
        if len(workDirsRootContents[1]) > 0 or len(workDirsRootContents[2]) > 0:
            _logger.error('"{}" is not empty ({},{})'.format(
                workDirsRoot,
                workDirsRootContents[1],
                workDirsRootContents[2]))
            return 1
    else:
        # Try to create the working directory
        try:
            os.mkdir(workDirsRoot)
        except Exception as e: # pylint: disable=broad-except
            _logger.error(
                'Failed to create working_dirs_root "{}"'.format(workDirsRoot))
            _logger.error(e)
            _logger.debug(traceback.format_exc())
            return 1

    # Get Runner class to use
    RunnerClass = RunnerFactory.getRunnerClass(config['runner'])

    if not 'runner_config' in config:
        _logger.error('"runner_config" missing from config')
        return 1

    if not isinstance(config['runner_config'], dict):
        _logger.error('"runner_config" should map to a dictionary')
        return 1

    rc = config['runner_config']

    # Create the runners
    runners = []
    for index, invocationInfo in enumerate(invocationInfoObjects):
        _logger.info('Creating runner {} out of {} ({:.1f}%)'.format(
            index + 1,
            len(invocationInfoObjects),
            100 * float(index + 1) / len(invocationInfoObjects)))
        # Create working directory for this runner
        workDir = os.path.join(workDirsRoot, 'workdir-{}'.format(index))
        assert not os.path.exists(workDir)

        try:
            os.mkdir(workDir)
        except Exception as e: # pylint: disable=broad-except
            _logger.error(
                'Failed to create working directory "{}"'.format(workDir))
            _logger.error(e)
            _logger.debug(traceback.format_exc())
            return 1

        # Pass in a copy of rc so that if a runner accidently modifies
        # a config it won't affect other runners.
        runners.append(RunnerClass(invocationInfo, workDir, rc.copy()))

    # Run the runners and build the report
    reports = []
    exitCode = 0

    if pargs.dry:
        _logger.info('Not running runners')
        return exitCode

    startTime = datetime.datetime.now()
    _logger.info('Starting {}'.format(startTime.isoformat(' ')))

    if pargs.jobs == 1:
        _logger.info('Running jobs sequentially')
        for r in runners:
            try:
                r.run()
                reports.append(r.getResults())
            except KeyboardInterrupt:
                _logger.error('Keyboard interrupt')
                # This is slightly redundant because the runner
                # currently kills itself if KeyboardInterrupt is thrown
                r.kill()
                break
            except Exception: # pylint: disable=broad-except
                _logger.error("Error handling:{}".format(r.program))
                _logger.error(traceback.format_exc())

                # Attempt to add the error to the reports
                errorLog = {}
                errorLog['invocation_info'] = r.InvocationInfo
                errorLog['error'] = traceback.format_exc()
                reports.append(errorLog)
                exitCode = 1
    else:

        # FIXME: Make windows compatible
        # Catch signals so we can clean up
        signal.signal(signal.SIGINT, handleInterrupt)
        signal.signal(signal.SIGTERM, handleInterrupt)

        _logger.info('Running jobs in parallel')
        completedFutureCounter = 0
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=pargs.jobs) as executor:
                futureToRunner = {executor.submit(r.run): r for r in runners}
                for future in concurrent.futures.as_completed(futureToRunner):
                    r = futureToRunner[future]
                    _logger.debug('{} runner finished'.format(
                        r.programPathArgument))

                    if future.done() and not future.cancelled():
                        completedFutureCounter += 1
                        _logger.info('Completed {}/{} ({:.1f}%)'.format(
                            completedFutureCounter,
                            len(runners),
                            100 * (float(completedFutureCounter) / len(runners))
                            ))

                    excep = None
                    try:
                        if future.exception():
                            excep = future.exception()
                    except concurrent.futures.CancelledError as e:
                        excep = e

                    if excep != None:
                        # Attempt to log the error reports
                        errorLog = {}
                        errorLog['invocation_info'] = r.InvocationInfo
                        errorLog['error'] = "\n".join(
                            traceback.format_exception(
                                type(excep),
                                excep,
                                None))
                        # Only emit messages about exceptions that aren't to do
                        # with cancellation
                        if not isinstance(excep, concurrent.futures.CancelledError):
                            _logger.error('{} runner hit exception:\n{}'.format(
                                r.programPathArgument, errorLog['error']))
                        reports.append(errorLog)
                    else:
                        reports.append(r.getResults())
        except KeyboardInterrupt:
            # The executor should of been cleaned terminated.
            # We'll then write what we can to the output YAML file
            _logger.error('Keyboard interrupt')
        finally:
            # Stop catching signals and just use default handlers
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

    # Write result to YAML file
    outputData = {
        'schema_version': schemaVersion,
        'results': reports
    }
    DriverUtil.writeYAMLOutputFile(yamlOutputFile, outputData)

    endTime = datetime.datetime.now()
    _logger.info('Finished {}'.format(endTime.isoformat(' ')))
    _logger.info('Total run time: {}'.format(endTime - startTime))
    return exitCode

if __name__ == '__main__':
    sys.exit(entryPoint(sys.argv[1:]))
