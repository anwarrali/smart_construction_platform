"""Cached IFC geometry generation for the interactive web viewer.

The BIMGEO1 artifact is intentionally simple and stream-friendly:
8-byte magic, uint32 JSON-header length, UTF-8 header, then contiguous
float32 positions, uint32 ExpressIDs-per-vertex, and uint32 indices.
"""
from __future__ import annotations

import json
import math
import multiprocessing
import os
import queue
import struct
import tempfile
import time
from array import array
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ifc import IFCElement, IFCModelVersion, IFCSpatialNode
from app.services.private_storage import private_storage

MAGIC = b"BIMGEO1\x00"


#: Cap on per-element boxes carried back from the worker. Bounds travel through
#: the result queue, so an unbounded federated model could otherwise return a
#: payload far larger than the mesh summary it accompanies.
MAX_ELEMENT_BOUNDS = 200_000


def build_geometry_artifact(
    source: Path,
    target: Path,
    selectable_step_ids: set[int],
    *,
    workers: int,
    max_vertices: int,
    version_id: str,
    source_hash: str,
) -> dict:
    """Convert one IFC source to the documented BIMGEO1 artifact.

    This function deliberately has no database dependency so it can run in an
    isolated process with a hard timeout and can be exercised by a real mesh
    integration test.
    """
    import ifcopenshell
    import ifcopenshell.geom

    model = ifcopenshell.open(str(source))
    geometry_settings = ifcopenshell.geom.settings()
    geometry_settings.set(geometry_settings.USE_WORLD_COORDS, True)
    iterator = ifcopenshell.geom.iterator(geometry_settings, model, max(1, workers))
    if not iterator.initialize():
        raise RuntimeError("IfcOpenShell did not produce any renderable geometry")
    positions = array("d")
    express_ids = array("I")
    indices = array("I")
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    shape_count = skipped_count = unmapped_shape_count = triangle_count = 0
    truncated = False
    # Per-element axis-aligned bounds in *world* coordinates, captured here
    # because this is the only place the real tessellated extent of each
    # element is known. They are what lets coordination analysis cite where an
    # element actually is, instead of guessing from names.
    element_bounds: dict[int, dict] = {}
    while True:
        try:
            shape = iterator.get()
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            local_vertex_count = len(verts) // 3
            if int(shape.id) not in selectable_step_ids:
                unmapped_shape_count += 1
            elif local_vertex_count and faces:
                if len(express_ids) + local_vertex_count > max_vertices:
                    truncated = True
                    break
                vertex_offset = len(express_ids)
                positions.extend(float(value) for value in verts)
                express_ids.extend([int(shape.id)] * local_vertex_count)
                indices.extend(vertex_offset + int(value) for value in faces)
                triangle_count += len(faces) // 3
                shape_count += 1
                low = [0.0, 0.0, 0.0]
                high = [0.0, 0.0, 0.0]
                for axis in range(3):
                    values = verts[axis::3]
                    low[axis] = float(min(values))
                    high[axis] = float(max(values))
                    minimum[axis] = min(minimum[axis], low[axis])
                    maximum[axis] = max(maximum[axis], high[axis])
                if len(element_bounds) < MAX_ELEMENT_BOUNDS:
                    element_bounds[int(shape.id)] = {"min": low, "max": high}
        except Exception:
            skipped_count += 1
        if not iterator.next():
            break
    if not shape_count:
        raise RuntimeError("The IFC contains metadata but no renderable geometry was produced")
    source_minimum = list(minimum)
    source_maximum = list(maximum)
    coordinate_origin = [(minimum[axis] + maximum[axis]) / 2 for axis in range(3)]
    for index in range(len(positions)):
        positions[index] -= coordinate_origin[index % 3]
    positions = array("f", positions)
    minimum = [source_minimum[axis] - coordinate_origin[axis] for axis in range(3)]
    maximum = [source_maximum[axis] - coordinate_origin[axis] for axis in range(3)]
    header = {
        "format": "BIMGEO1", "versionId": version_id, "sourceHash": source_hash,
        "vertexCount": len(express_ids), "indexCount": len(indices), "triangleCount": triangle_count,
        "shapeCount": shape_count, "skippedShapeCount": skipped_count,
        "unmappedShapeCount": unmapped_shape_count,
        "bounds": {"min": minimum, "max": maximum},
        "coordinateOrigin": coordinate_origin,
        "sourceBounds": {"min": source_minimum, "max": source_maximum},
        "layout": [
            {"name": "position", "componentType": "FLOAT32", "components": 3, "count": len(express_ids)},
            {"name": "expressId", "componentType": "UINT32", "components": 1, "count": len(express_ids)},
            {"name": "index", "componentType": "UINT32", "components": 1, "count": len(indices)},
        ],
        "partial": bool(truncated or skipped_count), "truncated": truncated,
        "boundsCaptured": len(element_bounds),
        "boundsTruncated": len(element_bounds) >= MAX_ELEMENT_BOUNDS,
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        with temporary.open("wb") as output:
            output.write(MAGIC); output.write(struct.pack("<I", len(encoded))); output.write(encoded)
            positions.tofile(output); express_ids.tofile(output); indices.tofile(output)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    header["byteSize"] = target.stat().st_size
    # Carried inside the header so the worker keeps its single-value contract.
    # `generate_geometry` lifts this out before the header is stored, because
    # per-element boxes belong on the elements, not in the version's stats.
    header["elementBounds"] = element_bounds
    return header


def _geometry_worker(result_queue, args: tuple) -> None:
    try:
        result_queue.put({"ok": True, "header": build_geometry_artifact(*args[:3], **args[3])})
    except BaseException as exc:  # the parent must receive native-library failures too
        result_queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


#: How often the parent checks for a result and for a dead worker.
GEOMETRY_POLL_SECONDS = 0.5
#: After the worker exits, how long a result may still be in flight on the queue.
GEOMETRY_EXIT_GRACE_SECONDS = 2.0


def _build_with_timeout(args: tuple, timeout_seconds: int) -> dict:
    """Run the tessellator in a child and collect its result, within a deadline.

    The result is read from the queue *while* the child runs, never after
    joining it. A child cannot exit until the data it put on a queue has been
    taken out — the queue's feeder thread blocks on a full pipe — so the old
    `join(timeout)`-then-read order deadlocked whenever the result outgrew the
    pipe buffer (~64 KB). Per-element bounds put a 1,636-element model well
    past that, and every such model "timed out" after the full 900 seconds
    while the actual tessellation took seconds. See "Joining processes that use
    queues" in the `multiprocessing` documentation.
    """
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_geometry_worker, args=(result_queue, args), daemon=False)
    process.start()
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            try:
                result = result_queue.get(timeout=max(0.1, min(GEOMETRY_POLL_SECONDS, remaining)))
                break
            except queue.Empty:
                if not process.is_alive():
                    try:
                        result = result_queue.get(timeout=GEOMETRY_EXIT_GRACE_SECONDS)
                        break
                    except queue.Empty:
                        raise RuntimeError(f"Geometry worker exited without a result (exit code {process.exitcode})") from None
                if remaining <= 0:
                    raise TimeoutError(f"IfcOpenShell geometry conversion exceeded {timeout_seconds} seconds") from None
    finally:
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
        result_queue.close()
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Geometry worker failed")
    return result["header"]


