# PikaBot

A Pokemon VGC (Video Game Championships) doubles battle bot built with [poke-env](https://github.com/hsahovic/poke-env). Designed for Gen 9 Champions VGC 2026 Regulation MA format.

## Features

- **VGC Doubles Battle Logic**: Custom move selection, and switching
- **Match Telemetry Logging**: Detailed battle logs with turn-by-turn state snapshots
- **Bot-vs-Bot Self-Play**: Two independent PikaBot instances can battle each other locally
- **Shared Match Storage**: Both bots write to a single `battle_logs/master.json` file with thread-safe atomic writes
- **Opponent Action Tracking**: Captures opponent moves, switches, and faints from battle observations

## Project Structure

```
pikabot/
├── bot.py              # Main PikaBot class with battle logic and logging
├── main.py             # Entry point for running bot battles
├── team.py             # Team definitions (EX_VGC_TEAM)
└── mixins/             # Battle decision logic modules
    ├── damage.py
    ├── ordering.py
    ├── opponent_tracker.py
    ├── pokemon_info.py
    ├── speed.py
    ├── status_moves.py
    └── switching.py
```

## Installation

```bash
# From the Pokemon project root directory
pip install poke-env
```

## Running Battles

### Bot vs Bot (Local Self-Play)

```bash
cd ~
python3 -m pikabot.main
```

This runs 1 battle between two PikaBot instances using poke-env's local battle mechanism. Results are appended to `battle_logs/master.json`.

### Custom Battle Count

Edit `main.py` to change `n_battles`:

```python
await player1.battle_against(player2, n_battles=10)
```

## Battle Logs

Match data is stored in `battle_logs/master.json` with this structure:

```json
{
  "matches": [
    {
      "match_id": "battle-tag",
      "match_uid": "unique-id",
      "player_username": "PikaBot 1",
      "opponent_username": "PikaBot 2",
      "match_outcome": "win|loss|tie",
      "total_turns": 15,
      "turns": [
        {
          "turn_number": 1,
          "field": { "weather": "None", "terrain": "None", "trick_room": 0 },
          "battle_history": [{ "turn_number": 0, "my_action": [], "opponent_action": [] }],
          "my_side": { "side_conditions": {...}, "active": [...], "bench": [...] },
          "opponent_side": { "side_conditions": {...}, "active": [...], "bench": [...] },
          "target": "incineroar uses flare blitz, rillaboom uses grassy glide"
        }
      ]
    }
  ]
}
```

Each battle creates **two match entries** (one per bot) with opposite outcomes.

## Key Implementation Details

- **Instance Isolation**: Each bot maintains independent state during battle (`opp_team_movepool`, `protect_last_turn`, etc.)
- **Thread-Safe Writes**: Shared `master.json` uses a global lock + read-merge-write pattern with atomic `os.replace`
- **Lowercase Actions**: All action strings in logs are lowercase for consistency
- **Force Switch Handling**: Forced switches are logged as part of the next turn's battle history

## Requirements

- Python 3.10+
- poke-env (installs automatically with pip)

## License

MIT