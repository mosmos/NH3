import arcpy
import time
import pandas as pd

# === CONFIGURE ===
sde_connection = r"SDE_730_3.sde"
table_name = "db730_3.DBO.nh_tg_hesderim_mutsaot"
layerA_path = f"{sde_connection}\\{table_name}"
query = "ms_gush_hesder = 80116 and version = 0"

layerB = r"https://dgt-ags02/arcgis/rest/services/WM/IView2WM/MapServer/524"

# Unique ID field names
# Layer A: ms_gush_hesder + ms_chelka_hesder
# Layer B: ms_gush + ms_chelka
GUSH_A = "ms_gush_hesder"
CHELKA_A = "ms_chelka_hesder"
GUSH_B = "ms_gush"
CHELKA_B = "ms_chelka"

arcpy.env.overwriteOutput = True
arcpy.env.workspace = "in_memory"


def find_field(fields, name):
    """Find field name in intersect result, handling _1 suffix for conflicts."""
    if name in fields:
        return name
    if f"{name}_1" in fields:
        return f"{name}_1"
    raise ValueError(f"Field '{name}' not found in intersect result. Available: {fields}")


def main():
    start = time.time()
    print("Starting overlap analysis...\n")

    # 1. Create filtered layer A
    layerA = arcpy.management.MakeFeatureLayer(layerA_path, "layerA_lyr", query)[0]

    # count features in layerA
    countA = int(arcpy.management.GetCount(layerA)[0])  
    print(f"Layer A: {countA} features match query: {query}")
    if countA == 0:
        print("\nNo features in Layer A match the query. Done.")
        return      

    # 2. Build area dictionary for Layer A (small filtered set)
    print("Building area dictionary for Layer A...")
    area_dict_A = {}
    with arcpy.da.SearchCursor(layerA, [GUSH_A, CHELKA_A, "SHAPE@AREA"]) as cursor:
        for row in cursor:
            a_id = f"{row[0]}_{row[1]}"
            area_dict_A[a_id] = row[2]
    print(f"  Found {len(area_dict_A)} features in Layer A")

    # 3. Intersect (no need to copy layerB — arcpy handles REST services directly)
    print("Running intersection...")
    intersect_fc = "intersect_result"
    arcpy.analysis.Intersect([layerA, layerB], intersect_fc, "ALL")
    count = int(arcpy.management.GetCount(intersect_fc)[0])
    print(f"  Found {count} overlapping pieces")

    if count == 0:
        print("\nNo overlaps found. Done.")
        return

    # 4. Resolve field names (intersect may rename duplicates with _1 suffix)
    intersect_fields = [f.name for f in arcpy.ListFields(intersect_fc)]
    print(f"\n  Intersect fields: {intersect_fields}")
    gush_a = find_field(intersect_fields, GUSH_A)
    chelka_a = find_field(intersect_fields, CHELKA_A)
    gush_b = find_field(intersect_fields, GUSH_B)
    chelka_b = find_field(intersect_fields, CHELKA_B)
    sw_musdar_f = find_field(intersect_fields, "sw_musdar")
    print(f"  Using: A=[{gush_a}, {chelka_a}]  B=[{gush_b}, {chelka_b}, sw_musdar={sw_musdar_f}]")

    # 5. Collect unique B IDs from intersect, then query ONLY those from layerB
    unique_b_ids = set()
    with arcpy.da.SearchCursor(intersect_fc, [gush_b, chelka_b]) as cursor:
        for row in cursor:
            unique_b_ids.add((row[0], row[1]))
    print(f"  Need areas for {len(unique_b_ids)} unique Layer B features")

    area_dict_B = {}
    if unique_b_ids:
        where_parts = [f"({GUSH_B} = {g} AND {CHELKA_B} = {c})" for g, c in unique_b_ids]
        where_clause = " OR ".join(where_parts)
        with arcpy.da.SearchCursor(layerB, [GUSH_B, CHELKA_B, "SHAPE@AREA"], where_clause) as cursor:
            for row in cursor:
                b_id = f"{row[0]}_{row[1]}"
                area_dict_B[b_id] = row[2]
        print(f"  Retrieved {len(area_dict_B)} Layer B areas")

    # 6. Build results as pandas DataFrame
    rows = []
    with arcpy.da.SearchCursor(intersect_fc,
                               [gush_a, chelka_a, gush_b, chelka_b, "SHAPE@AREA", sw_musdar_f]) as cursor:
        for row in cursor:
            a_id = f"{row[0]}_{row[1]}"
            b_id = f"{row[2]}_{row[3]}"
            overlap_area = row[4]
            sw_musdar_val = row[5]

            area_a = area_dict_A.get(a_id, 0)
            area_b = area_dict_B.get(b_id, 0)

            pct_a = (overlap_area / area_a * 100) if area_a and area_a > 1e-6 else 0.0
            pct_b = (overlap_area / area_b * 100) if area_b and area_b > 1e-6 else 0.0

            rows.append({
                "A_ID": a_id,
                "B_ID": b_id,
                "sw_musdar": sw_musdar_val,
                "Area_A": round(area_a, 3),
                "Area_B": round(area_b, 3),
                "Overlap_Area": round(overlap_area, 3),
                "Pct_of_A": round(pct_a, 2),
                "Pct_of_B": round(pct_b, 2),
            })

    df = pd.DataFrame(rows)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 150)
    print("\n")
    print(df.to_string(index=False))

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f} seconds.")


if __name__ == "__main__":
    main()