"""Represent KLEE working directories"""
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import functools
import logging
from .kleedir import KleeDir

_logger = logging.getLogger(__name__)

class KleeDirProxy(KleeDir):
    """
    Wrapper around a regular KleeDir
    that has (mostly) same interface but
    represents multiple runs of KLEE.

    It is intended that these be multiple
    runs of KLEE on the same program under
    the same condition.
    """
    def __init__(self, klee_dir_list):
        _logger.debug('Creating KleeDirProxy from {}'.format(klee_dir_list))
        assert isinstance(klee_dir_list, list)
        self._real_klee_dirs = []

        # This isn't the same interface but hopefully clients don't depend on it
        self.path = klee_dir_list

        for klee_dir_path in klee_dir_list:
            _logger.debug('Trying to create KleeDir from "{}"'.format(klee_dir_path))
            klee_dir = KleeDir(klee_dir_path)
            self._real_klee_dirs.append(klee_dir)

        # Setup the tests which are a union of all the tests from
        # the real KleeDirs
        self.tests = []
        for kd in self._real_klee_dirs:
            self.tests.extend(kd.tests)

  # DL: Not the same interface. Does it matter?
    @property
    def info(self):
        return [kd.info for kd in self._real_klee_dirs]

  # DL: Not the same interface. Does it matter?
    @property
    def messages(self):
        return [kd.messages for kd in self._real_klee_dirs]

  # DL: Not the same interface. Does it matter?
    @property
    def warnings(self):
        return [kd.warnings for kd in self._real_klee_dirs]

    @property
    def lost_test_cases(self):
        """
          Return the sum of the number of lost test cases across
          all real KleeDirs.
        """
        values = [kd.lost_test_cases for kd in self._real_klee_dirs]
        return functools.reduce(lambda a,b: a+b, values)

    @property
    def halt_timer_invoked(self):
        # Return true if the halt time was invoked for any of the real KLEE dirs
        return any([kd.halt_timer_invoked for kd in self._real_klee_dirs])

    @property
    def is_valid(self):
        # Return true iff all real KLEE dirs are valid
        return all([kd.is_valid for kd in self._real_klee_dirs])
