import os
import json
import uuid
from poke_env.player import Player, RandomPlayer
from poke_env.player.battle_order import DoubleBattleOrder
from pikabot.mixins.opponent_tracker import OpponentTrackerMixin
from pikabot.mixins.pokemon_info import PokemonInfoMixin
from pikabot.mixins.speed import SpeedMixin
from pikabot.mixins.damage import DamageMixin
from pikabot.mixins.status_moves import StatusMoveMixin
from pikabot.mixins.ordering import OrderingMixin
from pikabot.mixins.switching import SwitchingMixin


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

        # Match logging attributes
        self.all_matches = []
        self.current_match = None
        self.my_last_turn_actions = {}  # Keyed by battle_tag
        self.master_path = "battle_logs/master.json"

        # Load existing matches if master file exists
        if os.path.exists(self.master_path):
            try:
                with open(self.master_path, 'r') as f:
                    data = json.load(f)
                    self.all_matches = data.get("matches", [])
            except (json.JSONDecodeError, KeyError):
                # If cannot be parsed, rename to backup and start fresh
                os.rename(self.master_path, self.master_path + ".bak")
                self.all_matches = []

    def select_model_move(self, battle):
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
                    return DoubleBattleOrder(left_switch, right_switch)
                elif left_switch:
                    return left_switch
                elif right_switch:
                    return right_switch

            # Left forced switch
            elif battle.force_switch[0]:
                best_left_mon = self.choose_best_switch(0, battle)
                if best_left_mon:
                    return self.create_order(best_left_mon)

            # Right forced switch
            elif battle.force_switch[1]:
                best_right_mon = self.choose_best_switch(1, battle)
                if best_right_mon:
                    return self.create_order(best_right_mon)

        if battle.available_moves[0] and battle.available_moves[1]:

            left_order = self.choose_best_order(battle.active_pokemon[0], battle, battle.available_moves[0])
            right_order = self.choose_best_order(battle.active_pokemon[1], battle, battle.available_moves[1])

            return DoubleBattleOrder(left_order, right_order)

        elif battle.available_moves[0]:
            return self.choose_best_order(battle.active_pokemon[0], battle, battle.available_moves[0])

        elif battle.available_moves[1]:
            return self.choose_best_order(battle.active_pokemon[1], battle, battle.available_moves[1])

        # Fallback to random selection
        else:
            print("random move")
            return self.choose_random_doubles_move(battle)

    def choose_move(self, battle):
        # Get the chosen order from the model
        chosen_order = self.select_model_move(battle)

        # Skip logging during force switch (mid-turn replacement)
        if any(battle.force_switch):
            return chosen_order

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

            # Append snapshot to the current match
            self.current_match["turns"].append(turn_snapshot)

            # Save the chosen order so it becomes 'my_action' on the NEXT turn
            action_strings = self._order_to_action_strings(chosen_order, battle)
            self.my_last_turn_actions[battle_tag] = action_strings
            # Set target_moves to readable string
            turn_snapshot["target_moves"] = ", ".join(action_strings)

        except Exception as e:
            # Keep logging inside try/except, print one short error line on failure
            print(f"Logging error: {e}")

        return chosen_order

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

                # Write all matches to master file
                self._write_master_file()

                # Print confirmation
                print(f"saved match {match_uid[:8]} ({len(self.all_matches)} matches total)")

                # Reset current match
                self.current_match = None

        except Exception as e:
            print(f"Error in battle finished callback: {e}")

    def _build_turn_snapshot(self, battle, last_turn_history):
        """Build the turn snapshot for the current turn."""
        # Weather
        weather = "None"
        if hasattr(battle, 'weather') and battle.weather:
            from poke_env.battle.weather import Weather
            if battle.weather in Weather:
                weather_map = {
                    Weather.RAINDANCE: "Rain",
                    Weather.SUNNYDAY: "Sun",
                    Weather.SANDSTORM: "Sandstorm",
                    Weather.SNOWSCAPE: "Snow"
                }
                weather = weather_map.get(battle.weather, "None")

        # Terrain
        terrain = "None"
        from poke_env.battle.field import Field
        if hasattr(battle, 'fields'):
            terrain_map = {
                Field.ELECTRIC_TERRAIN: "Electric",
                Field.GRASSY_TERRAIN: "Grassy",
                Field.MISTY_TERRAIN: "Misty",
                Field.PSYCHIC_TERRAIN: "Psychic"
            }
            for field_field, terrain_name in terrain_map.items():
                if field_field in battle.fields:
                    terrain = terrain_name
                    break

        # Trick Room (remaining turns)
        trick_room = 0
        if hasattr(battle, 'fields') and Field.TRICK_ROOM in battle.fields:
            start_turn = battle.fields[Field.TRICK_ROOM]
            trick_room = max(0, 5 - (battle.turn - start_turn))

        # Side conditions for my side
        my_side_conditions = {
            "tailwind": 0, "reflect": 0, "light_screen": 0, "aurora_veil": 0,
            "stealth_rock": 0, "spikes": 0, "toxic_spikes": 0, "sticky_web": 0
        }
        if hasattr(battle, 'side_conditions'):
            side_condition_map = {
                "tailwind": "tailwind",
                "reflect": "reflect",
                "light_screen": "light_screen",
                "aurora_veil": "aurora_veil",
                "stealth_rock": "stealth_rock",
                "spikes": "spikes",
                "toxic_spikes": "toxic_spikes",
                "sticky_web": "sticky_web"
            }
            for condition_key, battle_key in side_condition_map.items():
                # Find the matching SideCondition enum value
                from poke_env.battle.side_condition import SideCondition
                for sc in SideCondition:
                    if sc.name.lower() == battle_key.upper():
                        if sc in battle.side_conditions:
                            start_turn = battle.side_conditions[sc]
                            if condition_key in ["tailwind", "reflect", "light_screen", "aurora_veil"]:
                                # Timed conditions: remaining turns
                                durations = {"tailwind": 4, "reflect": 5, "light_screen": 5, "aurora_veil": 5}
                                my_side_conditions[condition_key] = max(0, durations[condition_key] - (battle.turn - start_turn))
                            else:
                                # Hazard conditions: layer count
                                my_side_conditions[condition_key] = start_turn  # Assuming start_turn stores layer count
                        break

        # Side conditions for opponent side
        opponent_side_conditions = {
            "tailwind": 0, "reflect": 0, "light_screen": 0, "aurora_veil": 0,
            "stealth_rock": 0, "spikes": 0, "toxic_spikes": 0, "sticky_web": 0
        }
        if hasattr(battle, 'opponent_side_conditions'):
            side_condition_map = {
                "tailwind": "tailwind",
                "reflect": "reflect",
                "light_screen": "light_screen",
                "aurora_veil": "aurora_veil",
                "stealth_rock": "stealth_rock",
                "spikes": "spikes",
                "toxic_spikes": "toxic_spikes",
                "sticky_web": "sticky_web"
            }
            for condition_key, battle_key in side_condition_map.items():
                # Find the matching SideCondition enum value
                from poke_env.battle.side_condition import SideCondition
                for sc in SideCondition:
                    if sc.name.lower() == battle_key.upper():
                        if sc in battle.opponent_side_conditions:
                            start_turn = battle.opponent_side_conditions[sc]
                            if condition_key in ["tailwind", "reflect", "light_screen", "aurora_veil"]:
                                # Timed conditions: remaining turns
                                durations = {"tailwind": 4, "reflect": 5, "light_screen": 5, "aurora_veil": 5}
                                opponent_side_conditions[condition_key] = max(0, durations[condition_key] - (battle.turn - start_turn))
                            else:
                                # Hazard conditions: layer count
                                opponent_side_conditions[condition_key] = start_turn  # Assuming start_turn stores layer count
                        break

        # My active Pokemon
        my_active = []
        if hasattr(battle, 'active_pokemon'):
            for i, mon in enumerate(battle.active_pokemon):
                if mon is not None:
                    hp_pct = round(mon.current_hp_fraction * 100, 1) if mon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if mon.status:
                        from poke_env.battle.status import Status
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

        # Opponent active Pokemon (limited info)
        opponent_active = []
        if hasattr(battle, 'opponent_active_pokemon'):
            for i, mon in enumerate(battle.opponent_active_pokemon):
                if mon is not None:
                    hp_pct = round(mon.current_hp_fraction * 100, 1) if mon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if mon.status:
                        from poke_env.battle.status import Status
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

        # My bench
        my_bench = []
        if hasattr(battle, 'team'):
            active_species = [mon.species for mon in battle.active_pokemon if mon is not None and mon.species]
            for pokemon in battle.team.values():
                if pokemon.species not in active_species:
                    hp_pct = round(pokemon.current_hp_fraction * 100, 1) if pokemon.current_hp_fraction is not None else 0.0
                    status = "None"
                    if pokemon.status:
                        from poke_env.battle.status import Status
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

        # Opponent bench (limited info)
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

        # Build the turn snapshot
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
        """Get opponent actions from battle.observations for a specific turn."""
        opponent_actions = []
        if hasattr(battle, 'observations') and turn_number in battle.observations:
            for event in battle.observations[turn_number]:
                # Parse the event to get readable format
                # This is a simplified version - in practice we'd need to parse the actual event structure
                if hasattr(event, '__str__'):
                    event_str = str(event)
                    # Convert to format like "p2a: Incineroar used Parting Shot"
                    if ':' in event_str and 'used' in event_str:
                        opponent_actions.append(event_str)
                    elif 'switched' in event_str.lower():
                        opponent_actions.append(event_str)
        return opponent_actions

    def _order_to_action_strings(self, order, battle):
        """Convert a DoubleBattleOrder to readable action strings."""
        action_strings = []

        # Handle DoubleBattleOrder which has first_order and second_order attributes
        if hasattr(order, 'first_order') and hasattr(order, 'second_order'):
            # Process first order
            if order.first_order is not None:
                # Extract the actual order (Move or Pokemon) from SingleBattleOrder
                actual_order = order.first_order.order if hasattr(order.first_order, 'order') else order.first_order
                action_strings.append(self._single_order_to_string(actual_order, battle, 0))

            # Process second order
            if order.second_order is not None:
                # Extract the actual order (Move or Pokemon) from SingleBattleOrder
                actual_order = order.second_order.order if hasattr(order.second_order, 'order') else order.second_order
                action_strings.append(self._single_order_to_string(actual_order, battle, 1))
        else:
            # Fallback: try to treat as iterable
            if hasattr(order, '__iter__'):
                # It's a DoubleBattleOrder with two orders
                for i, single_order in enumerate(order):
                    if single_order is not None:
                        # Extract the actual order (Move or Pokemon) from SingleBattleOrder if needed
                        actual_order = single_order.order if hasattr(single_order, 'order') else single_order
                        action_strings.append(self._single_order_to_string(actual_order, battle, i))
            else:
                # It's a single order
                # Extract the actual order (Move or Pokemon) from SingleBattleOrder if needed
                actual_order = order.order if hasattr(order, 'order') else order
                action_strings.append(self._single_order_to_string(actual_order, battle, 0))

        return action_strings

    def _single_order_to_string(self, order, battle, index):
        """Convert a single order to a readable string."""
        # Import here to avoid circular imports
        from poke_env.player.battle_order import Move, Pokemon

        if isinstance(order, Move):
            # It's a move
            move = order
            pokemon = battle.active_pokemon[index] if index < len(battle.active_pokemon) else None
            species = pokemon.species if pokemon and pokemon.species else "Unknown"

            # Get move name - try to get the id, otherwise use the name
            move_name = getattr(move, 'id', None)
            if move_name is None:
                move_name = getattr(move, 'name', str(move))
            # Convert underscores to spaces and title case for readability
            move_name = move_name.replace('_', ' ').title()

            # Format: "Species uses Move"
            action = f"{species} uses {move_name}"

            # Add targeting info if applicable
            if hasattr(order, 'move_target') and order.move_target is not None:
                target = order.move_target
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

        elif isinstance(order, Pokemon):
            # It's a switch
            target_pokemon = order
            pokemon = battle.active_pokemon[index] if index < len(battle.active_pokemon) else None
            species = pokemon.species if pokemon and pokemon.species else "Unknown"
            target_species = target_pokemon.species if target_pokemon and target_pokemon.species else "Unknown"

            return f"{species} switches to {target_species}"

        else:
            # Fallback - try to make it readable
            order_str = str(order)
            # If it looks like a raw pokemon showdown command, try to make it nicer
            if order_str.startswith('/choose ') or '|' in order_str:
                return f"Pokemon action {index}"  # Generic fallback
            return order_str

    def _write_master_file(self):
        """Write all matches to the master JSON file using temp file + os.replace for safety."""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.master_path), exist_ok=True)

            # Prepare data
            data = {"matches": self.all_matches}

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

    def teampreview(self, battle):
        return self.random_teampreview(battle)