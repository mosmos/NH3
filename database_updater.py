import logging
import traceback
import pyodbc
import arcpy
from typing import Optional

from config import DB_PASSWORD, DB_USER

logger = logging.getLogger(__name__)

_STATUS_TEXT = {1: "Job Started", 5: "Error", 6: "Completed Successfully"}


def get_connection_string_from_sde(sde_connection: str) -> Optional[str]:
    try:
        desc = arcpy.Describe(sde_connection)
        props = desc.connectionProperties
        conn_str = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server={props.server};"
            f"Database={props.database};"
            f"UID={DB_USER};PWD={DB_PASSWORD};"
        )
        logger.info("[ODBC] Connection string built for server=%s database=%s", props.server, props.database)
        return conn_str
    except Exception as e:
        logger.error("[ODBC] Error getting connection string: %s\n%s", e, traceback.format_exc())
        return None


def update_status_teina(
    sde_connection: str,
    id_teina: int,
    status_value: int,
    table_name: str = "dbo.nh_t_teinat_mapot_hesder",
) -> bool:
    status_text = _STATUS_TEXT.get(status_value, f"Status {status_value}")
    logger.info(
        "[ODBC] Updating k_status_teina=%s (%s) for id_teina=%s",
        status_value, status_text, id_teina,
    )

    conn = None
    cursor = None
    try:
        conn_str = get_connection_string_from_sde(sde_connection)
        if not conn_str:
            logger.error("[ODBC] Failed to get connection string")
            return False

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        sql = f"UPDATE {table_name} SET k_status_teina = ? WHERE id_teina = ?"
        cursor.execute(sql, (status_value, id_teina))
        rows_affected = cursor.rowcount
        conn.commit()

        if rows_affected > 0:
            logger.info("[ODBC] Updated %s row(s) — k_status_teina=%s (%s)", rows_affected, status_value, status_text)
            return True
        else:
            logger.warning("[ODBC] No record found with id_teina=%s", id_teina)
            return False

    except pyodbc.Error as e:
        logger.error("[ODBC] Database error: %s", e)
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        logger.error("[ODBC] Error updating status: %s\n%s", e, traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def bump_spatial_versions(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
) -> int:
    """
    Before writing new features (always version=0), promote the existing
    version=0 rows in both spatial tables to their real historical version.

    Real historical version = MAX(version WHERE version > 0) + 1, or 1 if
    no prior historical rows exist.

    Returns the bump-to version number (i.e. what the old 0 became), or 0
    if there were no version=0 rows to bump.
    """
    logger.info(
        "Bumping version=0 rows in spatial tables for id_hesder=%s k_sug_mapa=%s",
        id_hesder, k_sug_mapa,
    )
    try:
        conn_str = get_connection_string_from_sde(sde_connection)
        if not conn_str:
            logger.error("Failed to get connection string for version bump")
            return 0

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        bump_to = None

        # Spatial tables: bump version=0 → MAX(historical)+1
        for table in ("DBO.NH_TG_HESDERIM_MUTSAOT", "DBO.NH_TG_HESDERIM"):
            cursor.execute(
                f"SELECT ISNULL(MAX(version), 0) FROM {table} "
                f"WHERE id_hesder = ? AND k_sug_mapa = ? AND version > 0",
                (id_hesder, k_sug_mapa),
            )
            row = cursor.fetchone()
            max_historical = row[0] if row is not None else 0
            table_bump_to = max_historical + 1

            cursor.execute(
                f"UPDATE {table} SET version = ? "
                f"WHERE id_hesder = ? AND k_sug_mapa = ? AND version = 0",
                (table_bump_to, id_hesder, k_sug_mapa),
            )
            rows = cursor.rowcount
            if rows > 0:
                logger.info("Bumped %s row(s) in %s: version 0 -> %s", rows, table, table_bump_to)
                bump_to = table_bump_to
            else:
                logger.info("No version=0 rows to bump in %s", table)

        # Tracking table: bump version=0 → real_version (which already holds
        # the correct chronological number for that row)
        tracking_table = "dbo.nh_t_teinat_mapot_hesder"
        cursor.execute(
            f"UPDATE {tracking_table} SET version = real_version "
            f"WHERE id_hesder = ? AND k_sug_mapa = ? AND version = 0",
            (id_hesder, k_sug_mapa),
        )
        rows = cursor.rowcount
        if rows > 0:
            logger.info("Bumped %s row(s) in %s: version 0 -> real_version", rows, tracking_table)
        else:
            logger.info("No version=0 rows to bump in %s", tracking_table)

        conn.commit()
        return bump_to or 0

    except pyodbc.Error as e:
        logger.error("Database error during version bump: %s", e)
        if conn:
            conn.rollback()
        return 0
    except Exception as e:
        logger.error("Error during version bump: %s\n%s", e, traceback.format_exc())
        if conn:
            conn.rollback()
        return 0
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def delete_shuma_rows(
    sde_connection: str,
    id_hesder: str,
    k_sug_mapa: int,
    table_name: str = "DBO.NH_TG_HESDER_MUTSAOT_SHUMA",
) -> int:
    """
    Delete all existing rows from the SHUMA table for the given
    (id_hesder, k_sug_mapa) pair before a fresh import.
    Returns the number of rows deleted, or -1 on error.
    """
    logger.info(
        "Deleting existing SHUMA rows for id_hesder=%s k_sug_mapa=%s",
        id_hesder, k_sug_mapa,
    )
    conn = None
    cursor = None
    try:
        conn_str = get_connection_string_from_sde(sde_connection)
        if not conn_str:
            logger.error("Failed to get connection string for SHUMA delete")
            return -1

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {table_name} WHERE id_hesder = ? AND k_sug_mapa = ?",
            (int(id_hesder), k_sug_mapa),
        )
        deleted = cursor.rowcount
        conn.commit()
        logger.info("Deleted %s SHUMA row(s)", deleted)
        return deleted

    except pyodbc.Error as e:
        logger.error("Database error deleting SHUMA rows: %s", e)
        if conn:
            conn.rollback()
        return -1
    except Exception as e:
        logger.error("Error deleting SHUMA rows: %s\n%s", e, traceback.format_exc())
        if conn:
            conn.rollback()
        return -1
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_status_teina(sde_connection=r"SDE_730_3.sde", id_teina=3, status_value=6)
