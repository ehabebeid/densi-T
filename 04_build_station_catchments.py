from pathlib import Path

import geopandas as gpd
import pandas as pd
from tobler.area_weighted import area_interpolate

DATA_DIR = Path("data")
PROJECTED_CRS = "EPSG:32619"
METERS_PER_MILE = 1609.344
BUFFER_MILES = [0.25, 0.5, 1.0]

# (path, list of columns to interpolate as extensive/count variables)
SOURCE_LAYERS = [
    (DATA_DIR / "pop_2010.geojson",       ["pop_2010"]),
    (DATA_DIR / "pop_2024.geojson",        ["pop_2024"]),
    (DATA_DIR / "jobs_2011.geojson",      ["jobs_2011"]),
    (DATA_DIR / "jobs_2023.geojson",      ["jobs_2023"]),
]


def load_sources() -> list[tuple[gpd.GeoDataFrame, list[str]]]:
    sources = []
    for path, cols in SOURCE_LAYERS:
        gdf = gpd.read_file(path).to_crs(PROJECTED_CRS)
        for col in cols:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0)
        sources.append((gdf, cols))
        print(f"  Loaded {path.name}: {len(gdf):,} rows")
    return sources


def main():
    stations = gpd.read_file(DATA_DIR / "gtfs_peak_freq.geojson")
    stations_proj = stations.to_crs(PROJECTED_CRS)
    print(f"Stations: {len(stations_proj):,}")

    print("\nLoading source layers...")
    sources = load_sources()

    frames = []
    for radius_mi in BUFFER_MILES:
        print(f"\nBuffering at {radius_mi} mi...")
        buffers = stations_proj.copy()
        buffers["geometry"] = buffers.geometry.buffer(radius_mi * METERS_PER_MILE)

        result = buffers[["parent_station", "stop_name", "routes",
                          "tph_am_peak", "tph_midday", "tph_pm_peak", "peak_trips_per_hr"]].copy()
        result["buffer_mi"] = radius_mi

        for src, cols in sources:
            interp = area_interpolate(src, buffers, extensive_variables=cols, allocate_total=False)
            for col in cols:
                result[col] = interp[col].values
                print(f"  {col}: total={result[col].sum():,.0f}")

        result["geometry"] = buffers["geometry"]
        area_acres = buffers.geometry.area / 4046.86
        for col in ["pop_2010", "pop_2024", "jobs_2011", "jobs_2023"]:
            result[f"{col}_per_acre"] = (result[col] / area_acres.values).round(2)
        result["pop_jobs_2010_per_acre"] = ((result["pop_2010"] + result["jobs_2011"]) / area_acres.values).round(2)
        result["pop_jobs_2024_per_acre"] = ((result["pop_2024"] + result["jobs_2023"]) / area_acres.values).round(2)
        frames.append(result)

    out = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=PROJECTED_CRS,
    ).to_crs("EPSG:4326")

    out_path = DATA_DIR / "catchments.geojson"
    out.to_file(out_path, driver="GeoJSON")
    print(f"\nSaved -> {out_path}  ({len(out):,} rows = {len(stations)} stations x {len(BUFFER_MILES)} radii)")
    print(out[["stop_name", "buffer_mi", "tph_am_peak", "tph_midday", "tph_pm_peak", "peak_trips_per_hr", "pop_2010", "pop_2024", "jobs_2011", "jobs_2023"]]
          .sort_values(["buffer_mi", "peak_trips_per_hr"], ascending=[True, False])
          .head(15)
          .to_string(index=False))


if __name__ == "__main__":
    main()
