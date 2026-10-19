#!/usr/bin/env python3
"""
A small JSON Schema validator, standard library only.

    python3 scripts/schema_check.py <schema.json> <document.json> [<document.json> …]

The harness has no dependencies (ADR 0002), so it cannot use the `jsonschema` package. This
implements the subset of JSON Schema draft 2020-12 that the evaluation schemas use
(`evals/schema/*.schema.json`), and it refuses a schema that uses anything else: an unknown keyword
silently ignored is a rule that silently does not run.

Supported: `$schema`, `$id`, `$comment`, `title`, `description`, `examples`, `default`, `$defs`,
`$ref` (local `#/...` pointers), `type`, `enum`, `const`, `required`, `properties`,
`additionalProperties`, `patternProperties`, `propertyNames`, `items`, `minItems`, `uniqueItems`,
`minLength`, `pattern`, `minimum`, `maximum`, `allOf`, `anyOf`, `oneOf`, `not`, `if`/`then`/`else`.

Exit: 0 = every document is valid · 1 = some are not, or the schema uses an unsupported keyword.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples", "default", "$defs"}
VALIDATORS = {"$ref", "type", "enum", "const", "required", "properties", "additionalProperties", "patternProperties",
              "propertyNames", "items", "minItems", "uniqueItems", "minLength", "pattern", "minimum", "maximum",
              "allOf", "anyOf", "oneOf", "not", "if", "then", "else"}
TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


class SchemaError(ValueError):
    """The schema itself is wrong (not the document)."""


def unsupported(schema, path: str = "#") -> list[str]:
    """Keywords this validator does not implement, wherever they appear in the schema."""
    out = []
    if isinstance(schema, dict):
        for k, v in schema.items():
            if k not in ANNOTATIONS | VALIDATORS:
                out.append(f"{path}: unsupported keyword `{k}`")
            if k in ("properties", "patternProperties", "$defs") and isinstance(v, dict):
                for name, sub in v.items():
                    out += unsupported(sub, f"{path}/{k}/{name}")
            elif k in ("allOf", "anyOf", "oneOf") and isinstance(v, list):
                for i, sub in enumerate(v):
                    out += unsupported(sub, f"{path}/{k}/{i}")
            elif k in ("items", "additionalProperties", "propertyNames", "not", "if", "then", "else") and isinstance(v, dict):
                out += unsupported(v, f"{path}/{k}")
    return out


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    t = TYPES.get(name)
    if t is None:
        raise SchemaError(f"unknown type `{name}`")
    return isinstance(value, t)


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local `$ref`s are supported, got `{ref}`")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"`$ref` {ref} points to nothing")
        node = node[part]
    return node


def validate(value, schema, root: dict | None = None, path: str = "$") -> list[str]:
    """Every error, as `<json path>: <what is wrong>`. Empty = valid."""
    root = root if root is not None else schema
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [f"{path}: not allowed here"]
    errs: list[str] = []
    if "$ref" in schema:
        errs += validate(value, _resolve(root, schema["$ref"]), root, path)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, n) for n in names):
            return errs + [f"{path}: expected {' or '.join(names)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {json.dumps(value, ensure_ascii=False)[:60]} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must be {json.dumps(schema['const'], ensure_ascii=False)}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value[:60]!r} does not match /{schema['pattern']}/")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: above the maximum {schema['maximum']}")
    if isinstance(value, dict):
        for k in schema.get("required") or []:
            if k not in value:
                errs.append(f"{path}: missing `{k}`")
        props = schema.get("properties") or {}
        patterns = schema.get("patternProperties") or {}
        for k, v in value.items():
            if "propertyNames" in schema:
                errs += [e.replace(f"{path}/@key", f"{path}: key {k!r}") for e in validate(k, schema["propertyNames"], root, f"{path}/@key")]
            matched = False
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
                matched = True
            for pat, sub in patterns.items():
                if re.search(pat, k):
                    errs += validate(v, sub, root, f"{path}.{k}")
                    matched = True
            if not matched and "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    errs.append(f"{path}: unknown key `{k}`")
                elif isinstance(extra, dict):
                    errs += validate(v, extra, root, f"{path}.{k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(x, sort_keys=True) for x in value]
            if len(set(seen)) != len(seen):
                errs.append(f"{path}: items are not unique")
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(value):
                errs += validate(v, schema["items"], root, f"{path}[{i}]")
    for sub in schema.get("allOf") or []:
        errs += validate(value, sub, root, path)
    if "anyOf" in schema and not any(not validate(value, s, root, path) for s in schema["anyOf"]):
        errs.append(f"{path}: matches none of the allowed shapes (anyOf)")
    if "oneOf" in schema:
        ok = sum(1 for s in schema["oneOf"] if not validate(value, s, root, path))
        if ok != 1:
            errs.append(f"{path}: matches {ok} of the shapes, exactly one is required (oneOf)")
    if "not" in schema and not validate(value, schema["not"], root, path):
        errs.append(f"{path}: matches a shape that is not allowed (not)")
    if "if" in schema:
        branch = schema.get("then") if not validate(value, schema["if"], root, path) else schema.get("else")
        if branch is not None:
            errs += validate(value, branch, root, path)
    return errs


def check_file(schema_path: Path, doc_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bad = unsupported(schema)
    if bad:
        raise SchemaError("; ".join(bad))
    return validate(json.loads(doc_path.read_text(encoding="utf-8")), schema)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    schema_path = Path(argv[0])
    rc = 0
    for doc in argv[1:]:
        try:
            errs = check_file(schema_path, Path(doc))
        except (SchemaError, ValueError) as e:
            print(f"✗ {doc}: {e}")
            return 1
        for e in errs:
            print(f"✗ {doc} {e}")
        if errs:
            rc = 1
        else:
            print(f"✓ {doc}")
    return rc


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
