#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Merge runs of KLEE. Optionally merging coverage and bug replay
information
"""

import argparse
import logging
import pprint
import copy
import os
import sys
import yaml
from load_klee_analysis import add_kleeanalysis_to_module_search_path
from load_klee_runner import add_KleeRunner_to_module_search_path
add_kleeanalysis_to_module_search_path()
import KleeRunner.ResultInfo
import KleeRunner.DriverUtil as DriverUtil
import KleeRunner.ResultInfoUtil
import KleeRunner.InvocationInfo
import kleeanalysis
import kleeanalysis.rank
_logger = logging.getLogger(__name__)

def handle_rejected_result_infos(rejected_result_infos, index_to_name_fn):
    assert isinstance(rejected_result_infos, list)
    had_rejected_result_infos = False
    for index, rejected_result_infos_list in enumerate(rejected_result_infos):
        name = index_to_name_fn(index)
        assert(isinstance(rejected_result_infos_list, list))
        for result_info in rejected_result_infos_list:
            had_rejected_result_infos = True
            _logger.warning('"{}" was rejected from "{}"'.format(
                KleeRunner.ResultInfoUtil.get_result_info_key(result_info),
                name))
    return had_rejected_result_infos

def report_missing_result_infos(key_to_result_infos, index_to_name_fn):
    assert isinstance(key_to_result_infos, dict)
    had_missing_result_infos = False
    for key, result_infos in key_to_result_infos.items():
        assert(isinstance(result_infos, list))
        for index, result_info in enumerate(result_infos):
            if result_info is None:
                had_missing_result_infos = True
                name = index_to_name_fn(index)
                _logger.warning('"{}" is missing from "{}"'.format(
                    key,
                    name))
    return had_missing_result_infos

# TODO: Remove when we are sure we don't need this.
def longest_common_prefix(list_of_strings):
    assert isinstance(list_of_strings, list)
    first_string = list_of_strings[0]
    prefix_end_index = len(first_string) - 1
    for string_index, s in enumerate(list_of_strings):
        assert isinstance(s, str)
        assert len(s) > 0
        if string_index == 0:
            # No need to compare the first string to itself
            continue
        if prefix_end_index == -1:
            break
        for char_index, char_value in enumerate(s):
            if char_index > prefix_end_index:
                # No need to look past this string.
                # We already know looking at other strings
                # that the prefix is shorter
                break
            if first_string[char_index] != char_value:
                # Character mismatch.
                # Largest prefix must include last successful character
                prefix_end_index = char_index -1

    if prefix_end_index >= 0:
        return first_string[0:(prefix_end_index + 1)]
    else:
        return None

def sort_paths(directories):
    assert isinstance(directories, list)
    #lcp = longest_common_prefix(directories)
    #if lcp is not None:
    #    raise Exception('Not implemented')

    # HACK: Check if all directory names are integers
    # For directories named like `0` and `10`.
    all_ints = True
    for d in directories:
        assert isinstance(d, str)
        try:
            _ = int(d)
        except ValueError:
            all_ints = False
    if all_ints:
        # Sort numerically rather than lexographically
        return sorted(directories, key=lambda v: int(v))

    # Sort lexographically
    return sorted(directories)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("klee_repeat_output_dir",
        help="Directory containing directories where each directory is a repeat run of KLEE"
        )
    parser.add_argument("--repeat-replay-coverage-output-dir",
        default=None,
        dest="repeat_replay_coverage_output_dir",
        help="Directory containing directories where each directory contains coverage info file")
    parser.add_argument("--replay-coverage-info-file",
        dest="replay_coverage_info_file",
        default="coverage_info.yml"
    )
    parser.add_argument("--klee-result-info-file-name",
        dest="klee_result_info_file_name",
        default="output.yml",
        help="File name to look for when looking for mergable result-info")
    parser.add_argument("--output-dir",
        dest="output_dir",
        required=True)
    parser.add_argument("--repeat-bug-replay-output-dir",
        default=None,
        dest="repeat_bug_replay_output_dir",
        help="Directory containing directories where each directory contages a bug replay info file")
    parser.add_argument("--bug-replay-info-file-name",
        dest="bug_replay_info_file",
        default="bug_replay_info.yml")
    DriverUtil.parserAddLoggerArg(parser)

    args = parser.parse_args(args=argv)
    DriverUtil.handleLoggerArgs(args, parser)

    klee_result_info_repeat_run_dir = os.path.abspath(args.klee_repeat_output_dir)
    if not os.path.exists(klee_result_info_repeat_run_dir):
        _logger.error('"{}" does not exist'.format(klee_result_info_repeat_run_dir))
        return 1

    if args.repeat_replay_coverage_output_dir:
        repeat_replay_coverage_output_dir = os.path.abspath(args.repeat_replay_coverage_output_dir)
        if not os.path.exists(repeat_replay_coverage_output_dir):
            _logger.error('"{}" does not exist'.format(repeat_replay_coverage_output_dir))
            return 1
    if args.repeat_bug_replay_output_dir:
        repeat_bug_replay_output_dir = os.path.abspath(args.repeat_bug_replay_output_dir)
        if not os.path.exists(repeat_bug_replay_output_dir):
            _logger.error('"{}" does not exist'.format(repeat_bug_replay_output_dir))
            return 1

    # Setup output directory
    output_dir, success = KleeRunner.DriverUtil.setupWorkingDirectory(args.output_dir)
    if not success:
        _logger.error('Failed to set up output directory "{}"'.format(args.output_dir))
        return 1

    # Find result info files
    _, dirnames, _ = next(os.walk(klee_result_info_repeat_run_dir))
    result_info_files = []
    for d in sort_paths(dirnames):
        result_info_file = os.path.join(klee_result_info_repeat_run_dir, d, args.klee_result_info_file_name)
        _logger.info('Looking for ResultInfo file "{}"'.format(result_info_file))
        if not os.path.exists(result_info_file):
            _logger.warning('"{}" not found'.format(result_info_file))
            continue
        _logger.info('"{}" found'.format(result_info_file))
        result_info_files.append(result_info_file)

    if len(result_info_files) < 2:
        _logger.error('Need two or more result info files')
        return 1

    # Find coverage info files
    coverage_info_files = []
    if args.repeat_replay_coverage_output_dir:
        _, dirnames, _ = next(os.walk(repeat_replay_coverage_output_dir))
        for d in sort_paths(dirnames):
            coverage_info_file = os.path.join(
                repeat_replay_coverage_output_dir,
                d,
                args.replay_coverage_info_file)
            _logger.info('Looking for CoverageInfo file "{}"'.format(coverage_info_file))
            if not os.path.exists(coverage_info_file):
                _logger.warning('"{}" not found'.format(coverage_info_file))
                continue
            _logger.info('"{}" found'.format(coverage_info_file))
            coverage_info_files.append(coverage_info_file)

        if len(coverage_info_files) != len(result_info_files):
            _logger.error('Found {} coverage info files but expected {}'.format(
                len(coverage_info_files),
                len(result_info_files)
            ))
            return 1

    # Find bug replay info files
    bug_replay_info_files = []
    if args.repeat_bug_replay_output_dir:
        _, dirnames, _ = next(os.walk(repeat_bug_replay_output_dir))
        for d in sort_paths(dirnames):
            bug_replay_info_file = os.path.join(
                repeat_bug_replay_output_dir,
                d,
                args.bug_replay_info_file)
            _logger.info('Looking for BugReplayInfo file "{}"'.format(bug_replay_info_file))
            if not os.path.exists(bug_replay_info_file):
                _logger.warning('"{}" not found'.format(bug_replay_info_file))
                continue
            _logger.info('"{}" found'.format(bug_replay_info_file))
            bug_replay_info_files.append(bug_replay_info_file)

        if len(bug_replay_info_files) != len(result_info_files):
            _logger.error('Found {} bug replay info files but expected {}'.format(
                len(bug_replay_info_files),
                len(result_info_files)
            ))
            return 1

    # Open result info files
    result_infos_list = []
    for result_info_file in result_info_files:
        with open(result_info_file, 'r') as f:
            _logger.info('Loading "{}"'.format(f.name))
            result_info = KleeRunner.ResultInfo.loadRawResultInfos(f)
            result_infos_list.append(result_info)


    def index_to_name_fn(i):
        return result_info_files[i]

    # Group result infos by key (program name)
    key_to_result_infos, rejected_result_infos = (
        KleeRunner.ResultInfoUtil.group_result_infos_by(result_infos_list)
    )
    had_rejected_result_infos = handle_rejected_result_infos(
        rejected_result_infos,
        index_to_name_fn
    )

    if had_rejected_result_infos:
        _logger.error('Rejected ResultInfo(s) where found.')
        return 1

    if len(key_to_result_infos) == 0:
        _logger.error('No accepeted result infos')
        return 1
    had_missing_result_infos = report_missing_result_infos(
        key_to_result_infos,
        index_to_name_fn)
    if had_missing_result_infos:
        _logger.error('Some result infos were missing')
        return 1

    # Open coverage info files
    coverage_infos_list = []
    for coverage_info_file in coverage_info_files:
        with open(coverage_info_file, 'r') as f:
            _logger.info('Loading "{}"'.format(f.name))
            coverage_info = KleeRunner.util.loadYaml(f)
            coverage_infos_list.append(coverage_info)

    # Open bug replay info files
    bug_replay_infos_list = []
    for bug_replay_info_file in bug_replay_info_files:
        with open(bug_replay_info_file, 'r') as f:
            _logger.info('Loading "{}"'.format(f.name))
            bug_replay_info = KleeRunner.util.loadYaml(f)
            bug_replay_infos_list.append(bug_replay_info)

    # Merge result infos and write data out
    merged_result_info = get_merged_result_infos(
        key_to_result_infos,
        result_infos_list)
    output_result_info_file_path = os.path.join(
        output_dir,
        args.klee_result_info_file_name
    )
    with open(output_result_info_file_path, 'w') as f:
        KleeRunner.util.writeYaml(f, merged_result_info)

    # Merge coverage data and write data out
    if len(coverage_infos_list) > 0:
        merged_coverage_info = get_merged_coverage_infos(
            coverage_infos_list,
            coverage_info_files)
        merged_coverage_info_file_path = os.path.join(
            output_dir,
            args.replay_coverage_info_file)
        with open(merged_coverage_info_file_path, 'w') as f:
            KleeRunner.util.writeYaml(f, merged_coverage_info)

    # Merge bug replay info and write data out
    if len(bug_replay_infos_list) > 0:
        merged_bug_replay_info = get_merged_bug_replay_infos(
            bug_replay_infos_list,
            bug_replay_info_files)
        merged_bug_replay_info_file_path = os.path.join(
            output_dir,
            args.bug_replay_info_file)
        with open(merged_bug_replay_info_file_path, 'w') as f:
            KleeRunner.util.writeYaml(f, merged_bug_replay_info)

    return 0

def get_merged_bug_replay_infos(bug_replay_infos_list, bug_replay_info_files):
    merged_bug_replay_info = {}
    def get_bug_replay_info():
        template_bug_replay_info = {
            'augmented_spec_file': None,
            'test_cases': {},
        }
        return template_bug_replay_info

    # Insert all the keys (program names)
    for cov_info in bug_replay_infos_list:
        assert isinstance(cov_info, dict)
        for program_name in cov_info.keys():
            if program_name not in merged_bug_replay_info:
                merged_bug_replay_info[program_name] = get_bug_replay_info()

    # Iterate over each program
    for program_name, prog_bug_replay_info in merged_bug_replay_info.items():
        for index, bug_replay_info in enumerate(bug_replay_infos_list):
            individual_bug_replay_info = None
            try:
                individual_bug_replay_info = bug_replay_info[program_name]
            except KeyError:
                _logger.warning('Missing bug replay info for "{}" in {}'.format(
                    program_name,
                    bug_replay_info_files[index]))
                continue
            prog_bug_replay_info['augmented_spec_file'] = individual_bug_replay_info['augmented_spec_file']
            _logger.debug('Adding {} to {}'.format(individual_bug_replay_info['test_cases'], program_name))
            prog_bug_replay_info['test_cases'].update(individual_bug_replay_info['test_cases'])
    return merged_bug_replay_info

def get_merged_result_infos(key_to_result_infos, result_infos_list):
    merged_result_info = {
        'results': [],
        'schema_version': KleeRunner.ResultInfo.getSchema()['__version__'],
        'misc': {
            'merged': True,
            'individual_misc': {}
        }
    }

    # TODO: Merge misc data

    # Merge result infos
    for program_name, result_infos in key_to_result_infos.items():
        assert isinstance(program_name, str)
        assert isinstance(result_infos, list)
        assert len(result_infos) == len(result_infos_list)
        _logger.info('Merging "{}"'.format(program_name))

        combined_result_info = merge_result_infos(result_infos)
        merged_result_info['results'].append(combined_result_info)
    return merged_result_info

def get_merged_coverage_infos(coverage_infos_list, coverage_info_files):
    merged_coverage_info = {}
    def get_coverage_info():
        template_coverage_info = {
            'branch_coverage': [],
            'line_coverage': [],
            'raw_data': [],
        }
        return template_coverage_info

    # Insert all the keys (program names)
    for cov_info in coverage_infos_list:
        assert isinstance(cov_info, dict)
        for program_name in cov_info.keys():
            if program_name not in merged_coverage_info:
                merged_coverage_info[program_name] = get_coverage_info()

    # Iterate over each program
    for program_name, prog_coverage_info in merged_coverage_info.items():
        for index, cov_info in enumerate(coverage_infos_list):
            individual_cov_info = None
            try:
                individual_cov_info = cov_info[program_name]
            except KeyError:
                # Assume no coverage
                _logger.warning('Assuming no coverage for "{}" from "{}"'.format(
                    program_name,
                    coverage_info_files[index]))
                individual_cov_info = {
                    'branch_coverage': 0.0,
                    'line_coverage': 0.0,
                    'raw_data': None
                }
            prog_coverage_info['branch_coverage'].append(
                individual_cov_info['branch_coverage'])
            prog_coverage_info['line_coverage'].append(
                individual_cov_info['line_coverage'])
            prog_coverage_info['raw_data'].append(
                individual_cov_info['raw_data'])

        # Warn if any coverage values differ
        same_branch_cov = same_values_or_list_of_values(
            prog_coverage_info['branch_coverage'])
        if isinstance(same_branch_cov, list):
            _logger.warning('Branch coverage ({}) differs for "{}"'.format(
                prog_coverage_info['branch_coverage'],
                program_name))
        same_line_cov = same_values_or_list_of_values(
            prog_coverage_info['line_coverage'])
        if isinstance(same_line_cov, list):
            _logger.warning('Line coverage ({})differs for "{}"'.format(
                prog_coverage_info['line_coverage'],
                program_name))
    return merged_coverage_info

def same_values_or_list_of_values(l):
    """
        If all elements of list `l` has
        same value l return that value
        otherwise return the original list
    """
    assert isinstance(l, list)
    assert len(l) > 0
    same_value = None
    for index, v in enumerate(l):
        if index == 0:
            same_value = v
            continue
        if v != same_value:
            return l
    return same_value


def merge_result_infos(result_infos):
    assert isinstance(result_infos, list)
    assert len(result_infos) > 1

    # Make a deep copy of the first to use as a template for the merged result
    merged_result_info = copy.deepcopy(result_infos[0])

    # Merge backend-timeout
    backed_timeout_values = [ r['backend_timeout'] for r in result_infos ]
    _logger.debug('Got backend timeout values: {}'.format(backed_timeout_values))
    backed_timeout_values = same_values_or_list_of_values(backed_timeout_values)
    _logger.debug('Merged backend timeout values: {}'.format(backed_timeout_values))
    merged_result_info['backend_timeout'] = backed_timeout_values

    # Merge exit code
    exit_code_values = [ r['exit_code'] for r in result_infos ]
    _logger.debug('Got exit code values: {}'.format(exit_code_values))
    exit_code_values = same_values_or_list_of_values(exit_code_values)
    _logger.debug('Merged exit code values: {}'.format(exit_code_values))
    merged_result_info['exit_code'] = exit_code_values

    # Merge klee_dir
    klee_dir_values = [ r['klee_dir'] for r in result_infos ]
    _logger.debug('Got klee_dir values: {}'.format(klee_dir_values))
    merged_result_info['klee_dir'] = klee_dir_values

    # Merge log_file
    log_file_values = [ r['log_file'] for r in result_infos ]
    _logger.debug('Got log_file values: {}'.format(log_file_values))
    merged_result_info['log_file'] = log_file_values

    # Merge out of memory
    out_of_memory_values = [ r['out_of_memory'] for r in result_infos]
    _logger.debug('Got out_of_memory values: {}'.format(out_of_memory_values))
    out_of_memory_values = same_values_or_list_of_values(out_of_memory_values)
    _logger.debug('Merged out_of_memory values: {}'.format(out_of_memory_values))
    merged_result_info['out_of_memory'] = out_of_memory_values

    # Merge working directory
    working_directory_values = [ r['working_directory'] for r in result_infos]
    merged_result_info['working_directory'] = working_directory_values

    # Merge numeric values

    # DL: Design decision. We could compute stats here but given this is
    # cheap to compute and I don't want to have re-generate the merged files
    # every time we change what stats we compute we will just make these the list
    # of values and let other tools worry about how to analyse these values.

    # merge sys_cpu_time
    sys_cpu_time_values = [r['sys_cpu_time'] for r in result_infos]
    merged_result_info['sys_cpu_time'] = sys_cpu_time_values

    # merge user_cpu_time
    user_cpu_time_values = [r['user_cpu_time'] for r in result_infos]
    merged_result_info['user_cpu_time'] = user_cpu_time_values

    # merge wallclock_time
    wallclock_time_values = [r['wallclock_time'] for r in result_infos]
    merged_result_info['wallclock_time'] = wallclock_time_values

    # Add an attribute that hints that this is a merged result
    merged_result_info['merged_result'] = True

    return merged_result_info


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
