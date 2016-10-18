#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
"""
Read an invocation info file and re-write paths contained
in the file.

This is useful if you have benchmarks built in a container
where the paths in the container don't match the paths
in the host.
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

def replaceString(oldString, prefix, replacement):
  """
  Returns a replacement string
  """
  if not oldString.startswith(prefix):
    _logger.debug('"{}" does not start with prefix "{}"'.format(oldString, prefix))
    return oldString

  # Remove the prefix
  assert len(prefix) < len(oldString)
  stripped = oldString[len(prefix):]
  finalString = "{}{}".format(replacement, stripped)
  _logger.debug('Replaced "{}" with "{}"'.format(oldString, finalString))
  if not os.path.exists(finalString):
    _logger.warning('Path "{}" does not exist on host'.format(finalString))
  return finalString

# Recursively rewrite data
# FIXME: Refactor to make this some sort of visitor
def visit(data, prefix, replacement):
  if isinstance(data, dict):
    # Leave keys unmodified but recursively modify the values
    newData = dict()
    for key, value in data.items():
      newData[key] = visit(value, prefix, replacement)
    return newData
  elif isinstance(data, list):
    # Retain position in list but modify if necessary
    newData = []
    for index in range(0, len(data)):
      newData[index] = visit(data[index], prefix, replacement)
    return newData
  elif isinstance(data, str):
    return replaceString(data, prefix, replacement)
  elif isinstance(data, int):
    # Leave unmodified
    return data
  elif isinstance(data, float):
    # Leave unmodified
    return data
  else:
    raise Exception('Unhandled data type "{}"'.format(data))

def main(args):
  global _logger
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("-l","--log-level",type=str, default="info",
                      dest="log_level",
                      choices=['debug','info','warning','error'])
  parser.add_argument('invocation_info_file',
                      help='Invocation info file',
                      type=argparse.FileType('r'))
  parser.add_argument('path_prefix_to_replace', type=str)
  parser.add_argument('path_prefix_replacement', type=str)
  parser.add_argument('-o', '--output',
                      type=argparse.FileType('w'),
                      default=sys.stdout,
                      help='Output location (default stdout)')

  pargs = parser.parse_args()
  logLevel = getattr(logging, pargs.log_level.upper(),None)
  logging.basicConfig(level=logLevel)
  _logger = logging.getLogger(__name__)

  if len(pargs.path_prefix_to_replace) < 1:
    _logger.error("path_prefix_to_replace can't be empty")
    return 1

  if not os.path.isabs(pargs.path_prefix_replacement):
    _logger.error("path_prefix_replacement must be absolute")
    return 1

  if len(pargs.path_prefix_replacement) < 1:
    _logger.error("path_prefix_replacement can't be empty")
    return 1

  # Use raw access so we don't add implicit fields
  invocationInfos = InvocationInfo.loadRawInvocationInfos(pargs.invocation_info_file)

  # Do replacement
  ii = invocationInfos['jobs']
  for index in range(0, len(ii)):
    ii[index] = visit(ii[index],
      pargs.path_prefix_to_replace,
      pargs.path_prefix_replacement)

  # Output as YAML
  pargs.output.write('# Automatically generated invocation info\n')
  pargs.output.write(yaml.dump(invocationInfos, default_flow_style=False))
  return 0

if __name__ == '__main__':
  sys.exit(main(sys.argv))
