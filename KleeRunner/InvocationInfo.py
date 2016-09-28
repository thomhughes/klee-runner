# Copyright (c) 2016, Daniel Liew
# This file is covered by the license in LICENSE
from . import util
import collections
import copy
import os
import pprint
import yaml
import jsonschema

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

  def GetInternalRepr(self):
    return self._data

class InvocationInfoValidationError(Exception):
  def __init__(self, message, absoluteSchemaPath=None):
    assert isinstance(message, str)
    if absoluteSchemaPath != None:
      assert isinstance(absoluteSchemaPath, collections.deque)
    self.message = message
    self.absoluteSchemaPath = absoluteSchemaPath

  def __str__(self):
    return self.message

def loadInvocationInfos(openFile):
  invocationInfos = util.loadYaml(openFile)
  validateInvocationInfos(invocationInfo)
  invocationInfoObjects = []
  for job in invocationInfos['jobs']:
    invocationInfoObjects.append(InvocationInfo(job))
  return invocationInfoObjects

def getSchema():
  """
    Return the Schema for InvocationInfo files.
  """
  yamlFile = os.path.join(os.path.dirname(__file__), 'InvocationInfoSchema.yml')
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
  if schema == None:
    schema = getSchema()
  assert isinstance(schema, dict)
  assert '__version__' in schema

  # Even though the schema validates this field in the invocationInfo we need to
  # check them ourselves first because if the schema version we have doesn't
  # match then we can't validate using it.
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
    raise Exception('Cannot downgrade benchmark specification to older schema')

  # TODO: Implement upgrade if we introduce new schema versions
  # We would implement various upgrade functions (e.g. ``upgrade_0_to_1()``, ``upgrade_1_to_2()``)
  # and call them successively until the ``invocationInfo`` has been upgraded to the correct version.
  raise NotImplementedException()

def upgradeBenchmarkSpecificationToSchema(invocationInfos, schema=None):
  """
    Upgrade a ``invocationInfo`` to the specified ``schema``.
    The resulting ``invocationInfo`` is validated against that schema.
  """
  if schema == None:
    schema = getSchema()
  assert '__version__' in schema
  assert 'schema_version' in invocationInfos

  newInvocationInfos = upgradeInvocationInfosToVersion(
      invocationInfos,
      schema['__version__']
  )

  # Check the upgraded benchmark spec against the schema
  validateInvocationInfos(newInvocationInfos, schema=schema)
  return newInvocationInfos
