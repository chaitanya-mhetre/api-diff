"""The rule registry: every kind of change api-diff can report, with its severity and the reason.

Severity guide:
  breaking - existing, correct clients can fail after this change
  warning  - may break some clients, or needs a human to look
  info     - additive or harmless, reported for visibility
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["breaking", "warning", "info"]
SEVERITY_ORDER: dict[Severity, int] = {"info": 0, "warning": 1, "breaking": 2}


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    description: str
    rationale: str


_RULES = [
    # --- operations ---------------------------------------------------------------------------
    Rule(
        "operation-removed",
        "breaking",
        "An operation (method + path) was removed.",
        "Clients calling it will get 404/405.",
    ),
    Rule("operation-added", "info", "A new operation was added.", "Additive."),
    Rule(
        "operation-deprecated",
        "warning",
        "An operation was marked deprecated.",
        "Not breaking yet, but clients should plan to migrate.",
    ),
    # --- parameters -------------------------------------------------------------------------
    Rule(
        "parameter-required-added",
        "breaking",
        "A new required parameter was added.",
        "Existing clients don't send it, so their requests become invalid.",
    ),
    Rule(
        "parameter-optional-added",
        "info",
        "A new optional parameter was added.",
        "Additive.",
    ),
    Rule(
        "parameter-removed",
        "warning",
        "A parameter was removed.",
        "Servers usually ignore unknown parameters, but a client relying on its effect "
        "(a filter, say) silently gets different results.",
    ),
    Rule(
        "parameter-became-required",
        "breaking",
        "An optional parameter became required.",
        "Clients that omitted it now send invalid requests.",
    ),
    Rule(
        "parameter-location-changed",
        "breaking",
        "A parameter moved (e.g. query -> header).",
        "Clients send it in the old place.",
    ),
    # --- request bodies -----------------------------------------------------------------------
    Rule(
        "request-body-required-added",
        "breaking",
        "A required request body was added.",
        "Existing clients send no body.",
    ),
    Rule(
        "request-body-became-required",
        "breaking",
        "The request body became required.",
        "Clients that omitted it now fail.",
    ),
    Rule(
        "request-media-type-removed",
        "breaking",
        "A request content type is no longer accepted.",
        "Clients sending it get 415 Unsupported Media Type.",
    ),
    Rule(
        "request-property-required-added",
        "breaking",
        "A new required property was added to a request schema.",
        "Existing clients don't send it.",
    ),
    Rule(
        "request-property-became-required",
        "breaking",
        "An optional request property became required.",
        "Clients that omitted it now fail.",
    ),
    Rule(
        "request-property-removed",
        "warning",
        "A request property was removed.",
        "Clients still send it; strict servers (additionalProperties: false) may reject it.",
    ),
    Rule(
        "request-property-optional-added",
        "info",
        "A new optional request property was added.",
        "Additive.",
    ),
    # --- responses ----------------------------------------------------------------------------
    Rule(
        "response-success-status-removed",
        "breaking",
        "A 2xx response code was removed.",
        "Clients handling that success code break.",
    ),
    Rule(
        "response-status-removed",
        "warning",
        "A non-2xx response code was removed.",
        "Usually harmless, but clients may branch on it.",
    ),
    Rule(
        "response-media-type-removed",
        "breaking",
        "A response content type was removed.",
        "Clients asking for it (Accept header) no longer get it.",
    ),
    Rule(
        "response-property-removed",
        "breaking",
        "A required response property was removed.",
        "Clients read it and will get undefined/KeyError.",
    ),
    Rule(
        "response-optional-property-removed",
        "warning",
        "An optional response property was removed.",
        "Clients were told it may be absent, but many still read it when present.",
    ),
    Rule(
        "response-property-became-optional",
        "breaking",
        "A required response property became optional.",
        "Clients assume it is always present.",
    ),
    Rule(
        "response-property-added",
        "info",
        "A response property was added.",
        "Additive; well-behaved clients ignore unknown fields.",
    ),
    # --- schema-level (apply in both directions, severity depends on direction) --------------
    Rule(
        "type-changed",
        "breaking",
        "A schema type changed incompatibly.",
        "Request: the server stops accepting values clients send. "
        "Response: clients receive a type they don't expect.",
    ),
    Rule(
        "type-widened",
        "info",
        "A schema type was widened compatibly (e.g. integer -> number in a request).",
        "Everything that was valid before is still valid.",
    ),
    Rule(
        "request-became-non-nullable",
        "breaking",
        "A request value can no longer be null.",
        "Clients sending null now fail.",
    ),
    Rule(
        "response-became-nullable",
        "breaking",
        "A response value can now be null.",
        "Clients that don't expect null crash on it.",
    ),
    Rule(
        "request-enum-value-removed",
        "breaking",
        "An enum value is no longer accepted.",
        "Clients sending it now fail.",
    ),
    Rule("request-enum-value-added", "info", "A new enum value is accepted.", "Additive."),
    Rule(
        "response-enum-value-added",
        "warning",
        "A response enum gained a value.",
        "Clients with an exhaustive switch/match may not handle it.",
    ),
    Rule(
        "response-enum-value-removed",
        "info",
        "A response enum lost a value.",
        "Clients simply never see it again.",
    ),
    Rule(
        "request-constraint-tightened",
        "breaking",
        "A request constraint got stricter (maxLength, minimum, ...).",
        "Values clients sent before may now be rejected.",
    ),
    Rule(
        "response-constraint-loosened",
        "warning",
        "A response constraint got looser (maxLength, maximum, ...).",
        "Clients sized buffers or validation around the old limit.",
    ),
    Rule(
        "pattern-changed",
        "warning",
        "A string pattern changed.",
        "Can't tell automatically whether it is stricter or looser.",
    ),
    Rule(
        "format-changed",
        "warning",
        "A string format changed (e.g. date -> date-time).",
        "Parsers built for the old format may fail.",
    ),
    Rule(
        "composition-changed",
        "warning",
        "A oneOf/anyOf schema changed.",
        "Compatibility of composed schemas is not analysed automatically; review by hand.",
    ),
]

RULES: dict[str, Rule] = {r.id: r for r in _RULES}
