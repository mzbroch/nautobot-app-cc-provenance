"""Config context provenance.

Nautobot resolves the config contexts that apply to an object, merges them in
weight order, and returns a single dictionary. The mapping from each key in that
dictionary back to the context that supplied it is computed and then discarded.

This module replays the same merge while recording that mapping, so that every
leaf path in a merged config context can name the context object that won it and
the contexts it shadowed.

The replay is never trusted on its own. `build_provenance` compares its
reconstruction against the object's own `get_config_context()` and reports a
mismatch rather than attributing values it cannot reproduce: a confidently wrong
attribution would send an operator to edit the wrong object.
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from nautobot.extras.models import ConfigContext

logger = logging.getLogger(__name__)

SOURCE_CONFIG_CONTEXT = "config_context"
SOURCE_LOCAL = "local_config_context_data"

PARITY_OK = "ok"
PARITY_MISMATCH = "mismatch"
PARITY_SKIPPED = "skipped"

RESTRICTED_LABEL = "Restricted context"
LOCAL_LABEL = "Local config context data"

# Sentinel distinguishing "key absent" from "key present and set to None".
_MISSING = object()


@dataclass(frozen=True)
class ProvenanceSource:
    """Identifies where a value came from.

    `restricted` marks a context the requesting user may not view. The value is
    still shown, because the merged config context already exposes it, but the
    context identity is redacted to its weight.
    """

    kind: str
    name: str
    weight: int | None = None
    context_id: str | None = None
    owner: str | None = None
    restricted: bool = False

    @property
    def is_local(self) -> bool:
        """Return True when the value came from the object's own local data."""
        return self.kind == SOURCE_LOCAL

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form used by the REST API."""
        return {
            "kind": self.kind,
            "name": self.name,
            "weight": self.weight,
            "context_id": self.context_id,
            "owner": self.owner,
            "restricted": self.restricted,
        }


@dataclass(frozen=True)
class ShadowedValue:
    """A value that was overwritten by a later layer.

    `path` is normally the path of the record holding it, but differs when a
    layer replaced a whole subtree: the shadowed entries then carry the deeper
    paths they originally occupied.
    """

    path: str
    value: Any
    source: ProvenanceSource

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form used by the REST API."""
        return {"path": self.path, "value": self.value, "source": self.source.to_dict()}


@dataclass
class ProvenanceRecord:
    """One leaf path of a merged config context and where it came from."""

    path: str
    value: Any
    source: ProvenanceSource
    shadowed: list[ShadowedValue] = field(default_factory=list)

    @property
    def is_conflicted(self) -> bool:
        """Return True when more than one layer supplied a value at this path."""
        return bool(self.shadowed)

    @property
    def is_list(self) -> bool:
        """Return True when the value is a list.

        Deep merge replaces lists wholesale rather than merging their elements,
        so a list is a single leaf with a single source. The UI labels it, to
        avoid implying a granularity the merge does not have.
        """
        return isinstance(self.value, list)

    @property
    def value_display(self) -> str:
        """Return a compact JSON rendering of the value for display."""
        return json.dumps(self.value, default=str, sort_keys=True)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form used by the REST API."""
        return {
            "path": self.path,
            "value": self.value,
            "source": self.source.to_dict(),
            "shadowed": [entry.to_dict() for entry in self.shadowed],
        }


@dataclass(frozen=True)
class ProvenanceLayer:
    """One config context, or the object's local data, as applied by the merge."""

    source: ProvenanceSource
    data: dict[str, Any]


