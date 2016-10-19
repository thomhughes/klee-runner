# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import os
import sys


def add_svcb_to_module_search_path():
    """
      Add the directory containing the ``svcb`` module directory into the
      search path so that tools can import svcb
    """
    repoRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    additionalPath = os.path.join(
        repoRoot, 'external_deps', 'fp-bench', 'svcb')
    sys.path.append(additionalPath)
