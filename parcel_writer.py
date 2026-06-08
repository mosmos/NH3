import logging
import os
import traceback
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import arcpy
import requests
from database_updater import bump_spatial_versions, delete_shuma_rows

logger = logging.getLogger(__name__)


def read_dwg_polygons(dwg_path: str) -> List[Dict]:
    logger.info("Reading polygons from: %s", dwg_path)

    if not os.path.exists(dwg_path):
        logger.error("DWG file not found: %s", dwg_path)
        return []

    DWG_POLY = dwg_path + "\\Polygon"
    if not arcpy.Exists(DWG_POLY):
        logger.warning("No polygon feature class in DWG: %s", dwg_path)
        return []

    exp = "Layer = 'C1602_1' And Entity <> 'Insert'"
    layer_name = f"poly_{uuid.uuid4().hex[:8]}"
    try:
        poly_layer = arcpy.MakeFeatureLayer_management(DWG_POLY, layer_name, exp)
        count = int(arcpy.GetCount_management(poly_layer).getOutput(0))
        logger.info("Found %s polygon(s) matching filter: %s", count, exp)

        polygons = []
        with arcpy.da.SearchCursor(poly_layer, ["OID@", "Layer", "Entity", "SHAPE@"]) as cursor:
            for idx, (oid, layer, entity, geometry) in enumerate(cursor, 1):
                polygons.append({"id": idx, "oid": oid, "layer": layer, "entity": entity, "geometry": geometry})

        logger.info("Read %s polygon(s)", len(polygons))
        return polygons
    finally:
        arcpy.management.Delete(layer_name)


def create_polygon_dictionary(polygons: List[Dict]) -> Dict[int, Dict]:
    result = {
        p["oid"]: {"OID": p["oid"], "geometry": p["geometry"]}
        for p in polygons
        if p.get("oid") is not None and p.get("geometry") is not None
    }
    logger.info("Polygon dictionary: %s entries", len(result))
    return result


def read_dwg_points(dwg_path: str) -> List[Dict]:
    logger.info("Reading points from: %s", dwg_path)

    if not os.path.exists(dwg_path):
        logger.error("DWG file not found: %s", dwg_path)
        return []

    DWG_POINT = dwg_path + "\\Point"
    if not arcpy.Exists(DWG_POINT):
        logger.warning("No point feature class in DWG: %s", dwg_path)
        return []

    exp = "Layer = 'C1603_1' And RefName = 'C1603'"
    layer_name = f"point_{uuid.uuid4().hex[:8]}"
    try:
        point_layer = arcpy.MakeFeatureLayer_management(DWG_POINT, layer_name, exp)
        count = int(arcpy.GetCount_management(point_layer).getOutput(0))
        logger.info("Found %s point(s) matching filter: %s", count, exp)

        fields = ["OID@", "PARCEL_NAME", "GUSH", "CALC_AREA", "LEGAL_AREA", "DocName", "SHAPE@", "Layer", "RefName"]
        points = []
        with arcpy.da.SearchCursor(point_layer, fields) as cursor:
            for idx, row in enumerate(cursor, 1):
                oid, parcel_name, gush, calc_area, legal_area, docname, geometry, layer, refname = row
                xy = (geometry.firstPoint.X, geometry.firstPoint.Y)
                points.append({
                    "id": idx, "oid": oid, "layer": layer, "geometry": geometry,
                    "x": xy[0], "y": xy[1], "parcel_name": parcel_name,
                    "gush": gush, "calc_area": calc_area, "legal_area": legal_area,
                    "docname": docname, "refname": refname,
                })

        logger.info("Read %s point(s)", len(points))
        return points
    finally:
        arcpy.management.Delete(layer_name)


def create_points_dictionary(points: List[Dict]) -> Dict[int, Dict]:
    result = {}
    for p in points:
        oid = p.get("oid")
        if oid is not None:
            result[oid] = {
                "PARCEL_NAME": p.get("parcel_name"),
                "GUSH": p.get("gush"),
                "calc_area": p.get("calc_area"),
                "legal_area": p.get("legal_area"),
                "docname": p.get("docname"),
                "geometry": p.get("geometry"),
            }
    logger.info("Points dictionary: %s entries", len(result))
    return result


