"""PGSync transform."""
import logging
from typing import Optional

from .constants import (  # noqa
    CONCAT_TRANSFORM,
    RENAME_TRANSFORM,
    REPLACE_TRANSFORM,
)

logger = logging.getLogger(__name__)


class Transform(object):
    """Transform is really a builtin plugin"""

    @classmethod
    def rename(
        cls, data: dict, nodes: dict, result: Optional[dict] = None
    ) -> dict:
        """Rename keys in a nested dictionary based on transform_node.
        "rename": {
            "id": "publisher_id",
            "name": "publisher_name"
        },
        """
        result: dict = result or {}
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(nodes.get(key), str):
                    key = nodes[key]
                elif isinstance(value, dict):
                    if key in nodes:
                        value = cls.rename(value, nodes[key])
                elif (
                    isinstance(value, list)
                    and value
                    and not isinstance(
                        value[0],
                        dict,
                    )
                ):
                    try:
                        value = sorted(value)
                    except TypeError:
                        pass
                elif key in nodes.keys():
                    if isinstance(value, list):
                        value = [cls.rename(v, nodes[key]) for v in value]
                    elif isinstance(value, (str, int, float)):
                        if nodes[key]:
                            key = str(nodes[key])
                result[key] = value
        return result

    @classmethod
    def concat(
        cls, data: dict, nodes: dict, result: Optional[dict] = None
    ) -> dict:
        """Concatenate column values into a new field
        {
            "columns": ["publisher_id", "publisher_name", "is_active", "foo"],
            "destination": "new_field",
            "delimiter": "-"
        },
        """
        result: dict = result or {}
        if isinstance(nodes, list):
            for node in nodes:
                cls.concat(data, node, result=result)

        if isinstance(data, dict):
            if "columns" in nodes:
                values: list = [data.get(key, key) for key in nodes["columns"]]
                delimiter: str = nodes.get("delimiter", "")
                destination: str = nodes["destination"]
                data[destination] = f"{delimiter}".join(
                    map(str, filter(None, values))
                )
            for key, value in data.items():
                if key in nodes:
                    if isinstance(value, dict):
                        value = cls.concat(value, nodes[key])
                    elif isinstance(value, list):
                        value = [
                            cls.concat(v, nodes[key])
                            for v in value
                            if key in nodes
                        ]
                result[key] = value
        return result

    """
    @classmethod
    def replace(
        cls, data: dict, nodes: dict, result: Optional[dict] = None
    ) -> dict:
        # TODO!
        Replace field where value is
        "replace": {
            "code": {
                "-": "="
            }
        }
        result_dict = result_dict or {}
        if isinstance(data, dict):
            if nodes:
                for key, values in nodes.items():
                    if key not in data:
                        continue
                    if isinstance(data[key], list):
                        for k in values:
                            for search, replace in values[k].items():
                                data[key] = [
                                    x.replace(search, replace)
                                    for x in data[key]
                                ]
                    else:
                        for search, replace in values.items():
                            data[key] = data[key].replace(search, replace)

            for key, value in data.items():
                if isinstance(value, dict):
                    value = cls.replace(value, nodes.get(key))
                elif isinstance(value, list):
                    value = [
                        cls.replace(v, nodes[key])
                        for v in value
                        if key in nodes
                    ]
                result_dict[key] = value
        return result_dict
    """

    @classmethod
    def transform(cls, data: dict, nodes: dict):
        data = cls.rename(data, cls.get(nodes, RENAME_TRANSFORM))
        data = cls.concat(data, cls.get(nodes, CONCAT_TRANSFORM))
        # data = cls.replace(data, cls.get(nodes, REPLACE_TRANSFORM))
        return data

    @classmethod
    def get(cls, nodes: dict, type_: str) -> dict:
        transform_node: dict = {}
        if "transform" in nodes.keys():
            if type_ in nodes["transform"]:
                transform_node = nodes["transform"][type_]
        for child in nodes.get("children", {}):
            node: dict = cls.get(child, type_)
            if node:
                transform_node[child.get("label", child["table"])] = node
        return transform_node


def get_private_keys(primary_keys):
    """Get private keys entry from a nested dict."""

    def squash_list(values, _values=None):
        if not _values:
            _values = []
        if isinstance(values, dict):
            if len(values) == 1:
                _values.append(values)
            else:
                for key, value in values.items():
                    _values.extend(squash_list({key: value}))
        elif isinstance(values, list):
            for value in values:
                _values.extend(squash_list(value))
        return _values

    target = []
    for values in squash_list(primary_keys):
        if len(values) > 1:
            for key, value in values.items():
                target.append({key: value})
            continue
        target.append(values)

    target3 = []
    for values in target:
        for key, value in values.items():
            if isinstance(value, dict):
                target3.append({key: value})
            elif isinstance(value, list):
                _value = {}
                for v in value:
                    for _k, _v in v.items():
                        _value.setdefault(_k, [])
                        if isinstance(_v, list):
                            _value[_k].extend(_v)
                        else:
                            _value[_k].append(_v)
                target3.append({key: _value})

    target4 = {}
    for values in target3:
        for key, value in values.items():
            if key not in target4:
                target4[key] = {}
            for k, v in value.items():
                if k not in target4[key]:
                    target4[key][k] = []
                if isinstance(v, list):
                    for _v in v:
                        if _v not in target4[key][k]:
                            target4[key][k].append(_v)
                    target4[key][k] = target4[key][k]
                else:
                    if v not in target4[key][k]:
                        target4[key][k].append(v)
            target4[key][k] = sorted(target4[key][k])
    return target4
