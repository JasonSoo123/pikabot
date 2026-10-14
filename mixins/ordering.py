import math
import numpy as np
import random
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.field import Field
from pikabot.constants import PROTECT_MOVES, NON_SINGLE_TARGET, SELF_OR_ALLY_TARGETS


class OrderingMixin():
    """Helper function to choose the best order for a specific pokemon in the current battle"""
    def choose_best_order(self, pokemon, battle, available_moves):

        # Mega Evolution Check
        slot_index = battle.active_pokemon.index(pokemon)
        can_mega = False
        if not self.mega:
            can_mega = battle.can_mega_evolve[slot_index]

        def_score, most_threatning_move, most_threat_opp = self.calc_defensive_score(pokemon, battle)

        current_hp_percent = pokemon.current_hp_fraction * 100
        is_going_to_faint = def_score >= current_hp_percent
        takes_alot_dmg = def_score > 80

        # Store all scored candidates
        scored_candidates = []

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

                order = self.create_order(move, move_target=0, mega=can_mega)
                scored_candidates.append({"score": current_score, "order": order, "is_protect": True, "is_mega": can_mega})

            # --- 2. Status Moves ---
            elif move.category == MoveCategory.STATUS and move.base_power == 0:

                if move.target in SELF_OR_ALLY_TARGETS:
                    current_score = self.self_ally_global_status_score(pokemon, move,
                                                                       battle, slot_index, is_going_to_faint)
                    if pokemon.ability == "prankster":
                        current_score += 30

                    move_target = 0
                    if move.id in ["coaching", "decorate"]:
                        move_target = \
                        battle.to_showdown_target(move, battle.active_pokemon[0 if slot_index == 1 else 1])

                    order = self.create_order(move, move_target=move_target, mega=can_mega)
                    scored_candidates.append({"score": current_score, "order": order, "is_protect": False, "is_mega": can_mega})
                else:
                    for i, opp in enumerate(battle.opponent_active_pokemon):
                        if opp is not None and not opp.fainted:
                            current_score = self.opponent_targeting_status_score(pokemon, move, opp, battle)
                            target = i + 1
                            order = self.create_order(move, move_target=target, mega=can_mega)
                            scored_candidates.append({"score": current_score, "order": order, "is_protect": False, "is_mega": can_mega})

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

                order = self.create_order(move, move_target=0, mega=can_mega)
                scored_candidates.append({"score": current_score, "order": order, "is_protect": False, "is_mega": can_mega})

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

                        target = i + 1
                        order = self.create_order(move, move_target=target, mega=can_mega)
                        scored_candidates.append({"score": current_score, "order": order, "is_protect": False, "is_mega": can_mega})

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

                order = self.create_order(bench)
                scored_candidates.append({"score": switch_score, "order": order, "is_protect": False, "is_mega": False})

        # If no candidates, return None
        if not scored_candidates:
            return None

        # STOCHASTIC CANDIDATE MOVE SELECTION LOGIC
        # 1. Take top 3 candidates sorted by score descending
        top_candidates = sorted(scored_candidates, key=lambda x: x["score"], reverse=True)[:3]

        # If only 1 candidate, return it immediately
        if len(top_candidates) == 1:
            chosen_candidate = top_candidates[0]
        else:
            # 2. Convert scores to relative probabilities via Softmax
            scores = np.array([c["score"] for c in top_candidates], dtype=np.float64)
            exp_scores = np.exp(scores - np.max(scores))
            raw_probs = exp_scores / np.sum(exp_scores)

            # 3. Apply 5% floor constraint
            min_prob = 0.05
            capped_probs = np.maximum(raw_probs, min_prob)

            # 4. Re-normalize to sum to 1.0
            final_probs = capped_probs / np.sum(capped_probs)

            # 5. Sample choice stochastically
            chosen_candidate = random.choices(top_candidates, weights=final_probs, k=1)[0]

        # --- Finalize Persistent State Updates ---
        self.protect_last_turn[slot_index] = chosen_candidate["is_protect"]
        if chosen_candidate["is_mega"]:
            self.mega = True

        print(f"best order is: {chosen_candidate['order']}")
        return chosen_candidate["order"]