def _store_element_bounds(db: Session, version: IFCModelVersion, bounds: dict) -> int:
    """Attach each element's real world-coordinate extent to its own row.

    The tessellator is the only component that knows where an element actually
    sits: `IfcLocalPlacement` chains, mapped representations and transformed
    geometry make placement unreadable from the STEP attributes alone, which is
    why the parser leaves `bounding_box_json` empty. Storing the result here
    turns "which elements might interfere" from a guess into arithmetic.

    Keyed by IFC STEP id (the ExpressID the viewer already maps), so the same
    identity links a box, a mesh and a database row.
    """
    if not bounds:
        return 0
    rows = db.query(IFCElement.id, IFCElement.metadata_json["stepId"].astext).filter(
        IFCElement.version_id == version.id
    ).all()
    # The worker keys by int STEP id; the database returns it as text. Normalise
    # both to strings, or every lookup silently misses and no element ever gets
    # a box — which looks exactly like a model that has no geometry.
    by_step = {str(key): value for key, value in bounds.items()}
    units = (version.model_summary_json or {}).get("units") or {}
    updates = []
    for element_id, step_id in rows:
        box = by_step.get(str(step_id)) if step_id else None
        if not box:
            continue
        updates.append({
            "id": element_id,
            "bounding_box_json": {
                "min": box["min"], "max": box["max"],
                "size": [box["max"][axis] - box["min"][axis] for axis in range(3)],
                "coordinateSpace": "IFC_WORLD",
                "lengthUnit": units.get("LENGTHUNIT"),
                "source": "IFC_GEOMETRY_TESSELLATION",
            },
        })
    if not updates:
        return 0
    # ORM bulk UPDATE by primary key: one statement for the whole revision
    # rather than one round trip per element, which matters on models with
    # hundreds of thousands of them.
    db.execute(update(IFCElement), updates)
    return len(updates)


