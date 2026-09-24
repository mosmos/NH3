# Parcel Overlap Calculation Spec

Describes how `write_shuma_intersections()` in [parcel_writer.py](parcel_writer.py) computes overlap between newly-submitted DWG parcels and existing chelkot (cadastral) parcels, and writes the result to `NH_TG_HESDER_MUTSAOT_SHUMA`.

## Inputs

| Source | Table / Layer | Filter |
|---|---|---|
| Layer A — this job's parcels | `SDE_730_3.sde` → `DBO.NH_TG_HESDERIM_MUTSAOT` | `id_teina = <current job>` |
| Layer B — cadastral parcels | `SDE_736.sde` → `db736.DBO.kadaster\db736.DBO.KD_TG_CHELKOT` | Spatially selected: `INTERSECT` layer A |

Both layers are read into memory using `arcpy.da.SearchCursor` with spatial reference **EPSG:2039** (Israeli TM Grid), so areas and geometries are directly comparable.

## Algorithm

1. Build feature layer A, filtered to the current `id_teina`. If empty, skip the step (return success, nothing to do).
2. Build feature layer B from the SDE-736 chelkot source, narrowed with `SelectLayerByLocation(..., "INTERSECT", lyr_a)` to reduce the candidate set.
3. Pull both layers' geometries and areas into memory, then release the SDE feature layers.
4. For every pair `(A, B)`:
   - Skip if `A.geom.disjoint(B.geom)` is `True`.
   - Compute `overlap_geom = A.geom.intersect(B.geom, 4)` (dimension `4` = polygon/area intersection).
   - Skip if `overlap_area <= 1e-6` (treated as no real overlap).
   - Compute the overlap percentage (see formula below).
   - Record the pair.
5. Insert one row per surviving pair into `NH_TG_HESDER_MUTSAOT_SHUMA`, tagged with the current `id_teina`, `id_hesder`, `k_sug_mapa`, and `version` (rolling-zero, i.e. always `0` for the current/live set).

## Overlap Formula

$$
achuz\_chelkat\_shuma\_bemutsaat = \frac{overlap\_area}{A.area} \times 100
$$

- `overlap_area` — area of the intersection geometry between parcel A (this job) and parcel B (chelkot).
- `A.area` — total area of parcel A (`SHAPE@AREA` from layer A).
- Result is rounded to 4 decimal places.
- Since the denominator is always `A.area`, all of A's overlaps with every matching B sum to (approximately) 100% if B fully tiles A, or less if A has gaps not covered by any chelkot parcel.
- If `A.area` is missing or ~0, `achuz` is set to `0.0` to avoid division errors.

## Output Row Fields

| Field | Source |
|---|---|
| `id_teina` | current job |
| `id_hesder` | current job |
| `k_sug_mapa` | current job |
| `version` | current job (rolling-zero: `0`) |
| `ms_gush_hesder`, `ms_chelka_hesder` | Layer A (this job's parcel) |
| `ms_gush`, `ms_chelka` | Layer B (chelkot parcel) |
| `sw_musdar` | Layer B `k_status_hesder` |
| `achuz_chelkat_shuma_bemutsaat` | computed overlap % (formula above) |

## Notes / Edge Cases

- No candidate overlaps found → function returns success, nothing is written.
- Manual pairwise `Geometry.intersect()` is used instead of `arcpy.analysis.Intersect` because the analysis tool reused a stale ArcSDE session when mixing an enterprise geodatabase input with the chelkot source.
- Old `version = 0` SHUMA rows for `(id_hesder, k_sug_mapa)` are bumped to a historical version **before** this step runs (via `bump_spatial_versions()` earlier in `process_dwg_to_sde()`), so this insert always represents the current/live overlap set.

## Diagram

See [overlap_parcels.mmd](overlap_parcels.mmd) for the flowchart version of this process.
