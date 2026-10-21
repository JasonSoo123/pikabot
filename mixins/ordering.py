import math
import numpy as np
import random
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.field import Field
from poke_env.player.battle_order import Pokemon, Move
from pikabot.constants import PROTECT_MOVES, NON_SINGLE_TARGET, SELF_OR_ALLY_TARGETS


class OrderingMixin():
    """Helper functions to choose the best order(s) for the active pokemon."""

    # ---------- Per-turn state ----------
    def _ensure_turn_state(self, battle):
        """Initialize/reset per-turn state. Safe to call repeatedly within a turn."""
        prev_tag = getattr(self, '_turn_tag', None)
        prev_key = getattr(self, '_turn_key', None)
        new_tag = prev_tag != battle.battle_tag
        new_turn = prev_key != (battle.battle_tag, battle.turn)

        if new_tag:
            # New battle — wipe everything.
            self.protect_last_turn = [False, False]
            self._protect_this_turn = [False, False]
        elif new_turn:
            # New turn, same battle — finalize what we chose last turn.
            self.protect_last_turn = list(self._protect_this_turn)
            self._protect_this_turn = [False, False]

        self._turn_tag = battle.battle_tag
        self._turn_key = (battle.battle_tag, battle.turn)

    # ---------- Order introspection ----------
    def _describe_order(self, order):
        """Return a dict describing a SingleBattleOrder: kind, name/species, target."""
        inner = order.order if hasattr(order, 'order') else order
        target = getattr(order, 'move_target', 0)
        if isinstance(inner, Pokemon):
            return {"kind": "switch", "species": inner.species, "target": None}
        elif isinstance(inner, Move):
            return {"kind": "move", "name": inner.id, "target": target}
        return {"kind": "unknown", "target": None}

    # ---------- Pair legality & synergy ----------
    def _pair_is_legal(self, left_order, right_order):
        ld = self._describe_order(left_order)
        rd = self._describe_order(right_order)
        # Can't switch both slots to the same bench mon.
        if ld["kind"] == "switch" and rd["kind"] == "switch" and ld["species"] == rd["species"]:
            return False
        # Can't double Fake Out (only one flinch per side is meaningful).
        if (ld["kind"] == "move" and rd["kind"] == "move"
                and ld["name"] == "fakeout" and rd["name"] == "fakeout"):
            return False
        return True

    def _pair_synergy(self, left_order, right_order):
        """Bonus/penalty based on how well two orders combine."""
        ld = self._describe_order(left_order)
        rd = self._describe_order(right_order)
        bonus = 0

        # Fake Out enabling the partner: check both orientations.
        for fd, ad in [(ld, rd), (rd, ld)]:
            if fd["kind"] == "move" and fd["name"] == "fakeout" and fd["target"] and fd["target"] > 0:
                if ad["kind"] == "move" and ad["name"] not in PROTECT_MOVES:
                    if ad["target"] == fd["target"]:
                        bonus += 60   # partner hits the flinched target — combo KO
                    elif ad["target"] == 0:
                        bonus += 40   # spread / setup behind Fake Out

        # Double Protect is rarely optimal.
        if (ld["kind"] == "move" and rd["kind"] == "move"
                and ld["name"] in PROTECT_MOVES and rd["name"] in PROTECT_MOVES):
            bonus -= 20

        # Two attacks on the same target risks overkill waste.
        if (ld["kind"] == "move" and rd["kind"] == "move"
                and ld["name"] not in PROTECT_MOVES and rd["name"] not in PROTECT_MOVES
                and ld["target"] and ld["target"] > 0
                and ld["target"] == rd["target"]):
            bonus -= 20

        return bonus

    # ---------- Candidate generation (pure) ----------
    def get_scored_candidates(self, pokemon, battle, available_moves):
        """Return scored candidates for a single slot. No state mutation."""
        slot_index = battle.active_pokemon.index(pokemon)
        can_mega = False
        if not self.mega:
            can_mega = battle.can_mega_evolve[slot_index]

        def_score, most_threatning_move, most_threat_opp = self.calc_defensive_score(pokemon, battle)

        current_hp_percent = pokemon.current_hp_fraction * 100
        is_going_to_faint = def_score >= current_hp_percent
        takes_alot_dmg = def_score > 80

        partner_slot = 1 if slot_index == 0 else 0
        partner = battle.active_pokemon[partner_slot] if len(battle.active_pokemon) > 1 else None
        partner_kos_opp = {}

        if partner and not partner.fainted:
            partner_is_faster = self.isFaster(pokemon, partner, battle)
            for i, opp in enumerate(battle.opponent_active_pokemon):
                if opp is not None and not opp.fainted:
                    partner_best_dmg = 0
                    best_move_prio = 0
                    for partner_move in battle.available_moves[partner_slot]:
                        partner_dmg = self.calculate_damage(partner, opp, partner_move, battle)
                        if partner_dmg > partner_best_dmg:
                            partner_best_dmg = partner_dmg
                            best_move_prio = partner_move.priority
                    if partner_is_faster or best_move_prio > 0:
                        partner_kos_opp[i] = partner_best_dmg >= (opp.current_hp_fraction * 100)

        scored_candidates = []

        for move in available_moves:
            acc = move.accuracy if isinstance(move.accuracy, (int, float)) else 1.0
            acc_penalty = math.floor((100 - math.floor(acc * 100)) / 2)
            move_priority = getattr(move, 'priority', 0)

            # 1. Protect
            if move.id in PROTECT_MOVES:
                current_score = def_score - acc_penalty
                if self.protect_last_turn[slot_index]:
                    current_score -= 40
                order = self.create_order(move, move_target=0, mega=can_mega)
                scored_candidates.append({"score": current_score, "order": order,
                                          "is_protect": True, "is_mega": can_mega})

            # 2. Status
            elif move.category == MoveCategory.STATUS and move.base_power == 0:
                if move.target in SELF_OR_ALLY_TARGETS:
                    current_score = self.self_ally_global_status_score(
                        pokemon, move, battle, slot_index, is_going_to_faint)
                    ally_move_target = 0
                    if move.id in ["coaching", "decorate"]:
                        ally_move_target = battle.to_showdown_target(
                            move, battle.active_pokemon[0 if slot_index == 1 else 1])
                    order = self.create_order(move, move_target=ally_move_target, mega=can_mega)
                    scored_candidates.append({"score": current_score, "order": order,
                                              "is_protect": False, "is_mega": can_mega})
                else:
                    for i, opp in enumerate(battle.opponent_active_pokemon):
                        if opp is not None and not opp.fainted:
                            current_score = self.opponent_targeting_status_score(
                                pokemon, move, opp, battle)
                            target = i + 1
                            order = self.create_order(move, move_target=target, mega=can_mega)
                            scored_candidates.append({"score": current_score, "order": order,
                                                      "is_protect": False, "is_mega": can_mega})

            # 3. Spread
            elif move.target in NON_SINGLE_TARGET:
                current_score = 0
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        dmg = self.calculate_damage(pokemon, opp, move, battle)
                        current_score += dmg
                        if self.isFaster(pokemon, opp, battle) and dmg >= (opp.current_hp_fraction * 100):
                            current_score += 150
                current_score -= acc_penalty
                if is_going_to_faint and not all(
                        self.isFaster(pokemon, opp, battle)
                        for opp in battle.opponent_active_pokemon if opp and not opp.fainted):
                    current_score *= 0.5
                order = self.create_order(move, move_target=0, mega=can_mega)
                scored_candidates.append({"score": current_score, "order": order,
                                          "is_protect": False, "is_mega": can_mega})

            # 4. Single-target
            else:
                for i, opp in enumerate(battle.opponent_active_pokemon):
                    if opp is not None and not opp.fainted:
                        if (move_priority > 0 and Field.PSYCHIC_TERRAIN in battle.fields
                                and self.is_grounded(opp)):
                            current_score = 0
                        else:
                            dmg = self.calculate_damage(pokemon, opp, move, battle)
                            current_score = dmg - acc_penalty
                            is_faster = self.isFaster(pokemon, opp, battle)

                            # Priority OHKO
                            if move_priority > 0 and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 200
                            # Standard outspeed OHKO
                            elif is_faster and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 150
                            # Desperation priority
                            elif is_going_to_faint and not is_faster and move_priority > 0:
                                current_score += 100
                            # Slower + threatened penalty
                            elif is_going_to_faint and not is_faster and move_priority <= 0:
                                current_score *= 0.5

                            # ---- Improved Fake Out ----
                            if move.id == "fakeout" and dmg > 0:
                                fakeout_bonus = 150
                                if self.isFaster(opp, pokemon, battle):
                                    fakeout_bonus += 100
                                if partner and not partner.fainted and self.isFaster(opp, partner, battle):
                                    fakeout_bonus += 50
                                current_score += fakeout_bonus

                        if partner_kos_opp.get(i):
                            current_score *= 0.35

                        target = i + 1
                        order = self.create_order(move, move_target=target, mega=can_mega)
                        scored_candidates.append({"score": current_score, "order": order,
                                                  "is_protect": False, "is_mega": can_mega})

        # 5. Switching
        boost_stats = ["atk", "def", "spa", "spd", "spe"]
        if Field.TRICK_ROOM in battle.fields:
            boost_stats.remove("spe")
        negative_boost_total = sum(
            -pokemon.boosts.get(stat, 0) for stat in boost_stats if pokemon.boosts.get(stat, 0) < 0)
        has_heavy_drops = negative_boost_total >= 2

        if is_going_to_faint or takes_alot_dmg or has_heavy_drops:
            for bench in battle.available_switches[slot_index]:
                if bench.fainted or bench.current_hp_fraction == 0:
                    continue
                estimated_dmg = 0
                if most_threat_opp and most_threatning_move:
                    estimated_dmg = self.calculate_damage(
                        most_threat_opp, bench, most_threatning_move, battle)
                switch_score = (bench.current_hp_fraction * 100) - estimated_dmg
                if self.protect_last_turn[slot_index]:
                    switch_score += 30
                if is_going_to_faint:
                    switch_score += 100
                switch_score += negative_boost_total * 25
                order = self.create_order(bench)
                scored_candidates.append({"score": switch_score, "order": order,
                                          "is_protect": False, "is_mega": False})

        return scored_candidates

    # ---------- Picking + state updates ----------
    def _pick_from_candidates(self, candidates):
        """Softmax-sample from the top 3 candidates. Returns None if empty."""
        if not candidates:
            return None
        top = sorted(candidates, key=lambda x: x["score"], reverse=True)[:3]
        if len(top) == 1:
            return top[0]
        scores = np.array([c["score"] for c in top], dtype=np.float64)
        exp_scores = np.exp(scores - np.max(scores))
        raw_probs = exp_scores / np.sum(exp_scores)
        capped_probs = np.maximum(raw_probs, 0.05)
        final_probs = capped_probs / np.sum(capped_probs)
        return random.choices(top, weights=final_probs, k=1)[0]

    def _apply_chosen(self, chosen_candidate, slot_index):
        """Update per-slot persistent state after a choice is made."""
        self._protect_this_turn[slot_index] = chosen_candidate["is_protect"]
        if chosen_candidate["is_mega"]:
            self.mega = True

    # ---------- Public entry points ----------
    def choose_best_order(self, pokemon, battle, available_moves):
        """Single-slot selection. Used when only one slot has moves available."""
        self._ensure_turn_state(battle)
        slot_index = battle.active_pokemon.index(pokemon)
        candidates = self.get_scored_candidates(pokemon, battle, available_moves)
        chosen = self._pick_from_candidates(candidates)
        if chosen is None:
            return None
        self._apply_chosen(chosen, slot_index)
        print(f"Turn: {battle.turn}")
        print(f"best order is: {pokemon.species} {chosen['order']}")
        return chosen["order"]

    def choose_best_double_order(self, battle):
        """Combo selection: generate all legal pairs of candidates, pick the best pair.
        Returns (left_order, right_order) as raw SingleBattleOrders (caller wraps in
        DoubleBattleOrder)."""
        self._ensure_turn_state(battle)

        left_mon = battle.active_pokemon[0]
        right_mon = battle.active_pokemon[1]
        left_candidates = self.get_scored_candidates(left_mon, battle, battle.available_moves[0])
        right_candidates = self.get_scored_candidates(right_mon, battle, battle.available_moves[1])

        # Safety fallback: something empty — pick per-slot independently.
        if not left_candidates or not right_candidates:
            lc = self._pick_from_candidates(left_candidates)
            rc = self._pick_from_candidates(right_candidates)
            if lc:
                self._apply_chosen(lc, 0)
            if rc:
                self._apply_chosen(rc, 1)
            return (lc["order"] if lc else None, rc["order"] if rc else None)

        # Enumerate legal pairs.
        pairs = []
        for lc in left_candidates:
            for rc in right_candidates:
                if not self._pair_is_legal(lc["order"], rc["order"]):
                    continue
                pair_score = lc["score"] + rc["score"] + self._pair_synergy(lc["order"], rc["order"])
                pairs.append({"score": pair_score, "left": lc, "right": rc})

        if not pairs:
            # No legal pair (extremely rare — should not happen when both slots
            # have moves). Fall back to independent picking.
            lc = self._pick_from_candidates(left_candidates)
            rc = self._pick_from_candidates(right_candidates)
            self._apply_chosen(lc, 0)
            self._apply_chosen(rc, 1)
            return lc["order"], rc["order"]

        chosen_pair = self._pick_from_candidates(pairs)
        self._apply_chosen(chosen_pair["left"], 0)
        self._apply_chosen(chosen_pair["right"], 1)

        print(f"Turn: {battle.turn}")
        print(f"best order is: {left_mon.species} {chosen_pair['left']['order']}")
        print(f"best order is: {right_mon.species} {chosen_pair['right']['order']}")
        return chosen_pair["left"]["order"], chosen_pair["right"]["order"]