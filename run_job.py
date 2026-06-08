"""
One-off script to run the full DWG→SDE workflow without starting the API server.
"""
import importlib
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import parcel_writer
importlib.reload(parcel_writer)

from config import SDE_CONNECTION
from database_writer import write_to_mapot_hesder, verify_inserted_record
from database_updater import update_status_teina
ID_HESDER    = "80115"
K_SUG_MAPA   = 1
DWG_PATH     = r"\\nas01\Gis_Users\moshe-yaniv\PROJECTS\NEHASIM_PARCELS\CAD\80115.dwg"
MISHTAMESH   = None

def main():
    print("=" * 60)
    print(f"id_hesder  : {ID_HESDER}")
    print(f"k_sug_mapa : {K_SUG_MAPA}")
    print(f"dwg_path   : {DWG_PATH}")
    print("=" * 60)

    # Step 1: insert submission record
    new_id_teina = write_to_mapot_hesder(
        sde_connection=SDE_CONNECTION,
        id_hesder=ID_HESDER,
        k_sug_mapa=K_SUG_MAPA,
        dwg_path=DWG_PATH,
        mishtamesh=MISHTAMESH,
    )
    if new_id_teina is None:
        print("FAILED: could not insert submission record")
        sys.exit(1)

    print(f"Submission record created — id_teina={new_id_teina}")

    # Step 2: process DWG → SDE
    try:
        success = parcel_writer.process_dwg_to_sde(
            dwg_path=DWG_PATH,
            id_hesder=ID_HESDER,
            k_sug_mapa=K_SUG_MAPA,
            sde_connection=SDE_CONNECTION,
        )
    except Exception as exc:
        import traceback
        print(f"EXCEPTION during processing:\n{traceback.format_exc()}")
        update_status_teina(SDE_CONNECTION, new_id_teina, 5)
        sys.exit(1)

    if success:
        update_status_teina(SDE_CONNECTION, new_id_teina, 6)
        print(f"\n{'='*60}")
        print(f"SUCCESS — id_teina={new_id_teina}")
        print(f"{'='*60}")
    else:
        update_status_teina(SDE_CONNECTION, new_id_teina, 5)
        print(f"\n{'='*60}")
        print(f"FAILED — id_teina={new_id_teina}, status set to 5 (Error)")
        print(f"{'='*60}")
        sys.exit(1)

if __name__ == "__main__":
    main()
