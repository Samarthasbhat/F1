"""Replay-based live tyre monitor.

FastF1 cannot stream data into analysis during a session: its live client only
RECORDS the feed to a file, which you process afterwards. So this script replays
a finished session one lap at a time, in the order laps were completed, and the
monitor only ever sees laps that have already happened. The monitor logic is
what a true live feed would use; only the lap source differs.

Put this file next to tyre_deg.py (it reuses its constants and cache setup).
"""
import time

import numpy as np
import pandas as pd

MIN_LAPS = 5             # laps needed in a stint before a slope is shown
CLIFF_S = 0.7            # lap this many seconds slower than the stint trend counts as a cliff candidate
CLIFF_CONSECUTIVE = 2    # candidates in a row before alerting (filters one-off traffic laps)
SLOW_LAP_LIMIT = 1.07    # ignore laps slower than 107% of the best lap seen so far
PIT_LOSS_S = 22.0        # ASSUMPTION: time lost per pit stop. Indicative only.
REPLAY_DELAY_S = 0.0     # seconds to pause between laps (e.g. 0.5 to watch it "live")


class StintMonitor:
    """Online per-stint tyre tracker. Feed it laps in order with update()."""

    def __init__(self, fuel_effect):
        self.fuel_effect = fuel_effect
        self.best_lap = np.inf
        self.stints = {}   # stint -> dict(first_lap, life, corr, cliff_count)

    def update(self, lap):
        """Process one completed lap (a dict or Series). Returns a status string or None."""
        lap_s = lap["LapTimeSec"]
        if pd.isna(lap_s) or pd.isna(lap["TyreLife"]) or pd.isna(lap["Stint"]):
            return None
        self.best_lap = min(self.best_lap, lap_s)

        # Causal filters: only information available at this moment
        if pd.notna(lap.get("PitInTime")) or pd.notna(lap.get("PitOutTime")):
            return None   # in/out lap
        track_status = lap.get("TrackStatus")
        if pd.notna(track_status) and str(track_status) != "1":
            return None   # safety car, VSC or yellow flag lap
        if lap_s > SLOW_LAP_LIMIT * self.best_lap:
            return None   # too slow compared with the best lap so far

        stint_no = int(lap["Stint"])
        st = self.stints.setdefault(
            stint_no, dict(first_lap=lap["LapNumber"], life=[], corr=[], cliff_count=0))
        corr = lap_s + self.fuel_effect * (lap["LapNumber"] - st["first_lap"])

        # Cliff check BEFORE adding this lap, so it is compared with the prior trend
        cliff_msg = ""
        if len(st["life"]) >= MIN_LAPS:
            fit = np.polyfit(st["life"], st["corr"], 1)
            residual = corr - np.polyval(fit, lap["TyreLife"])
            st["cliff_count"] = st["cliff_count"] + 1 if residual > CLIFF_S else 0
            if st["cliff_count"] >= CLIFF_CONSECUTIVE:
                cliff_msg = f" | ALERT: {st['cliff_count']} laps in a row >{CLIFF_S:.1f}s off trend (possible cliff)"

        st["life"].append(float(lap["TyreLife"]))
        st["corr"].append(float(corr))

        text = (f"[Lap {int(lap['LapNumber']):>3}] S{stint_no} {lap.get('Compound', '?')} "
                f"life {int(lap['TyreLife']):>2} | {lap_s:.3f}s (fuel-corr {corr:.3f}s)")
        if len(st["life"]) >= MIN_LAPS:
            slope = np.polyfit(st["life"], st["corr"], 1)[0]
            text += f" | slope {slope:+.3f} s/lap (n={len(st['life'])})"
            if slope > 0.02:   # optimal stint length is only meaningful if tyres are degrading
                best_n = np.sqrt(2 * PIT_LOSS_S / slope)
                text += f" | indicative stint length ~{best_n:.0f} laps"
        return text + cliff_msg


def lap_stream(laps):
    """Yield laps in the order they were completed (FastF1 'Time' = session time at lap end)."""
    laps = laps.copy()
    laps["LapTimeSec"] = laps["LapTime"].dt.total_seconds()
    for _, lap in laps.sort_values("Time").iterrows():
        yield lap


def main():
    # Imported here so the monitor classes above can be tested without FastF1 installed
    from test import DRIVER, FUEL_EFFECT_S_PER_LAP, load_session, session_label

    session = load_session()
    raw_laps = session.laps.pick_drivers(DRIVER)   # no hindsight filters: the monitor does its own

    monitor = StintMonitor(FUEL_EFFECT_S_PER_LAP)
    print(f"Replaying {DRIVER}, {session_label()} "
          f"(fuel effect assumed {FUEL_EFFECT_S_PER_LAP:.2f} s/lap)\n")
    for lap in lap_stream(raw_laps):
        msg = monitor.update(lap)
        if msg:
            print(msg)
            if REPLAY_DELAY_S:
                time.sleep(REPLAY_DELAY_S)


if __name__ == "__main__":
    main()