def validate_polygon_point_pairs(
    poly_dict: Dict[int, Dict],
    points_dict: Dict[int, Dict],
) -> List[Dict]:
    logger.info("Validating %s polygon(s) against %s point(s)", len(poly_dict), len(points_dict))

    poly_point_map: Dict[int, List[int]] = {oid: [] for oid in poly_dict}
    point_poly_map: Dict[int, List[int]] = {}

    for poly_oid, poly_data in poly_dict.items():
        for point_oid, point_data in points_dict.items():
            if poly_data["geometry"].contains(point_data["geometry"]):
                poly_point_map[poly_oid].append(point_oid)
                point_poly_map.setdefault(point_oid, []).append(poly_oid)

    valid_pairs = []
    errors = []

    for poly_oid, contained in poly_point_map.items():
        if len(contained) == 0:
            errors.append(f"Polygon OID {poly_oid} has no points")
        elif len(contained) > 1:
            errors.append(f"Polygon OID {poly_oid} contains {len(contained)} points: {contained}")
        else:
            p = points_dict[contained[0]]
            valid_pairs.append({
                "polygon_oid": poly_oid,
                "point_oid": contained[0],
                "polygon_geom": poly_dict[poly_oid]["geometry"],
                "point_geom": p["geometry"],
                "parcel_name": p["PARCEL_NAME"],
                "gush": p["GUSH"],
                "calc_area": p["calc_area"],
                "legal_area": p["legal_area"],
                "docname": p["docname"],
            })

    for point_oid in points_dict:
        if point_oid not in point_poly_map:
            errors.append(f"Point OID {point_oid} is not inside any polygon")
        elif len(point_poly_map[point_oid]) > 1:
            errors.append(f"Point OID {point_oid} is inside {len(point_poly_map[point_oid])} polygons")

    for err in errors:
        logger.warning(err)

    logger.info("Validation result: %s valid pair(s), %s error(s)", len(valid_pairs), len(errors))
    return valid_pairs


def write_parcels_to_SDE(
    sde_parcel_layer: str,
    id_hesder: str,
    k_sug_mapa: int,
    version: int,
    dwg_path: str,
    valid_pairs: List[Dict],
    id_teina: Optional[int] = None,
) -> None:
    insert_fields = [
        "id_hesder", "k_sug_mapa", "version",
        "ms_gush_hesder", "ms_chelka_hesder",
        "shetach_rashum", "shetach_mechushav",
        "tr_idkun", "shem_kovetz_autocad", "id_teina", "SHAPE@",
    ]
    with arcpy.da.InsertCursor(sde_parcel_layer, insert_fields) as cursor:
        for pair in valid_pairs:
            try:
                cursor.insertRow([
                    id_hesder, k_sug_mapa, version,
                    pair["gush"], pair["parcel_name"],
                    pair["calc_area"], pair["legal_area"],
                    datetime.now(), os.path.basename(dwg_path),
                    id_teina, pair["polygon_geom"],
                ])
                logger.info("Inserted parcel gush=%s chelka=%s", pair["gush"], pair["parcel_name"])
            except Exception as e:
                logger.error(
                    "Error inserting parcel gush=%s chelka=%s: %s\n%s",
                    pair.get("gush"), pair.get("parcel_name"), e, traceback.format_exc(),
                )


def get_id_teina_from_database(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
) -> Optional[int]:
    logger.info("Getting id_teina for id_hesder=%s k_sug_mapa=%s", id_hesder, k_sug_mapa)
    try:
        table_path = f"{sde_connection}\\DBO.NH_T_TEINAT_MAPOT_HESDER"
        if not arcpy.Exists(table_path):
            logger.error("Table not found: %s", table_path)
            return None

        where_clause = f"id_hesder = '{id_hesder}' AND k_sug_mapa = {k_sug_mapa}"
        id_teina = None
        max_val = -1
        with arcpy.da.SearchCursor(table_path, ["id_teina"], where_clause) as cursor:
            for (val,) in cursor:
                if val is not None and val > max_val:
                    max_val = val
                    id_teina = val

        if id_teina is not None:
            logger.info("Found id_teina=%s", id_teina)
        else:
            logger.warning("No id_teina found for id_hesder=%s k_sug_mapa=%s", id_hesder, k_sug_mapa)
        return id_teina

    except Exception as e:
        logger.error("Error getting id_teina: %s\n%s", e, traceback.format_exc())
        return None


def get_next_version(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
) -> int:
    # New features are always written as version=0 (rolling-zero pattern).
    # The caller must bump any existing version=0 rows first via
    # database_updater.bump_spatial_versions() before calling write functions.
    logger.info("Next version for id_hesder=%s k_sug_mapa=%s: 0 (current)", id_hesder, k_sug_mapa)
    return 0


