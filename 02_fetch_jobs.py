import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pygris

from config import COVERAGE

STATE_ABBR = {"25": "ma", "44": "ri"}

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# LODES8 recasts all historical years into 2020 Census blocks
LODES8_WAC = "https://lehd.ces.census.gov/data/lodes/LODES8/{state}/wac/{state}_wac_S000_JT00_{year}.csv.gz"
LODES_YEARS = [2011, 2023]


def fetch_lodes_wac(year: int) -> pd.DataFrame:
    frames = []
    for state_fips, counties in COVERAGE.items():
        url = LODES8_WAC.format(state=STATE_ABBR[state_fips], year=year)
        print(f"  Downloading {url}")
        df = pd.read_csv(url, dtype={"w_geocode": str})
        df = df[df["w_geocode"].str[2:5].isin(counties)].copy()
        frames.append(df)
    return (
        pd.concat(frames, ignore_index=True)
        .rename(columns={"w_geocode": "GEOID", "C000": f"jobs_{year}"})
        [["GEOID", f"jobs_{year}"]]
    )


def _geoid_col(gdf: gpd.GeoDataFrame) -> str:
    for col in ["GEOID20", "GEOID10", "GEOID00", "BLKIDFP00", "GEOID"]:
        if col in gdf.columns:
            return col
    raise ValueError(f"No GEOID column found. Columns: {gdf.columns.tolist()}")


def _fetch_tiger(fn, *args, **kwargs):
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"    TIGER download failed ({e.__class__.__name__}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_block_geometries(year: int = 2020) -> gpd.GeoDataFrame:
    frames = []
    for state, counties in COVERAGE.items():
        for county in counties:
            frames.append(_fetch_tiger(pygris.blocks, state=state, county=county, year=year, cache=True))
    gdf = pd.concat(frames, ignore_index=True)
    col = _geoid_col(gdf)
    return gdf[["geometry", col]].rename(columns={col: "GEOID"}).to_crs("EPSG:4326")


def main():
    print("Fetching 2020 block geometries...")
    geom = fetch_block_geometries(2020)
    print(f"  {len(geom):,} block geometries\n")

    for year in LODES_YEARS:
        print(f"Fetching LODES8 WAC {year}...")
        jobs = fetch_lodes_wac(year)
        print(f"  {len(jobs):,} blocks with jobs data")

        gdf = geom.merge(jobs, on="GEOID", how="left")
        out = OUTPUT_DIR / f"jobs_{year}.geojson"
        gdf.to_file(out, driver="GeoJSON")
        print(f"  Saved -> {out}  ({len(gdf):,} rows)\n")


if __name__ == "__main__":
    main()
