"""Lossless native topology preparation for the loop-closure solver."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from cave_closure import prepare_arrays

from stalagmight_lib.graph import SHOT_START_INDEX_FLAG


@dataclass(frozen=True)
class NativeLoopClosureResult:
    fingerprint: str
    report: object

    @property
    def coordinates(self):
        return self.report.coordinates

    @property
    def observations(self):
        return self.report.observations

    def require_converged(self):
        self.report.require_converged()
        return self

    def to_json(self):
        return self.report.to_json()


@dataclass(frozen=True)
class NativeLoopClosureSnapshot:
    prepared: object
    station_ids: tuple[str, ...]
    source_json: str
    fingerprint: str
    legs: tuple[tuple[str, str, str, str, float, str], ...]
    mode: str

    def solve(self, **kwargs):
        result = self.prepared.solve(**kwargs)
        result.require_converged()
        return NativeLoopClosureResult(self.fingerprint, result)

    def validate_source(self, source):
        original = getattr(source, "_native", source)
        if original.model_dump_json() != self.source_json:
            raise ValueError("native source no longer matches its preparation")


def prepare_loop_closure(
    source, *, mode, sigma_m, baseline_policy, preserved_z_policy=None, controls=None
):
    """Prepare schema-18/19 native topology without using display geometry.

    Baseline policy must explicitly be 'stored_measurements'. Aligned non-Move
    closure evidence requires 'accept_potentially_adjusted_measurements'. Root
    layout positions and geometry locks remain metadata. GPS datums require caller
    projected local-ENU controls; they are never treated as ENU coordinates.
    """

    if baseline_policy not in {
        "stored_measurements",
        "accept_potentially_adjusted_measurements",
    }:
        raise ValueError("explicit native measurement baseline policy is required")
    if (
        any(c.is_aligned and c.strategy != "Move" for c in source.loop_closures)
        and baseline_policy != "accept_potentially_adjusted_measurements"
    ):
        raise ValueError(
            "aligned native closures indicate uncertain raw-measurement provenance"
        )
    if mode == "horizontal" and preserved_z_policy != "raw_endpoint_depth":
        raise ValueError(
            "horizontal loop closure requires raw_endpoint_depth preservation policy"
        )
    if not math.isfinite(sigma_m) or sigma_m <= 0:
        raise ValueError("sigma_m must be positive and finite")
    controls = {} if controls is None else controls
    if source.zero_datums and any(
        (d.section_id, d.station_index) not in controls for d in source.zero_datums
    ):
        raise ValueError(
            "native geographic datums require caller-projected ENU controls"
        )
    stations, depths, references, rows, relationships = _native_rows(source, mode)
    for merge in source.station_merges:
        relationships.append(
            (
                f"merge:{merge.id}",
                "equivalent",
                references[merge.station_a_section, merge.station_a_index],
                references[merge.station_b_section, merge.station_b_index],
                (0.0, 0.0, 0.0),
            )
        )
    for closure in source.loop_closures:
        u = references[closure.station_a_section, closure.station_a_index]
        v = references[closure.station_b_section, closure.station_b_index]
        # Only native activation asserts identity; recording alone is evidence.
        kind = "equivalent" if closure.is_aligned else "recorded"
        relationships.append((f"closure:{closure.id}", kind, u, v, (0.0, 0.0, 0.0)))
    ids = sorted(stations)
    index = {name: i for i, name in enumerate(ids)}
    variance = sigma_m**2
    covariance = [[variance, 0.0, 0.0], [0.0, variance, 0.0], [0.0, 0.0, variance]]
    dimension = 3 if mode == "spatial" else 2
    prepared = prepare_arrays(
        ids,
        [r[0] for r in rows],
        [(index[u], index[v]) for _, u, v, _ in rows],
        [r[3] for r in rows],
        [covariance for _ in rows],
        mode=mode,
        preserved_z=([depths[name] for name in ids] if mode == "horizontal" else None),
        controls=[
            (
                f"control:{section}:{station}",
                index[references[section, station]],
                list(range(dimension)),
                list(value[:dimension]),
                None,
            )
            for (section, station), value in sorted(controls.items())
        ],
        relationships=[
            (identity, kind, index[u], index[v], value)
            for identity, kind, u, v, value in relationships
        ],
        reading_ids=[
            [
                f"{r[0]}/length",
                f"{r[0]}/bearing",
                f"{r[0]}/depth_in",
                f"{r[0]}/depth_out",
            ]
            for r in rows
        ],
        provenance=[
            "Native topology; no migrations or layout cycle cuts",
            baseline_policy,
            (
                "Independent Cartesian placement covariance; "
                "depth readings not modeled as separate factors"
            ),
        ],
    )
    source_json = source.model_dump_json()
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                source_json,
                mode,
                sigma_m,
                baseline_policy,
                preserved_z_policy,
                sorted(controls.items()),
            ],
            allow_nan=False,
        ).encode()
    ).hexdigest()
    shots = ((section, shot) for section in source.sections for shot in section.shots)
    legs = tuple(
        (
            row[0],
            row[1],
            row[2],
            section.name or f"Section {section.id}",
            shot.depth_out,
            section.color,
        )
        for row, (section, shot) in zip(rows, shots, strict=True)
    )
    return NativeLoopClosureSnapshot(
        prepared, tuple(ids), source_json, fingerprint, legs, mode
    )


def _native_rows(source, mode):
    explicit = source.schema_version == 19 and source.shot_graph.explicit
    numbers = source.live_numbers() if source.schema_version == 19 else {}
    origins = (
        {entry.number: entry.parent for entry in source.shot_graph.origins}
        if explicit
        else {}
    )
    live = set(numbers.values())
    stations, depths, references, rows, relationships = {}, {}, {}, [], []
    overrides = (
        {entry.number: entry.reference for entry in source.shot_graph.azimuth_overrides}
        if source.shot_graph is not None
        else {}
    )
    for section in source.sections:
        if not section.shots:
            name = f"section:{section.id}/empty"
            stations[name] = None
            depths[name] = 0.0
            references[section.id, 0] = name
        for shot in section.shots:
            number = numbers.get((section.id, shot.sequence_order))
            identity = (
                f"section:{section.id}/shot:"
                f"{number if number is not None else shot.sequence_order}"
            )
            if explicit:
                u, v = f"shot:{number}/start", f"shot:{number}/end"
                start_ref = (
                    0
                    if shot.sequence_order == 0
                    else SHOT_START_INDEX_FLAG | shot.sequence_order
                )
                references[section.id, start_ref] = u
                references[section.id, shot.sequence_order + 1] = v
            else:
                u, v = (
                    f"section:{section.id}/station:{shot.sequence_order}",
                    f"section:{section.id}/station:{shot.sequence_order + 1}",
                )
                references[section.id, shot.sequence_order] = u
                references[section.id, shot.sequence_order + 1] = v
            stations[u] = stations[v] = None
            # Shared sequential endpoints may carry conflicting depth readings.
            # Preserve Z through the named endpoint policy, never average silently.
            for name, depth in ((u, -shot.depth_in), (v, -shot.depth_out)):
                if mode == "horizontal" and name in depths and depths[name] != depth:
                    raise ValueError(
                        f"{identity}: conflicting preserved endpoint depths; "
                        "supply a different explicit model"
                    )
                depths[name] = depth
            delta = _shot_delta(
                source, section, shot, number, overrides=overrides, identity=identity
            )
            rows.append((identity, u, v, delta))
            if explicit:
                parent = origins[number]
                while parent is not None and parent not in live:
                    parent = origins[parent]  # lineage was validated by the reader
                if parent is not None:
                    relationships.append(
                        (
                            f"origin:{number}",
                            "equivalent",
                            u,
                            f"shot:{parent}/end",
                            (0.0, 0.0, 0.0),
                        )
                    )
    return stations, depths, references, rows, relationships


def _shot_delta(source, section, shot, number, *, overrides, identity):
    if shot.kind != 0:
        raise ValueError(
            f"{identity}: non-normal native shot requires "
            "an explicit relationship interpretation"
        )
    t = shot.depth_out - shot.depth_in
    if shot.length < abs(t):
        raise ValueError(f"{identity}: length shorter than depth difference")
    horizontal = math.sqrt((shot.length - abs(t)) * (shot.length + abs(t)))
    bearing = (
        shot.azimuth_in + ((shot.azimuth_out - shot.azimuth_in + 540) % 360 - 180) / 2
    )
    reference = overrides.get(number)
    if reference is not None:
        correction = reference.correction
    elif section.azimuth_north is not None:
        correction = section.azimuth_correction or 0.0
    elif source.project.default_azimuth_reference is not None:
        correction = source.project.default_azimuth_reference.correction
    else:
        correction = 0.0
    bearing = math.radians(bearing + correction)
    return horizontal * math.sin(bearing), horizontal * math.cos(bearing), -t