def generate_geometry(db: Session, version_id) -> dict:
    version = db.get(IFCModelVersion, version_id)
    if not version:
        raise ValueError("IFC version does not exist")
    if not settings.IFC_GEOMETRY_ENABLED:
        version.geometry_status = "GEOMETRY_NOT_GENERATED"
        version.geometry_error = "Geometry processing is disabled by server configuration."
        db.commit()
        return {"status": version.geometry_status}
    version.geometry_status = "GEOMETRY_PROCESSING"
    version.geometry_error = None
    db.commit()
    started = perf_counter()
    try:
        selectable_step_ids = {
            int(value) for (value,) in db.query(IFCElement.metadata_json["stepId"].astext)
            .filter(IFCElement.version_id == version.id).all() if value
        }
        selectable_step_ids.update(
            int(value) for (value,) in db.query(IFCSpatialNode.metadata_json["stepId"].astext)
            .filter(IFCSpatialNode.version_id == version.id, IFCSpatialNode.node_type.in_(["BUILDING", "STOREY", "SPACE"])).all() if value
        )
        # The website's 3D viewer was removed, and with it the only reader of
        # the mesh file. Tessellation still runs because it is what measures
        # each element's real extent — interference detection and the IFC
        # knowledge context use those bounds — but the mesh is written to a
        # scratch directory and discarded instead of being stored. Existing
        # stored meshes and `geometry_storage_key` values are left untouched.
        with tempfile.TemporaryDirectory(prefix="ifc-geometry-") as scratch, \
                private_storage.local_path(version.storage_key) as source:
            target = Path(scratch) / "mesh.bimgeom"
            args = (
                source, target, selectable_step_ids,
                {"workers": settings.IFC_GEOMETRY_WORKERS, "max_vertices": settings.IFC_GEOMETRY_MAX_VERTICES,
                 "version_id": str(version.id), "source_hash": version.file_hash},
            )
            header = _build_with_timeout(args, settings.IFC_GEOMETRY_TIMEOUT_SECONDS)
        bounds = header.pop("elementBounds", None) or {}
        header["boundsStored"] = _store_element_bounds(db, version, bounds)
        duration_ms = int((perf_counter() - started) * 1000)
        header["durationMs"] = duration_ms
        version.geometry_stats_json = header
        version.geometry_generated_at = datetime.now(timezone.utc)
        version.geometry_status = "GEOMETRY_PARTIAL" if header["partial"] else "GEOMETRY_READY"
        version.geometry_error = None
        db.commit()
        return {"status": version.geometry_status, **header}
    except Exception as exc:
        version = db.get(IFCModelVersion, version_id)
        version.geometry_status = "GEOMETRY_FAILED"
        version.geometry_error = str(exc)[:4000]
        version.geometry_stats_json = {"durationMs": int((perf_counter() - started) * 1000)}
        db.commit()
        return {"status": version.geometry_status, "error": version.geometry_error}
