# vim: set sw=4 ts=4 softtabstop=4 expandtab:
from collections import namedtuple
import logging
from .kleedir import KleeDir
from .verificationtasks import TASKS

_logger = logging.getLogger(__name__)

def get_yaml_load():
    """Acquires the yaml load function"""
    from yaml import load
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader
    return lambda file: load(file, Loader)
yaml_load = get_yaml_load()

VerificationFailure = namedtuple("VerificationFailure", ["task", "failures"])

def analyse_result(r):
    """
      Analyse a single result produced
      by klee-runner.

      TODO: return failures and also
      data structures relating to klee
      dir.
    """
    assert isinstance(r, dict) # FIXME: Don't use raw form
    # FIXME: Emit some sort of data structure representing the failure
    if r["exit_code"] is not None and r["exit_code"] != 0:
        _logger.warning("{} terminated with exit code {}".format(
            r["klee_dir"],
            r["exit_code"]))
        return False
    if r["out_of_memory"]:
        _logger.warning("{} killed due to running out of memory".format(
                r["klee_dir"]))
    if r["backend_timeout"]:
        _logger.warning("killed due to running out of alloted time".format(
            r["klee_dir"]))
        return False

    kleedir = KleeDir(r["klee_dir"])
    if not kleedir.is_valid:
        failure_found = True
        _logger.warning("{} is not valid".format(r["klee_dir"]))
        return False

    # FIXME: Factor this fp-bench specific stuff out
    failure_found = False
    augmentedSpecFilePath = None
    try:
        augmentedSpecFilePath = r["invocation_info"]["misc"]["augmented_spec_file"]
    except KeyError as e:
        _logger.error('Failed to find augmentedSpecFilePath key')
        raise e
    
    # FIXME: Use the fp-bench infrastructure to load the spec
    spec = None
    with open(augmentedSpecFilePath) as f:
        spec = yaml_load(f)
    failures = []
    misc_failures = list(kleedir.misc_errors)
    if len(misc_failures) > 0:
        failures.append(VerificationFailure("no_misc_failures", misc_failures))
    for name, task in TASKS.items():
        task_failures = list(task(spec["verification_tasks"][name], kleedir))
        if len(task_failures) > 0:
            failures.append(VerificationFailure(name, task_failures))

    # FIXME: Don't print this stuff. Emit it as a data structure instead
    if len(failures) > 0:
        failure_found = True
        print(kleedir.path, ":", sep="")
        for fail_task in failures:
            print("  Verification failures for task ", fail_task.task, ":", sep="")
            for fail in fail_task.failures:
                print("    Test {:06} in {}:{}".format(fail.identifier, fail.error.file, fail.error.line))

    return not failure_found
