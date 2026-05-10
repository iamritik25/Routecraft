# 🗺️ Routing & Graph Engine

The core of RouteCraft is a custom-built routing engine that combines static transit data (GTFS) with dynamic traffic predictions.

## 🏗️ Graph Construction (`graph_builder.py`)

The `MultiLayerGraphBuilder` assembles a directed weighted graph using `networkx`.

### Data Sources
1. **Hubs (`locations.json`)**: 69 hand-picked major transit hubs in Bengaluru (Koramangala, Majestic, Silk Board, etc.).
2. **BMTC Bus (GTFS)**: Real-world bus schedules including 4,433 stops and 4,271 routes.
3. **Namma Metro (KML)**: Station coordinates and line geometry for Purple and Green lines.
4. **Road Network**: Simulated via Haversine distance between hubs, adjusted by mode speed.

### Mode-Specific Logic
- **WALK**: Fixed speed (5 km/h). High transfer penalty.
- **AUTO/CAB**: Subject to the ML traffic model. Includes a base fare + per-km cost.
- **BUS**: Travel time derived from GTFS `stop_times`.
- **METRO**: Fixed travel times between stations based on Namma Metro operational speeds.

---

## 🚀 The Route Engine (`route_engine.py`)

The `RouteEngine` performs multiple Dijkstra searches on the graph to find the "Best" routes according to different user preferences.

### Search Variants
For every query, the engine returns up to 7 route variants:
1. **Fastest**: Minimizes `total_time`.
2. **Cheapest**: Minimizes `total_cost`.
3. **Balanced**: A Pareto-optimal route minimizing a normalized sum of time and cost.
4. **Cab Only**: Strictly uses Auto/Cab modes.
5. **Bus Only**: Strictly uses BMTC Bus + walking.
6. **Metro Only**: Strictly uses Namma Metro + walking.
7. **Metro + Cab**: Prioritizes Metro for long distances with Cab "last-mile" connectivity.

---

## 📊 ETA Confidence Intervals

RouteCraft doesn't just give a single ETA. It provides statistical bounds using the `eta_confidence.py` service:

- **P10 (Best Case)**: 10th percentile travel time (clear roads, all green lights).
- **P50 (Expected)**: Median travel time (what the user usually experiences).
- **P90 (Worst Case)**: 90th percentile (heavy congestion or minor incidents).

**Confidence Score**: 
- `High`: Low variance between P10 and P90 (usually Metro/Bus).
- `Medium/Low`: High variance (usually Cabs during peak hours).

---

## 🔴 Surge Pricing Engine (`surge_engine.py`)

Surge is calculated in real-time based on three factors:
1. **Temporal Demand**: Peak hours (8-11 AM, 5-8 PM) trigger a multiplier.
2. **Weather Impact**: Rain and storms increase the multiplier by up to 1.5x.
3. **Zone Sensitivity**: High-demand areas like Whitefield or M.G. Road have higher base surge.

The final multiplier (1.0x – 3.5x) is applied to all Auto and Cab fares.
