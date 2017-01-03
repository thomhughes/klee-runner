#!/usr/bin/env python
# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import logging

_logger = logging.getLogger(__name__)

def get_result_info_key(ri):
    return ri['invocation_info']['program']

def group_result_infos_by(result_infos_list, key_fn=get_result_info_key):
    """
    Given a list of raw `ResultInfos` group them by `key_fn`. `key_fn` should be a
    function that takes a raw `ResultInfo` and returns a unique identifier.

    Returns a tuple (key_to_result_infos, rejected_result_infos)

    `key_to_result_infos` is a dictionary mapping the key to a list of raw `ResultInfo`s
    where the index of the `ResultInfo` corresponds to the index in which it was found
    in `result_infos_list`.

    `rejected_result_infos` is a list containing rejected raw `ResultInfo`s.
    It maps the index of the raw `ResultInfos` (in `result_infos_list`) to
    a list of rejected raw `ResultInfo`s.
    """
    rejected_result_infos = [ ]
    assert(len(result_infos_list) > 1)

    key_to_result_infos = dict()
    number_of_result_infos = len(result_infos_list)

    defaultGroup = []
    for _ in range(0, number_of_result_infos):
        defaultGroup.append(None)
        rejected_result_infos.append([])
    assert(len(defaultGroup) == number_of_result_infos)
    assert(len(rejected_result_infos) == number_of_result_infos)

    for result_infos_index in range(0, number_of_result_infos):
        for r in result_infos_list[result_infos_index]['results']:
            key = key_fn(r)
            if key not in key_to_result_infos:
                key_to_result_infos[key] = defaultGroup.copy()
                _logger.debug('Added key "{}" = {}'.format(key, key_to_result_infos[key]))
            group_for_key = key_to_result_infos[key]
            if group_for_key[result_infos_index] is not None:
                _logger.error(
                    '"{}" cannot appear more than once in the same result infos (index {})'.format(
                    key, result_infos_index))
                _logger.debug('group_for_key: {}'.format(group_for_key))
                rejected_result_infos[result_infos_index].append(r)
                continue
            else:
                _logger.debug('Inserting at index {} for key "{}"'.format(result_infos_index, key))
                key_to_result_infos[key][result_infos_index] = r

    return (key_to_result_infos, rejected_result_infos)
