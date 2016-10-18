#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
"""
Read an invocation info files and display information
about it.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
add_KleeRunner_to_module_search_path()
from KleeRunner import InvocationInfo

import argparse
import logging
import os
import pprint
import re
import sys
import yaml

_logger = None

def main(args):
  global _logger
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("-l","--log-level",type=str, default="info",
                      dest="log_level",
                      choices=['debug','info','warning','error'])
  parser.add_argument("--check-program-path", dest="check_program_path",
                      default=False, action='store_true')
  parser.add_argument('invocation_info_file',
                      help='Invocation info file',
                      type=argparse.FileType('r'))

  pargs = parser.parse_args()
  logLevel = getattr(logging, pargs.log_level.upper(),None)
  logging.basicConfig(level=logLevel)
  _logger = logging.getLogger(__name__)

  invocationInfos = InvocationInfo.loadRawInvocationInfos(pargs.invocation_info_file)
  print("schema version: {}".format(invocationInfos['schema_version']))
  print("# of jobs: {}".format(len(invocationInfos['jobs'])))

  exitCode = 0
  if pargs.check_program_path:
    for info in invocationInfos['jobs']:
      programPath = info['program']
      if not os.path.exists(programPath):
        _logger.error('Program path "{}" does not exist'.format(programPath))
      else:
        _logger.debug('Program path "{}" exists'.format(programPath))
        exitCode = 1

  return exitCode

if __name__ == '__main__':
  sys.exit(main(sys.argv))
