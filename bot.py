import os
import json
import uuid
import threading
from poke_env.player import Player, RandomPlayer
from poke_env.player.battle_order import DoubleBattleOrder
from pikabot.mixins.opponent_tracker import OpponentTrackerMixin
from pikabot.mixins.pokemon_info import PokemonInfoMixin
from pikabot.mixins.speed import SpeedMixin
from pikabot.mixins.damage import DamageMixin
from pikabot.mixins.status_moves import StatusMoveMixin
from pikabot.mixins.ordering import OrderingMixin
from pikabot.mixins.switching import SwitchingMixin


# Shared lock for thread-safe file writes to master.json
_master_file_lock = threading.Lock()

# Shared master path - both bots write to the same file
_SHARED_MASTER_PATH = os.path.join("battle_logs", "master.json")


class PikaBot(OpponentTrackerMixin, PokemonInfoMixin, SpeedMixin, DamageMixin, StatusMoveMixin, OrderingMixin, SwitchingMixin, Player):
    def __init__(self, *args, **kwargs):
        # This safely passes all configuration arguments (team, format, etc.) to the parent class
        super().__init__(*args, **kwargs)

        # Initialize opp team move pool attribute
        self.opp_team_movepool = {}
        self.mega = False
        self.protect_last_turn = [False, False]
        self.item_used = [False, False]
        self.last_moved_used = [None, None]

        # Match logging attributes - instance-level for isolation during battle
        self.all_matches = []
        self.current_match = None
        self.my_last_turn_actions = {}  # Keyed by battle_tag - actions from PREVIOUS turn for battle_history
        self._current_turn_planned = {}  # Keyed by battle_tag - planned moves for CURRENT turn (for move turn's target_moves)
        self._prev_opp_active = {}  # battle_tag -> list of species
        self._session_match_count = 0  # Track matches added in current session
        # Duplicate switch tracking now done by checking current_match["turns"] directly
        self._logged_move_turns = set()  # Track (battle_tag, turn_number) to prevent duplicate move entries
        self._logged_pivot_switches = set()  # Track (battle_tag, turn_number, pivot_key) to prevent duplicate pivot switch entries

        # Use shared master path for bot-vs-bot (both instances write to same file)
        self.master_path = _SHARED_MASTER_PATH

        # Load existing matches if master file exists (for resume capability)
        if os.path.exists(self.master_path):
            try:
                with open(self.master_path, 'r') as f:
                    data = json.load(f)
                    self.all_matches = data.get("matches", [])
            except (json.JSONDecodeError, KeyError):
                # If cannot be parsed, rename to backup and start fresh
                os.rename(self.master_path, self.master_path + ".bak")
                self.all_matches = []

    def _write_master_file(self):
        """Write all matches to the shared master JSON file using thread-safe read-merge-write."""
        with _master_file_lock:
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(self.master_path), exist_ok=True)

                # Read current file to get latest matches from other bot
                current_matches = []
                if os.path.exists(self.master_path):
                    try:
                        with open(self.master_path, 'r') as f:
                            data = json.load(f)
                            current_matches = data.get("matches", [])
                    except (json.JSONDecodeError, KeyError):
                        current_matches = []

                # Merge our matches with existing (avoid duplicates by match_uid)
                existing_uids = {m.get("match_uid") for m in current_matches if m.get("match_uid")}
                for match in self.all_matches:
                    if match.get("match_uid") not in existing_uids:
                        current_matches.append(match)

                # Prepare data
                data = {"matches": current_matches}

                # Write to temp file first
                temp_path = self.master_path + ".tmp"
                with open(temp_path, 'w') as f:
                    json.dump(data, f, indent=2)

                # Atomic replace
                os.replace(temp_path, self.master_path)

            except Exception as e:
                print(f"Error writing master file: {e}")
                # Clean up temp file if it exists
                temp_path = self.master_path + ".tmp"
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

    def _battle_finished_callback(self, battle):
        # Call super() first if it exists
        if hasattr(super(), '_battle_finished_callback'):
            super()._battle_finished_callback(battle)

        try:
            battle_tag = battle.battle_tag

            # Only process if this is our current match
            if self.current_match is not None and self.current_match["match_id"] == battle_tag:
                # Finalize match data
                if battle.won:
                    self.current_match["match_outcome"] = "win"
                elif battle.lost:
                    self.current_match["match_outcome"] = "loss"
                else:
                    self.current_match["match_outcome"] = "tie"

                self.current_match["total_turns"] = battle.turn

                # Avoid duplicates
                match_uid = self.current_match["match_uid"]
                if not any(match.get("match_uid") == match_uid for match in self.all_matches):
                    self.all_matches.append(self.current_match)
                    self._session_match_count += 1

                # Write all matches to shared master file (thread-safe)
                self._write_master_file()

                # Print confirmation
                print(f"saved match {match_uid[:8]} ({self._session_match_count} matches total for {self.username})")

                # Reset current match
                self.current_match = None

        except Exception as e:
            print(f"Error in battle finished callback: {e}")

    def _build_turn_snapshot(self, battle, last_turn_history):
        """Build the turn snapshot for the current turn."""
        from poke_env.battle.weather import Weather
        from poke_env.battle.field import Field
        from poke_env.battle.side_condition import SideCondition
        from poke_env.battle.status import Status

        # ---------- Weather ----------
        weather = "None"
        weather_map = {
            Weather.RAINDANCE: "Rain",
            Weather.SUNNYDAY: "Sun",
            Weather.SANDSTORM: "Sandstorm",
            Weather.SNOWSCAPE: "Snow",
        }
        raw_weather = getattr(battle, 'weather', None)
        if isinstance(raw_weather, dict):
            for weather_enum, weather_name in weather_map.items():
                if weather_enum in raw_weather:
                    weather = weather_name
                    break
        elif raw_weather in weather_map:
            weather = weather_map[raw_weather]

        # ---------- Terrain ----------
        terrain = "None"
        terrain_map = {
            Field.ELECTRIC_TERRAIN: "Electric",
            Field.GRASSY_TERRAIN: "Grassy",
            Field.MISTY_TERRAIN: "Misty",
            Field.PSYCHIC_TERRAIN: "Psychic",
        }
        if hasattr(battle, 'fields'):
            for field_enum, terrain_name in terrain_map.items():
                if field_enum in battle.fields:
                    terrain = terrain_name
                    break

        # ---------- Trick Room ----------
        trick_room = 0
        if hasattr(battle, 'fields') and Field.TRICK_ROOM in battle.fields:
            start_turn = battle.fields[Field.TRICK_ROOM]
            trick_room = max(0, 5 - (battle.turn - start_turn))

        # ---------- Side conditions (shared logic for both sides) ----------
        def build_side_conditions(side_conditions):
            sc = {
                "tailwind": 0, "reflect": 0, "light_screen": 0, "aurora_veil": 0,
                "stealth_rock": 0, "spikes": 0, "toxic_spikes": 0, "sticky_web": 0,
            }
            if not side_conditions:
                return sc

            # Timed effects: dict value is the turn the effect started
            timed = {
                SideCondition.TAILWIND: ("tailwind", 4),
                SideCondition.REFLECT: ("reflect", 5),
                SideCondition.LIGHT_SCREEN: ("light_screen", 5),
                SideCondition.AURORA_VEIL: ("aurora_veil", 5),
            }
            for enum_key, (json_key, duration) in timed.items():
                if enum_key in side_conditions:
                    start_turn = side_conditions[enum_key]
                    sc[json_key] = max(0, duration - (battle.turn - start_turn))

            # Stackable hazards: dict value is the layer count
            if SideCondition.SPIKES in side_conditions:
                sc["spikes"] = side_conditions[SideCondition.SPIKES]
            if SideCondition.TOXIC_SPIKES in side_conditions:
                sc["toxic_spikes"] = side_conditions[SideCondition.TOXIC_SPIKES]

            # Non-stackable hazards: present => 1
            if SideCondition.STEALTH_ROCK in side_conditions:
                sc["stealth_rock"] = 1
            if SideCondition.STICKY_WEB in side_conditions:
                sc["sticky_web"] = 1

            return sc

        my_side_conditions = build_side_conditions(
            getattr(battle, 'side_conditions', None))
        opponent_side_conditions = build_side_conditions(
            getattr(battle, 'opponent_side_conditions', None))

        # ---------- My active Pokemon ----------
        my_active = []
        if hasattr(battle, 'active_pokemon'):
            for i, mon in enumerate(battle.active_pokemon):
                if mon is not None:
                    hp_pct = round(mon.current_hp_fraction * 100, 1) if mon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if mon.status:
                        status_map = {
                            Status.BRN: "BRN", Status.FNT: "FNT", Status.FRZ: "FRZ",
                            Status.PAR: "PAR", Status.PSN: "PSN", Status.SLP: "SLP", Status.TOX: "TOX"
                        }
                        status = status_map.get(mon.status, str(mon.status).split('.')[-1] if mon.status else "None")

                    my_active.append({
                        "slot": i + 1,
                        "species": mon.species if mon.species else "Unknown",
                        "hp_pct": hp_pct,
                        "status": status,
                        "item": mon.item if mon.item else None,
                        "ability": mon.ability if mon.ability else None
                    })

        # ---------- Opponent active Pokemon (limited info) ----------
        opponent_active = []
        if hasattr(battle, 'opponent_active_pokemon'):
            for i, mon in enumerate(battle.opponent_active_pokemon):
                if mon is not None:
                    hp_pct = round(mon.current_hp_fraction * 100, 1) if mon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if mon.status:
                        status_map = {
                            Status.BRN: "BRN", Status.FNT: "FNT", Status.FRZ: "FRZ",
                            Status.PAR: "PAR", Status.PSN: "PSN", Status.SLP: "SLP", Status.TOX: "TOX"
                        }
                        status = status_map.get(mon.status, str(mon.status).split('.')[-1] if mon.status else "None")

                    opponent_active.append({
                        "slot": i + 1,
                        "species": mon.species if mon.species else "Unknown",
                        "hp_pct": hp_pct,
                        "status": status
                    })

        # ---------- My bench ----------
        my_bench = []
        if hasattr(battle, 'team'):
            active_species = [mon.species for mon in battle.active_pokemon if mon is not None and mon.species]
            for pokemon in battle.available_switches[0]:
                if pokemon.species not in active_species:
                    hp_pct = round(pokemon.current_hp_fraction * 100, 1) if pokemon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if pokemon.status:
                        status_map = {
                            Status.BRN: "BRN", Status.FNT: "FNT", Status.FRZ: "FRZ",
                            Status.PAR: "PAR", Status.PSN: "PSN", Status.SLP: "SLP", Status.TOX: "TOX"
                        }
                        status = status_map.get(pokemon.status, str(pokemon.status).split('.')[-1] if pokemon.status else "None")

                    my_bench.append({
                        "species": pokemon.species if pokemon.species else "Unknown",
                        "hp_pct": hp_pct,
                        "status": status
                    })

        # ---------- Opponent bench (limited info) ----------
        opponent_bench = []
        if hasattr(battle, 'opponent_team'):
            active_species = [mon.species for mon in battle.opponent_active_pokemon if mon is not None and mon.species]
            for pokemon in battle.opponent_team.values():
                if pokemon.species not in active_species:
                    hp_pct = round(pokemon.current_hp_fraction * 100, 1) if pokemon.current_hp_fraction is not None else 0.0
                    opponent_bench.append({
                        "species": pokemon.species if pokemon.species else "Unknown",
                        "hp_pct": hp_pct
                    })

        # ---------- Build the turn snapshot ----------
        turn_snapshot = {
            "turn_number": battle.turn,
            "field": {
                "weather": weather,
                "terrain": terrain,
                "trick_room": trick_room
            },
            "battle_history": [last_turn_history] if last_turn_history else [],
            "my_side": {
                "side_conditions": my_side_conditions,
                "active": my_active,
                "bench": my_bench
            },
            "opponent_side": {
                "side_conditions": opponent_side_conditions,
                "active": opponent_active,
                "bench": opponent_bench
            }
        }

        return turn_snapshot

    def _get_opponent_actions(self, battle, turn_number):
        """Extract opponent actions for the given (just-finished) turn from battle.observations
        and from opponent_active_pokemon.last_move as fallback. Also detects switches by
        comparing with previous turn's active pokemon."""
        opponent_actions = []
        battle_tag = battle.battle_tag

        # First try: extract from battle.observations (detailed event log)
        observations = getattr(battle, 'observations', None)
        if isinstance(observations, dict) and turn_number in observations:
            obs = observations[turn_number]
            events = getattr(obs, 'events', None)
            if isinstance(events, list):
                # Determine the opponent's role ("p1" / "p2")
                opp_role = getattr(battle, 'opponent_role', None)
                if opp_role is None:
                    player_role = getattr(battle, 'player_role', None)
                    if player_role == "p1":
                        opp_role = "p2"
                    elif player_role == "p2":
                        opp_role = "p1"

                if opp_role is not None:
                    for event in events:
                        if not isinstance(event, list) or len(event) < 3:
                            continue
                        event_type = event[1]
                        pokemon_str = event[2]  # e.g. "p2a: Incineroar"
                        if not isinstance(pokemon_str, str) or not pokemon_str.startswith(opp_role):
                            continue

                        if event_type == "move":
                            move_name = event[3] if len(event) > 3 else ""
                            action = f"{pokemon_str} used {move_name}"
                            target = event[4] if len(event) > 4 else ""
                            if target:
                                action += f" targeting {target}"
                            opponent_actions.append(action.lower())

                        elif event_type == "switch":
                            opponent_actions.append(f"{pokemon_str} switched in".lower())

        # Fallback 1: if observations didn't yield actions, use opponent_active_pokemon.last_move
        if not opponent_actions and hasattr(battle, 'opponent_active_pokemon'):
            for i, opp_pokemon in enumerate(battle.opponent_active_pokemon):
                if opp_pokemon is not None and not opp_pokemon.fainted:
                    last_move = getattr(opp_pokemon, 'last_move', None)
                    if last_move is not None:
                        move_name = getattr(last_move, 'id', str(last_move))
                        species = opp_pokemon.species if opp_pokemon.species else "Unknown"
                        # Format similar to our own action strings
                        action = f"{species} uses {move_name.replace('_', ' ').title()}"
                        opponent_actions.append(action.lower())
                    elif opp_pokemon.fainted:
                        species = opp_pokemon.species if opp_pokemon.species else "Unknown"
                        opponent_actions.append(f"{species} fainted".lower())

        # Fallback 2: detect switches by comparing with previous turn's active pokemon
        # Get current active species (at the time this is called - which is start of next turn)
        current_opp_active = []
        if hasattr(battle, 'opponent_active_pokemon'):
            for opp_pokemon in battle.opponent_active_pokemon:
                if opp_pokemon is not None and opp_pokemon.species:
                    current_opp_active.append(opp_pokemon.species)

        # Compare with previous turn's active pokemon
        prev_opp_active = self._prev_opp_active.get(battle_tag, [])
        if prev_opp_active:
            # Find pokemon that were in prev but not in current (switched out or fainted)
            # Find pokemon that are in current but not in prev (switched in)
            for species in current_opp_active:
                if species not in prev_opp_active:
                    # This pokemon was switched in
                    opponent_actions.append(f"{species} switched in".lower())
            # Also check for fainted pokemon that were in prev but not in current
            for species in prev_opp_active:
                if species not in current_opp_active:
                    # Check if it's in bench with 0 HP (fainted)
                    found_in_bench = False
                    if hasattr(battle, 'opponent_team'):
                        for p in battle.opponent_team.values():
                            if p.species == species and p.current_hp_fraction == 0:
                                found_in_bench = True
                                break
                    if found_in_bench:
                        opponent_actions.append(f"{species} fainted".lower())
                    else:
                        opponent_actions.append(f"{species} switched out".lower())

        return opponent_actions

    def _order_to_action_strings(self, order, battle):
        """Convert a DoubleBattleOrder to readable action strings."""
        action_strings = []

        # Handle DoubleBattleOrder which has first_order and second_order attributes
        if hasattr(order, 'first_order') and hasattr(order, 'second_order'):
            # Process first order - pass the SingleBattleOrder wrapper to preserve mega flag
            if order.first_order is not None:
                action_strings.append(self._single_order_to_string(order.first_order, battle, 0))

            # Process second order
            if order.second_order is not None:
                action_strings.append(self._single_order_to_string(order.second_order, battle, 1))
        else:
            # Fallback: try to treat as iterable
            if hasattr(order, '__iter__'):
                # It's a DoubleBattleOrder with two orders
                for i, single_order in enumerate(order):
                    if single_order is not None:
                        action_strings.append(self._single_order_to_string(single_order, battle, i))
            else:
                # It's a single order
                action_strings.append(self._single_order_to_string(order, battle, 0))

        return action_strings

    def _single_order_to_string(self, order, battle, index):
        """Convert a single order to a readable string."""
        # Import here to avoid circular imports
        from poke_env.player.battle_order import Move, Pokemon, SingleBattleOrder

        # Check if this is a SingleBattleOrder wrapper with mega/z_move/dynamax/terastallize flags
        is_mega = False
        is_z_move = False
        is_dynamax = False
        is_terastallize = False
        move_target = 0

        if isinstance(order, SingleBattleOrder):
            is_mega = getattr(order, 'mega', False)
            is_z_move = getattr(order, 'z_move', False)
            is_dynamax = getattr(order, 'dynamax', False)
            is_terastallize = getattr(order, 'terastallize', False)
            move_target = getattr(order, 'move_target', 0)
            # Extract the actual order (Move or Pokemon) from SingleBattleOrder
            actual_order = order.order
        else:
            actual_order = order

        if isinstance(actual_order, Move):
            # It's a move
            move = actual_order
            pokemon = battle.active_pokemon[index] if index < len(battle.active_pokemon) else None
            species = pokemon.species if pokemon and pokemon.species else "unknown"

            # If species unknown, try to infer from move ownership
            if species == "unknown":
                move_id = getattr(move, 'id', None)
                if move_id is not None:
                    for p in battle.active_pokemon:
                        if p and hasattr(p, 'moves') and move_id in p.moves:
                            species = p.species if p.species else "unknown"
                            break

            # Get move name - try to get the id, otherwise use the name
            move_name = getattr(move, 'id', None)
            if move_name is None:
                move_name = getattr(move, 'name', str(move))
            # Convert underscores to spaces, lowercase for consistency
            move_name = move_name.replace('_', ' ').lower()

            # Format: "species mega evolves and uses move" or "species uses move"
            if is_mega:
                action = f"{species.lower()} mega evolves and uses {move_name}"
            else:
                action = f"{species.lower()} uses {move_name}"

            # Add targeting info if applicable
            if move_target is not None:
                target = move_target
                if target == 1:
                    action += " targeting opponent slot 1"
                elif target == 2:
                    action += " targeting opponent slot 2"
                elif target == -1:
                    action += " targeting ally slot 1"
                elif target == -2:
                    action += " targeting ally slot 2"
                # target == 0 means no target (field move) - no addition

            return action

        elif isinstance(actual_order, Pokemon):
            # It's a switch
            target_pokemon = actual_order
            pokemon = battle.active_pokemon[index] if index < len(battle.active_pokemon) else None
            species = pokemon.species if pokemon and pokemon.species else "unknown"
            target_species = target_pokemon.species if target_pokemon and target_pokemon.species else "unknown"

            return f"{species.lower()} switches to {target_species.lower()}"

        else:
            # Fallback - try to make it readable
            order_str = str(order)
            # If it looks like a raw pokemon showdown command, try to make it nicer
            if order_str.startswith('/choose ') or '|' in order_str:
                return f"pokemon action {index}"  # Generic fallback
            return order_str.lower()

    def choose_move(self, battle):
        # Update clam bot data on opponnent
        self.update_opponent_knowledge(battle)

        # Light check for item used
        for index, pokemon in enumerate(battle.active_pokemon):
            if pokemon is not None and pokemon.item is None:
                self.item_used[index] = True
            else:
                self.item_used[index] = False

        # If there is a force switch
        if any(battle.force_switch):
            left_switch = None
            right_switch = None

            # Double forced switch
            if battle.force_switch[0] and battle.force_switch[1]:

                best_left_mon = self.choose_best_switch(0, battle)
                best_right_mon = self.choose_best_switch(1, battle, exclude_mon=best_left_mon)

                if best_left_mon:
                    left_switch = self.create_order(best_left_mon)
                if best_right_mon:
                    right_switch = self.create_order(best_right_mon)

                if left_switch and right_switch:
                    chosen_order = DoubleBattleOrder(left_switch, right_switch)
                elif left_switch:
                    chosen_order = left_switch
                elif right_switch:
                    chosen_order = right_switch
                else:
                    chosen_order = self.choose_random_doubles_move(battle)
            # Left forced switch
            elif battle.force_switch[0]:
                best_left_mon = self.choose_best_switch(0, battle)
                if best_left_mon:
                    chosen_order = self.create_order(best_left_mon)
                else:
                    chosen_order = self.choose_random_doubles_move(battle)
            # Right forced switch
            elif battle.force_switch[1]:
                best_right_mon = self.choose_best_switch(1, battle)
                if best_right_mon:
                    chosen_order = self.create_order(best_right_mon)
                else:
                    chosen_order = self.choose_random_doubles_move(battle)
        else:
            if battle.available_moves[0] and battle.available_moves[1]:
                # Use choose_best_double_order for proper pair legality & synergy
                left_order, right_order = self.choose_best_double_order(battle)
                if left_order is not None and right_order is not None:
                    chosen_order = DoubleBattleOrder(left_order, right_order)
                elif left_order is not None:
                    chosen_order = left_order
                elif right_order is not None:
                    chosen_order = right_order
                else:
                    chosen_order = self.choose_random_doubles_move(battle)

            elif battle.available_moves[0]:
                chosen_order = self.choose_best_order(battle.active_pokemon[0], battle, battle.available_moves[0])

            elif battle.available_moves[1]:
                chosen_order = self.choose_best_order(battle.active_pokemon[1], battle, battle.available_moves[1])

            # Fallback to random selection
            else:
                print("random move")
                chosen_order = self.choose_random_doubles_move(battle)

        # --- Battle logging ---
        try:
            battle_tag = battle.battle_tag

            # Initialize match container if it's a new game or safety net for unfinished match
            if self.current_match is None or self.current_match["match_id"] != battle_tag:
                # Safety net: if current_match exists but is for a different battle, save it first
                if self.current_match is not None:
                    self.all_matches.append(self.current_match)
                    self._write_master_file()

                # Start new match
                self.current_match = {
                    "match_id": battle_tag,
                    "match_uid": str(uuid.uuid4()),
                    "player_username": battle.player_username,
                    "opponent_username": battle.opponent_username,
                    "match_outcome": None,
                    "total_turns": None,
                    "turns": []
                }
                self.my_last_turn_actions[battle_tag] = []
                self._current_turn_planned[battle_tag] = []
                self._logged_move_turns.discard((battle_tag, battle.turn))  # Clear for new match
                # Clear pivot switch tracking for this battle
                keys_to_remove = [k for k in self._logged_pivot_switches if k[0] == battle_tag]
                for k in keys_to_remove:
                    self._logged_pivot_switches.discard(k)

            # Build history for the turn that JUST finished (turn N-1)
            last_turn_number = battle.turn - 1
            if last_turn_number >= 1:
                last_turn_history = {
                    "turn_number": last_turn_number,
                    "my_action": self.my_last_turn_actions.get(battle_tag, []),
                    "opponent_action": self._get_opponent_actions(battle, last_turn_number)
                }
            else:
                last_turn_history = {}

            # Build current turn board state snapshot (for turn N)
            turn_snapshot = self._build_turn_snapshot(battle, last_turn_history)

            # Store opponent active pokemon for switch detection in next turn
            opp_active_species = []
            if "opponent_side" in turn_snapshot and "active" in turn_snapshot["opponent_side"]:
                for opp in turn_snapshot["opponent_side"]["active"]:
                    if opp and "species" in opp:
                        opp_active_species.append(opp["species"])
            self._prev_opp_active[battle_tag] = opp_active_species

            # Handle force_switch: create switch entry ONLY for death slots (fainted Pokemon)
            # Pivot switches (U-turn, Parting Shot, etc.) are appended to the previous move turn
            if any(battle.force_switch):
                # Separate forced slots into death slots and pivot slots
                death_switch_slots = []
                death_switch_reasons = []
                death_switch_target_moves = []
                pivot_switch_slots = []
                pivot_switch_target_moves = []

                for i, force_sw in enumerate(battle.force_switch):
                    if not force_sw:
                        continue

                    slot_num = i + 1  # 1 = left, 2 = right

                    # Check if the Pokemon in this slot has fainted (death) or is pivoting
                    mon = battle.active_pokemon[i] if i < len(battle.active_pokemon) else None
                    is_death = mon is not None and (getattr(mon, 'fainted', False) or (getattr(mon, 'current_hp_fraction', 1) or 1) <= 0)

                    # Get the replacement species from the chosen_order
                    replacement_species = "unknown"
                    if hasattr(chosen_order, 'first_order') and hasattr(chosen_order, 'second_order'):
                        # DoubleBattleOrder - check first_order or second_order based on slot
                        order_for_slot = chosen_order.first_order if i == 0 else chosen_order.second_order
                        if order_for_slot is not None:
                            actual_order = order_for_slot.order if hasattr(order_for_slot, 'order') else order_for_slot
                            if hasattr(actual_order, 'species'):
                                replacement_species = actual_order.species
                    elif hasattr(chosen_order, 'order'):
                        # SingleBattleOrder
                        actual_order = chosen_order.order
                        if hasattr(actual_order, 'species'):
                            replacement_species = actual_order.species

                    switch_str = f"switches to {replacement_species.lower()}"

                    if is_death:
                        death_switch_slots.append(slot_num)
                        death_switch_reasons.append("fainted")
                        death_switch_target_moves.append(switch_str)
                    else:
                        pivot_switch_slots.append(slot_num)
                        pivot_switch_target_moves.append(switch_str)

                # Handle pivot slots: append to previous move turn's following_moves and my_action
                if pivot_switch_target_moves:
                    # Create a unique key for this pivot switch combination
                    pivot_key = tuple(sorted(pivot_switch_target_moves))
                    pivot_dedup_key = (battle_tag, battle.turn, pivot_key)

                    # Skip if already logged
                    if pivot_dedup_key in self._logged_pivot_switches:
                        pass  # Already logged, skip
                    else:
                        self._logged_pivot_switches.add(pivot_dedup_key)

                        # Find the last move turn in current_match to append pivot replacements
                        # Only consider turns with turn_number < battle.turn (previous turns)
                        # because choose_move can be called twice per turn in local battles
                        last_move_turn = None
                        for turn in reversed(self.current_match.get("turns", [])):
                            # Any turn without turn_type is a valid turn (we removed turn_type)
                            if "target_orders" in turn and turn.get("turn_number", 0) < battle.turn:
                                last_move_turn = turn
                                break

                        if last_move_turn is not None:
                            # Initialize following_moves if not present
                            if "following_moves" not in last_move_turn:
                                last_move_turn["following_moves"] = []

                            # Append pivot replacements to the move turn's following_moves
                            last_move_turn["following_moves"].extend([s.lower() for s in pivot_switch_target_moves])

                            # Also append to the my_action history for that turn (stored in my_last_turn_actions)
                            # This will be used for the next turn's battle_history
                            my_actions = self.my_last_turn_actions.get(battle_tag, [])
                            my_actions.extend([s.lower() for s in pivot_switch_target_moves])
                            self.my_last_turn_actions[battle_tag] = my_actions

                            # Also update the last_turn_history that was just built for this turn's battle_history
                            if last_turn_history and "my_action" in last_turn_history:
                                last_turn_history["my_action"].extend([s.lower() for s in pivot_switch_target_moves])

                # Handle death slots: create turn entry with target_orders/following_moves
                if death_switch_target_moves:
                    # Deduplicate by checking existing turns in current match
                    turn_num = battle.turn
                    slots_tuple = tuple(death_switch_slots)
                    already_logged = False
                    for existing_turn in self.current_match.get("turns", []):
                        if (existing_turn.get("turn_number") == turn_num and
                            tuple(existing_turn.get("switch_slots", [])) == slots_tuple):
                            already_logged = True
                            break

                    if already_logged:
                        return chosen_order

                    # New schema: target_orders = all initial switches (up to 2), following_moves = rest
                    switch_target_orders = [s.lower() for s in death_switch_target_moves[:2]] if death_switch_target_moves else []
                    switch_following = [s.lower() for s in death_switch_target_moves[2:]] if len(death_switch_target_moves) > 2 else []

                    switch_snapshot = {
                        "turn_number": battle.turn,
                        "switch_slots": death_switch_slots,
                        "switch_reasons": death_switch_reasons,
                        "field": turn_snapshot["field"],
                        "battle_history": turn_snapshot["battle_history"],
                        "my_side": turn_snapshot["my_side"],
                        "opponent_side": turn_snapshot["opponent_side"],
                        "target_orders": switch_target_orders,
                        "following_moves": switch_following
                    }

                    # Get the planned actions for this turn (stored when move turn was logged)
                    planned_actions = self._current_turn_planned.get(battle_tag, [])

                    # Save planned actions for NEXT turn's battle_history, extended with death switch actions
                    next_turn_my_actions = planned_actions + [s.lower() for s in death_switch_target_moves]
                    self.my_last_turn_actions[battle_tag] = next_turn_my_actions

                    # Append the switch turn
                    self.current_match["turns"].append(switch_snapshot)

                # If only pivot slots (no death slots), we don't create a switch entry
                # Just return the chosen_order after handling pivot logging above
                return chosen_order

            # Normal move turn (no force switch) - log the planned moves

            # Check if we've already logged a move turn for this battle turn
            move_key = (battle_tag, battle.turn)
            if move_key in self._logged_move_turns:
                # Already logged move turn for this turn, skip
                return chosen_order
            self._logged_move_turns.add(move_key)

            # Save the chosen order as planned actions for this turn
            action_strings = self._order_to_action_strings(chosen_order, battle)
            action_strings = [s.lower() for s in action_strings]
            self._current_turn_planned[battle_tag] = action_strings

            # Save for NEXT turn's battle_history
            self.my_last_turn_actions[battle_tag] = action_strings

            # New schema: target_orders = max 2 initial orders, following_moves = rest
            turn_snapshot["target_orders"] = action_strings[:2]
            turn_snapshot["following_moves"] = action_strings[2:] if len(action_strings) > 2 else []

            # Append snapshot to the current match
            self.current_match["turns"].append(turn_snapshot)

        except Exception as e:
            # Keep logging inside try/except, print one short error line on failure
            print(f"Logging error: {e}")

        return chosen_order

    def teampreview(self, battle):
        return self.random_teampreview(battle)