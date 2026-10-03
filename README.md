# F1 Tyre Degradation Analyzer
A Python tool that loads Formula 1 timing data, cleans and fuel-corrects lap times,estimates tyre degradation for each stint, and flags possible tyre "cliffs". Results can be viewed as a static chart or as a lap-by-lap replay window.

Built with FastF1 and tested on the 2026 Azerbaijan Grand Prix and 2026 pre-season testing data.


## Problem statement
Raw F1 lap times mix tyre wear with fuel burn, traffic, safety cars and pit laps, so it is hard to tell how quickly a tyre is acutally degrading during a run.
