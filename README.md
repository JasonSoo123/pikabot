# PikaBot

A competitive Pokémon VGC (Video Game Championships) doubles battle bot built with [poke-env](https://github.com/hsahovic/poke-env). Designed for **Gen 9 Champions VGC 2026 Regulation MA** format.

## Features

- **VGC Doubles Battle Logic**: Custom move selection, switching, and mega evolution handling
- **Match Telemetry Logging**: Detailed battle logs with turn-by-turn state snapshots in JSONL format
- **Bot-vs-Bot Self-Play**: Tournament mode running all teams against all teams locally
- **Player-vs-Bot Mode**: Connect to a local Pokémon Showdown server and challenge human players
  - Random team selection from 50 pre-built VGC teams for each match
  - Bot connects as "PikaBot" and challenges a target username
  - No hardcoded team — every run picks a different random team from `VGC_TEAMS_LIST`
- **Incremental JSONL Logging**: OOM-safe — each match appended as a single compact line to `battle_logs/master.json`
- **Opponent Action Tracking**: Captures opponent moves, switches, and faints from battle observations
- **50 Pre-built VGC Teams**: Loaded from Champions VGC statistics data

## Project Structure

```
pikabot/
├── bot.py                    # Main PikaBot class with battle logic and logging
├── main.py                   # Tournament entry point (all teams vs all teams)
├── pvb.py                    # Player-vs-Bot entry point (local Showdown server)
├── team.py                   # Team definitions (EX_VGC_TEAM + VGC_TEAMS_LIST)
├── constants.py              # Move categories, targets, setup moves, protect moves
├── data_loader.py            # Loads Champions VGC stats JSON
├── champions-vgc-stats.json  # Raw VGC usage statistics
├── top-50-vgc-teams.json     # 50 pre-built VGC teams
└── mixins/                   # Battle decision logic modules
    ├── __init__.py
    ├── damage.py             # Damage calculation with type/ability/item/weather/terrain
    ├── ordering.py           # Move scoring, pair synergy, candidate generation
    ├── opponent_tracker.py   # Opponent team movepool tracking
    ├── pokemon_info.py       # Ability, stat, item, grounded checks
    ├── speed.py              # Speed comparison with items/abilities/weather/tailwind/TR
    ├── status_moves.py       # Status move scoring (setup, speed control, disruption)
    └── switching.py          # Switch scoring with Intimidate, Regenerator, hazards, pivots
```

## Installation

```bash
# From the Pokemon project root directory
pip install poke-env
```

## Running Battles

### Tournament Mode (Bot vs Bot Self-Play)

Runs all 50 teams against each other (5 battles per pair by default):

```bash
# From the Pokemon project root directory
python3 -m pikabot.main
```

Or from inside pikabot/:

```bash
cd pikabot
python3 main.py
```

This uses poke-env's local `battle_against()` mechanism (no server needed). Results are appended incrementally to `battle_logs/master.json` in JSONL format.

**Configuration**: Edit `main.py` to change `battles_per_pair` (line 26) or the team skip logic (lines 35-37).

### Player vs Bot Mode (Local Showdown Server)

Challenge a human player on a local Pokémon Showdown server. The bot uses a **randomly selected team** from the 50 pre-built VGC teams for each match — no hardcoded team, every run is different.

**Prerequisites:**
- Local Pokémon Showdown server running (from `pokemon-showdown/` directory or globally installed via `npm install -g pokemon-showdown`)
- A Showdown account logged in as `testing12344444` on the local server (default: `http://localhost:8000`)

**Steps to run:**

1. **Start the local Showdown server:**
   ```bash
   # From the pokemon-showdown/ directory
   node pokemon-showdown
   # Or if globally installed
   pokemon-showdown
   ```

2. **Log in as the target user:**
   - Open `http://localhost:8000` in a browser
   - Log in as username `testing12344444` (no password needed for local)
   - Stay on the home screen or lobby

3. **Run the bot:**
   ```bash
   # From the Pokemon project root directory
   python3 -m pikabot.pvb
   ```

**What happens:**
- The bot connects to `localhost:8000` as "PikaBot"
- Randomly selects one team from `VGC_TEAMS_LIST` (50 teams from Champions VGC stats)
- Sends a challenge to `testing12344444` for 1 battle
- Battle proceeds on the Showdown server; watch it live in the browser
- Match data is logged to `battle_logs/master.json` in JSONL format

**To play multiple battles:** Re-run the script — each run picks a new random team.

## Battle Logs (JSONL Format)

Match data is stored in `battle_logs/master.json` as **JSON Lines** (one compact JSON object per line):

```json
{"match_id":"battle-tag","match_uid":"uuid","player_username":"PikaBot 1","opponent_username":"PikaBot 2","match_outcome":"win|loss|tie","total_turns":15,"turns":[{"turn_number":1,"field":{"weather":"None","terrain":"None","trick_room":0},"battle_history":[],"my_side":{"side_conditions":{...},"active":[...],"bench":[...]},"opponent_side":{"side_conditions":{...},"active":[...],"bench":[...]},"target_orders":["incineroar uses fakeout targeting opponent slot 2","gengar mega evolves and uses shadowball targeting opponent slot 2"],"following_orders":[]},...]}
{"match_id":"battle-tag","match_uid":"uuid","player_username":"PikaBot 2","opponent_username":"PikaBot 1","match_outcome":"loss|win|tie","total_turns":15,"turns":[...]}
```

### Log Structure Per Match

| Field | Description |
|-------|-------------|
| `match_id` | Battle tag from poke-env (e.g., `battle-gen9championsvgc2026regmc-1711`) |
| `match_uid` | Unique UUID for deduplication |
| `player_username` | Bot's username |
| `opponent_username` | Opponent's username |
| `match_outcome` | `"win"`, `"loss"`, or `"tie"` |
| `total_turns` | Number of turns played |
| `turns` | Array of turn snapshots |

### Turn Snapshot Structure

```json
{
  "turn_number": 1,
  "field": { "weather": "None", "terrain": "None", "trick_room": 0 },
  "battle_history": [{ "turn_number": 0, "my_action": [...], "opponent_action": [...] }],
  "my_side": {
    "side_conditions": { "tailwind": 0, "reflect": 0, ... },
    "active": [{ "slot": 1, "species": "incineroar", "hp_pct": 100.0, "status": "None", "item": "sitrusberry", "ability": "intimidate" }, ...],
    "bench": [{ "species": "rillaboom", "hp_pct": 100.0, "status": "None" }, ...]
  },
  "opponent_side": { ... },
  "target_orders": ["incineroar uses fakeout targeting opponent slot 2", "rillaboom uses grassy glide targeting opponent slot 1"],
  "following_orders": ["incineroar switches to charizard"]
}
```

**Key fields:**
- `target_orders` — Initial orders for the turn (max 2, one per slot)
- `following_orders` — Subsequent actions (force switches, mega evolutions after initial order)
- `battle_history` — Previous turn's actions (my_action + opponent_action)
- All action strings are **lowercase** for consistency

Each battle creates **two match entries** (one per bot) with opposite outcomes.

## Key Implementation Details

- **Instance Isolation**: Each bot maintains independent state during battle (`opp_team_movepool`, `protect_last_turn`, `mega`, `item_used`, etc.)
- **Thread-Safe Writes**: Shared `master.json` uses a global `threading.Lock` + atomic append (single line per match)
- **OOM Prevention**: `self.all_matches` stores only UIDs (strings) for deduplication; full match objects never accumulate in memory
- **JSONL Format**: Each match written as `json.dumps(match, separators=(',', ':'), cls=DecimalEncoder)` + newline
- **Force Switch Handling**: Forced switches logged in `following_orders` and carried into next turn's `battle_history`
- **Mega Evolution**: Slot 0 priority when both active Pokémon can mega evolve; enforced by pair legality check
- **Lowercase Actions**: All action strings in logs normalized to lowercase

## Requirements

- Python 3.10+
- poke-env (installs automatically with pip)
- Local Pokémon Showdown server (for `pvb.py` mode only)

## Data Sources

- **champions-vgc-stats.json** — Raw usage stats from Champions VGC 2026 Regulation MA
- **top-50-vgc-teams.json** — 50 top teams parsed from the stats
- **EX_VGC_TEAM** — Hardcoded example team in `team.py`

## License

MIT