# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import collections
import copy
import os
import jsonschema
import logging
from . import util

_logger = logging.getLogger(__name__)

class InvocationInfo:

    def __init__(self, data):
        assert isinstance(data, dict)
        self._data = data

        # Add implicitly empty fields
        if 'misc' not in self._data:
            self._data['misc'] = {}
        if 'extra_klee_arguments' not in self._data:
            self._data['extra_klee_arguments'] = []
        if 'ktest_file' not in self._data:
            self._data['ktest_file'] = None
        if 'coverage_dir' not in self._data:
            self._data['coverage_dir'] = None
        if 'attach_gdb' not in self._data:
            self._data['attach_gdb'] = False

    @property
    def Program(self):
        return self._data['program']

    @property
    def CommandLineArguments(self):
        return self._data['command_line_arguments']

    @property
    def EnvironmentVariables(self):
        return self._data['environment_variables']

    @property
    def ExtraKleeCommandLineArguments(self):
        return self._data['extra_klee_arguments']

    @property
    def KTestFile(self):
        return self._data['ktest_file']

    @property
    def CoverageDir(self):
        return self._data['coverage_dir']

    @property
    def AttachGDB(self):
        return self._data['attach_gdb']

    def GetInternalRepr(self):
        return self._data


class InvocationInfoValidationError(Exception):

    def __init__(self, message, absoluteSchemaPath=None):
        # pylint: disable=super-init-not-called
        assert isinstance(message, str)
        if absoluteSchemaPath != None:
            assert isinstance(absoluteSchemaPath, collections.deque)
        self.message = message
        self.absoluteSchemaPath = absoluteSchemaPath

    def __str__(self):
        return self.message


def loadInvocationInfos(openFile, auto_upgrade=True):
    invocationInfos = loadRawInvocationInfos(openFile, auto_upgrade=auto_upgrade)
    invocationInfoObjects = []
    for job in invocationInfos['jobs']:
        invocationInfoObjects.append(InvocationInfo(job))

    misc_data = None
    if 'misc' in invocationInfos:
        misc_data = invocationInfos['misc']
    return invocationInfoObjects, misc_data


def loadRawInvocationInfos(openFile, auto_upgrade=True):
    invocationInfos = util.loadYaml(openFile)
    if auto_upgrade:
        invocationInfos = upgradeBenchmarkSpecificationToSchema(invocationInfos)
    validateInvocationInfos(invocationInfos)
    return invocationInfos


def getSchema():
    """
      Return the Schema for InvocationInfo files.
    """
    yamlFile = os.path.join(os.path.dirname(__file__),
                            'InvocationInfoSchema.yml')
    schema = None
    with open(yamlFile, 'r') as f:
        schema = util.loadYaml(f)
    assert isinstance(schema, dict)
    assert '__version__' in schema
    return schema


def validateInvocationInfos(invocationInfo, schema=None):
    """
      Validate a ``invocationInfo`` file.
      Will throw a ``InvocationInfoValidationError`` exception if
      something is wrong
    """
    assert isinstance(invocationInfo, dict)
    if schema is None:
        schema = getSchema()
    assert isinstance(schema, dict)
    assert '__version__' in schema

    # Even though the schema validates this field in the invocationInfo we need
    # to check them ourselves first because if the schema version we have
    # doesn't match then we can't validate using it.
    if 'schema_version' not in invocationInfo:
        raise InvocationInfoValidationError(
            "'schema_version' is missing")
    if not isinstance(invocationInfo['schema_version'], int):
        raise InvocationInfoValidationError(
            "'schema_version' should map to an integer")
    if not invocationInfo['schema_version'] >= 0:
        raise InvocationInfoValidationError(
            "'schema_version' should map to an integer >= 0")
    if invocationInfo['schema_version'] != schema['__version__']:
        # pylint: disable=bad-continuation
        raise InvocationInfoValidationError(
            ('Schema version used by benchmark ({}) does not match' +
             ' the currently support schema ({})').format(
                invocationInfo['schema_version'],
                schema['__version__']))

    # Validate against the schema
    try:
        jsonschema.validate(invocationInfo, schema)
    except jsonschema.exceptions.ValidationError as e:
        raise InvocationInfoValidationError(
            str(e),
            e.absolute_schema_path)
    return


def upgradeInvocationInfosToVersion(invocationInfo, schemaVersion):
    """
      Upgrade invocation info to a particular schemaVersion. This
      does not validate it against the schema.

      This returns a new dict and does not modify the original
      `invocationInfo`.
    """
    assert isinstance(invocationInfo, dict)
    assert isinstance(schemaVersion, int)
    schemaVersionUsedByInstance = invocationInfo['schema_version']
    assert isinstance(schemaVersionUsedByInstance, int)
    assert schemaVersionUsedByInstance >= 0
    assert schemaVersion >= 0
    newInvocationInfo = copy.deepcopy(invocationInfo)

    if schemaVersionUsedByInstance == schemaVersion:
        # Nothing todo
        return newInvocationInfo
    elif schemaVersionUsedByInstance > schemaVersion:
        raise Exception(
            'Cannot downgrade benchmark specification to older schema')

    # Handle upgrading from 0 to 1
    if schemaVersionUsedByInstance == 0:
        newInvocationInfo = upgrade_0_to_1(newInvocationInfo)
        schemaVersionUsedByInstance = newInvocationInfo['schema_version']

    if schemaVersionUsedByInstance == schemaVersion:
        # Done
        return newInvocationInfo

    # TODO: Implement upgrade if we introduce new schema versions
    # We would implement various upgrade functions (e.g. ``upgrade_0_to_1()``,
    # ``upgrade_1_to_2()``) and call them successively until the
    # ``invocationInfo`` has been upgraded to the correct version.
    raise NotImplementedError("Schema upgrade not implemented. Want {} but have {}".format(
        schemaVersion,
        schemaVersionUsedByInstance))


def upgradeBenchmarkSpecificationToSchema(invocationInfos, schema=None):
    """
      Upgrade a ``invocationInfo`` to the specified ``schema``.
    """
    if schema is None:
        schema = getSchema()
    assert '__version__' in schema
    assert 'schema_version' in invocationInfos

    newInvocationInfos = upgradeInvocationInfosToVersion(
        invocationInfos,
        schema['__version__']
    )

    return newInvocationInfos

# Upgrade functions

def upgrade_0_to_1(invocationInfo):
    _logger.info('Upgrading InvocationInfo schema from version 0 to 1')
    # Only new fields were added
    invocationInfo['schema_version'] = 1
    return invocationInfo