def dissolve_and_write_hesder_boundary(
    poly_dict: Dict[int, Dict],
    id_hesder: str,
    version: int,
    valid_pairs: List[Dict],
    id_teina: Optional[int],
    k_sug_mapa: int,
    sde_connection: str = "SDE_730_3.sde",
) -> bool:
    logger.info("Dissolving %s polygon(s) into hesder boundary", len(poly_dict))
    try:
        hesder_fc = f"{sde_connection}\\DBO.NH_TG_HESDERIM"
        if not arcpy.Exists(hesder_fc):
            logger.error("Feature class not found: %s", hesder_fc)
            return False

        geometries = [d["geometry"] for d in poly_dict.values() if d.get("geometry")]
        if not geometries:
            logger.error("No geometries to dissolve")
            return False

        dissolved = geometries[0]
        for g in geometries[1:]:
            dissolved = dissolved.union(g)

        ms_gush = valid_pairs[0].get("gush") if valid_pairs else None

        with arcpy.da.InsertCursor(
            hesder_fc, ["id_hesder", "version", "id_teina", "k_sug_mapa", "ms_gush_hesder", "SHAPE@"]
        ) as cursor:
            cursor.insertRow([id_hesder, version, id_teina, k_sug_mapa, ms_gush, dissolved])

        logger.info(
            "Wrote dissolved boundary — id_hesder=%s version=%s id_teina=%s",
            id_hesder, version, id_teina,
        )
        return True

    except Exception as e:
        logger.error("Error writing hesder boundary: %s\n%s", e, traceback.format_exc())
        return False


_SHUMA_SERVICE_URL = "https://dgt-ags02/arcgis/rest/services/WM/IView2WM/MapServer/524/query"


