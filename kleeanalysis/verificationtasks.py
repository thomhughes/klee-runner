"""
Implementations for the various verification tasks.
"""
import logging
import os
import pprint

_logger = logging.getLogger(__name__)


def _fail_generator(spec: "A failure specification", failures: "An iterable list of failures", task_name):
    if failures is None:
        raise Exception("Hell")
    # FIXME: Handle missing counter example and exhaustive keyword
    allowed_failures = {}
    if "counter_examples" in spec:
        for cex in spec["counter_examples"]:
            for loc in cex["locations"]:
                if loc["file"] not in allowed_failures:
                    allowed_failures[loc["file"]] = set()
                allowed_failures[loc["file"]].add(int(loc["line"]))
    _logger.debug('Allowed failures for task {}: {}'.format(task_name, pprint.pformat(allowed_failures)))
    if spec["correct"] and len(allowed_failures) > 0:
        raise Exception("A failure that must not happen, but has counterexamples makes no sense")

    actual_failures = []
    for fail in failures:
      _logger.debug('Considering failure:\n{}\n'.format(fail))
      # The file path in failure is absolute (e.g. `/path/to/file.c`) where as the spec will have `file.c` so
      # we need to check if `/file.c` is a suffix of the error path.
      assert os.path.isabs(fail.error.file)
      allowed_failure_file = None
      for af in allowed_failures.keys():
        assert not af.startswith('/')
        suffix = '/{}'.format(af)
        if fail.error.file.endswith(suffix):
          allowed_failure_file = af
          break

      if allowed_failure_file is None:
        _logger.debug('"{}" is not in allowed failures. This is not a failure that the spec expects'.format(fail.error.file))
        actual_failures.append(fail)
        continue
      if fail.error.line not in allowed_failures[allowed_failure_file]:
        _logger.debug('"{}" is in allowed failures. But the error line for this failure ({}) is not expected by the spec ({}'.format(
          fail.error.file,
          fail.error.line,
          allowed_failures[fail.error.file]))
        actual_failures.append(fail)
        continue
      # Appears to be an allowed failure
      _logger.debug('{}:{} appears to be an allowed failure'.format(fail.error.file, fail.error.line))
    return actual_failures

TASKS = {
    "no_assert_fail": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.assertion_errors, task_name),
    "no_integer_division_by_zero": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.division_errors, task_name),
    "no_invalid_deref": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.ptr_errors, task_name),
    "no_invalid_free": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.free_errors, task_name),
    "no_overshift": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.overshift_errors, task_name),
    "no_reach_error_function": lambda spec, kleedir, task_name: _fail_generator(spec, kleedir.abort_errors, task_name)
}
