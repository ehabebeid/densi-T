import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

GTFS_PATH = Path("data/MBTA_GTFS_20260328.zip")
OUTPUT_DIR = Path("data")
RAIL_TYPES = {"0", "1", "2"}
SERVICE_DATE = "20260506"

PERIODS = {
    "am_peak":  ("07:00:00", "09:00:00", 2),
    "midday":   ("10:00:00", "14:00:00", 4),
    "pm_peak":  ("16:00:00", "18:00:00", 2),
}


def load_gtfs() -> dict[str, pd.DataFrame]:
    tables = ["routes", "trips", "stop_times", "stops", "calendar", "calendar_dates"]
    with zipfile.ZipFile(GTFS_PATH) as z:
        return {t: pd.read_csv(z.open(f"{t}.txt"), dtype=str, low_memory=False) for t in tables}


def active_service_ids(cal: pd.DataFrame, cal_dates: pd.DataFrame, date: str) -> set[str]:
    dow = pd.Timestamp(date).strftime("%A").lower()  # e.g. "wednesday"
    active = set(
        cal[
            (cal[dow] == "1") &
            (cal["start_date"] <= date) &
            (cal["end_date"] >= date)
        ]["service_id"]
    )
    added = set(cal_dates[(cal_dates["date"] == date) & (cal_dates["exception_type"] == "1")]["service_id"])
    removed = set(cal_dates[(cal_dates["date"] == date) & (cal_dates["exception_type"] == "2")]["service_id"])
    return (active | added) - removed


def freq_for_period(st: pd.DataFrame, start: str, end: str, hours: float) -> pd.DataFrame:
    window = st[(st["departure_time"] >= start) & (st["departure_time"] <= end)].copy()
    window = window.drop_duplicates(subset=["trip_id", "parent_station"])
    by_dir = (
        window.groupby(["parent_station", "direction_id"])
        .size()
        .reset_index(name="trip_count")
    )
    result = (
        by_dir.sort_values("trip_count", ascending=False)
        .drop_duplicates(subset="parent_station")[["parent_station", "trip_count"]]
    )
    result["trips_per_hr"] = (result["trip_count"] / hours).round(1)
    return result


def main():
    g = load_gtfs()

    weekday_service_ids = active_service_ids(g["calendar"], g["calendar_dates"], SERVICE_DATE)
    print(f"Active service_ids on {SERVICE_DATE}: {len(weekday_service_ids)}")

    rail_route_ids = g["routes"][g["routes"]["route_type"].isin(RAIL_TYPES)]["route_id"]
    rail_trip_ids = g["trips"][
        g["trips"]["route_id"].isin(rail_route_ids) &
        g["trips"]["service_id"].isin(weekday_service_ids)
    ]["trip_id"]

    # build base stop-times table with direction + parent_station pre-joined
    st = g["stop_times"][g["stop_times"]["trip_id"].isin(rail_trip_ids)][
        ["trip_id", "stop_id", "departure_time"]
    ].copy()
    st = st.merge(g["trips"][["trip_id", "direction_id"]], on="trip_id", how="left")
    st = st.merge(g["stops"][["stop_id", "parent_station"]], on="stop_id", how="left")
    st = st.dropna(subset=["parent_station"])

    # routes per parent station
    routes_per_station = (
        st[["trip_id", "parent_station"]]
        .drop_duplicates()
        .merge(g["trips"][["trip_id", "route_id"]], on="trip_id", how="left")
        [["parent_station", "route_id"]]
        .drop_duplicates()
        .groupby("parent_station")["route_id"]
        .apply(lambda x: ",".join(sorted(x.unique())))
        .reset_index(name="routes")
    )

    # compute frequency for each period
    period_frames = {}
    for name, (start, end, hours) in PERIODS.items():
        period_frames[name] = freq_for_period(st, start, end, hours).rename(
            columns={"trip_count": f"trips_{name}", "trips_per_hr": f"tph_{name}"}
        )
        print(f"{name}: {len(period_frames[name]):,} stations")

    # merge all periods and take max tph as peak_trips_per_hr
    freq = period_frames["am_peak"]
    for name in ("midday", "pm_peak"):
        freq = freq.merge(period_frames[name], on="parent_station", how="outer")

    tph_cols = [f"tph_{p}" for p in PERIODS]
    freq[tph_cols] = freq[tph_cols].fillna(0)
    freq["peak_trips_per_hr"] = freq[tph_cols].max(axis=1)
    freq = freq.merge(routes_per_station, on="parent_station", how="left")

    # join parent station name + coordinates
    parents = g["stops"][g["stops"]["stop_id"].isin(freq["parent_station"])][
        ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ].rename(columns={"stop_id": "parent_station"})

    freq = freq.merge(parents, on="parent_station", how="left")
    freq["stop_lat"] = pd.to_numeric(freq["stop_lat"])
    freq["stop_lon"] = pd.to_numeric(freq["stop_lon"])

    gdf = gpd.GeoDataFrame(
        freq,
        geometry=gpd.points_from_xy(freq["stop_lon"], freq["stop_lat"]),
        crs="EPSG:4326",
    )

    out = OUTPUT_DIR / "gtfs_peak_freq.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"\nSaved -> {out}  ({len(gdf):,} stations)\n")
    print(
        gdf[["stop_name", "tph_am_peak", "tph_midday", "tph_pm_peak", "peak_trips_per_hr"]]
        .sort_values("peak_trips_per_hr", ascending=False)
        .head(20)
        .to_string(index=False)
    )
    print("\nFall River / South Coast Rail:")
    mask = gdf["stop_name"].str.contains("Fall River|New Bedford|Freetown|East Taunton", na=False)
    print(gdf[mask][["stop_name", "tph_am_peak", "tph_midday", "tph_pm_peak", "peak_trips_per_hr"]].to_string(index=False))


if __name__ == "__main__":
    main()
