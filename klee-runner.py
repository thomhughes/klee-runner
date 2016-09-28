#!/usr/bin/env python
# vim: set sw=2 ts=2 softtabstop=2 expandtab:
"""
    Script to run a program
"""
import argparse
import logging
import os
from  KleeRunner import InvocationInfo
from KleeRunner import ConfigLoader
from KleeRunner import RunnerFactory
import pprint
import traceback
import yaml
import sys

def entryPoint(args):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("-l","--log-level",type=str, default="info", dest="log_level", choices=['debug','info','warning','error'])
  parser.add_argument("--dry", action='store_true', help="Stop after initialising runners")
  parser.add_argument("config_file", help="YAML configuration file")
  # parser.add_argument("invocation_info", help="invocation info")
  parser.add_argument("working_dir", help="Working directory")
  parser.add_argument("yaml_output", help="path to write YAML output to")
  parser.add_argument("program", help="Program to run")
  # `program_args` is a dummy argument so we get the right usage message from argparse.
  # We parse `programs_args` ourselves
  parser.add_argument("program_args", nargs="*", help="Arguments to pass to program")

  # Determine where the `program` argument is so
  # we split the arguments into to lists. One to give
  # to argparse and the other to use in an instance of InvocationInfo.
  # FIXME: We need a better heuristic.
  index = 0
  while index < (len(args) -1):
    # FIXME: We need to support native executables too.
    if args[index].endswith('.bc'): # This is such a hack!
      break
    index += 1

  argParseArgs = args[:index+1]
  programArgs = []
  if len(args) >= index + 2:
    programArgs = args[index+1:]

  pargs = parser.parse_args(argParseArgs)

  logLevel = getattr(logging, pargs.log_level.upper(),None)
  if logLevel == logging.DEBUG:
    logFormat = '%(levelname)s:%(threadName)s: %(filename)s:%(lineno)d %(funcName)s()  : %(message)s'
  else:
    logFormat = '%(levelname)s:%(threadName)s: %(message)s'

  logging.basicConfig(level=logLevel, format=logFormat)
  _logger = logging.getLogger(__name__)

  # Check if output file already exists
  yamlOutputFile = os.path.abspath(pargs.yaml_output)
  if os.path.exists(yamlOutputFile):
    _logger.error('yaml_output file ("{}") already exists'.format(yamlOutputFile))
    return 1

  # Load runner configuration
  try:
    _logger.debug('Loading configuration from "{}"'.format(pargs.config_file))
    config = ConfigLoader.load(pargs.config_file)
  except ConfigLoader.ConfigLoaderException as e:
    _logger.error(e)
    _logger.debug(traceback.format_exc())
    return 1

  # Create invocation info
  invocationInfoRepr = {
    'program': pargs.program,
    'command_line_arguments': programArgs,
    'environment_variables': {},
    'extra_klee_arguments': [],
  }
  print(invocationInfoRepr)
  invocationInfo = InvocationInfo.InvocationInfo(invocationInfoRepr)

  # Setup the working directory
  workDir = os.path.abspath(pargs.working_dir)
  if os.path.exists(workDir):
    # Check it's a directory and it's empty
    if not os.path.isdir(workDir):
      _logger.error('"{}" exists but is not a directory'.format(workDir))
      return 1

    workDirRootContents = next(os.walk(workDir, topdown=True))
    if len(workDirRootContents[1]) > 0 or len(workDirRootContents[2]) > 0:
      _logger.error('"{}" is not empty ({},{})'.format(workDir,
        workDirRootContents[1], workDirRootContents[2]))
      return 1
  else:
    # Try to create the working directory
    try:
      os.mkdir(workDir)
    except Exception as e:
      _logger.error('Failed to create working_dirs_root "{}"'.format(workDirsRoot))
      _logger.error(e)
      _logger.debug(traceback.format_exc())
      return 1

  # Get Runner class to use
  # FIXME: Not sure how we want this tool to work with multiple use cases
  # (i.e. running natively with ktest files, or running klee in replay
  # mode with ktest files). For now just force this particular running
  # as a sanity check.
  assert config['runner'] == 'Klee'
  RunnerClass = RunnerFactory.getRunnerClass(config['runner'])
  runner = RunnerClass(invocationInfo, workDir, config['runner_config'])

  if pargs.dry:
    _logger.info('Not running runner')
    return 0

  # Run the runner
  report = [ ]
  exitCode = 0
  try:
    runner.run()
    report.append(runner.getResults())
  except KeyboardInterrupt:
    _logger.error('Keyboard interrupt')
  except:
    _logger.error("Error handling:{}".format(runner.program))
    _logger.error(traceback.format_exc())

    # Attempt to add the error to the report
    errorLog = {}
    errorLog['program'] = runner.program
    errorLog['error'] = traceback.format_exc()
    report.append(errorLog)
    exitCode = 1

  # Write result to YAML file
  _logger.info('Writing output to {}'.format(yamlOutputFile))
  result = yaml.dump(report, default_flow_style=False)
  with open(yamlOutputFile, 'w') as f:
    f.write('# klee-runner report using runner {}\n'.format(config['runner']))
    f.write(result)

  return exitCode

if __name__ == '__main__':
  sys.exit(entryPoint(sys.argv[1:]))
