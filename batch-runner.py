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
futureToRunners = None


def handleInterrupt(signum, _):
    logging.info('Received signal {}'.format(signum))
    if futureToRunners != None:
        cancel(futureToRunners)


def cancel(futureToRunnersMap):
    _logger.warning('Cancelling futures')
    # Cancel all futures first. If we tried
    # to kill the runner at the same time then
    # other futures would start which we don't want
    for future in futureToRunnersMap.keys():
        future.cancel()

    # Then we can kill the runners if required
    _logger.warning('Killing runners')
    for runner_list in futureToRunnersMap.values():
        if isinstance(runner_list, list):
            for runner in runner_list:
                runner.kill()
        else:
            assert isinstance(runner_list, SequentialRunnerHolder)
            runner_list.kill()

class SequentialRunnerHolder:
    """
    Convenient wrapper for doing force sequentialised execution
    during a parallel run
    """
    def __init__(self, seq_runners):
        assert isinstance(seq_runners, list)
        self._seq_runners = seq_runners
        assert len(self._seq_runners) > 0
        self._completed_runs = []
        self._killSequentialLoop = False

    def run(self):
        for index, r in enumerate(self._seq_runners):
            if self._killSequentialLoop is True:
                _logger.warning('Sequential loop killed')
                break
            _logger.info('Doing sequential run {}/{} with runner "{}"'.format(
                index+1,
                len(self._seq_runners),
                r.programPathArgument))
            r.run()
            self._completed_runs.append(r)
        return

    def kill(self):
        _logger.info('Killing SequentialRunnerHolder')
        self._killSequentialLoop = True
        for r in self._seq_runners:
            r.kill()

    def completed_runs(self):
        return self._completed_runs

def entryPoint(args):
    # pylint: disable=global-statement,too-many-branches,too-many-statements
    # pylint: disable=too-many-return-statements
    global _logger, futureToRunners
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

    DriverUtil.handleLoggerArgs(pargs, parser)
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
            invocationInfoObjects, misc_data = InvocationInfo.loadInvocationInfos(f)
    except Exception as e: # pylint: disable=broad-except
        _logger.error(e)
        _logger.debug(traceback.format_exc())
        return 1

    # Misc data we will put into output result info file.
    output_misc_data = {
        'runner': config['runner'],
        'jobs_in_parallel': pargs.jobs
    }

    sequential_execution_indices = None
    if misc_data is not None:
        # Handle `sequential_execution_indices`
        if 'sequential_execution_indices' in misc_data:
            _logger.info('Invocation info requests execution order')
            # Verify the indices refer to every job and that the indices don't
            # refer out of range or that jobs are repeated.
            seen_indices = set()
            assert isinstance(misc_data['sequential_execution_indices'], list)
            for l in misc_data['sequential_execution_indices']:
                assert isinstance(l, list)
                for index in l:
                    if index in seen_indices:
                        _logger.error('index "{}" is repeated in sequential_execution_indices'.format(index))
                        return 1
                    seen_indices.add(index)
            invocation_indices = set(range(0, len(invocationInfoObjects)))
            seq_does_not_handle = invocation_indices.difference(seen_indices)
            if len(seq_does_not_handle) > 0:
                _logger.error('sequential_execution_indices does not refer to indices: {}'.format(seq_does_not_handle))
                return 1
            inv_does_not_handle = seen_indices.difference(invocation_indices)
            if len(inv_does_not_handle):
                _logger.error('sequential_execution_indices refers to invalid indices: {}'.format(inv_does_not_handle))
                return 1
            # All okay
            sequential_execution_indices = misc_data['sequential_execution_indices']

        # copy misc data over
        output_misc_data['invocation_info_misc'] = dict(filter(lambda kv_tup: kv_tup[0] != 'sequential_execution_indices', misc_data.items()))


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

        # Do coverage_dir subtitution if necessary
        if invocationInfo.CoverageDir is not None:
            coverage_dir = invocationInfo.CoverageDir
            assert isinstance(coverage_dir, str)
            new_coverage_dir = coverage_dir.replace('@global_work_dir@', workDirsRoot)
            _logger.info('Replacing coverage dir "{}" with "{}"'.format(
                coverage_dir,
                new_coverage_dir)
            )
            invocationInfo.GetInternalRepr()['coverage_dir'] = new_coverage_dir
            # Create the directory if necessary
            if not os.path.exists(new_coverage_dir):
                _logger.info('Creating coverage directory "{}"'.format(new_coverage_dir))
                os.makedirs(new_coverage_dir)

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
    output_misc_data['start_time'] = str(startTime.isoformat(' '))

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
                if sequential_execution_indices:
                    # Force sequential execution of runners where appropriate
                    futureToRunners = {}
                    for l in sequential_execution_indices:
                        # Create list of runners to run sequentially
                        _logger.info('Forcing indicies "{}" to run sequentially'.format(l))
                        seq_runners = []
                        for runner_index in l:
                            seq_runners.append(runners[runner_index])

                        # Use wrapper to force sequential execution
                        seq_runner = SequentialRunnerHolder(seq_runners)
                        future = executor.submit(seq_runner.run)
                        futureToRunners[future] = seq_runner
                else:
                    # Simple: One runner to one future mapping.
                    futureToRunners = {executor.submit(r.run): [r] for r in runners}
                for future in concurrent.futures.as_completed(futureToRunners):
                    completed_runner_list = None
                    if isinstance(futureToRunners[future], list):
                        completed_runner_list = futureToRunners[future]
                    else:
                        assert isinstance(futureToRunners[future], SequentialRunnerHolder)
                        completed_runner_list = futureToRunners[future].completed_runs()
                    for r in completed_runner_list:
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

    endTime = datetime.datetime.now()
    output_misc_data['end_time'] = str(endTime.isoformat(' '))
    output_misc_data['run_time'] = str(endTime- startTime)

    # Write result to YAML file
    outputData = {
        'schema_version': schemaVersion,
        'results': reports,
        'misc': output_misc_data,
    }
    DriverUtil.writeYAMLOutputFile(yamlOutputFile, outputData)

    _logger.info('Finished {}'.format(endTime.isoformat(' ')))
    _logger.info('Total run time: {}'.format(endTime - startTime))
    return exitCode

if __name__ == '__main__':
    sys.exit(entryPoint(sys.argv[1:]))