def query_shuma_by_gush(ms_gush) -> List[Dict]:
    """
    Query MapServer layer 524 for all features where ms_gush matches.
    Returns the raw feature list (attributes + Esri JSON geometry).
    """
    logger.info("Querying shuma service for ms_gush=%s", ms_gush)
    try:
        params = {
            "where": f"ms_gush = {ms_gush}",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "2039",   # request coordinates in EPSG:2039 (Israeli TM Grid)
            "f": "json",
        }
        response = requests.get(_SHUMA_SERVICE_URL, params=params, verify=False, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            logger.error("Service returned error: %s", data["error"])
            return []

        features = data.get("features", [])
        logger.info("Shuma service returned %s feature(s) for ms_gush=%s", len(features), ms_gush)
        return features

    except requests.exceptions.RequestException as e:
        logger.error("Network error querying shuma service: %s", e)
        return []
    except Exception as e:
        logger.error("Error querying shuma service: %s\n%s", e, traceback.format_exc())
        return []


def write_shuma_intersections(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
    version: int,
    id_teina: int,
    service_features: List[Dict],
) -> None:
    """
    For each SDE parcel (version=0, id_teina) matched by ms_chelka to a service
    feature, compute the geometric intersection, calculate the overlap percentage
    as intersection_area / service_parcel_area * 100, and write to
    DBO.NH_TG_HESDER_MUTSAOT_SHUMA.

    Both layers are in EPSG:2039 — no reprojection.
    """
    logger.info(
        "Computing shuma intersections for id_teina=%s, %s service features",
        id_teina, len(service_features),
    )

    # Build a lookup: ms_chelka -> {attributes, arcpy geometry}
    # Both layers are in EPSG:2039 — assign SR explicitly so intersect() works.
    service_by_chelka: Dict = {}
    spatial_ref = arcpy.SpatialReference(2039)
    for feat in service_features:
        attrs = feat.get("attributes", {})
        geom_json = feat.get("geometry")
        chelka = attrs.get("ms_chelka")
        if chelka is None or geom_json is None:
            continue
        try:
            import json as _json
            # Embed the spatial reference into the geometry JSON so arcpy
            # assigns EPSG:2039 correctly when converting.
            geom_with_sr = dict(geom_json)
            geom_with_sr["spatialReference"] = {"wkid": 2039}
            geom = arcpy.AsShape(geom_with_sr, True)
        except Exception as e:
            logger.warning("Could not convert service geometry for ms_chelka=%s: %s", chelka, e)
            continue
        service_by_chelka[chelka] = {"attrs": attrs, "geom": geom}

    logger.info("Service lookup built: %s chelka entries", len(service_by_chelka))

    # Read SDE parcels for this id_teina
    parcel_fc = f"{sde_connection}\\DBO.NH_TG_HESDERIM_MUTSAOT"
    shuma_fc  = f"{sde_connection}\\DBO.NH_TG_HESDER_MUTSAOT_SHUMA"

    if not arcpy.Exists(shuma_fc):
        logger.error("Target table not found: %s", shuma_fc)
        return

    # Delete previous rows for this hesder before inserting the new set
    delete_shuma_rows(sde_connection, id_hesder, k_sug_mapa)

    insert_fields = [
        "id_hesder", "k_sug_mapa", "version",
        "ms_gush_hesder", "ms_chelka_hesder",
        "ms_gush", "ms_chelka",
        "achuz_chelkat_shuma_bemutsaat",
    ]

    where_clause = f"id_teina = {id_teina}"
    read_fields  = ["ms_gush_hesder", "ms_chelka_hesder", "SHAPE@"]

    inserted = 0
    skipped  = 0

    with arcpy.da.SearchCursor(parcel_fc, read_fields, where_clause) as search_cur:
        with arcpy.da.InsertCursor(shuma_fc, insert_fields) as insert_cur:
            for ms_gush_hesder, ms_chelka_hesder, sde_geom in search_cur:
                # Match service feature by chelka number
                service = service_by_chelka.get(ms_chelka_hesder)
                if service is None:
                    logger.warning(
                        "No service feature for ms_chelka_hesder=%s — skipping", ms_chelka_hesder
                    )
                    skipped += 1
                    continue

                service_geom  = service["geom"]
                service_attrs = service["attrs"]

                # Compute geometric intersection (4 = polygon output dimension)
                try:
                    intersection = sde_geom.intersect(service_geom, 4)
                except Exception as e:
                    logger.warning(
                        "Intersection failed for chelka=%s: %s", ms_chelka_hesder, e
                    )
                    skipped += 1
                    continue

                if intersection is None or intersection.area == 0:
                    logger.warning(
                        "Zero-area intersection for chelka=%s — skipping", ms_chelka_hesder
                    )
                    skipped += 1
                    continue

                achuz_chelkat = (intersection.area / service_geom.area * 100) if service_geom.area else 0

                insert_cur.insertRow([
                    int(id_hesder), k_sug_mapa, version,
                    ms_gush_hesder, ms_chelka_hesder,
                    service_attrs.get("ms_gush"), service_attrs.get("ms_chelka"),
                    round(achuz_chelkat, 4),
                ])
                logger.info(
                    "Inserted shuma row chelka=%s overlap=%.2f%%",
                    ms_chelka_hesder, achuz_chelkat,
                )
                inserted += 1

    logger.info(
        "Shuma intersections complete: %s inserted, %s skipped", inserted, skipped
    )


def process_dwg_to_sde(
    dwg_path: str,
    id_hesder: str,
    k_sug_mapa: int,
    sde_connection: str = "SDE_730_3.sde",
) -> bool:
    logger.info("DWG-to-SDE start — dwg=%s id_hesder=%s k_sug_mapa=%s", dwg_path, id_hesder, k_sug_mapa)
    try:
        id_teina = get_id_teina_from_database(sde_connection, id_hesder, k_sug_mapa)
        version = get_next_version(sde_connection, id_hesder, k_sug_mapa)

        polygons = read_dwg_polygons(dwg_path)
        if not polygons:
            logger.error("No polygons found in DWG")
            return False

        points = read_dwg_points(dwg_path)
        if not points:
            logger.error("No points found in DWG")
            return False

        poly_dict = create_polygon_dictionary(polygons)
        points_dict = create_points_dictionary(points)

        valid_pairs = validate_polygon_point_pairs(poly_dict, points_dict)
        if not valid_pairs:
            logger.error("No valid polygon-point pairs")
            return False

        # Promote any existing version=0 rows to their real historical version
        # before writing the new features as version=0.
        bump_spatial_versions(sde_connection, id_hesder, k_sug_mapa)

        parcel_layer = f"{sde_connection}\\DBO.NH_TG_HESDERIM_MUTSAOT"
        write_parcels_to_SDE(parcel_layer, id_hesder, k_sug_mapa, version, dwg_path, valid_pairs, id_teina)

        success = dissolve_and_write_hesder_boundary(
            poly_dict, id_hesder, version, valid_pairs, id_teina, k_sug_mapa, sde_connection
        )
        if not success:
            logger.error("Failed to write hesder boundary")
            return False

        # Step h: intersect SDE parcels with cadastral service and write to SHUMA table
        ms_gush = valid_pairs[0].get("gush") if valid_pairs else None
        if ms_gush is not None:
            service_features = query_shuma_by_gush(ms_gush)
            if service_features:
                write_shuma_intersections(
                    sde_connection, id_hesder, k_sug_mapa, version, id_teina, service_features
                )
            else:
                logger.warning("No service features returned for ms_gush=%s — skipping shuma step", ms_gush)
        else:
            logger.warning("No gush value available — skipping shuma step")

        logger.info("DWG-to-SDE completed — id_hesder=%s version=%s", id_hesder, version)
        return True

    except Exception as e:
        logger.error("Error in process_dwg_to_sde: %s\n%s", e, traceback.format_exc())
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = process_dwg_to_sde(
        dwg_path=r"C:\DEV\NH_HESDER\CAD_FILES\80119.dwg",
        id_hesder="906090",
        k_sug_mapa=1,
        sde_connection="SDE_730_3.sde",
    )
