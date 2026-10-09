import math
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.field import Field
from pikabot.constants import PROTECT_MOVES, NON_SINGLE_TARGET, SELF_OR_ALLY_TARGETS


class OrderingMixin():
    """Helper function to choose the best order for a specific pokemon in the current battle"""
    def choose_best_order(self, pokemon, battle, available_moves):
        
        best_score = -1
        best_order = None
        
        # State trackers for the WINNING move
        chosen_is_protect = False
        chosen_is_mega = False

        # Mega Evolution Check
        slot_index = battle.active_pokemon.index(pokemon)
        can_mega = False
        if not self.mega:
            can_mega = battle.can_mega_evolve[slot_index]

        def_score, most_threatning_move, most_threat_opp = self.calc_defensive_score(pokemon, battle)
        
        current_hp_percent = pokemon.current_hp_fraction * 100
        is_going_to_faint = def_score >= current_hp_percent
        takes_alot_dmg = def_score > 80

        for move in available_moves:
            # Safely extract accuracy penalty
            acc = move.accuracy if isinstance(move.accuracy, (int, float)) else 1.0
            acc_penalty = math.floor((100 - math.floor(acc * 100)) / 2)
            
            # Get priority
            move_priority = getattr(move, 'priority', 0)
             
            # --- 1. Protect Moves ---
            if move.id in PROTECT_MOVES:
                current_score = def_score - acc_penalty
                
                # Penalty for consecutive Protect attempts
                if self.protect_last_turn[slot_index]:
                    current_score -= 40

                if current_score > best_score:
                    best_score = current_score
                    best_order = self.create_order(move, move_target=0, mega=can_mega)
                    chosen_is_protect = True
                    chosen_is_mega = can_mega
            
            # --- 2. Status Moves ---
            elif move.category == MoveCategory.STATUS and move.base_power == 0:        
                
                if move.target in SELF_OR_ALLY_TARGETS:
                    current_score = self.self_ally_global_status_score(pokemon, move,
                                                                       battle, slot_index, is_going_to_faint)
                    if pokemon.ability == "prankster":
                        current_score += 30
                    
                    if current_score > best_score:
                        best_score = current_score
                        move_target = 0
                        
                        if move.id in ["coaching", "decorate"]:
                            move_target = -1 if slot_index == 1 else -2
                            
                        best_order = self.create_order(move, move_target=move_target, mega=can_mega)
                        chosen_is_protect = False
                        chosen_is_mega = can_mega
                else:
                    for i, opp in enumerate(battle.opponent_active_pokemon):
                        if opp is not None and not opp.fainted: 
                            current_score = self.opponent_targeting_status_score(pokemon, move, opp, battle)
                            
                            if current_score > best_score:
                                best_score = current_score
                                target = i + 1
                                best_order = self.create_order(move, move_target=target, mega=can_mega)
                                chosen_is_protect = False
                                chosen_is_mega = can_mega

                # --- 3. Spread / Multi-Target Moves ---
            elif move.target in NON_SINGLE_TARGET:
                current_score = 0
                
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        dmg = self.calculate_damage(pokemon, opp, move, battle)
                        current_score += dmg
                        
                        # SPEED HEURISTIC: Outspeed KO bonus
                        if self.isFaster(pokemon, opp, battle) and dmg >= (opp.current_hp_fraction * 100):
                            current_score += 150

                current_score -= acc_penalty

                # SPEED HEURISTIC: If slower and about to faint, penalize attacking moves
                if is_going_to_faint and not all(self.isFaster(pokemon, opp, battle) 
                        for opp in battle.opponent_active_pokemon if opp and not opp.fainted):
                    current_score *= 0.5

                if current_score > best_score:
                    best_score = current_score
                    best_order = self.create_order(move, move_target=0, mega=can_mega)
                    chosen_is_protect = False
                    chosen_is_mega = can_mega

            # --- 4. Single Target Moves ---
            else:
                for i, opp in enumerate(battle.opponent_active_pokemon):
                    if opp is not None and not opp.fainted:
                        
                        if move_priority > 0 and Field.PSYCHIC_TERRAIN in battle.fields and self.is_grounded(opp):
                            current_score = 0
                        else:
                            dmg = self.calculate_damage(pokemon, opp, move, battle)
                            current_score = dmg - acc_penalty

                            is_faster = self.isFaster(pokemon, opp, battle)
                            
                            # --- PRIORITY & SPEED HEURISTICS ---

                            # 1. PRIORITY OHKO: Secure the kill before taking damage
                            if move_priority > 0 and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 200

                            # 2. STANDARD OUTSPEED OHKO
                            elif is_faster and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 150

                            # 3. DESPERATION PRIORITY (Going to die, slower, but can strike first via Priority!)
                            elif is_going_to_faint and not is_faster and move_priority > 0:
                                current_score += 100  

                            # 4. SLOWER + THREATENED PENALTY (Non-priority moves will likely fail)
                            elif is_going_to_faint and not is_faster and move_priority <= 0:
                                current_score *= 0.5

                            # Additive priority bonus for Fake Out (only if it deals damage)
                            if move.id == "fakeout" and dmg > 0:
                                current_score += 200

                        if current_score > best_score:
                            best_score = current_score
                            target = i + 1
                            best_order = self.create_order(move, move_target=target, mega=can_mega)
                            chosen_is_protect = False
                            chosen_is_mega = can_mega

        # --- 5. Smart Switching Logic ---
        if is_going_to_faint or takes_alot_dmg:
            for bench in battle.available_switches[slot_index]:
                if bench.fainted or bench.current_hp_fraction == 0:
                    continue

                estimated_dmg = 0
                if most_threat_opp and most_threatning_move:
                    estimated_dmg = self.calculate_damage(most_threat_opp, bench, most_threatning_move, battle)

                switch_score = (bench.current_hp_fraction * 100) - estimated_dmg

                if self.protect_last_turn[slot_index]:
                    switch_score += 30

                if is_going_to_faint:
                    switch_score += 100

                if switch_score > best_score:
                    best_score = switch_score
                    best_order = self.create_order(bench)
                    chosen_is_protect = False
                    chosen_is_mega = False

        # --- Finalize Persistent State Updates ---
        self.protect_last_turn[slot_index] = chosen_is_protect
        if chosen_is_mega:
            self.mega = True

        print(f"best order is: {best_order}")
        return best_order
