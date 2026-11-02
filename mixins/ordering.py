import math
import numpy as np
import random
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.field import Field
from poke_env.battle.effect import Effect
from poke_env.player.battle_order import Pokemon, Move
from pikabot.constants import PROTECT_MOVES, NON_SINGLE_TARGET, SELF_OR_ALLY_TARGETS, SETUP_MOVES


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
            self.mega = False  # Reset mega evolution for new battle
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
        # Can't double Mega Evolve (only one Mega per battle).
        if (hasattr(left_order, 'mega') and left_order.mega and
            hasattr(right_order, 'mega') and right_order.mega):
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
                        bonus += 100  # Increased: partner hits the flinched target — combo KO / focus fire
                    elif ad["target"] == 0:
                        bonus += 60   # Increased: spread / setup behind Fake Out

        # Double Protect is rarely optimal.
        if (ld["kind"] == "move" and rd["kind"] == "move"
                and ld["name"] in PROTECT_MOVES and rd["name"] in PROTECT_MOVES):
            bonus -= 30  # Increased penalty

        # Two attacks on the same target: ENCOURAGE focus fire in VGC (securing KOs is paramount)
        # Only penalize if it's clear overkill (both would KO individually)
        if (ld["kind"] == "move" and rd["kind"] == "move"
                and ld["name"] not in PROTECT_MOVES and rd["name"] not in PROTECT_MOVES
                and ld["target"] and ld["target"] > 0
                and ld["target"] == rd["target"]):
            bonus += 30  # Changed from penalty to bonus: VGC rewards focused damage to secure KOs

        # Speed control synergy: Tailwind/Trick Room + attacker
        for fd, ad in [(ld, rd), (rd, ld)]:
            if fd["kind"] == "move" and fd["name"] in ["tailwind", "trickroom", "icywind", "electroweb"]:
                if ad["kind"] == "move" and ad["name"] not in PROTECT_MOVES:
                    bonus += 40  # Setting speed control while partner attacks

        # Helping Hand + strong attack synergy
        for fd, ad in [(ld, rd), (rd, ld)]:
            if fd["kind"] == "move" and fd["name"] == "helpinghand":
                if ad["kind"] == "move" and ad["name"] not in PROTECT_MOVES:
                    bonus += 50  # Helping Hand enables partner's KO potential

        # Follow Me / Rage Powder + setup/sweeper synergy
        for fd, ad in [(ld, rd), (rd, ld)]:
            if fd["kind"] == "move" and fd["name"] in ["followme", "ragepowder"]:
                if ad["kind"] == "move" and ad["name"] not in PROTECT_MOVES:
                    bonus += 35  # Redirect allows partner to act freely

        return bonus

    # ---------- Candidate generation (pure) ----------
    def get_scored_candidates(self, pokemon, battle, available_moves, can_mega=None):
        """Return scored candidates for a single slot. No state mutation."""
        slot_index = battle.active_pokemon.index(pokemon)
        if can_mega is None:
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
            try:
                move_priority = move.priority
            except (KeyError, AttributeError):
                move_priority = 0

            # 1. Protect
            if move.id in PROTECT_MOVES:
                current_score = def_score - acc_penalty
                if self.protect_last_turn[slot_index]:
                    current_score -= 50  # Increased penalty for consecutive Protect (diminishing returns)

                # Bonus for Protect when partner is setting up / using key move
                if partner and not partner.fainted:
                    # Protect is more valuable when partner can do something impactful
                    partner_has_setup = any(m.id in SETUP_MOVES for m in battle.available_moves[partner_slot])
                    partner_has_speed_control = any(m.id in ["tailwind", "trickroom", "icywind", "electroweb"]
                                                     for m in battle.available_moves[partner_slot])
                    if partner_has_setup or partner_has_speed_control:
                        current_score += 25  # Protect enables partner's setup/control

                # Small bonus if we're low HP and need to survive
                if current_hp_percent < 30:
                    current_score += 20

                order = self.create_order(move, move_target=0, mega=can_mega)
                scored_candidates.append({"score": current_score, "order": order,
                                          "is_protect": True, "is_mega": can_mega})

            # 2. Status
            elif move.category == MoveCategory.STATUS and move.base_power == 0:
                if move.target in SELF_OR_ALLY_TARGETS:
                    current_score = self.self_ally_global_status_score(
                        pokemon, move, battle, slot_index, is_going_to_faint)
                    ally_move_target = 0
                    if move.id in ["coaching", "decorate", "helpinghand"]:
                        ally_move_target = -1 if slot_index == 1 else -2
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
                spread_ko_count = 0
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        dmg = self.calculate_damage(pokemon, opp, move, battle)
                        current_score += dmg
                        # Bonus for KO on faster targets (secure KOs before they move)
                        if self.isFaster(pokemon, opp, battle) and dmg >= (opp.current_hp_fraction * 100):
                            current_score += 200  # Increased from 150: securing KOs is critical
                            spread_ko_count += 1
                        # Bonus for significant chunk on slower targets (setting up partner KOs)
                        elif not self.isFaster(pokemon, opp, battle) and dmg >= (opp.current_hp_fraction * 50):
                            current_score += 50  # Chunking slower foes helps partner finish

                # Multi-KO bonus: spread moves that can KO multiple foes are premium
                if spread_ko_count >= 2:
                    current_score += 150  # Double KO potential is huge in VGC

                current_score -= acc_penalty
                if is_going_to_faint and not all(
                        self.isFaster(pokemon, opp, battle)
                        for opp in battle.opponent_active_pokemon if opp and not opp.fainted):
                    current_score *= 0.6  # Slightly less harsh penalty (was 0.5)
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

                            # Priority OHKO - highest value (secures KO before opponent moves)
                            if move_priority > 0 and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 250  # Increased from 200
                            # Standard outspeed OHKO
                            elif is_faster and dmg >= (opp.current_hp_fraction * 100):
                                current_score += 200  # Increased from 150
                            # Priority move that chunks but doesn't KO - still valuable for chip
                            elif move_priority > 0 and dmg >= (opp.current_hp_fraction * 50):
                                current_score += 80  # New: priority chip damage
                            # Desperation priority (we're dying, get a hit in)
                            elif is_going_to_faint and not is_faster and move_priority > 0:
                                current_score += 120  # Increased from 100
                            # Slower + threatened penalty - but less harsh if we chunk
                            elif is_going_to_faint and not is_faster and move_priority <= 0:
                                if dmg >= (opp.current_hp_fraction * 70):
                                    current_score *= 0.8  # Less penalty if we do significant damage
                                else:
                                    current_score *= 0.5

                            # ---- Fake Out: premium disruption / enable tool ----
                            if move.id == "fakeout" and dmg > 0:
                                fakeout_bonus = 200  # Increased from 150: Fake Out is elite in VGC
                                # Extra value if opponent is faster (we flip speed control)
                                if self.isFaster(opp, pokemon, battle):
                                    fakeout_bonus += 120  # Increased from 100
                                # Extra value if partner outspeeds flinched target (guaranteed follow-up)
                                if partner and not partner.fainted and self.isFaster(opp, partner, battle):
                                    fakeout_bonus += 80  # Increased from 50
                                # Bonus if target has Focus Sash / Sturdy (breaks it)
                                if opp.item in ["focussash", "focusband"] or self.get_ability(opp) == "sturdy":
                                    fakeout_bonus += 50
                                current_score += fakeout_bonus

                            # Bonus for targeting the bigger threat
                            opp_threat = max(self.get_stat(opp, "atk"), self.get_stat(opp, "spa"))
                            my_threat = max(self.get_stat(pokemon, "atk"), self.get_stat(pokemon, "spa"))
                            if opp_threat > my_threat * 1.2:  # Opponent is significantly stronger
                                current_score += 30  # Prioritize neutralizing bigger threats

                            # Partner KO logic: if partner can KO, we should focus DIFFERENT target
                            # But if we ALSO can KO, focus fire is good (secures the KO)
                            if partner_kos_opp.get(i):
                                can_ko_ourselves = dmg >= (opp.current_hp_fraction * 100)
                                if can_ko_ourselves:
                                    current_score *= 1.2  # BOOST: both can KO = guaranteed removal (focus fire)
                                else:
                                    current_score *= 0.4  # Slightly less harsh than 0.35

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

        effected = any(eff in pokemon.effects for eff in [Effect.TAUNT, Effect.ENCORE, Effect.IMPRISON])

        # Also consider switching proactively for type advantage / momentum
        consider_switch = is_going_to_faint or takes_alot_dmg or has_heavy_drops or effected

        # Proactive switching: if we have a bad matchup and a good switch available
        if not consider_switch and partner and not partner.fainted:
            # Check if current mon has terrible type matchup vs both foes
            bad_matchup = True
            for opp in battle.opponent_active_pokemon:
                if opp is not None and not opp.fainted:
                    type_mult = opp.damage_multiplier(pokemon.type_1)
                    if pokemon.type_2:
                        type_mult *= opp.damage_multiplier(pokemon.type_2)
                    if type_mult < 1.0:  # We resist at least one
                        bad_matchup = False
                        break

            # And partner has good matchup
            if bad_matchup:
                partner_good = False
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        type_mult = opp.damage_multiplier(partner.type_1)
                        if partner.type_2:
                            type_mult *= opp.damage_multiplier(partner.type_2)
                        if type_mult > 1.0:
                            partner_good = True
                            break
                if partner_good:
                    consider_switch = True

        # Additional VGC switching considerations:
        # - Intimidate cycling (reset Atk drops)
        # - Regenerator/Natural Cure healing
        # - Entry hazard avoidance
        # - Preserving late-game wincons
        # - Pivot moves (U-turn, Volt Switch, Flip Turn, Parting Shot)
        # - Weather/Terrain setter preservation
        # - Ally Switch / Follow Me support

        if consider_switch:
            for bench in battle.available_switches[slot_index]:
                if bench.fainted or bench.current_hp_fraction == 0:
                    continue
                estimated_dmg = 0
                if most_threat_opp and most_threatning_move:
                    estimated_dmg = self.calculate_damage(
                        most_threat_opp, bench, most_threatning_move, battle)
                switch_score = (bench.current_hp_fraction * 100) - estimated_dmg

                # Bonus if we protected last turn (safe switch)
                if self.protect_last_turn[slot_index]:
                    switch_score += 60  # Increased from 55

                # Emergency switch bonus
                if is_going_to_faint:
                    switch_score += 150  # Increased from 100: saving a mon is critical

                # Status effect relief
                if effected:
                    switch_score += 40  # Increased from 30

                # Stat drop relief (Intimidate, Parting Shot, etc.)
                switch_score += negative_boost_total * 30  # Increased from 25

                # Type matchup bonus: prefer switches that resist opponent's moves
                type_bonus = 0
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        type_mult = opp.damage_multiplier(bench.type_1)
                        if bench.type_2:
                            type_mult *= opp.damage_multiplier(bench.type_2)
                        if type_mult < 1.0:  # Resist
                            type_bonus += 25
                        elif type_mult == 0:  # Immune
                            type_bonus += 50
                switch_score += type_bonus

                # Offensive presence bonus: prefer switches that threaten opponents
                bench_offense = max(self.get_stat(bench, "atk"), self.get_stat(bench, "spa"))
                switch_score += min(bench_offense // 10, 40)  # Cap at 40

                # Speed tier bonus: faster switches gain momentum
                bench_speed = self.get_stat(bench, "spe")
                opp_speeds = [self.get_stat(o, "spe") for o in battle.opponent_active_pokemon if o and not o.fainted]
                if opp_speeds and bench_speed > max(opp_speeds):
                    switch_score += 20  # Outspeed both foes
                elif opp_speeds and bench_speed > min(opp_speeds):
                    switch_score += 10  # Outspeed one foe

                # --- VGC-specific bonuses ---

                # Intimidate cycling: if bench has Intimidate, extra value vs physical attackers
                bench_ability = self.get_ability(bench)
                if bench_ability == "intimidate":
                    phys_attackers = sum(1 for o in battle.opponent_active_pokemon
                                        if o and not o.fainted and self.get_stat(o, "atk") > self.get_stat(o, "spa"))
                    if phys_attackers > 0:
                        switch_score += 35  # Intimidate on switch-in is huge value

                # Regenerator / Natural Cure: passive healing on switch
                if bench_ability in ["regenerator", "naturalcure"]:
                    switch_score += 30  # Free healing / status cure
                    if bench_ability == "naturalcure" and pokemon.status is not None:
                        switch_score += 20  # Curing status is extra valuable

                # Entry hazard avoidance: penalize switching into known hazards
                hazard_penalty = 0
                for opp in battle.opponent_active_pokemon:
                    if opp and not opp.fainted:
                        opp_moves = self.opp_team_movepool.get(opp.species.capitalize(), [])
                        if any(m in ["stealthrock", "spikes", "toxicspikes", "stickyweb"] for m in opp_moves):
                            if self.is_grounded(bench):
                                bench_item = self.get_item(bench)
                                if bench_item != "heavydutyboots" and bench_ability != "magicguard":
                                    hazard_penalty += 15  # Stealth Rock chip
                switch_score -= hazard_penalty

                # Preserve late-game win conditions: if bench is a setup sweeper, value it more
                bench_has_setup = any(m.id in SETUP_MOVES for m in bench.moves.values())
                if bench_has_setup:
                    bench_offense_val = max(self.get_stat(bench, "atk"), self.get_stat(bench, "spa"))
                    if bench_offense_val > 130:  # Strong sweeper
                        switch_score += 40  # Preserve wincon
                        if battle.turn > 10:
                            switch_score += 25

                # Pivot move synergy: if current mon has pivot move, switching is more natural
                pivot_moves = {"uturn", "voltswitch", "flipturn", "partingshot", "batonpass", "chillyreception"}
                has_pivot = any(m.id in pivot_moves for m in pokemon.moves.values())
                if has_pivot:
                    switch_score += 15  # Pivot moves make switching free/advantageous

                # Weather/Terrain setter preservation: don't switch out our setter early
                is_weather_setter = any(m.id in ["raindance", "sunnyday", "sandstorm", "snowscape"]
                                       for m in pokemon.moves.values())
                is_terrain_setter = any(m.id in ["electricterrain", "grassyterrain", "mistyterrain", "psychicterrain"]
                                       for m in pokemon.moves.values())
                if (is_weather_setter or is_terrain_setter) and not is_going_to_faint and not takes_alot_dmg:
                    switch_score -= 40  # Discourage switching out setter early

                # Ally Switch / Follow Me support: if partner has redirection, we can switch more freely
                if partner and not partner.fainted:
                    partner_has_redirect = any(m.id in ["followme", "ragepowder"]
                                             for m in battle.available_moves[partner_slot])
                    if partner_has_redirect:
                        switch_score += 15  # Partner can absorb hits while we switch

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

        # Determine Mega Evolution eligibility: only one per battle
        # Allow both slots to have the option; _pair_is_legal prevents double mega
        left_can_mega = battle.can_mega_evolve[0] if not self.mega else False
        right_can_mega = battle.can_mega_evolve[1] if not self.mega else False

        # Generate candidates with pre-determined mega eligibility
        left_candidates = self.get_scored_candidates(left_mon, battle, battle.available_moves[0], left_can_mega)
        right_candidates = self.get_scored_candidates(right_mon, battle, battle.available_moves[1], right_can_mega)

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