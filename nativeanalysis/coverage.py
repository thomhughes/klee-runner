# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import logging
import pprint
import re

_logger = logging.getLogger(__name__)

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

def load_raw_coverage_xml(path_to_xml_file):
    return ET.parse(path_to_xml_file)

def raw_coverage_xml_to_branch_cov_set(path_to_xml_file):
    raw_data = load_raw_coverage_xml(path_to_xml_file)
    root = raw_data.getroot()
    # Overall branch coverage
    branch_cov = root.get('branch-rate')

    # FIXME: There's a problem here. We don't have unique identifiers
    # for branch targets so we can't distinguish when different targets are
    # covered but give the same number of covered branch targets.
    # Now walk data structure building up set of tuples
    # (<file name>, <line>, <num branch targets>, <covered branch target number>)
    bcs = set()
    RE_COND_COV= re.compile(r'^\d+%\s+\((\d+)/(\d+)\)$')

    packages = raw_data.findall('packages')
    assert len(packages) == 1
    packages = packages[0]
    # I think packages correspond to object files
    for package in packages.findall('package'):
        name = package.get('name')
        _logger.debug('Loading coverage data from package "{}"'.format(name))
        # I think "classes" correspond to source files
        classes = package.findall('classes')
        assert len(classes) == 1
        classes = classes[0]
        for cl in classes.findall('class'):
            filename = cl.get('filename')
            _logger.debug('Loading coverage info for file "{}"'.format(filename))

            lines = cl.findall('lines')
            assert len(lines) == 1
            lines = lines[0]
            # Now loop over lines
            for line in lines.findall('line'):
                if line.get('branch') == "true":
                    line_num = int(line.get('number'))
                    _logger.debug('Adding cov for {}:{}'.format(filename, line_num))
                    condition_cov_str = line.get('condition-coverage')
                    # Parse out the number of targets and how many were covered
                    m = RE_COND_COV.match(condition_cov_str)
                    assert m is not None
                    num_targets_covered = int(m.group(1))
                    num_targets = int(m.group(2))
                    assert num_targets >= 2
                    _logger.debug('Covered branches {}/{}'.format(
                        num_targets_covered,
                        num_targets))
                    for target_num in range(1, num_targets_covered + 1):
                        tup = (filename, line_num, num_targets, target_num)
                        _logger.debug('Add tupple:\n{}'.format(
                            pprint.pformat(tup)))
                        bcs.add(tup)

    return bcs
