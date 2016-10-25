"""Represent KLEE working directories"""

import os
import logging

from .info import Info
from .test import Test
from ..exceptions import InputError

_logger = logging.getLogger(__name__)

class KleeDir:
    """A KLEE working directory"""

    def __init__(self, path: "Path to a KLEE working directory."):
        """
        Open a KLEE working directory.
        """
        _logger.debug('Creating KleeDir from "{}"'.format(path))
        self.path = path
        try:
            self.info = Info(os.path.join(path, "info"))
        except InputError:
            self.info = None
        if self.is_valid:
            self.tests = [Test(path, x) for x in range(1, self.info.tests+1)]
        else:
            self.tests = []
        with open(os.path.join(path, "messages.txt")) as file:
            self.messages = file.readlines()
        with open(os.path.join(path, "warnings.txt")) as file:
            self.warnings = file.readlines()

    @property
    def is_valid(self):
        """If the KLEE directory is in a valid state"""
        return self.info is not None and not self.info.empty

    @property
    def assertion_failures(self):
        """Returns all assertion failures"""
        return (test for test in self.tests if test.assertion is not None)

    @property
    def division_failures(self):
        """Returns all division failures"""
        return (test for test in self.tests if test.division is not None)

    @property
    def abortions(self):
        """Returns all abortions"""
        return (test for test in self.tests if test.abort is not None)

    @property
    def execution_errors(self):
        """Returns all execution failures"""
        return (test for test in self.tests if test.execution_error is not None)

    @property
    def free_errors(self):
        """Returns all execution failures"""
        return (test for test in self.tests if test.free is not None)

    @property
    def ptr_errors(self):
        """Returns all execution failures"""
        return (test for test in self.tests if test.ptr is not None)

    @property
    def overshifts(self):
        """Returns all execution failures"""
        return (test for test in self.tests if test.overshift is not None)

    @property
    def misc_errors(self):
        """Returns all uncategorized failures"""
        return (test for test in self.tests if test.misc_error is not None)
