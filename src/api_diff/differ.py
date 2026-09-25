"""Walk two specs side by side and emit :class:`Change` objects.

The one idea to understand here is **direction**:

* Request schemas are *contravariant*: the new server must accept everything old clients send.
  Loosening is safe; tightening breaks.
* Response schemas are *covariant*: old clients must understand everything the new server returns.
  Tightening is safe; loosening (new types, new enum values, nulls) can break.

Every schema comparison carries a ``direction`` so the same walker applies the right rule.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from api_diff.loader import Spec
from api_diff.model import Change

Direction = Literal["request", "response"]
METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
MAX_DEPTH = 64
UPPER_BOUNDS = ("maxLength", "maximum", "maxItems", "exclusiveMaximum", "maxProperties")
LOWER_BOUNDS = ("minLength", "minimum", "minItems", "exclusiveMinimum", "minProperties")
_TEMPLATE_VAR = re.compile(r"\{[^}]+\}")


def escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def normalize_path(path: str) -> str:
    """``/users/{id}`` and ``/users/{userId}`` are the same route."""
    return _TEMPLATE_VAR.sub("{}", path)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _bounds(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite OpenAPI 3.0 boolean ``exclusiveMinimum``/``exclusiveMaximum`` into the 3.1 number form.

    ``{minimum: 0, exclusiveMinimum: true}`` (3.0) and ``{exclusiveMinimum: 0}`` (3.1) mean the same
    thing. Without this, a spec migrating between them looks like a new constraint was added.
    """
    out = dict(schema)
    for excl, inclusive in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        flag = out.get(excl)
        if isinstance(flag, bool):
            if flag and inclusive in out:
                out[excl] = out.pop(inclusive)
            else:
                del out[excl]
    return out


def _ref_members(members: list[Any]) -> dict[str, tuple[int, Any]]:
    """Map each ``$ref`` string in a oneOf/anyOf list to (position, member)."""
    out: dict[str, tuple[int, Any]] = {}
    for i, member in enumerate(members):
        if isinstance(member, dict) and isinstance(member.get("$ref"), str):
            out.setdefault(member["$ref"], (i, member))
    return out


@dataclass
class _Node:
    """A schema-ish node after ``$ref`` resolution, remembering which document it came from."""

    value: dict[str, Any]
    base: str
    identity: tuple[str, int]  # stable id for cycle detection


