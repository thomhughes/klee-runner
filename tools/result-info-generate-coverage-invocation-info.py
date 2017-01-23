#!/usr/bin/env python
# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE-SVCB.txt
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
"""
Read a result info describing a set of runs with KLEE and
generate an invocation info file to gather coverage
from the generated ktest files.

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
    parser.add_argument('coverage_mode',
        choices=['global', 'program', 'testcase'],
        help='Coverage merge mode. `global` merges coverage for all test'
        'cases. `program` merges coverage for all test cases that execute the'
        'same program. `testcase` does not merge covereage at all')
    parser.add_argument('result_info_file',
                        help='Result info file',
                        type=argparse.FileType('r'))
    parser.add_argument('--patch-aug-spec-path',
        dest='patch_augmented_spec_path',
        default=None,
        help='Replace augmented spec path <prefix>:<replacement>.'
        'This is useful for using a different build to the one that'
        ' was used for KLEE runs.'
        'E.g. `--patch-aug-spec-path /home/user:/home/foo`')
    parser.add_argument('-o', '--output',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output location (default stdout)')

    DriverUtil.parserAddLoggerArg(parser)
    pargs = parser.parse_args()
    DriverUtil.handleLoggerArgs(pargs, parser)

    aug_spec_path_prefix = None
    aug_spec_path_replacement= None

    # Setup function for doing augmented spec file path patching.
    if pargs.patch_augmented_spec_path:
        if pargs.patch_augmented_spec_path.count(':') != 1:
            _logger.error('Invalid spec path replacement. It should contain the ":" character')
            return 1
        m = re.match(r'^(.+):(.+)$', pargs.patch_augmented_spec_path)
        if m is None:
            _logger.error("Invalid spec replacement. It did not match regex")
            return 1
        aug_spec_path_prefix = m.group(1)
        aug_spec_path_replacement = m.group(2)
        _logger.info('Using augmented spec path replacement')
        _logger.info('Will replace prefix "{}" with "{}"'.format(
            aug_spec_path_prefix,
            aug_spec_path_replacement))
        if not os.path.isabs(aug_spec_path_prefix):
            _logger.info('"{}" is not absolute'.format(aug_spec_path_prefix))
            return 1
        if not os.path.isabs(aug_spec_path_replacement):
            _logger.info('"{}" is not absolute'.format(aug_spec_path_replacement))
            return 1
        def replace_spec_path(s):
            if not s.startswith(aug_spec_path_prefix):
                _logger.warning('Failed to do replacement on "{}"'.format(s))
                return s
            prefix_stripped = s[len(aug_spec_path_prefix):]
            ret = aug_spec_path_replacement + prefix_stripped
            _logger.debug('Replacing "{}" with "{}"'.format(s, ret))
            return ret
    else:
        def replace_spec_path(s):
            return s

    invocation_infos = {
        'jobs': [],
        'schema_version': KleeRunner.InvocationInfo.getSchema()['__version__'],
        'misc': {
            # Hint to runners. It is a list of lists of indices that cannot
            # be executed in parallel. Different lists can be safely executed.
            # e.g.
            #
            # [ [0], [1] ] - indicies 0 and 1 may be executed in parallel
            # [ [0, 1] [2] ] - indicies 0 and 1 must be executed sequentially.
            #                  Index 2 may be executed in parallel with either
            #                  0 or 1.
            'sequential_execution_indices': [],
            # Let clients know how we intend coverage to be merged.
            'coverage_merge_type': pargs.coverage_mode
        },
    }
    jobs = invocation_infos['jobs']
    sequential_execution_indices = invocation_infos['misc']['sequential_execution_indices']

    coverage_run_ii_template = {
        'command_line_arguments': [],
        'environment_variables': {},
        'ktest_file': '',
        'coverage_dir': '',
        'program': '',
        'misc' : {},
    }
    def get_coverage_run_ii():
        x = coverage_run_ii_template.copy()
        x['command_line_arguments'] = []
        x['environment_variables'] = {}
        x['misc'] = {}
        return x

    resultInfos = ResultInfo.loadResultInfos(pargs.result_info_file)
    coverage_dir_to_program_map = {} # For sanity checking
    coverage_dir_set = set() # For sanity checking
    for result_index, r in enumerate(resultInfos):
        _logger.info('Processing {}/{}'.format(result_index + 1, len(resultInfos)))

        result_ii = r.RawInvocationInfo

        # FIXME: This is fp-bench specific
        # Retrieve the native program
        augmented_spec_file_path = result_ii['misc']['augmented_spec_file']
        _logger.debug('Retrieved augmented spec file path "{}"'.format(augmented_spec_file_path))
        augmented_spec_file_path = replace_spec_path(augmented_spec_file_path)
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
        for test in test_cases:
            job_index = len(jobs) # The index of this job in the output invocation info
            if getattr(test, 'ktest_file', None) is None:
                _logger.error('Skipping test "{}"'.format(test))
                continue
            # Get a copy of the dictionary that we can safely mutate
            coverage_run_ii = get_coverage_run_ii()
            # Set the program
            coverage_run_ii['program'] = exe_path
            # Set the test case
            coverage_run_ii['ktest_file'] = test.ktest_file

            # FIXME: This is fp-bench specific
            # Set the augmented spec file path
            coverage_run_ii['misc']['augmented_spec_file'] = augmented_spec_file_path

            # Set the coverage_dir based on the mode
            if pargs.coverage_mode == 'global':
                # All runs will share the same coverage directory
                coverage_run_ii['coverage_dir'] = '@global_work_dir@/coverage_dir'
                # All runs must be sequential.
                if len(sequential_execution_indices) == 0:
                    sequential_execution_indices.append([job_index])
                else:
                    sequential_execution_indices[0].append(job_index)
            elif pargs.coverage_mode == 'program':
                # Come up with a unique name for the coverage directory for this
                # program
                program_coverage_dir = '@global_work_dir@/coverage_dir/{}'.format(
                    exe_name)
                # Sanity check: Check that we are never using `program_coverage_dir`
                # for the wrong program
                if program_coverage_dir not in coverage_dir_to_program_map:
                    coverage_dir_to_program_map[program_coverage_dir] = exe_path
                    sequential_execution_indices.append([job_index])
                else:
                    if coverage_dir_to_program_map[program_coverage_dir] != exe_path:
                        raise Exception('Should never happen!')
                    # Make sure that we explicitly state that it is not safe to run
                    # invocations that share the same program_coverage_dir in parallel.
                    sequential_execution_indices[-1].append(job_index)
                coverage_run_ii['coverage_dir'] = program_coverage_dir
                pass
            elif pargs.coverage_mode == 'testcase':
                assert isinstance(test.identifier, int)
                coverage_dir = '@global_work_dir@/coverage_dir/{}/{}'.format(
                    exe_name,
                    test.identifier)
                # Sanity check
                if coverage_dir in coverage_dir_set:
                    raise Exception('Should never happen')
                coverage_dir_set.add(coverage_dir)
                coverage_run_ii['coverage_dir'] = coverage_dir
                # All jobs are independent so can run in parallel
                sequential_execution_indices.append([job_index])
            else:
                raise Exception('Unhandled coverage_mode "{}"'.format(pargs.coverage_mode))

            jobs.append(coverage_run_ii)

    # Sanity check: Check sequential_execution_indices doesn't accidently
    # repeat values
    used_indices_set = set()
    for l in sequential_execution_indices:
        for i in l:
            if i in used_indices_set:
                raise Exception('Should never happen')
            used_indices_set.add(i)

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

if __name__ == '__main__':
    sys.exit(main(sys.argv))