@dataclass
class ProvenanceResult:
    """The outcome of a provenance replay for one object."""

    records: list[ProvenanceRecord]
    merged: dict[str, Any]
    parity: str
    diverging_paths: list[str]
    candidate_contexts: int
    has_local_data: bool

    @property
    def is_trustworthy(self) -> bool:
        """Return False when the replay could not reproduce the merged context."""
        return self.parity != PARITY_MISMATCH

    @property
    def conflict_count(self) -> int:
        """Return the number of paths supplied by more than one layer."""
        return sum(1 for record in self.records if record.is_conflicted)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form used by the REST API."""
        return {
            "parity": self.parity,
            "candidate_contexts": self.candidate_contexts,
            "has_local_data": self.has_local_data,
            "conflict_count": self.conflict_count,
            "paths": [record.to_dict() for record in self.records],
        }


def merge_with_provenance(
    layers: list[ProvenanceLayer],
) -> tuple[dict[str, Any], dict[str, ProvenanceRecord]]:
    """Merge `layers` in order, recording which layer wrote each leaf path.

    Mirrors Nautobot's deep merge: dictionaries merge recursively, while scalars
    and lists replace whatever they land on. Layers must already be ordered the
    way Nautobot applies them -- lowest weight first, so the highest weight wins
    by being applied last.

    Returns the merged dictionary and the records keyed by path.
    """
    merged: dict[str, Any] = {}
    records: dict[str, ProvenanceRecord] = {}

    for layer in layers:
        _apply_layer(merged, layer.data or {}, layer.source, records, "", ())

    return merged, records


def _apply_layer(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    target: dict[str, Any],
    data: dict[str, Any],
    source: ProvenanceSource,
    records: dict[str, ProvenanceRecord],
    prefix: str,
    inherited_shadows: tuple[ShadowedValue, ...],
) -> None:
    """Apply one layer into `target`, recording provenance as it writes."""
    for key, value in data.items():
        path = f"{prefix}{key}"
        existing = target.get(key, _MISSING)

        if isinstance(value, dict):
            carried = inherited_shadows
            if not isinstance(existing, dict):
                if existing is not _MISSING:
                    # A scalar is being replaced by a nested structure. It has no
                    # record of its own any more, so it is carried down and
                    # attached to every leaf this subtree introduces.
                    carried = tuple(_take_shadows(records, path)) + carried
                target[key] = {}
            _apply_layer(target[key], value, source, records, f"{path}.", carried)
            continue

        if isinstance(existing, dict):
            # A whole subtree is being replaced by a scalar or list. Its records
            # are removed and become this record's shadowed entries.
            shadowed = _collapse_subtree(records, path)
        elif existing is not _MISSING:
            shadowed = _take_shadows(records, path)
        else:
            shadowed = []

        target[key] = copy.deepcopy(value)
        records[path] = ProvenanceRecord(
            path=path,
            value=copy.deepcopy(value),
            source=source,
            shadowed=shadowed + list(inherited_shadows),
        )


def _take_shadows(records: dict[str, ProvenanceRecord], path: str) -> list[ShadowedValue]:
    """Remove the record at `path` and return it, newest first, as shadows."""
    previous = records.pop(path, None)
    if previous is None:
        return []
    return [
        ShadowedValue(path=previous.path, value=previous.value, source=previous.source),
        *previous.shadowed,
    ]


def _collapse_subtree(records: dict[str, ProvenanceRecord], path: str) -> list[ShadowedValue]:
    """Remove every record beneath `path` and return them as shadows."""
    descendant_prefix = f"{path}."
    collapsed: list[ShadowedValue] = []

    for record_path in sorted(records):
        if not record_path.startswith(descendant_prefix):
            continue
        record = records.pop(record_path)
        collapsed.append(ShadowedValue(path=record.path, value=record.value, source=record.source))
        collapsed.extend(record.shadowed)

    return collapsed


def diverging_paths(replayed: Any, reference: Any, prefix: str = "") -> list[str]:
    """Return the leaf paths where `replayed` and `reference` disagree."""
    if isinstance(replayed, dict) and isinstance(reference, dict):
        differences: list[str] = []
        for key in sorted(set(replayed) | set(reference)):
            path = f"{prefix}{key}"
            if key not in replayed or key not in reference:
                differences.append(path)
                continue
            differences.extend(diverging_paths(replayed[key], reference[key], f"{path}."))
        return differences

    if replayed != reference:
        return [prefix.rstrip(".") or ""]
    return []


def config_context_layers(obj: Any, user: Any = None) -> list[ProvenanceLayer]:
    """Return the layers Nautobot would merge for `obj`, in application order.

    Contexts the user may not view are included, because their values are
    already visible in the merged config context, but their identity is redacted
    to the weight at which they applied.
    """
    contexts = list(ConfigContext.objects.get_for_object(obj).order_by("weight", "name"))

    visible_pks: set[Any] = set()
    if user is not None and contexts:
        visible_pks = set(
            ConfigContext.objects.restrict(user, "view")
            .filter(pk__in=[context.pk for context in contexts])
            .values_list("pk", flat=True)
        )

    layers: list[ProvenanceLayer] = []
    for context in contexts:
        visible = user is None or context.pk in visible_pks
        layers.append(
            ProvenanceLayer(
                source=ProvenanceSource(
                    kind=SOURCE_CONFIG_CONTEXT,
                    name=context.name if visible else RESTRICTED_LABEL,
                    weight=context.weight,
                    context_id=str(context.pk) if visible else None,
                    owner=_owner_label(context) if visible else None,
                    restricted=not visible,
                ),
                data=context.data or {},
            )
        )

    local_data = getattr(obj, "local_config_context_data", None)
    if local_data:
        layers.append(
            ProvenanceLayer(
                source=ProvenanceSource(kind=SOURCE_LOCAL, name=LOCAL_LABEL),
                data=local_data,
            )
        )

    return layers


def _owner_label(context: ConfigContext) -> str | None:
    """Return a display label for a context's owner, such as a Git repository."""
    owner = getattr(context, "owner", None)
    return str(owner) if owner is not None else None


def build_provenance(obj: Any, user: Any = None, check_parity: bool = True) -> ProvenanceResult:
    """Return the provenance of every leaf path in `obj`'s merged config context.

    When `check_parity` is set the replay is compared against the object's own
    `get_config_context()`. This costs a second scope resolution, and buys the
    guarantee that the attribution describes the config context Nautobot actually
    serves. Callers that have already paid for the merged context elsewhere may
    turn it off, but should then not present the result as authoritative.
    """
    layers = config_context_layers(obj, user=user)
    merged, records = merge_with_provenance(layers)

    parity = PARITY_SKIPPED
    divergences: list[str] = []

    if check_parity:
        reference = obj.get_config_context()
        divergences = diverging_paths(merged, reference)
        parity = PARITY_OK if not divergences else PARITY_MISMATCH
        if divergences:
            logger.warning(
                "Config context provenance replay diverged for %s (%s): %s",
                obj,
                getattr(obj, "pk", None),
                ", ".join(divergences[:10]),
            )

    return ProvenanceResult(
        records=sorted(records.values(), key=lambda record: record.path),
        merged=merged,
        parity=parity,
        diverging_paths=divergences,
        candidate_contexts=sum(1 for layer in layers if not layer.source.is_local),
        has_local_data=any(layer.source.is_local for layer in layers),
    )


def filter_records(
    records: list[ProvenanceRecord],
    conflicts_only: bool = False,
    query: str = "",
) -> list[ProvenanceRecord]:
    """Apply the view's path filters to a list of provenance records."""
    filtered = records

    if conflicts_only:
        filtered = [record for record in filtered if record.is_conflicted]

    needle = query.strip().lower()
    if needle:
        filtered = [record for record in filtered if needle in record.path.lower()]

    return filtered
