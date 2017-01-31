# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import logging
import os
import tempfile
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

        # Check if we should attach gdb
        self._attach_gdb = invocationInfo.AttachGDB
        if not isinstance(self._attach_gdb, bool):
            raise NativeReplayRunnerException('Invocation info "attach_gdb" should be a bool')

        super(NativeReplayRunner, self).__init__(
            invocationInfo, workingDirectory, rc)
        self.toolPath = None

        # Disallow client using environment variable which we use
        if ('KTEST_FILE' in invocationInfo.EnvironmentVariables or
            'KTEST_FILE' in self.toolEnvironmentVariables):
            raise NativeReplayRunnerException(
                '"KTEST_FILE" is not allowed as an environment variable')

        if invocationInfo.CoverageDir is not None:
            if not os.path.exists(invocationInfo.CoverageDir):
                raise NativeReplayRunnerException(
                    'Coverage directory "{}" does not exist'.format(invocationInfo.CoverageDir))
            if not os.path.isdir(invocationInfo.CoverageDir):
                raise NativeReplayRunnerException(
                    '"{}" is not a directory'.format(invocationInfo.CoverageDir))

            # Disallow client using environment variables which we use
            for env_var_to_check in ['GCOV_PREFIX', 'GCOV_PREFIX_STRIP']:
                if (env_var_to_check in invocationInfo.EnvironmentVariables or
                    env_var_to_check in self.toolEnvironmentVariables):
                    raise NativeReplayRunnerException(
                        '"{}" is not allowed as an environment variable'.format(env_var_to_check))

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

        gdb_script_file = None
        try:
            if self._attach_gdb:
                # YUCK: We have to do this because gdb seems to except
                # if statements to have new lines. Using `-ex` option
                # containing \n does not seem to work. Using multiple
                # `-ex` commands doesn't seem to work either.
                gdb_script = """
    set print address off
    run
    if $_isvoid($_exitcode)
      bt
    end
    """
                gdb_script_file = tempfile.NamedTemporaryFile()
                gdb_script_file.write(gdb_script.encode())
                gdb_script_file.flush()
                cmdLine = [
                    'gdb',
                    '-batch', # non-interactive
                    '-return-child-result', # Use child exit code
                    '-x', gdb_script_file.name, # Run commands in gdb script
                    '--args', # Give remaining arguments to the program
                ] + cmdLine

            backendResult = self.runTool(cmdLine, envExtra=env)
            if backendResult.outOfTime:
                _logger.warning('Hard timeout hit')
        finally:
            if gdb_script_file is not None:
                gdb_script_file.close()


def get():
    return NativeReplayRunner
