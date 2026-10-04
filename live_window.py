"""Replay the session in a window: live chart on the left, status log on the right.

Uses only matplotlib (no extra GUI library). Keep this file next to
tyre_deg.py and live_monitor.py.
"""
import textwrap
from collections import deque

import matplotlib.pyplot as plt

REPLAY_DELAY_S = 0.4     # pause between laps; raise it to slow the replay down
LOG_WIDTH = 56           # characters per line in the log panel
LOG_LINES = 30           # wrapped lines kept on screen


def render(ax_chart, ax_log, monitor, compounds, log, color_fn, title):
    """Redraw both panels from the monitor's current state."""
    ax_chart.clear()
    for stint_no, st in monitor.stints.items():
        color = color_fn(compounds.get(stint_no))
        ax_chart.plot(st["life"], st["corr"], color="lightgray", zorder=1)
        ax_chart.scatter(st["life"], st["corr"], c=[color], edgecolors="black",
                         s=45, zorder=2)
        if st["life"]:
            ax_chart.annotate(f"S{stint_no}", (st["life"][0], st["corr"][0]),
                              xytext=(-10, 8), textcoords="offset points",
                              fontsize=9, fontweight="bold")
    ax_chart.set_title(title)
    ax_chart.set_xlabel("Tyre life (laps)")
    ax_chart.set_ylabel("Fuel-corrected lap time (s)")
    ax_chart.grid(alpha=0.3)

    ax_log.clear()
    ax_log.axis("off")
    wrapped = []
    for msg in log:
        wrapped.extend(textwrap.wrap(msg, LOG_WIDTH, subsequent_indent="    "))
    wrapped = wrapped[-LOG_LINES:]
    alert = any("ALERT" in m for m in list(log)[-5:])   # stays red for 5 laps
    ax_log.set_title("Status: possible tyre cliff" if alert else "Status: running",
                     color="red" if alert else "black", loc="left")
    ax_log.text(0, 1, "\n".join(wrapped), va="top", ha="left",
                family="monospace", fontsize=8, transform=ax_log.transAxes)


def main():
    from live_monitor import StintMonitor, lap_stream
    from test import (DRIVER, FUEL_EFFECT_S_PER_LAP, compound_color,
                          load_session, session_label)

    session = load_session()
    raw_laps = session.laps.pick_drivers(DRIVER)

    monitor = StintMonitor(FUEL_EFFECT_S_PER_LAP)
    compounds = {}
    log = deque(maxlen=40)
    title = (f"{DRIVER}: replay, {session_label()}\n"
             f"Fuel-corrected, assumed {FUEL_EFFECT_S_PER_LAP:.2f} s/lap (estimate)")

    plt.ion()
    fig, (ax_chart, ax_log) = plt.subplots(
        1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [2, 1]})

    def color_fn(compound):
        return compound_color(compound, session) if compound else "gray"

    for lap in lap_stream(raw_laps):
        if not plt.fignum_exists(fig.number):   # window was closed
            return
        msg = monitor.update(lap)
        if not msg:
            continue
        compounds[int(lap["Stint"])] = lap.get("Compound")
        log.append(msg)
        render(ax_chart, ax_log, monitor, compounds, log, color_fn, title)
        fig.tight_layout()
        plt.pause(REPLAY_DELAY_S)

    plt.ioff()
    plt.show()   # keep the window open after the replay finishes


if __name__ == "__main__":
    main()