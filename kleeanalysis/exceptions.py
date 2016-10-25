"""
The exceptions module contains all kleeanalysis exceptions
"""

class Error(Exception):
    """
    Base class for exceptions in this module.
    """
    pass

class InputError(Error):
    """
    Exception raised for errors in the input.
    """

    def __init__(self, message):
        Error.__init__(self, message)
