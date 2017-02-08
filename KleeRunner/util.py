# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import logging
import yaml

_logger = logging.getLogger(__name__)

if hasattr(yaml, 'CLoader'):
    # Use libyaml which is faster
    _loader = yaml.CLoader
else:
    _loader = yaml.Loader


def loadYaml(openFile):
    return yaml.load(openFile, Loader=_loader)

def writeYaml(openFile, data):
    _logger.info('Writing "{}"'.format(openFile.name))
    as_yaml = yaml.dump(data, default_flow_style=False)
    openFile.write(as_yaml)
    return
