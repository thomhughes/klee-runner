# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import logging
import os
from . RunnerBase import RunnerBaseClass

_logger = logging.getLogger(__name__)


class NativeReplayRunnerException(Exception):

    def __init__(self, msg):
        # pylint: disable=super-init-not-called
        self.msg = msg


class NativeReplayRunner(RunnerBaseClass):

    def __init__(self, invocationInfo, workingDirectory, rc):
        _logger.debug('Initialising {}'.format(invocationInfo.Program))

        # Tool path doesn't mean anything here
        if 'tool_path' in rc:
            raise NativeReplayRunnerException(
                '"tool_path" should not be specified')

        # Check have KTest file
        if invocationInfo.KTestFile is None:
            raise NativeReplayRunnerException('KTest file must be specified')
        if not os.path.exists(invocationInfo.KTestFile):
            raise NativeReplayRunnerException(
                'KTest file "{}" does not exist'.format(
                    invocationInfo.KTestFile))


        super(NativeReplayRunner, self).__init__(
            invocationInfo, workingDirectory, rc)
        self.toolPath = None

        if invocationInfo.CoverageDir is not None:
            if not os.path.exists(invocationInfo.CoverageDir):
                raise NativeReplayRunnerException(
                    'Coverage directory "{}" does not exist'.format(invocationInfo.CoverageDir))
            if not os.path.isdir(invocationInfo.CoverageDir):
                raise NativeReplayRunnerException(
                    '"{}" is not a directory'.format(invocationInfo.CoverageDir))

    @property
    def name(self):
        return "Native replay"

    def getResults(self):
        r = super(NativeReplayRunner, self).getResults()
        return r

    def _checkToolExistsInBackend(self):
        # There is no "tool" here so don't check if it exists.
        pass

    def _setupToolPath(self, rc):
        self.toolPath = None

    def run(self):
        # Build the command line
        cmdLine = [self.toolPath] + self.additionalArgs
        cmdLine = [self.programPathArgument] + self.additionalArgs

        # Make sure the backend knows that this file needs to be available in
        # the backend.
        self._backend.addFileToBackend(self.InvocationInfo.KTestFile, read_only=True)

        # Now add the command line arguments for program under test
        cmdLine.extend(self.InvocationInfo.CommandLineArguments)

        env = self.InvocationInfo.EnvironmentVariables
        env['KTEST_FILE'] = self._backend.getFilePathInBackend(
            self.InvocationInfo.KTestFile)

        if self.InvocationInfo.CoverageDir is not None:
            # NOTE: Coverage directory must be writable
            self._backend.addFileToBackend(self.InvocationInfo.CoverageDir, read_only=False)
            # This is Gcov specific. This will tell the instrumented binary
            # to emit all `*.gcda` files into a path prefixed by this path.
            env['GCOV_PREFIX'] = self._backend.getFilePathInBackend(
                self.InvocationInfo.CoverageDir)
            # Don't strip anything off the initial hardwired paths.
            env['GCOV_PREFIX_STRIP'] = "0"

        backendResult = self.runTool(cmdLine, envExtra=env)
        if backendResult.outOfTime:
            _logger.warning('Hard timeout hit')


def get():
    return NativeReplayRunner
