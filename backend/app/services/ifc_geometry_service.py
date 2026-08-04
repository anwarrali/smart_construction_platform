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
from array import array
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ifc import IFCElement, IFCModelVersion, IFCSpatialNode
from app.services.file_storage import resolve_private_storage_key

MAGIC = b"BIMGEO1\x00"


def geometry_storage_key(version_id) -> str:
    return f"ifc_geometry/{version_id}.bimgeom"


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
                for axis in range(3):
                    values = verts[axis::3]
                    minimum[axis] = min(minimum[axis], min(values))
                    maximum[axis] = max(maximum[axis], max(values))
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
    return header


def _geometry_worker(result_queue, args: tuple) -> None:
    try:
        result_queue.put({"ok": True, "header": build_geometry_artifact(*args[:3], **args[3])})
    except BaseException as exc:  # the parent must receive native-library failures too
        result_queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _build_with_timeout(args: tuple, timeout_seconds: int) -> dict:
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_geometry_worker, args=(result_queue, args), daemon=False)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise TimeoutError(f"IfcOpenShell geometry conversion exceeded {timeout_seconds} seconds")
    try:
        result = result_queue.get_nowait()
    except queue.Empty as exc:
        raise RuntimeError(f"Geometry worker exited without a result (exit code {process.exitcode})") from exc
    finally:
        result_queue.close()
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "Geometry worker failed")
    return result["header"]


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
    target: Path | None = None
    try:
        selectable_step_ids = {
            int(value) for (value,) in db.query(IFCElement.metadata_json["stepId"].astext)
            .filter(IFCElement.version_id == version.id).all() if value
        }
        selectable_step_ids.update(
            int(value) for (value,) in db.query(IFCSpatialNode.metadata_json["stepId"].astext)
            .filter(IFCSpatialNode.version_id == version.id, IFCSpatialNode.node_type.in_(["BUILDING", "STOREY", "SPACE"])).all() if value
        )
        key = geometry_storage_key(version.id)
        target = resolve_private_storage_key(key)
        args = (
            resolve_private_storage_key(version.storage_key), target, selectable_step_ids,
            {"workers": settings.IFC_GEOMETRY_WORKERS, "max_vertices": settings.IFC_GEOMETRY_MAX_VERTICES,
             "version_id": str(version.id), "source_hash": version.file_hash},
        )
        header = _build_with_timeout(args, settings.IFC_GEOMETRY_TIMEOUT_SECONDS)
        duration_ms = int((perf_counter() - started) * 1000)
        header["durationMs"] = duration_ms
        version.geometry_storage_key = key
        version.geometry_stats_json = header
        version.geometry_generated_at = datetime.now(timezone.utc)
        version.geometry_status = "GEOMETRY_PARTIAL" if header["partial"] else "GEOMETRY_READY"
        version.geometry_error = None
        db.commit()
        return {"status": version.geometry_status, **header}
    except Exception as exc:
        if target:
            target.with_suffix(target.suffix + ".tmp").unlink(missing_ok=True)
        version = db.get(IFCModelVersion, version_id)
        version.geometry_status = "GEOMETRY_FAILED"
        version.geometry_error = str(exc)[:4000]
        version.geometry_stats_json = {"durationMs": int((perf_counter() - started) * 1000)}
        db.commit()
        return {"status": version.geometry_status, "error": version.geometry_error}
