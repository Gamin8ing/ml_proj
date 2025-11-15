# CAIGA – Context Aware In‑Game Assistant (Fabric, client‑side)

A client‑side Fabric mod (Java 17 toolchain, Gradle 8.8, Loom 1.7.x) that exposes a live REST API with the player’s game state and writes structured logs (CSV + JSONL) for ML training.

- REST server: http://localhost:8080
- Endpoints: `/state`, `/inventory`, `/events?n=20`, **POST** `/tip`
- Logs: `config/caiga/state.csv` and `config/caiga/state.jsonl` (about once per second)

## Requirements

- Java toolchain 17 (system JDK 21 is OK; build targets 17)
- Gradle wrapper 8.8 (use `./gradlew`)
- Fabric Loom 1.7.x
- Minecraft 1.20.4, Fabric Loader 0.16.x, Fabric API 0.97.0+1.20.4

## Project layout

- `src/main/java/com/caiga/`
  - `CAIGA.java` – common (non‑client) mod initializer
  - `GameStateStore.java` – thread‑safe store for current state + events
  - `GameStateServer.java` – built‑in HttpServer exposing `/state`, `/inventory`, `/events`
  - `FileLogger.java` – CSV/JSONL logging approximately every second
- `src/client/java/com/caiga/`
  - `CAIGAClient.java` – client initializer; wires store, logger, tick handler, server
  - `TickHandler.java` – captures state each tick, detects events, updates store
- `src/main/resources/fabric.mod.json` – Fabric metadata (client entrypoint present)

Notes:
- We use Loom’s split environment source sets. Client‑only code lives under `src/client`.
- The HTTP server uses Java’s built‑in `com.sun.net.httpserver.HttpServer` (no external loop).

## Build and run

```bash
# From project root
./gradlew runClient
```

- When the client loads, the HTTP server starts on `http://localhost:8080`.
- You can query endpoints from menu or in‑world, though more fields populate in‑world.

## REST API

- GET `/state` – Full game state snapshot (see Data model)
- GET `/inventory` – Short inventory summary `{ logs, planks, foods }`
- GET `/events?n=20` – Last N events (default N=20)
- POST `/tip` – Send a tip/chat message into the client. Body JSON must include `"message"` or `"tip"`.

Examples:

```bash
curl -s http://localhost:8080/state | jq .
curl -s http://localhost:8080/inventory | jq .
curl -s "http://localhost:8080/events?n=50" | jq .
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"message":"Remember to eat!"}' http://localhost:8080/tip | jq .
```

### Example `/state` response

```json
{
  "x": -123.45,
  "y": 64.0,
  "z": 256.12,
  "health": 18.0,
  "hunger": 16,
  "dimension": "minecraft:overworld",
  "biome": "minecraft:plains",
  "timeOfDay": 14237,
  "isNight": false,
  "blockUnderCrosshair": "minecraft:oak_log",
  "movementVector": { "dx": 0.02, "dy": 0.0, "dz": -0.01 },
  "selectedItem": "minecraft:stone_pickaxe",
  "inventory": { "logs": 12, "planks": 64, "foods": 5 },
  "recentEvents": [
    { "type": "mine_attempt", "timestamp": 1731656932000, "details": { "target": "minecraft:oak_log" } },
    { "type": "pickup", "timestamp": 1731656930000, "details": { "delta": 2 } }
  ]
}
```

## Data collected (for ML)

Updated every client tick by `TickHandler` and stored in `GameStateStore`.

- Position and motion:
  - `x, y, z` (double)
  - `movementVector.dx, dy, dz` (delta since previous tick)
- Player vitals:
  - `health` (float), `hunger` (int)
- World context:
  - `dimension` (namespaced id), `biome` (namespaced id at player block pos)
  - `timeOfDay` (0..23999), `isNight` (simple boolean)
- Focus and selection:
  - `blockUnderCrosshair` (namespaced block id or null)
  - `selectedItem` (namespaced item id or null)
- Inventory summary (simple counts):
  - `logs`, `planks`, `foods`
- Recent events (deque, newest first):
  - `mine_attempt` – attack key pressed while crosshair on a block
  - `attack_attempt` – attack key pressed while targeting an entity
  - `place_attempt` – use key pressed (records selected item)
  - `damage` – health decreased this tick (records from/to)
  - `pickup` – heuristic when total inventory count increases (records delta)

## Logging

- Frequency: every 20 ticks (~1 second)
- Location: `config/caiga/`
  - `state.csv` – compact tabular log with key columns:
    - `timestamp,x,y,z,health,hunger,biome,dimension,blockUnderCrosshair,isNight,movementVector,inventoryCounts,lastEvent`
  - `state.jsonl` – one JSON snapshot per line (recent events omitted for size)

## Configuration ideas (future)

- Toggle logging on/off
- Change log frequency and output directory
- Change HTTP port (default 8080)
- Add POST endpoints to mark/label moments during play (existing: `/tip`)

## Troubleshooting

- No response at `/state`:
  - Ensure the client is running (`./gradlew runClient`) and watch the log: `GameStateServer listening on http://localhost:8080/state`.
  - Ensure port 8080 is free.
- Empty state at menu:
  - When no world/player is active, some fields remain unavailable; go in‑game.
- Build warnings about duplicates:
  - We split main/client source sets. `sourcesJar` excludes duplicate source paths by configuration in `build.gradle`.

## Tech notes

- Java 17 target; Gradle wrapper 8.8; Loom 1.7.x
- HTTP server: `com.sun.net.httpserver.HttpServer` (daemon thread pool; non‑blocking)
- JSON: Gson
- Fabric API is required; dependency is declared in `build.gradle` and the Fabric Maven repo is present.

---

If you want me to add a small config file (e.g., `config/caiga/config.json`) to control logging frequency and port, say the word and I’ll wire it in.

### POST /tip details

Request:

```json
{ "message": "Drink a potion before the fight" }
```

or

```json
{ "tip": "Low health detected, retreat" }
```

Response:

```json
{ "status": "ok", "echo": "Drink a potion before the fight" }
```

Behavior:
- Message is prefixed with `[TIP]` and sent to in‑game chat.
- Executed on the client thread; ignored if player not present.
- Invalid / missing body returns `{"error":"Missing 'message' or 'tip' field"}`.
