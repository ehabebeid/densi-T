import os
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
from census import Census
from dotenv import load_dotenv
import pygris

from config import COVERAGE

load_dotenv()

ACS5_YEAR = 2024

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

c = Census(os.environ["CENSUS_API_KEY"])


# ---------------------------------------------------------------------------
# Census API helpers
# ---------------------------------------------------------------------------

def _fetch_with_retry(fetcher, *args, max_attempts: int = 3) -> list:
    for attempt in range(max_attempts):
        try:
            return fetcher(*args)
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            wait = 2 ** attempt
            print(f"    {args} failed ({e.__class__.__name__}), retrying in {wait}s...")
            time.sleep(wait)


def _concat_county_rows(fetcher) -> pd.DataFrame:
    frames = []
    for state, counties in COVERAGE.items():
        for county in counties:
            frames.append(pd.DataFrame(_fetch_with_retry(fetcher, state, county)))
    return pd.concat(frames, ignore_index=True)


def _block_geoid(row) -> str:
    return (
        str(row["state"]).zfill(2)
        + str(row["county"]).zfill(3)
        + str(row["tract"]).zfill(6)
        + str(row["block"]).zfill(4)
    )


def _bg_geoid(row) -> str:
    return (
        str(row["state"]).zfill(2)
        + str(row["county"]).zfill(3)
        + str(row["tract"]).zfill(6)
        + str(row["block group"])
    )


def fetch_decennial_blocks(year: int) -> pd.DataFrame:
    var = "P001001"

    def fetcher(state, county):
        return c.sf1.get(
            (var,),
            {"for": "block:*", "in": f"state:{state} county:{county} tract:*"},
            year=year,
        )

    df = _concat_county_rows(fetcher)
    df["GEOID"] = df.apply(_block_geoid, axis=1)
    df = df.rename(columns={var: f"pop_{year}"})[["GEOID", f"pop_{year}"]]
    df[f"pop_{year}"] = pd.to_numeric(df[f"pop_{year}"])
    return df


def fetch_acs_block_groups() -> pd.DataFrame:
    def fetcher(state, county):
        return c.acs5.get(
            ("B01003_001E",),
            {"for": "block group:*", "in": f"state:{state} county:{county} tract:*"},
            year=ACS5_YEAR,
        )

    df = _concat_county_rows(fetcher)
    df["GEOID"] = df.apply(_bg_geoid, axis=1)
    df = df.rename(columns={"B01003_001E": f"pop_{ACS5_YEAR}"})[["GEOID", f"pop_{ACS5_YEAR}"]]
    df[f"pop_{ACS5_YEAR}"] = pd.to_numeric(df[f"pop_{ACS5_YEAR}"])
    return df


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

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


def fetch_block_geometries(year: int) -> gpd.GeoDataFrame:
    frames = []
    for state, counties in COVERAGE.items():
        for county in counties:
            frames.append(_fetch_tiger(pygris.blocks, state=state, county=county, year=year, cache=True))
    gdf = pd.concat(frames, ignore_index=True)
    col = _geoid_col(gdf)
    return gdf[["geometry", col]].rename(columns={col: "GEOID"}).to_crs("EPSG:4326")


def fetch_block_group_geometries(year: int = 2020) -> gpd.GeoDataFrame:
    frames = []
    for state, counties in COVERAGE.items():
        for county in counties:
            frames.append(_fetch_tiger(pygris.block_groups, state=state, county=county, year=year, cache=True))
    gdf = pd.concat(frames, ignore_index=True)
    col = _geoid_col(gdf)
    return gdf[["geometry", col]].rename(columns={col: "GEOID"}).to_crs("EPSG:4326")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Fetching 2010 decennial blocks...")
    pop = fetch_decennial_blocks(2010)
    print(f"  {len(pop):,} block records")

    print("  Fetching 2010 block geometries...")
    geom = fetch_block_geometries(2010)
    print(f"  {len(geom):,} block geometries")

    gdf = geom.merge(pop, on="GEOID", how="left")
    out = OUTPUT_DIR / "pop_2010.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"  Saved -> {out}  ({len(gdf):,} rows)\n")

    print("Fetching ACS 5-year block groups...")
    pop_bg = fetch_acs_block_groups()
    print(f"  {len(pop_bg):,} block group records")

    print("  Fetching block group geometries...")
    geom_bg = fetch_block_group_geometries()
    print(f"  {len(geom_bg):,} block group geometries")

    gdf_bg = geom_bg.merge(pop_bg, on="GEOID", how="left")
    out_bg = OUTPUT_DIR / f"pop_{ACS5_YEAR}.geojson"
    gdf_bg.to_file(out_bg, driver="GeoJSON")
    print(f"  Saved -> {out_bg}  ({len(gdf_bg):,} rows)")


if __name__ == "__main__":
    main()
