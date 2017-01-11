# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import argparse
import logging
import os
import traceback
import yaml
from . import ConfigLoader

_logger = logging.getLogger(__name__)


def parserAddLoggerArg(parser):
    assert isinstance(parser, argparse.ArgumentParser)
    parser.add_argument("-l", "--log-level", type=str, default="info",
                        dest="log_level",
                        choices=['debug', 'info', 'warning', 'error'])
    parser.add_argument("--log-file",
                        dest='log_file',
                        type=str,
                        default=None,
                        help="Log to specified file")
    parser.add_argument("--log-only-file",
                        dest='log_only_file',
                        action='store_true',
                        default=False,
                        help='Only log to file specified by --log-file and not the console')
    return


def handleLoggerArgs(pargs, parser):
    assert isinstance(pargs, argparse.Namespace)
    assert isinstance(parser, argparse.ArgumentParser)
    logLevel = getattr(logging, pargs.log_level.upper(), None)
    if logLevel == logging.DEBUG:
        logFormat = ('%(levelname)s:%(threadName)s: %(filename)s:%(lineno)d '
                     '%(funcName)s()  : %(message)s')
    else:
        logFormat = '%(levelname)s:%(threadName)s: %(message)s'

    if not pargs.log_only_file:
        # Add default console level with appropriate formatting and level.
        logging.basicConfig(level=logLevel, format=logFormat)
    else:
        if pargs.log_file is None:
            parser.error('--log-file-only must be used with --log-file')
        logging.getLogger().setLevel(logLevel)
    if pargs.log_file is not None:
        file_handler = logging.FileHandler(pargs.log_file)
        log_formatter = logging.Formatter(logFormat)
        file_handler.setFormatter(log_formatter)
        logging.getLogger().addHandler(file_handler)


def loadRunnerConfig(configFilePath):
    # Load runner configuration
    config = None
    try:
        _logger.debug('Loading configuration from "{}"'.format(configFilePath))
        config = ConfigLoader.load(configFilePath)
    except ConfigLoader.ConfigLoaderException as e:
        _logger.error(e)
        _logger.debug(traceback.format_exc())
        return (None, False)
    return (config, True)


def setupWorkingDirectory(workingDir):
    # Setup the working directory
    absWorkDir = os.path.abspath(workingDir)
    if os.path.exists(absWorkDir):
        # Check it's a directory and it's empty
        if not os.path.isdir(absWorkDir):
            _logger.error(
                '"{}" exists but is not a directory'.format(absWorkDir))
            return (None, False)

        absWorkDirRootContents = next(os.walk(absWorkDir, topdown=True))
        if (len(absWorkDirRootContents[1]) > 0 or
                len(absWorkDirRootContents[2]) > 0):
            _logger.error('"{}" is not empty ({},{})'.format(
                absWorkDir,
                absWorkDirRootContents[1],
                absWorkDirRootContents[2]))
            return (None, False)
    else:
        # Try to create the working directory
        try:
            os.mkdir(absWorkDir)
        except Exception as e: # pylint: disable=broad-except
            _logger.error(
                'Failed to create working_dirs_root "{}"'.format(absWorkDir))
            _logger.error(e)
            _logger.debug(traceback.format_exc())
            return (None, False)
    return (absWorkDir, True)


def writeYAMLOutputFile(yamlOutputFilePath, data):
    _logger.info('Writing output to {}'.format(yamlOutputFilePath))
    result = yaml.dump(data, default_flow_style=False)
    with open(yamlOutputFilePath, 'w') as f:
        f.write('# Generated by klee-runner\n')
        f.write(result)
    return
