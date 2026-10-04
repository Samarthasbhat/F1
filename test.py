# requirements.txt: fastf1>=3.8.3, matplotlib, numpy
import os

import fastf1
import fastf1.plotting
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

YEAR = 2026
SESSION_MODE = "race"     # "race" or "testing"
EVENT = "Monaco"      # race mode: event name (or round number)
TEST_NUMBER = 2  # testing mode: confirm with list_testing_events(). Test 1 may be the Barcelona shakedown.
DAY = 1          # testing mode only
DRIVER = "HAM"
# Anchored to this file so the cache is reused no matter where you launch from
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# Fuel correction: how much faster the car gets per lap of fuel burned.
# ASSUMPTION, not measured data. Teams use roughly 0.03-0.07 s/lap; the true value
# depends on the car and the 2026 fuel rules. Treat results as a range, not a fact.
FUEL_EFFECT_S_PER_LAP = 0.05
FUEL_SENSITIVITY = (0.03, 0.05, 0.07)   # printed side by side in print_slopes
USE_FUEL_CORRECTION = True              # False plots raw lap times

FALLBACK_COLORS = {"SOFT": "red", "MEDIUM": "gold", "HARD": "white",
                   "INTERMEDIATE": "green", "WET": "blue"}


def setup_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)


setup_cache()  # must run before any FastF1 call so the default cache isn't used


def list_testing_events():
    """Print testing events so you pick the right TEST_NUMBER instead of guessing."""
    schedule = fastf1.get_event_schedule(YEAR, include_testing=True)
    print(schedule[schedule["EventFormat"] == "testing"][["RoundNumber", "EventName", "EventDate"]])


def load_session():
    """Load the race or testing session chosen by the settings at the top."""
    if SESSION_MODE == "race":
        session = fastf1.get_session(YEAR, EVENT, "R")
    else:
        session = fastf1.get_testing_session(YEAR, TEST_NUMBER, DAY)
    session.load(telemetry=False, weather=False, messages=False)
    return session


def session_label():
    if SESSION_MODE == "race":
        return f"{YEAR} {EVENT} GP race"
    return f"{YEAR} testing, test {TEST_NUMBER}, day {DAY}"


def add_fuel_correction(laps, effect=FUEL_EFFECT_S_PER_LAP):
    """Add LapTimeCorr: lap time as if the car had the same fuel load as the stint's first lap.

    Only the burn rate matters, not the starting fuel, because each stint is
    compared against its own first lap. Absolute pace between stints is still
    NOT comparable, since starting fuel loads differ.
    """
    laps = laps.copy()
    # Laps since the stint's first surviving lap. Uses LapNumber so removed laps still count as burned fuel.
    laps["StintLap"] = laps["LapNumber"] - laps.groupby("Stint")["LapNumber"].transform("min")
    laps["LapTimeCorr"] = laps["LapTimeSec"] + effect * laps["StintLap"]
    return laps


def load_laps():
    session = load_session()

    # pick_wo_box drops in/out laps, which skew the data
    laps = session.laps.pick_drivers(DRIVER).pick_quicklaps().pick_wo_box()
    if SESSION_MODE == "race" and "TrackStatus" in laps.columns:
        # Keep green-flag laps only: safety car, VSC and yellow laps are not representative pace
        laps = laps.pick_track_status("1", how="equals")

    before = len(laps)
    laps = laps.dropna(subset=["TyreLife", "LapTime"])
    if len(laps) < before:
        print(f"Dropped {before - len(laps)} laps with missing TyreLife/LapTime.")

    if laps.empty:
        raise SystemExit(
            f"No usable laps for {DRIVER} ({session_label()}). "
            "Check the session settings, whether the driver took part, or whether the data is published yet."
        )

    laps = laps.copy()
    laps["LapTimeSec"] = laps["LapTime"].dt.total_seconds()
    laps = add_fuel_correction(laps)
    return session, laps


def compound_color(compound, session):
    try:
        return fastf1.plotting.get_compound_color(compound, session=session)
    except (KeyError, ValueError, TypeError):
        return FALLBACK_COLORS.get(compound, "gray")


def print_slopes(laps, min_laps=5):
    """Raw slope plus fuel-corrected slopes for a range of assumed fuel effects."""
    header = "  ".join(f"@{e:.2f}" for e in FUEL_SENSITIVITY)
    print(f"Slopes in s/lap. Raw first, then fuel-corrected at assumed effect: {header}")
    for stint_no, stint in laps.groupby("Stint"):
        if len(stint) < min_laps:
            continue
        raw = np.polyfit(stint["TyreLife"], stint["LapTimeSec"], 1)[0]
        corrected = []
        for effect in FUEL_SENSITIVITY:
            corr_times = stint["LapTimeSec"] + effect * stint["StintLap"]
            corrected.append(np.polyfit(stint["TyreLife"], corr_times, 1)[0])
        lap_range = f"laps {int(stint['LapNumber'].min())}-{int(stint['LapNumber'].max())}"
        corr_text = "  ".join(f"{c:+.3f}" for c in corrected)
        print(f"S{int(stint_no)} ({stint['Compound'].iloc[0]}, {lap_range}, {len(stint)} laps): "
              f"raw {raw:+.3f} | corrected {corr_text}")


def plot_stints(session, laps):
    y_col = "LapTimeCorr" if USE_FUEL_CORRECTION else "LapTimeSec"
    fig, ax = plt.subplots(figsize=(11, 6))
    seen = {}

    for stint_no, stint in laps.groupby("Stint"):
        compound = stint["Compound"].iloc[0]
        color = compound_color(compound, session)
        seen[compound] = color

        ax.plot(stint["TyreLife"], stint[y_col], color="lightgray", zorder=1)
        ax.scatter(stint["TyreLife"], stint[y_col], c=[color],
                   edgecolors="black", s=45, zorder=2)

        # Label the first lap of each stint; alternate offsets to reduce overlap
        first = stint.iloc[0]
        offset = (-10, 8) if int(stint_no) % 2 else (8, -14)
        ax.annotate(f"S{int(stint_no)}",
                    xy=(first["TyreLife"], first[y_col]),
                    xytext=offset, textcoords="offset points",
                    fontsize=9, fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.8))

    handles = [Line2D([0], [0], marker="o", linestyle="", markerfacecolor=c,
                      markeredgecolor="black", label=str(k).replace("_", " ").title())
               for k, c in seen.items()]
    ax.legend(handles=handles, title="Tyre compound", loc="best", framealpha=0.5)

    if USE_FUEL_CORRECTION:
        subtitle = f"Fuel-corrected, assumed {FUEL_EFFECT_S_PER_LAP:.2f} s/lap (estimate)"
    else:
        subtitle = "Uncorrected for fuel load"
    ax.set_title(f"{DRIVER}: lap time vs tyre life ({session_label()})\n{subtitle}")
    ax.set_xlabel("Tyre life (laps)")
    ax.set_ylabel("Lap time (s)")
    ax.grid(alpha=0.3)
    plt.show()


if __name__ == "__main__":
    list_testing_events()   # run once to find TEST_NUMBER, then leave commented
    session, laps = load_laps()
    print_slopes(laps)
    plot_stints(session, laps)