@dataclass
class Differ:
    old: Spec
    new: Spec
    changes: list[Change] = field(default_factory=list)
    _visited: set[tuple[Any, ...]] = field(default_factory=set)

    # ---- helpers ------------------------------------------------------------------------------

    def _emit(
        self,
        rule: str,
        loc: str,
        op: str | None,
        msg: str,
        old: Any = None,
        new: Any = None,
    ) -> None:
        self.changes.append(Change(rule, loc, op, msg, old, new))

    def _deref(self, spec: Spec, node: Any, base: str) -> _Node | None:
        if not isinstance(node, dict):
            return None
        value, base, pointer = spec.resolver.deref(node, base)
        if not isinstance(value, dict):
            return None
        identity = (pointer or f"{base}@{id(value)}", id(value))
        return _Node(value, base, identity)

    def _flatten(self, spec: Spec, node: _Node, depth: int = 0) -> dict[str, Any]:
        """Merge ``allOf`` members into one schema (properties, required, and scalar keywords)."""
        schema = {k: v for k, v in node.value.items() if k != "allOf"}
        members = node.value.get("allOf")
        if not isinstance(members, list) or depth > MAX_DEPTH:
            return schema
        props: dict[str, Any] = dict(schema.get("properties") or {})
        required: set[str] = set(schema.get("required") or [])
        for member in members:
            resolved = self._deref(spec, member, node.base)
            if resolved is None:
                continue
            flat = self._flatten(spec, resolved, depth + 1)
            for key, value in flat.items():
                if key == "properties":
                    props.update(value or {})
                elif key == "required":
                    required.update(value or [])
                else:
                    schema.setdefault(key, value)
        if props:
            schema["properties"] = props
        if required:
            schema["required"] = sorted(required)
        return schema

    def _normalize(self, spec: Spec, node: _Node, depth: int = 0) -> dict[str, Any]:
        """Flatten ``allOf`` and unwrap nullable unions.

        OpenAPI 3.1 has no ``nullable``; specs write ``anyOf: [X, {type: "null"}]`` instead (OpenAI's
        spec switched to this between 3.0 and 3.1). Without unwrapping, every such change looks like
        an opaque ``anyOf`` edit and nothing inside ``X`` is compared. So ``X`` is merged in and
        ``null`` is added to its type, which makes it equivalent to the 3.0 ``nullable: true`` form.
        """
        schema = self._flatten(spec, node)
        for keyword in ("anyOf", "oneOf"):
            members = schema.get(keyword)
            if not isinstance(members, list) or len(members) < 2 or depth > MAX_DEPTH:
                continue
            nulls = [m for m in members if isinstance(m, dict) and m.get("type") == "null"]
            others = [m for m in members if m not in nulls]
            if not nulls or len(others) != 1:
                continue
            inner = self._deref(spec, others[0], node.base)
            if inner is None or inner.base != node.base:
                continue  # cross-document $ref: nested refs would resolve against the wrong base
            merged = {k: v for k, v in schema.items() if k != keyword}
            for key, value in self._normalize(spec, inner, depth + 1).items():
                merged.setdefault(key, value)
            raw = merged.get("type")
            if isinstance(raw, str):
                merged["type"] = [raw, "null"]
            elif isinstance(raw, list) and "null" not in raw:
                merged["type"] = [*raw, "null"]
            return merged
        return schema

    # ---- entry point ---------------------------------------------------------------------------

    def run(self) -> list[Change]:
        old_paths = self._path_index(self.old)
        new_paths = self._path_index(self.new)
        for norm, (old_path, old_item) in old_paths.items():
            new_entry = new_paths.get(norm)
            for method in METHODS:
                if method not in old_item:
                    continue
                op_name = f"{method.upper()} {old_path}"
                if new_entry is None or method not in new_entry[1]:
                    self._emit(
                        "operation-removed",
                        f"/paths/{escape(old_path)}/{method}",
                        op_name,
                        f"{op_name} was removed",
                    )
                    continue
                new_path, new_item = new_entry
                self._operation(
                    f"{method.upper()} {new_path}",
                    f"/paths/{escape(new_path)}/{method}",
                    old_path,
                    new_path,
                    old_item,
                    old_item[method],
                    new_item,
                    new_item[method],
                )
        for norm, (new_path, new_item) in new_paths.items():
            old_entry = old_paths.get(norm)
            for method in METHODS:
                if method in new_item and (old_entry is None or method not in old_entry[1]):
                    op_name = f"{method.upper()} {new_path}"
                    self._emit(
                        "operation-added",
                        f"/paths/{escape(new_path)}/{method}",
                        op_name,
                        f"{op_name} was added",
                    )
        return self.changes

    def _path_index(self, spec: Spec) -> dict[str, tuple[str, dict[str, Any]]]:
        index: dict[str, tuple[str, dict[str, Any]]] = {}
        for path, item in (spec.root.get("paths") or {}).items():
            resolved = self._deref(spec, item, spec.base)
            if resolved is not None:
                index[normalize_path(path)] = (path, resolved.value)
        return index

    # ---- operations ------------------------------------------------------------------------------

    def _operation(
        self,
        op: str,
        loc: str,
        old_path: str,
        new_path: str,
        old_item: dict[str, Any],
        old_op: dict[str, Any],
        new_item: dict[str, Any],
        new_op: dict[str, Any],
    ) -> None:
        if new_op.get("deprecated") and not old_op.get("deprecated"):
            self._emit("operation-deprecated", loc, op, f"{op} is now deprecated")
        self._parameters(op, loc, old_path, new_path, old_item, old_op, new_item, new_op)
        self._request_body(op, loc, old_op.get("requestBody"), new_op.get("requestBody"))
        self._responses(op, loc, old_op.get("responses") or {}, new_op.get("responses") or {})

    def _collect_params(
        self, spec: Spec, path: str, item: dict[str, Any], op: dict[str, Any]
    ) -> dict[tuple[str, str], _Node]:
        """Path-level params overridden by operation-level ones, keyed for matching.

        Path params are keyed by *position* so a rename (``{id}`` -> ``{userId}``) still matches.
        """
        names = [m.group(0)[1:-1] for m in _TEMPLATE_VAR.finditer(path)]
        params: dict[tuple[str, str], _Node] = {}
        for raw in [*(item.get("parameters") or []), *(op.get("parameters") or [])]:
            node = self._deref(spec, raw, spec.base)
            if node is None:
                continue
            where, name = str(node.value.get("in")), str(node.value.get("name"))
            in_template = where == "path" and name in names
            key = ("path", str(names.index(name))) if in_template else (where, name)
            params[key] = node
        return params

    def _parameters(
        self,
        op: str,
        loc: str,
        old_path: str,
        new_path: str,
        old_item: dict[str, Any],
        old_op: dict[str, Any],
        new_item: dict[str, Any],
        new_op: dict[str, Any],
    ) -> None:
        old = self._collect_params(self.old, old_path, old_item, old_op)
        new = self._collect_params(self.new, new_path, new_item, new_op)
        new_names = {name: where for (where, name) in new}
        for key, old_node in old.items():
            where, name = key
            ploc = f"{loc}/parameters/{escape(where)}:{escape(name)}"
            if key not in new:
                if where != "path" and name in new_names and new_names[name] != where:
                    self._emit(
                        "parameter-location-changed",
                        ploc,
                        op,
                        f"parameter {name!r} moved from {where} to {new_names[name]}",
                        where,
                        new_names[name],
                    )
                elif where != "path":
                    self._emit(
                        "parameter-removed",
                        ploc,
                        op,
                        f"{where} parameter {name!r} was removed",
                    )
                continue
            new_node = new[key]
            if new_node.value.get("required") and not old_node.value.get("required"):
                self._emit(
                    "parameter-became-required",
                    ploc,
                    op,
                    f"{where} parameter {name!r} is now required",
                )
            self._schema(
                op,
                f"{ploc}/schema",
                "request",
                old_node.value.get("schema"),
                old_node.base,
                new_node.value.get("schema"),
                new_node.base,
                0,
            )
        for key, new_node in new.items():
            where, name = key
            if key in old or (where != "path" and any(n == name for (_, n) in old)):
                continue
            if where == "path":
                continue  # a new path variable means a different route (reported as added)
            ploc = f"{loc}/parameters/{escape(where)}:{escape(name)}"
            if new_node.value.get("required"):
                self._emit(
                    "parameter-required-added",
                    ploc,
                    op,
                    f"new required {where} parameter {name!r}",
                )
            else:
                self._emit(
                    "parameter-optional-added",
                    ploc,
                    op,
                    f"new optional {where} parameter {name!r}",
                )

    def _request_body(self, op: str, loc: str, old_raw: Any, new_raw: Any) -> None:
        bloc = f"{loc}/requestBody"
        old = self._deref(self.old, old_raw, self.old.base)
        new = self._deref(self.new, new_raw, self.new.base)
        if new is None:
            return  # removing a body is tolerated: clients' extra body is ignored
        if old is None:
            if new.value.get("required"):
                self._emit(
                    "request-body-required-added",
                    bloc,
                    op,
                    "a required request body was added",
                )
            return
        if new.value.get("required") and not old.value.get("required"):
            self._emit(
                "request-body-became-required",
                bloc,
                op,
                "the request body is now required",
            )
        self._content(op, bloc, "request", old, new)

    def _responses(self, op: str, loc: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        for code, old_raw in old.items():
            code = str(code)
            rloc = f"{loc}/responses/{escape(code)}"
            if code not in {str(c) for c in new}:
                rule = (
                    "response-success-status-removed" if code.startswith("2") else "response-status-removed"
                )
                self._emit(rule, rloc, op, f"response {code} was removed")
                continue
            new_raw = next(v for c, v in new.items() if str(c) == code)
            old_node = self._deref(self.old, old_raw, self.old.base)
            new_node = self._deref(self.new, new_raw, self.new.base)
            if old_node is not None and new_node is not None:
                self._content(op, rloc, "response", old_node, new_node)

    def _content(self, op: str, loc: str, direction: Direction, old: _Node, new: _Node) -> None:
        old_content = old.value.get("content") or {}
        new_content = new.value.get("content") or {}
        for media, old_media in old_content.items():
            mloc = f"{loc}/content/{escape(media)}"
            if media not in new_content:
                rule = f"{direction}-media-type-removed"
                self._emit(rule, mloc, op, f"{direction} content type {media!r} was removed")
                continue
            self._schema(
                op,
                f"{mloc}/schema",
                direction,
                (old_media or {}).get("schema"),
                old.base,
                (new_content[media] or {}).get("schema"),
                new.base,
                0,
            )

    # ---- schemas -------------------------------------------------------------------------------

    def _schema(
        self,
        op: str,
        loc: str,
        direction: Direction,
        old_raw: Any,
        old_base: str,
        new_raw: Any,
        new_base: str,
        depth: int,
    ) -> None:
        if depth > MAX_DEPTH:
            return
        if depth == 0:
            # Cycle detection is per traversal: a shared schema is still reported for every
            # operation that uses it, so the report says exactly which endpoints are affected.
            self._visited = set()
        old = self._deref(self.old, old_raw, old_base)
        new = self._deref(self.new, new_raw, new_base)
        if old is None or new is None:
            return
        key = (old.identity, new.identity, direction)
        if key in self._visited:
            return  # recursive schema: this pair is already being compared higher up
        self._visited.add(key)

        o, n = self._normalize(self.old, old), self._normalize(self.new, new)
        self._types(op, loc, direction, o, n)
        self._enums(op, loc, direction, o, n)
        self._constraints(op, loc, direction, o, n)
        self._composition(op, loc, direction, o, old.base, n, new.base, depth)
        self._properties(op, loc, direction, o, old.base, n, new.base, depth)
        if "items" in o and "items" in n:
            self._schema(
                op,
                f"{loc}/items",
                direction,
                o["items"],
                old.base,
                n["items"],
                new.base,
                depth + 1,
            )

    @staticmethod
    def _type_set(schema: dict[str, Any]) -> set[str] | None:
        raw = schema.get("type")
        if raw is None:
            return None
        types = {raw} if isinstance(raw, str) else {str(t) for t in raw}
        if schema.get("nullable") is True:  # OpenAPI 3.0 spelling of "type: [..., null]"
            types.add("null")
        return types

    @staticmethod
    def _covers(wide: set[str], narrow: set[str]) -> bool:
        """Does ``wide`` accept every value of ``narrow``? (``number`` accepts ``integer``.)"""
        return all(t in wide or (t == "integer" and "number" in wide) for t in narrow)

    def _types(
        self,
        op: str,
        loc: str,
        direction: Direction,
        o: dict[str, Any],
        n: dict[str, Any],
    ) -> None:
        old_t, new_t = self._type_set(o), self._type_set(n)
        if old_t is None or new_t is None:
            return
        old_nn, new_nn = old_t - {"null"}, new_t - {"null"}
        if old_nn and new_nn:
            if direction == "request":
                if not self._covers(new_nn, old_nn):
                    self._emit(
                        "type-changed",
                        loc,
                        op,
                        f"request type {sorted(old_nn)} -> {sorted(new_nn)}",
                        sorted(old_nn),
                        sorted(new_nn),
                    )
                elif new_nn != old_nn:
                    self._emit(
                        "type-widened",
                        loc,
                        op,
                        f"request type widened {sorted(old_nn)} -> {sorted(new_nn)}",
                        sorted(old_nn),
                        sorted(new_nn),
                    )
            elif not self._covers(old_nn, new_nn):
                self._emit(
                    "type-changed",
                    loc,
                    op,
                    f"response type {sorted(old_nn)} -> {sorted(new_nn)}",
                    sorted(old_nn),
                    sorted(new_nn),
                )
        if direction == "request" and "null" in old_t and "null" not in new_t:
            self._emit(
                "request-became-non-nullable",
                loc,
                op,
                "request value can no longer be null",
            )
        if direction == "response" and "null" in new_t and "null" not in old_t:
            self._emit("response-became-nullable", loc, op, "response value can now be null")

    def _enums(
        self,
        op: str,
        loc: str,
        direction: Direction,
        o: dict[str, Any],
        n: dict[str, Any],
    ) -> None:
        old_e, new_e = o.get("enum"), n.get("enum")
        if old_e is None and new_e is None:
            return
        if old_e is None:  # enum introduced = narrowing
            if direction == "request":
                self._emit(
                    "request-constraint-tightened",
                    loc,
                    op,
                    "request value is now restricted to an enum",
                    None,
                    new_e,
                )
            return
        if new_e is None:  # enum dropped = widening
            if direction == "response":
                self._emit(
                    "response-constraint-loosened",
                    loc,
                    op,
                    "response value is no longer restricted to an enum",
                    old_e,
                    None,
                )
            return
        old_set = {_canonical(v): v for v in old_e}
        new_set = {_canonical(v): v for v in new_e}
        removed = [old_set[k] for k in old_set.keys() - new_set.keys()]
        added = [new_set[k] for k in new_set.keys() - old_set.keys()]
        for value in removed:
            rule = "request-enum-value-removed" if direction == "request" else "response-enum-value-removed"
            self._emit(rule, loc, op, f"{direction} enum value {value!r} removed", value, None)
        for value in added:
            rule = "request-enum-value-added" if direction == "request" else "response-enum-value-added"
            self._emit(rule, loc, op, f"{direction} enum value {value!r} added", None, value)

    def _constraints(
        self,
        op: str,
        loc: str,
        direction: Direction,
        o: dict[str, Any],
        n: dict[str, Any],
    ) -> None:
        o, n = _bounds(o), _bounds(n)

        def num(schema: dict[str, Any], key: str) -> int | float | None:
            value = schema.get(key)
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        def lt(x: float, y: float) -> bool:
            # Past 2**53, JSON numbers aren't exact: a JS serializer writes int64 max as
            # 9223372036854776000. Compare as doubles there so re-serialization isn't a "change".
            if max(abs(x), abs(y)) > 2**53:
                return float(x) < float(y)
            return x < y

        for key in UPPER_BOUNDS:
            a, b = num(o, key), num(n, key)
            if direction == "request" and b is not None and (a is None or lt(b, a)):
                self._emit(
                    "request-constraint-tightened",
                    loc,
                    op,
                    f"request {key} tightened {a} -> {b}",
                    a,
                    b,
                )
            if direction == "response" and a is not None and (b is None or lt(a, b)):
                self._emit(
                    "response-constraint-loosened",
                    loc,
                    op,
                    f"response {key} loosened {a} -> {b}",
                    a,
                    b,
                )
        for key in LOWER_BOUNDS:
            a, b = num(o, key), num(n, key)
            if direction == "request" and b is not None and (a is None or lt(a, b)):
                self._emit(
                    "request-constraint-tightened",
                    loc,
                    op,
                    f"request {key} tightened {a} -> {b}",
                    a,
                    b,
                )
            if direction == "response" and a is not None and (b is None or lt(b, a)):
                self._emit(
                    "response-constraint-loosened",
                    loc,
                    op,
                    f"response {key} loosened {a} -> {b}",
                    a,
                    b,
                )
        if o.get("pattern") != n.get("pattern") and (o.get("pattern") or n.get("pattern")):
            self._emit(
                "pattern-changed",
                loc,
                op,
                "pattern changed",
                o.get("pattern"),
                n.get("pattern"),
            )
        if o.get("format") != n.get("format") and o.get("format") and n.get("format"):
            self._emit(
                "format-changed",
                loc,
                op,
                f"format {o['format']!r} -> {n['format']!r}",
                o["format"],
                n["format"],
            )

    def _composition(
        self,
        op: str,
        loc: str,
        direction: Direction,
        o: dict[str, Any],
        old_base: str,
        n: dict[str, Any],
        new_base: str,
        depth: int,
    ) -> None:
        for keyword in ("oneOf", "anyOf"):
            a, b = o.get(keyword), n.get(keyword)
            if a is None and b is None:
                continue
            if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                for i, (x, y) in enumerate(zip(a, b, strict=True)):
                    self._schema(
                        op,
                        f"{loc}/{keyword}/{i}",
                        direction,
                        x,
                        old_base,
                        y,
                        new_base,
                        depth + 1,
                    )
            elif _canonical(a) != _canonical(b):
                self._emit(
                    "composition-changed",
                    loc,
                    op,
                    f"{keyword} changed; review manually",
                )
                if isinstance(a, list) and isinstance(b, list):
                    # Members were added or removed. Positions no longer line up, but members that
                    # point at the same $ref are the same variant, so still compare those. Otherwise
                    # a change inside a surviving variant hides behind the "review manually" warning.
                    old_refs = _ref_members(a)
                    new_refs = _ref_members(b)
                    for ref in sorted(old_refs.keys() & new_refs.keys()):
                        i, x = old_refs[ref]
                        _, y = new_refs[ref]
                        self._schema(
                            op,
                            f"{loc}/{keyword}/{i}",
                            direction,
                            x,
                            old_base,
                            y,
                            new_base,
                            depth + 1,
                        )

    def _properties(
        self,
        op: str,
        loc: str,
        direction: Direction,
        o: dict[str, Any],
        old_base: str,
        n: dict[str, Any],
        new_base: str,
        depth: int,
    ) -> None:
        old_props: dict[str, Any] = o.get("properties") or {}
        new_props: dict[str, Any] = n.get("properties") or {}
        if not old_props and not new_props:
            return
        old_req, new_req = set(o.get("required") or []), set(n.get("required") or [])
        for name, old_schema in old_props.items():
            ploc = f"{loc}/properties/{escape(name)}"
            if name not in new_props:
                if direction == "request":
                    self._emit(
                        "request-property-removed",
                        ploc,
                        op,
                        f"request property {name!r} removed",
                    )
                elif name in old_req:
                    self._emit(
                        "response-property-removed",
                        ploc,
                        op,
                        f"response property {name!r} removed",
                    )
                else:
                    self._emit(
                        "response-optional-property-removed",
                        ploc,
                        op,
                        f"optional response property {name!r} removed",
                    )
                continue
            if direction == "request" and name in new_req and name not in old_req:
                self._emit(
                    "request-property-became-required",
                    ploc,
                    op,
                    f"request property {name!r} is now required",
                )
            if direction == "response" and name in old_req and name not in new_req:
                self._emit(
                    "response-property-became-optional",
                    ploc,
                    op,
                    f"response property {name!r} is no longer guaranteed",
                )
            self._schema(
                op,
                ploc,
                direction,
                old_schema,
                old_base,
                new_props[name],
                new_base,
                depth + 1,
            )
        for name in new_props.keys() - old_props.keys():
            ploc = f"{loc}/properties/{escape(name)}"
            if direction == "request":
                rule = (
                    "request-property-required-added"
                    if name in new_req
                    else "request-property-optional-added"
                )
                self._emit(
                    rule,
                    ploc,
                    op,
                    f"new {'required ' if name in new_req else ''}request property {name!r}",
                )
            else:
                self._emit(
                    "response-property-added",
                    ploc,
                    op,
                    f"response property {name!r} added",
                )


def diff_specs(old: Spec, new: Spec) -> list[Change]:
    return Differ(old, new).run()
