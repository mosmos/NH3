import logging
import traceback
from datetime import datetime
from typing import Optional

import arcpy

logger = logging.getLogger(__name__)

_TABLE = "dbo.nh_t_teinat_mapot_hesder"


def calculate_next_id_teina(
    sde_connection: str,
    table_name: str = _TABLE,
) -> int:
    try:
        table_path = f"{sde_connection}\\{table_name}"

        if not arcpy.Exists(table_path):
            logger.error("Table does not exist: %s", table_path)
            return 1

        max_id = 0
        with arcpy.da.SearchCursor(table_path, ["id_teina"]) as cursor:
            for (val,) in cursor:
                if val is not None and val > max_id:
                    max_id = val

        next_id = max_id + 1
        logger.info("Next id_teina: %s (max was %s)", next_id, max_id)
        return next_id

    except Exception as e:
        logger.error("Error calculating id_teina: %s\n%s", e, traceback.format_exc())
        return 1


def calculate_next_version(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
    table_name: str = _TABLE,
) -> int:
    try:
        table_path = f"{sde_connection}\\{table_name}"

        if not arcpy.Exists(table_path):
            logger.error("Table does not exist: %s", table_path)
            return 1

        where_clause = f"id_hesder = {int(id_hesder)} AND k_sug_mapa = {k_sug_mapa}"
        max_version = 0
        with arcpy.da.SearchCursor(table_path, ["version"], where_clause) as cursor:
            for (val,) in cursor:
                if val is not None and val > max_version:
                    max_version = val

        next_ver = max_version + 1
        logger.info(
            "Next version for id_hesder=%s k_sug_mapa=%s: %s (max was %s)",
            id_hesder, k_sug_mapa, next_ver, max_version,
        )
        return next_ver

    except Exception as e:
        logger.error("Error calculating version: %s\n%s", e, traceback.format_exc())
        return 1


def write_to_mapot_hesder(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
    dwg_path: str,
    mishtamesh: Optional[str] = None,
    table_name: str = _TABLE,
) -> Optional[int]:
    try:
        table_path = f"{sde_connection}\\{table_name}"

        if not arcpy.Exists(table_path):
            logger.error("Table does not exist: %s", table_path)
            return None

        table_fields = [f.name for f in arcpy.ListFields(table_path)]

        new_id_teina = calculate_next_id_teina(sde_connection, table_name)
        new_version = calculate_next_version(sde_connection, id_hesder, k_sug_mapa, table_name)
        now = datetime.now()

        # version=0 means "current" (rolling-zero, same as spatial tables).
        # real_version holds the permanent chronological counter (1, 2, 3…).
        fields = ["id_teina", "id_hesder", "k_sug_mapa", "dwg_path", "k_status_teina", "version", "tr_version"]
        values = [new_id_teina, int(id_hesder), k_sug_mapa, dwg_path, 1, 0, now]

        if "real_version" in table_fields:
            fields.append("real_version")
            values.append(new_version)

        if "mishtamesh" in table_fields and mishtamesh:
            fields.append("mishtamesh")
            values.append(mishtamesh)

        logger.info(
            "Inserting record — id_teina=%s id_hesder=%s k_sug_mapa=%s real_version=%s mishtamesh=%s",
            new_id_teina, id_hesder, k_sug_mapa, new_version, mishtamesh,
        )

        with arcpy.da.InsertCursor(table_path, fields) as cursor:
            cursor.insertRow(values)

        logger.info("Record inserted — id_teina=%s", new_id_teina)
        return new_id_teina

    except Exception as e:
        logger.error("Error inserting record: %s\n%s", e, traceback.format_exc())
        return None


def verify_inserted_record(
    sde_connection: str,
    id_teina: int,
    table_name: str = _TABLE,
) -> Optional[dict]:
    try:
        table_path = f"{sde_connection}\\{table_name}"

        if not arcpy.Exists(table_path):
            logger.error("Table does not exist: %s", table_path)
            return None

        table_fields = [f.name for f in arcpy.ListFields(table_path)]
        fields_to_read = [
            f for f in
            ["id_teina", "id_hesder", "k_sug_mapa", "dwg_path", "version", "mishtamesh", "tr_version", "k_status_teina"]
            if f in table_fields
        ]

        where_clause = f"id_teina = {int(id_teina)}"
        with arcpy.da.SearchCursor(table_path, fields_to_read, where_clause) as cursor:
            for row in cursor:
                record = dict(zip(fields_to_read, row))
                logger.info("Verified record id_teina=%s: %s", id_teina, record)
                return record

        logger.warning("No record found for id_teina=%s", id_teina)
        return None

    except Exception as e:
        logger.error("Error verifying record: %s\n%s", e, traceback.format_exc())
        return None
