#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info describing a set of KLEE test case
runs that were on coverage instrumented binaries and then
emit coverage information.
"""
from load_klee_runner import add_KleeRunner_to_module_search_path
from load_klee_analysis import add_kleeanalysis_to_module_search_path
add_KleeRunner_to_module_search_path()
add_kleeanalysis_to_module_search_path()
from KleeRunner import ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import KleeRunner.InvocationInfo
import KleeRunner.util
import kleeanalysis.analyse
import kleeanalysis.kleedir

import argparse
import logging
import os
import pprint
import re
import shutil
import subprocess
import sys
import yaml

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)


def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_info_file',
                        help='Result info file',
                        type=argparse.FileType('r'))
    parser.add_argument('--output-yaml',
                        dest='output_yaml',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')
    parser.add_argument('--output-dir',
            dest='output_dir',
            default=None,
            required=True,
            help='Directory to dump coverage information')

    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args()
    DriverUtil.handleLoggerArgs(pargs, parser)

    aug_spec_path_prefix = None
    aug_spec_path_replacement= None

    # Check output directory
    output_dir, success = DriverUtil.setupWorkingDirectory(pargs.output_dir)
    if not success:
        _logger.error('Failed to setup output directory')
        return 1

    _logger.info('Loading "{}"...'.format(pargs.result_info_file.name))
    resultInfos, resultInfoMisc  = ResultInfo.loadResultInfos(pargs.result_info_file)
    _logger.info('Loading complete')

    # Check the misc data
    if resultInfoMisc is None:
        _logger.error('Expected result info to have misc data')
        return 1
    if resultInfoMisc['runner'] != 'NativeReplay':
        _logger.error('Expected runner to have been NativeReplay but was "{}"'.format(
            resultInfoMisc['runner']))
        return 1

    if 'invocation_info_misc' not in resultInfoMisc:
        _logger.error('Expected "invocation_info_misc" in result info misc but it was not found')
        return 1

    if not isinstance(resultInfoMisc['invocation_info_misc'], dict):
        _logger.error('Expected "invocation_info_misc" to be a dictionary')
        return 1

    if not 'coverage_merge_type' in resultInfoMisc['invocation_info_misc']:
        _logger.error('Expected "coverage_merge_type" to be present')
        return 1

    coverageType = resultInfoMisc['invocation_info_misc']['coverage_merge_type']
    _logger.info('Coverage type:{}'.format(coverageType))

    # FIXME: Support other coverage types
    if coverageType != 'program':
        _logger.info('Only program coverage type supported')
        return 1

    program_to_coverage_dir_map = dict()
    for result_index, r in enumerate(resultInfos):
        _logger.info('Processing {}/{}'.format(result_index + 1, len(resultInfos)))
        result_ii = r.RawInvocationInfo
        program_to_coverage_dir_map[result_ii['program']] = result_ii['coverage_dir']

    _logger.info('Found {} coverage directories'.format(len(program_to_coverage_dir_map)))

    # Create merged coverage directories. We need to merge the `*.gcno` files from
    # the build tree and the `*.gcda` coverage counters to keep gcov happy.
    program_to_merged_cov_dir_map = dict()
    program_to_coverage_info = dict()
    for program, gcda_cov_dir in program_to_coverage_dir_map.items():
        program_name = os.path.basename(program)
        program_to_coverage_info[program_name] = {
            'branch_coverage': 0.0, # percentage. 1.0 is 100%
            'line_coverage': 0.0, # percentage. 1.0 is 100%
        }
        dest = os.path.join(pargs.output_dir, program_name + '.cov')
        dest_abs = os.path.abspath(dest)
        success = merge_coverage_dirs(gcda_cov_dir, dest_abs)
        if success is False:
            _logger.error('Merging directories failed')
            return 1

        if success is None:
            _logger.error('Coverage information missing!')
            continue

        if program_name in program_to_merged_cov_dir_map:
            _logger.error('Already have program called "{}"'.format(program_name))
            return 1
        program_to_merged_cov_dir_map[program_name] = dest_abs

    program_to_coverage_xml_file_map = dict()
    # Run gcovr to extact the coverage information
    for program, merged_cov_dir in program_to_merged_cov_dir_map.items():
        output_xml = merged_cov_dir.rstrip(os.sep)
        output_xml = '{}.xml'.format(output_xml)
        cmd_line = [
            "gcovr",
            "--root", merged_cov_dir,
            "--filter", "/",
            "--xml",
            "--output", output_xml]
        _logger.info('Running: {}'.format(cmd_line))

        # Run
        ret_code = subprocess.call(cmd_line)
        if ret_code != 0:
            _logger.error('Calling gcovr failed')
            return False
        program_to_coverage_xml_file_map[program] = output_xml

    # Extract the information we want
    for program, output_xml in program_to_coverage_xml_file_map.items():
        _logger.info('Getting coverage info for "{}"'.format(program))
        tree = ET.parse(output_xml)
        root = tree.getroot()
        # Get the data from the root `coverage` element
        attributes = root.attrib
        # FIXME: It's debatable if we should take the global coverage
        # when working library dependencies like libgmp and libgsl.
        # We will likely get low coverage within the library itself.
        branch_cov = float(attributes['branch-rate'])
        line_cov = float(attributes['line-rate'])
        program_to_coverage_info[program]['branch_coverage'] = branch_cov
        program_to_coverage_info[program]['line_coverage'] = line_cov
        program_to_coverage_info[program]['raw_data'] = output_xml

    # Now emit as YAML
    as_yaml = yaml.dump(program_to_coverage_info, default_flow_style=False)
    pargs.output_yaml.write(as_yaml)
    return 0

_RE_GCDA = re.compile(r'(^.+)\.gcda$')

def merge_coverage_dirs(gcda_dir, dest):
    """
        returns True is success, False if there was a fatal error.
        None if no coverage information is available.
    """
    _logger.info('Merging "{}" into "{}"'.format(
        gcda_dir, dest))
    assert os.path.isabs(gcda_dir)
    
    # Walk the gcda_dir to find all the gcda_dir files
    covfiles_src_to_dest = dict() # destination is relative to dest
    for dirpath, dirnames, filenames in os.walk(gcda_dir):
        for f in filenames:
            if not f.endswith('.gcda'):
                _logger.debug('Skipping file "{}"'.format(f))
                continue
            gcda_path = os.path.join(dirpath, f)
            # Strip the prefix
            assert dirpath.startswith(gcda_dir)
            stripped_dirpath = dirpath[len(gcda_dir):]
            stripped_gcda_path = os.path.join(stripped_dirpath, f)
            # Add entry for copying over gcda file
            covfiles_src_to_dest[gcda_path] = stripped_gcda_path

            # Now look for corresponding gcno file. We make
            # an assumption that these files are in the correct
            # place on the file system
            _logger.info(stripped_gcda_path)
            m = _RE_GCDA.match(stripped_gcda_path)
            if m is None:
                _logger.error('Failed to match re')
                return False
            gcno_path = '{}{}'.format(m.group(1), '.gcno')
            _logger.info('Looking for "{}"'.format(gcno_path))
            if not os.path.exists(gcno_path):
                _logger.error('Failed to find "{}"'.format(gcno_path))
                return False
            covfiles_src_to_dest[gcno_path] = gcno_path

    if len(covfiles_src_to_dest) == 0:
        _logger.error('Failed to find any coverage files')
        return None

    # Copy over files
    for src_path, relative_dest_path in covfiles_src_to_dest.items():
        abs_dest_path = "{}{}".format(dest, relative_dest_path)
        _logger.info('Dest "{}"'.format(abs_dest_path))

        # Make the directories as needed
        assert os.path.isabs(abs_dest_path)
        covfile_destination_dir = os.path.dirname(abs_dest_path)

        # Make the directory if it doesn't already exist
        os.makedirs(covfile_destination_dir, exist_ok=True)

        # Now copy file over
        shutil.copyfile(src_path, abs_dest_path)
    return True

if __name__ == '__main__':
    sys.exit(main(sys.argv))

