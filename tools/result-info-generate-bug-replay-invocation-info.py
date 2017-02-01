#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info describing a set of runs with KLEE and
generate an invocation info file to replay reported
bugs on appropriately instrumented binaries.

The generated invocation info file should be used with
the NativeReplay runner
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
import kleeanalysis.verificationtasks
import kleeanalysis.kleedir

import argparse
import logging
import os
import pprint
import re
import sys
import yaml

_logger = logging.getLogger(__name__)


def main(args):
    global _logger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_info_file',
                        help='Result info file',
                        type=argparse.FileType('r'))
    parser.add_argument('--asan-build-root',
                        dest='asan_build_root',
                        required=True
                       )
    parser.add_argument('--ubsan-build-root',
                        dest='ubsan_build_root',
                        required=True
                       )
    parser.add_argument('--normal-build-root',
                        dest='normal_build_root',
                        required=True
                       )
    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')

    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args()
    DriverUtil.handleLoggerArgs(pargs, parser)

    aug_spec_path_prefix = None
    aug_spec_path_replacement= None

    invocation_infos = {
        'jobs': [],
        'schema_version': KleeRunner.InvocationInfo.getSchema()['__version__'],
    }
    jobs = invocation_infos['jobs']

    bug_run_ii_template = {
        'command_line_arguments': [],
        'environment_variables': {},
        'ktest_file': '',
        'attach_gdb': False,
        'program': '',
        'misc' : {},
    }
    def get_bug_replay_run_ii():
        x = bug_run_ii_template.copy()
        x['command_line_arguments'] = []
        x['environment_variables'] = {}
        x['misc'] = {}
        return x

    resultInfos, _  = ResultInfo.loadResultInfos(pargs.result_info_file)
    coverage_dir_to_program_map = {} # For sanity checking
    coverage_dir_set = set() # For sanity checking
    for result_index, r in enumerate(resultInfos):
        _logger.info('Processing {}/{}'.format(result_index + 1, len(resultInfos)))

        result_ii = r.RawInvocationInfo

        # FIXME: This is fp-bench specific
        # Retrieve the native program
        augmented_spec_file_path = result_ii['misc']['augmented_spec_file']
        _logger.debug('Retrieved augmented spec file path "{}"'.format(augmented_spec_file_path))
        if not os.path.exists(augmented_spec_file_path):
            _logger.error('"{}" does not exist'.format(augmented_spec_file_path))
            return 1
        with open(augmented_spec_file_path, 'r') as f:
            augmented_spec = KleeRunner.util.loadYaml(f)
        assert isinstance(augmented_spec, dict)
        exe_dir = os.path.dirname(augmented_spec_file_path)
        exe_name = augmented_spec['misc']['exe_path']
        exe_path = os.path.join(exe_dir, exe_name)
        if not os.path.exists(exe_path):
            _logger.error('Failed to find native executable "{}"'.format(exe_path))
            return 1

        # Make sure build paths ends in slash if they don't already
        if not pargs.normal_build_root.endswith(os.sep):
            pargs.normal_build_root += os.sep
        if not pargs.asan_build_root.endswith(os.sep):
            pargs.asan_build_root += os.sep
        if not pargs.ubsan_build_root.endswith(os.sep):
            pargs.ubsan_build_root += os.sep

        # Check paths exist
        if not os.path.exists(pargs.normal_build_root):
            _logger.error('normal build root "{}" does not exist'.format(pargs.normal_build_root))
            return 1
        if not os.path.exists(pargs.asan_build_root):
            _logger.error('asan build root "{}" does not exist'.format(pargs.asan_build_root))
            return 1
        if not os.path.exists(pargs.ubsan_build_root):
            _logger.error('ubsan build root "{}" does not exist'.format(pargs.ubsan_build_root))
            return 1

        # FIXME: This is fp-bench specific
        # Retrieve runtime_environment if it exists
        extra_cmd_line_args = []
        extra_env_vars = {}
        if 'runtime_environment' in augmented_spec:
            runtime_env = augmented_spec['runtime_environment']
            extra_cmd_line_args = runtime_env['command_line_arguments']
            _logger.info('Found extra cmd line args:{}'.format(extra_cmd_line_args))
            extra_env_vars = runtime_env['environment_variables']
            _logger.info('Found extra environment vars: {}'.format(extra_env_vars))

        klee_dir_path = r.KleeDir
        if klee_dir_path is None:
            _logger.error('KLEE dir missing')
            return 1

        if not os.path.exists(klee_dir_path):
            _logger.error('KLEE directory "{}" does not exist'.format(klee_dir_path))
            return 1

        # Open the KLEE dir
        klee_dir_obj = kleeanalysis.kleedir.KleeDir(klee_dir_path)
        test_cases = list(klee_dir_obj.tests)
        _logger.info('Found {} tests cases in "{}"'.format(len(test_cases), klee_dir_path))

        # collect the test cases that are counter examples to correctness (i.e. bugs)
        task_to_test_case_map = dict()
        # FIXME: This is fp-bench specific
        for task in kleeanalysis.verificationtasks.fp_bench_tasks:
            cexs = kleeanalysis.verificationtasks.get_cex_test_cases_for_fp_bench_task(
                task,
                klee_dir_obj)
            task_to_test_case_map[task] = cexs
        for task, test_cases in task_to_test_case_map.items():
            for test in test_cases:
                job_index = len(jobs) # The index of this job in the output invocation info
                if getattr(test, 'ktest_file', None) is None:
                    _logger.error('Skipping test "{}"'.format(test))
                    continue
                # Get a copy of the dictionary that we can safely mutate
                bug_replay_run_ii = get_bug_replay_run_ii()

                # Add spec mandated cmdline args/environment vars
                bug_replay_run_ii['command_line_arguments'].extend(extra_cmd_line_args)
                bug_replay_run_ii['environment_variables'].update(extra_env_vars)

                build_type, attach_gdb = task_to_build_type_and_gdb_attach_property(task)
                bug_replay_run_ii['attach_gdb'] = attach_gdb

                # Update the environment variables for any build type specific environment variables.
                bug_replay_run_ii['environment_variables'].update(get_env_for_build_type(build_type))

                # Set the program
                replay_exe = get_exe_path(
                    build_type,
                    exe_path,
                    pargs.normal_build_root,
                    pargs.asan_build_root,
                    pargs.ubsan_build_root
                )
                bug_replay_run_ii['program'] = replay_exe
                # Set the test case
                bug_replay_run_ii['ktest_file'] = test.ktest_file

                # FIXME: This is fp-bench specific
                # Set the augmented spec file path
                bug_replay_run_ii['misc']['augmented_spec_file'] = augmented_spec_file_path
                bug_replay_run_ii['misc']['fp_bench_task'] = task
                bug_replay_run_ii['misc']['bug_replay_build_type'] = build_type

                jobs.append(bug_replay_run_ii)

    # Report some stats
    _logger.info('# of invocations: {}'.format(len(jobs)))

    # Check is invalid invocation info
    _logger.info('Validating invocation info...')
    KleeRunner.InvocationInfo.validateInvocationInfos(invocation_infos)
    _logger.info('Invocation info is valid')
    # Now emit as YAML
    as_yaml = yaml.dump(invocation_infos, default_flow_style=False)
    pargs.output.write(as_yaml)
    return 0

