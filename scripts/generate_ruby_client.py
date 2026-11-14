"""Generate the Ruby worker's typed API client from the Python API contract.

The Python FastAPI application is the only authority. This script never edits it; it reads it:

1. exports ``app.openapi()`` from a hermetic child process (scrubbed environment, temporary
   working directory, local storage only, so no database, network, or repository file is touched),
2. prunes that document to the operations the non-authoritative Ruby worker may call, keeping only
   semantic keys, and writes it to ``apps/ruby_worker/contract/openapi.json``,
3. renders ``apps/ruby_worker/lib/goblin_workflow/generated/api_v1.rb`` (enums, response and
   request models, and one operation descriptor per allowed endpoint) from that pruned contract.

``--check`` regenerates both files in memory and exits non-zero when either committed file differs,
so a Python API change cannot ship without a reviewed regeneration. Never hand-edit either file.

Usage (repository root, in the API environment):

    python scripts/generate_ruby_client.py           # rewrite both files
    python scripts/generate_ruby_client.py --check   # fail on drift (CI / release)
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
RUBY_WORKER = ROOT / "apps" / "ruby_worker"
SNAPSHOT_PATH = RUBY_WORKER / "contract" / "openapi.json"
GENERATED_PATH = RUBY_WORKER / "lib" / "goblin_workflow" / "generated" / "api_v1.rb"
GENERATOR_NAME = "scripts/generate_ruby_client.py"

# The worker is non-authoritative, so its client is an explicit allowlist, never "every route".
# Keys are the Ruby operation names; values are the (HTTP method, path) pair in the Python
# contract. Deliberately absent: PATCH /v1/runtime/control (mutates runtime authority), the SSE
# stream, learning-consent withdrawal, compute-node routes, and the public rate-limit route.
OPERATIONS: dict[str, tuple[str, str]] = {
    "action_execute": ("POST", "/v1/actions"),
    "cognition_cancel": ("POST", "/v1/cognition/{request_id}/cancel"),
    "cognition_run": ("POST", "/v1/cognition"),
    "cognition_trace": ("GET", "/v1/cognition/{request_id}/trace"),
    "grounding_record": ("POST", "/v1/grounding"),
    "learning_label": ("POST", "/v1/cognition/{request_id}/learning-label"),
    "rag_ingest": ("POST", "/v1/rag/documents"),
    "rag_search": ("POST", "/v1/rag/search"),
    "runtime_health": ("GET", "/v1/runtime/health"),
    "runtime_incidents": ("GET", "/v1/runtime/incidents"),
    "runtime_release_evidence": ("GET", "/v1/runtime/release-evidence"),
    "runtime_release_evidence_publish": ("POST", "/v1/runtime/release-evidence"),
    "runtime_provider_metrics": ("GET", "/v1/runtime/provider-metrics"),
    "workflow_inbox": ("POST", "/v1/workflow/inbox"),
}

# Keys that carry prose or presentation, not shape. Dropping them keeps the snapshot stable across
# FastAPI/pydantic releases (the repository pins only lower bounds) and across docstring edits.
NON_SEMANTIC_KEYS = frozenset({"title", "description", "examples", "example", "summary"})
# Values under these keys are data, not schemas, so they are copied verbatim.
OPAQUE_KEYS = frozenset({"default", "const", "enum"})
# Schema keywords the Ruby runtime does not model. Meeting one is an error, not a silent `any`.
UNSUPPORTED_KEYWORDS = frozenset(
    {"oneOf", "not", "if", "then", "else", "prefixItems", "patternProperties", "discriminator"}
)
CONSTRAINT_KEYS = (
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
)
PRIMITIVES = frozenset({"string", "integer", "number", "boolean"})
PASSTHROUGH_ENV = (
    "PATH",
    "SYSTEMROOT",
    "SystemRoot",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
)

_EXPORT_SNIPPET = """
import json, sys
sys.path.insert(0, sys.argv[1])
from dual_lineage.main import app
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(app.openapi(), handle)
"""


class GeneratorError(RuntimeError):
    """The contract cannot be represented faithfully; fix the generator deliberately."""


# --------------------------------------------------------------------------------------------
# Export and prune
# --------------------------------------------------------------------------------------------


def export_openapi() -> dict[str, Any]:
    """Return ``app.openapi()`` from a hermetic child process.

    The app selects PostgreSQL stores from ``DATABASE_URL`` even in local mode and writes local
    state relative to the working directory, so the child gets an allowlisted environment and a
    temporary working directory. Doing this in-process would poison a pytest session.
    """
    with tempfile.TemporaryDirectory(prefix="ruby-client-export-") as scratch:
        output = Path(scratch) / "openapi.json"
        env = {name: os.environ[name] for name in PASSTHROUGH_ENV if name in os.environ}
        env["DUAL_LINEAGE_DATABASE_MODE"] = "local"
        env["DUAL_LINEAGE_RAG_DB"] = str(Path(scratch) / "rag.sqlite3")
        # Contract export only imports the API; it never calls this loopback client.
        # Ruby is the sole RAG owner, so give the mandatory client harmless local settings.
        env["DUAL_LINEAGE_RAG_URL"] = "http://127.0.0.1:8102"
        env["DUAL_LINEAGE_RAG_SERVICE_TOKEN"] = "contract-export-only"
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _EXPORT_SNIPPET, str(API_SRC), str(output)],
            cwd=scratch,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise GeneratorError(
                "could not import the Python API to export its contract:\n"
                + completed.stderr.strip()[-2000:]
            )
        loaded: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
        return loaded


def strip_non_semantic(node: Any) -> Any:
    if isinstance(node, list):
        return [strip_non_semantic(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in NON_SEMANTIC_KEYS:
            continue
        if key in OPAQUE_KEYS:
            cleaned[key] = value
        elif key == "properties" and isinstance(value, dict):
            # Property *names* such as "title" must survive; only their schemas are cleaned.
            cleaned[key] = {name: strip_non_semantic(sub) for name, sub in value.items()}
        else:
            cleaned[key] = strip_non_semantic(value)
    return cleaned


def _collect_refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.add(ref.rsplit("/", 1)[-1])
        for value in node.values():
            _collect_refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_refs(value, found)


def prune(spec: dict[str, Any]) -> dict[str, Any]:
    """Reduce the full contract to the allowed operations and the schemas they reach."""
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    paths: dict[str, Any] = {}
    reached: set[str] = set()
    for name, (method, path) in OPERATIONS.items():
        operation = spec.get("paths", {}).get(path, {}).get(method.lower())
        if operation is None:
            raise GeneratorError(
                f"operation {name!r} ({method} {path}) is not in the Python API contract; "
                "remove or update it in OPERATIONS"
            )
        entry: dict[str, Any] = {"x-ruby-operation": name}
        parameters = [
            {key: value for key, value in strip_non_semantic(p).items() if key in _PARAM_KEYS}
            for p in operation.get("parameters", [])
        ]
        if parameters:
            entry["parameters"] = parameters
        if "requestBody" in operation:
            entry["requestBody"] = {
                "required": bool(operation["requestBody"].get("required", False)),
                "content": {"application/json": _json_content(operation["requestBody"], name)},
            }
        success = operation.get("responses", {}).get("200")
        if success is None:
            raise GeneratorError(f"operation {name!r} has no 200 response in the contract")
        entry["responses"] = {
            "200": {
                "description": "Successful Response",
                "content": {"application/json": _json_content(success, name)},
            }
        }
        _collect_refs(entry, reached)
        paths.setdefault(path, {})[method.lower()] = entry

    closure: set[str] = set()
    pending = sorted(reached)
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        if current not in schemas:
            raise GeneratorError(f"schema {current!r} is referenced but not defined")
        closure.add(current)
        nested: set[str] = set()
        _collect_refs(schemas[current], nested)
        pending.extend(sorted(nested - closure))

    return {
        "openapi": spec["openapi"],
        "info": {"title": spec["info"]["title"], "version": spec["info"]["version"]},
        "paths": paths,
        "components": {
            "schemas": {name: strip_non_semantic(schemas[name]) for name in sorted(closure)}
        },
    }


_PARAM_KEYS = frozenset({"name", "in", "required", "schema"})


def _json_content(container: dict[str, Any], operation: str) -> dict[str, Any]:
    content = container.get("content", {})
    if set(content) != {"application/json"}:
        raise GeneratorError(
            f"operation {operation!r} must use exactly application/json, found {sorted(content)}"
        )
    return {"schema": strip_non_semantic(content["application/json"].get("schema", {}))}


def render_snapshot(pruned: dict[str, Any]) -> str:
    return json.dumps(pruned, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


# --------------------------------------------------------------------------------------------
# Schema to Ruby type spec
# --------------------------------------------------------------------------------------------

Spec = Any  # "string" | ("array", Spec) | ("map", Spec) | ("ref", str) | ("enum", list) | ...


def type_spec(schema: dict[str, Any], schemas: dict[str, Any], where: str) -> Spec:
    for keyword in UNSUPPORTED_KEYWORDS & schema.keys():
        raise GeneratorError(f"{where}: schema keyword {keyword!r} is not supported")
    ref = schema.get("$ref")
    if ref is not None:
        name = ref.rsplit("/", 1)[-1]
        target = schemas[name]
        if "properties" in target:
            return ("ref", name)
        return type_spec(target, schemas, name)
    if "const" in schema:
        return ("enum", [schema["const"]])
    if "enum" in schema:
        return ("enum", list(schema["enum"]))
    if "anyOf" in schema:
        members = schema["anyOf"]
        concrete = [m for m in members if m.get("type") != "null"]
        if len(concrete) != 1:
            raise GeneratorError(f"{where}: anyOf with {len(concrete)} non-null members")
        inner = type_spec(concrete[0], schemas, where)
        return ("nullable", inner) if len(concrete) != len(members) else inner
    if "allOf" in schema:
        if len(schema["allOf"]) != 1:
            raise GeneratorError(f"{where}: allOf with {len(schema['allOf'])} members")
        return type_spec(schema["allOf"][0], schemas, where)
    kind = schema.get("type")
    if kind == "array":
        return ("array", type_spec(schema.get("items", {}), schemas, where))
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return ("map", type_spec(extra, schemas, where))
        return "object"
    if kind in PRIMITIVES:
        return kind
    if kind is None:
        return "any"
    raise GeneratorError(f"{where}: unsupported schema type {kind!r}")


def constraints_of(schema: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for candidate in [schema, *schema.get("anyOf", [])]:
        for key in CONSTRAINT_KEYS:
            if key in candidate:
                found[_snake(key)] = candidate[key]
    return dict(sorted(found.items()))


def _snake(name: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), name)


# --------------------------------------------------------------------------------------------
# Ruby rendering
# --------------------------------------------------------------------------------------------

_CONSTANT = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_FIELD = re.compile(r"^[a-z_][a-z0-9_]*$")


def rb_str(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def rb(value: Any) -> str:
    """A JSON value as a Ruby literal (string keys, frozen by the caller where needed)."""
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return rb_str(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(rb(item) for item in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{rb_str(k)} => {rb(v)}" for k, v in value.items()) + " }"
    raise GeneratorError(f"cannot render {value!r} as a Ruby literal")


def rb_spec(spec: Spec) -> str:
    if isinstance(spec, str):
        return f":{spec}"
    kind, arg = spec
    if kind in ("array", "map", "nullable"):
        return f"[:{kind}, {rb_spec(arg)}]"
    if kind == "ref":
        return f"[:ref, {rb_str(arg)}]"
    if kind == "enum":
        return f"[:enum, {_rb_enum_values(arg)}]"
    raise GeneratorError(f"unknown spec {spec!r}")


def _rb_enum_values(values: list[Any]) -> str:
    if values and all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_]+", v) for v in values):
        return "%w[" + " ".join(values) + "]"
    return rb(values)


def rb_constraints(constraints: dict[str, Any]) -> str:
    return "{ " + ", ".join(f"{key}: {rb(value)}" for key, value in constraints.items()) + " }"


def _enum_constant(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _canonical_header(name: str) -> str:
    return "-".join(part.capitalize() for part in name.split("-"))


def render_ruby(snapshot: dict[str, Any], snapshot_text: str) -> str:
    schemas: dict[str, Any] = snapshot["components"]["schemas"]
    digest = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
    enums = {n: s for n, s in schemas.items() if "enum" in s and "properties" not in s}
    models = {n: s for n, s in schemas.items() if "properties" in s}

    lines: list[str] = [
        "# frozen_string_literal: true",
        "",
        "# GENERATED FILE. DO NOT EDIT.",
        "#",
        "# Source of truth: the Python FastAPI contract (apps/api). The Ruby worker is",
        "# non-authoritative; it follows this contract and never defines API shapes itself.",
        f"#   regenerate: python {GENERATOR_NAME}",
        f"#   verify:     python {GENERATOR_NAME} --check",
        "#   snapshot:   apps/ruby_worker/contract/openapi.json",
        "",
        'require_relative "../contract"',
        "",
        "module GoblinWorkflow",
        "  module ApiV1",
        "    module Generated",
        f"      CONTRACT_SHA256 = {rb_str(digest)}",
        f"      OPENAPI_VERSION = {rb_str(snapshot['openapi'])}",
        f"      API_TITLE = {rb_str(snapshot['info']['title'])}",
        f"      API_VERSION = {rb_str(snapshot['info']['version'])}",
        "",
        "      module Enums",
    ]
    for name in sorted(enums):
        _require_pattern(_CONSTANT, name, "enum schema name")
        values = enums[name]["enum"]
        lines.append(f"        {_enum_constant(name)} = {_rb_enum_values(values)}.freeze")
    lines += ["      end", "", "      module Models"]

    for name in sorted(models):
        _require_pattern(_CONSTANT, name, "schema name")
        schema = models[name]
        required = set(schema.get("required", []))
        lines += [
            f"        class {name} < Contract::Model",
            f"          schema {rb_str(name)}",
        ]
        for field_name, field_schema in schema["properties"].items():
            _require_pattern(_FIELD, field_name, f"{name} field name")
            spec = type_spec(field_schema, schemas, f"{name}.{field_name}")
            parts = [f"field :{field_name}", rb_spec(spec)]
            if field_name in required:
                parts.append("required: true")
            default = field_schema.get("default")
            if default is not None:
                parts.append(f"default: {rb(default)}")
            constraints = constraints_of(field_schema)
            if constraints:
                parts.append(f"constraints: {rb_constraints(constraints)}")
            lines.append("          " + ", ".join(parts))
        lines += ["        end", ""]
    if lines[-1] == "":
        lines.pop()
    lines += ["      end", "", "      OPERATIONS = {"]

    operation_blocks: list[str] = []
    for method_path in sorted(snapshot["paths"].items()):
        path, by_method = method_path
        for method, entry in sorted(by_method.items()):
            operation_blocks.append(_render_operation(path, method, entry, schemas))
    lines.append(",\n".join(sorted(operation_blocks)))
    lines += ["      }.freeze", "    end", "  end", "end", ""]
    return "\n".join(lines)


def _require_pattern(pattern: re.Pattern[str], value: str, what: str) -> None:
    if not pattern.match(value):
        raise GeneratorError(f"{what} {value!r} cannot be rendered as a Ruby identifier")


def _render_operation(path: str, method: str, entry: dict[str, Any], schemas: dict[str, Any]) -> str:
    name = entry["x-ruby-operation"]
    where = f"{method.upper()} {path}"
    path_params: list[str] = []
    query_params: list[str] = []
    header_params: list[str] = []
    for param in entry.get("parameters", []):
        location = param["in"]
        if location == "path":
            path_params.append(param["name"])
        elif location == "query":
            spec = type_spec(param.get("schema", {}), schemas, f"{where} {param['name']}")
            parts = [f"name: {rb_str(param['name'])}", f"spec: {rb_spec(spec)}"]
            parts.append(f"required: {rb(bool(param.get('required', False)))}")
            default = param.get("schema", {}).get("default")
            if default is not None:
                parts.append(f"default: {rb(default)}")
            constraints = constraints_of(param.get("schema", {}))
            if constraints:
                parts.append(f"constraints: {rb_constraints(constraints)}")
            query_params.append("Contract::Param.new(" + ", ".join(parts) + ")")
        elif location == "header":
            header_params.append(
                f"Contract::Header.new(name: {rb_str(_canonical_header(param['name']))}, "
                f"required: {rb(bool(param.get('required', False)))})"
            )
        else:
            raise GeneratorError(f"{where}: unsupported parameter location {location!r}")
    declared = set(re.findall(r"\{([^}]+)\}", path))
    if declared != set(path_params):
        raise GeneratorError(f"{where}: path placeholders {declared} != parameters {path_params}")

    request = _body_schema_name(entry.get("requestBody"), where)
    response = _body_schema_name(entry["responses"]["200"], where)
    pad = " " * 10
    body = [
        f"        {name}: Contract::Operation.new(",
        f"{pad}name: :{name}, http_method: :{method}, path: {rb_str(path)},",
    ]
    if path_params:
        body.append(f"{pad}path_params: %w[{' '.join(path_params)}],")
    if query_params:
        inner = (",\n" + pad + "  ").join(query_params)
        body.append(f"{pad}query_params: [\n{pad}  {inner}\n{pad}],")
    if header_params:
        body.append(f"{pad}header_params: [{', '.join(header_params)}],")
    if request:
        body.append(f"{pad}request: {rb_str(request)},")
    body.append(f"{pad}response: {rb_str(response)}")
    body.append("        )")
    return "\n".join(body)


def _body_schema_name(container: dict[str, Any] | None, where: str) -> str:
    if container is None:
        return ""
    schema = container["content"]["application/json"]["schema"]
    ref = schema.get("$ref")
    if ref is None:
        raise GeneratorError(f"{where}: request and response bodies must be named schemas")
    return str(ref.rsplit("/", 1)[-1])


# --------------------------------------------------------------------------------------------
# Build, check, write
# --------------------------------------------------------------------------------------------


def build_artifacts() -> dict[Path, str]:
    snapshot_text = render_snapshot(prune(export_openapi()))
    ruby = render_ruby(json.loads(snapshot_text), snapshot_text)
    return {SNAPSHOT_PATH: snapshot_text, GENERATED_PATH: ruby}


def drift(artifacts: dict[Path, str] | None = None) -> list[str]:
    """Unified diffs for every committed file that differs from a fresh generation."""
    expected = artifacts if artifacts is not None else build_artifacts()
    problems: list[str] = []
    for path, text in expected.items():
        relative = path.relative_to(ROOT).as_posix()
        if not path.exists():
            problems.append(f"{relative}: missing")
            continue
        current = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        if current != text:
            diff = difflib.unified_diff(
                current.splitlines(), text.splitlines(), f"{relative} (committed)", "generated", lineterm=""
            )
            problems.append("\n".join(list(diff)[:120]))
    return problems


def write_artifacts(artifacts: dict[Path, str]) -> None:
    for path, text in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed files drift")
    args = parser.parse_args(argv)
    try:
        artifacts = build_artifacts()
    except GeneratorError as error:
        print(f"generate_ruby_client: {error}", file=sys.stderr)
        return 2
    if args.check:
        problems = drift(artifacts)
        if problems:
            print("Ruby client is out of sync with the Python API contract:\n", file=sys.stderr)
            print("\n\n".join(problems), file=sys.stderr)
            print(f"\nRegenerate with: python {GENERATOR_NAME}", file=sys.stderr)
            return 1
        print("Ruby client matches the Python API contract.")
        return 0
    write_artifacts(artifacts)
    for path in artifacts:
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
