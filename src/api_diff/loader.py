"""Load OpenAPI documents from files or URLs and resolve ``$ref`` pointers.

Only ``yaml.safe_load`` is used (YAML is a superset of JSON, so one loader handles both).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MAX_BYTES = 20 * 1024 * 1024
TIMEOUT_S = 10


class SpecError(Exception):
    """The input is not a usable OpenAPI 3.x document."""


def _is_url(location: str) -> bool:
    return urllib.parse.urlparse(location).scheme in ("http", "https")


class _HttpOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        if not _is_url(newurl):
            raise SpecError(f"refusing redirect to non-HTTP URL {newurl!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_text(location: str) -> str:
    if _is_url(location):
        opener = urllib.request.build_opener(_HttpOnlyRedirects)
        with opener.open(location, timeout=TIMEOUT_S) as resp:  # noqa: S310 (scheme checked)
            data: bytes = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise SpecError(f"{location} is larger than {MAX_BYTES} bytes")
        return data.decode("utf-8")
    path = Path(location)
    if not path.is_file():
        raise SpecError(f"no such file: {location}")
    return path.read_text(encoding="utf-8")


def parse(text: str, source: str = "<string>") -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"{source}: invalid YAML/JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{source}: top level must be a mapping")
    return data


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


@dataclass
class Resolver:
    """Resolves local (``#/...``) and relative-file (``other.yaml#/...``) references.

    Documents are cached by location. Ref *chains* (A -> B -> A) raise; recursive *schemas*
    (a Node whose children point back at it) are fine here and handled by the differ.
    """

    documents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load(self, location: str) -> dict[str, Any]:
        key = location if _is_url(location) else str(Path(location).resolve())
        if key not in self.documents:
            self.documents[key] = parse(read_text(location), location)
        return self.documents[key]

    def _join(self, base: str, ref_file: str) -> str:
        if _is_url(base):
            return urllib.parse.urljoin(base, ref_file)
        return str(Path(base).resolve().parent / ref_file)

    def deref(self, node: Any, base: str) -> tuple[Any, str, str | None]:
        """Follow ``$ref`` until a non-ref node. Returns ``(node, base, pointer_or_None)``."""
        seen: set[tuple[str, str]] = set()
        pointer: str | None = None
        while isinstance(node, dict) and isinstance(node.get("$ref"), str):
            ref: str = node["$ref"]
            file_part, _, fragment = ref.partition("#")
            target_base = self._join(base, file_part) if file_part else base
            if (target_base, fragment) in seen:
                raise SpecError(f"circular $ref chain at {ref!r}")
            seen.add((target_base, fragment))
            doc = self.documents.get(target_base) if not file_part else self.load(target_base)
            if doc is None:
                doc = self.load(target_base)
            node = doc
            for token in [t for t in fragment.split("/") if t]:
                try:
                    node = node[_unescape(token)] if isinstance(node, dict) else node[int(token)]
                except (KeyError, IndexError, ValueError) as exc:
                    raise SpecError(f"unresolvable $ref {ref!r}") from exc
            base, pointer = target_base, ref
        return node, base, pointer


@dataclass
class Spec:
    """A loaded root document plus the resolver that owns its referenced files."""

    root: dict[str, Any]
    base: str
    resolver: Resolver

    @property
    def version(self) -> str:
        return str(self.root.get("openapi", ""))


def load_spec(source: str | Path | dict[str, Any]) -> Spec:
    resolver = Resolver()
    if isinstance(source, dict):
        base = "<memory>"
        resolver.documents[base] = source
        root = source
    else:
        location = str(source)
        root = resolver.load(location)
        base = location if _is_url(location) else str(Path(location).resolve())
    version = str(root.get("openapi", ""))
    if not version.startswith("3."):
        raise SpecError(f"only OpenAPI 3.x is supported (got openapi: {version or 'missing'!r})")
    return Spec(root=root, base=base, resolver=resolver)