def task_to_build_type_and_gdb_attach_property(task):
    build_type = None
    if task == 'no_invalid_deref' or task == 'no_invalid_free':
        return ("asan", False)
    elif task == "no_overshift" or task == "no_integer_division_by_zero":
        return ("ubsan", False)
    else:
        return ("normal", True)

def get_exe_path(build_type, original_exe, normal_build_root, asan_build_root, ubsan_build_root):
    # We assume that the original exe uses the same build path as the normal_build
    assert original_exe.startswith(normal_build_root)
    prefix_stripped = original_exe[len(normal_build_root):]
    if build_type == 'normal':
        return original_exe
    elif build_type == 'asan':
        new_exe_path = os.path.join(asan_build_root, prefix_stripped)
        if not os.path.exists(new_exe_path):
            _logger.error('"{}" does not exist'.format(new_exe_path))
            sys.exit(1)
        return new_exe_path
    elif build_type == 'ubsan':
        new_exe_path = os.path.join(ubsan_build_root, prefix_stripped)
        if not os.path.exists(new_exe_path):
            _logger.error('"{}" does not exist'.format(new_exe_path))
            sys.exit(1)
        return new_exe_path
    else:
        raise Exception('Unknown build_type {}'.format(build_type))

def get_env_for_build_type(build_type):
    if build_type == 'normal':
        return {}
    elif build_type == 'ubsan':
        # HACK use exit code 19 for ubsan
        return { 'UBSAN_OPTIONS': 'halt_on_error=1,abort_on_error=0,print_stacktrace=1,exitcode=19' }
    elif build_type == 'asan':
        # HACK use exit code 20 for asan
        return { 'ASAN_OPTIONS': 'abort_on_error=0,exitcode=20,detect_leaks=false'}
    else:
        raise Exception('Unknown build_type {}'.format(build_type))

if __name__ == '__main__':
    sys.exit(main(sys.argv))
