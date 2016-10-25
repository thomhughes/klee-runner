"""KLEE test cases"""

import os
import re
import glob
import logging
from collections import namedtuple
from ..exceptions import InputError

_logger = logging.getLogger(__name__)

def _force_match(regex, line, message, path):
    match = regex.fullmatch(line)
    if not match:
        raise InputError(message.format(path))
    return match

Early = namedtuple("Early", ["message"])
def _parse_early(path):
    """Load a .early file"""
    try:
        with open(path) as file:
            return Early(file.readlines())
    except FileNotFoundError:
        return None

ErrorFile = namedtuple("ErrorFile", ["message", "file", "line", "assembly_line", "stack"])

_RE_ERROR = re.compile(r"Error: (.*)\r?\n")
_RE_FILE = re.compile(r"File: (.*)\r?\n")
_RE_LINE = re.compile(r"Line: (\d+)\r?\n")
_RE_ASSEMBLY_LINE = re.compile(r"assembly.ll line: (\d+)\r?\n")

def _parse_error(path):
    try:
        with open(path) as file:
            match = _force_match(_RE_ERROR, file.readline(), "{}: Invalid error message in line 1", path)
            message = match.group(1)
            match = _force_match(_RE_FILE, file.readline(), "{}: Invalid file in line 2", path)
            filename = match.group(1)
            match = _force_match(_RE_LINE, file.readline(), "{}: Invalid line number in line 3", path)
            line = int(match.group(1))
            match = _force_match(_RE_ASSEMBLY_LINE, file.readline(), "{}: Invalid assembly.ll line number in line 4", path)
            assline = int(match.group(1))
            if file.readline().rstrip() != "Stack:":
                raise InputError("{}: Invalid begin stacktrace stack in line 5".format(path))
            stack = file.readlines()
            return ErrorFile(message, filename, line, assline, stack)
    except FileNotFoundError:
        return None

class Test:
    """
    A KLEE test case

    Attributes:
        early -- early termination info (None if it did not happen)
        error -- execution error info (None if it did not happen)
        abort -- abortion error info (None if it did not happen)
        assertion -- assertion error info (None if it did not happen)
        division -- division error info (None if it did not happen)
    """

    def __init__(self, path: "path to the klee working directory", identifier: "numeric identifier"):
      # pylint: disable=too-many-branches
        """Load a KLEE test case"""
        self.identifier = identifier
        self.__pathstub = os.path.join(path, "test{:06}".format(self.identifier))
        _logger.debug('Creating test with pathstub "{}"'.format(self.__pathstub))
        self.early = _parse_early(self.__pathstub + ".early")
        self.error = None
        self.execution_error = None
        self.abort = None
        self.division = None
        self.assertion = None
        self.free = None
        self.ptr = None
        self.overshift = None
        self.readonly_error = None
        self.user_error = None
        self.overflow = None
        self.misc_error = None
        error = glob.glob(glob.escape(self.__pathstub) + ".*.err")
        if len(error) > 1:
            raise Exception("Only one error case per path?!")
        if len(error) == 1:
            error = error[0]
            self.error = _parse_error(error)
            error = error[:-4]
            error = error[error.rfind(".")+1:]
            if error == "exec":
                self.execution_error = self.error
            elif error == "abort":
                self.abort = self.error
            elif error == "div":
                self.division = self.error
            elif error == "assert":
                self.assertion = self.error
            elif error == "free":
                self.free = self.error
            elif error == "ptr":
                self.ptr = self.error
            elif error == "overshift":
                self.overshift = self.error
            elif error == "readonly":
                self.readonly_error = self.error
            elif error == "user":
                self.user_error = self.error
            elif error == "overflow":
                self.overflow = self.error
            else:
                self.misc_error = self.error

    @property
    def ktest_path(self):
        """Path to the matching .ktest file"""
        return self.__pathstub + ".ktest"

    @property
    def pc_path(self):
        """Path to the matching .pc file"""
        return self.__pathstub + ".pc"
