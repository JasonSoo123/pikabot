from poke_env.battle.side_condition import SideCondition
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from poke_env.battle.target import Target
from poke_env.battle.effect import Effect
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.move import Move
from pikabot.constants import SETUP_MOVES, POWDER_MOVES, PROTECT_MOVES
from pikabot.data_loader import trickroom_pokemon, tailwind_pokemon

class StatusMoveMixin:
    # Move categories for scoring
    STATUS_INFLICT = {
        "thunderwave", "willowisp", "spore", "sleeppowder", "hypnosis",
        "lovelykiss", "sing", "yawn", "toxic", "poisonpowder", "spore",
        "stunspore", "glare"
        
    }
    STAT_DEBUFF = {
        "charm": ["atk"],
        "faketears": ["spd"],
        "screech": ["def"],
        "leer": ["def"],
        "growl": ["atk"],
        "eerieimpulse": ["spa"],
        "tickle": ["atk", "def"],
        "partingshot": ["atk", "spa"],
    }
    
    DISRUPTION = {
        "taunt", "encore"
    }

    """Helper function to calculate self status move score"""
    def self_ally_global_status_score(self, my_pokemon, move, battle, slot_index, is_going_to_faint):

        partner_slot = 1 if slot_index == 0 else 0
        partner = battle.active_pokemon[partner_slot] if len(battle.active_pokemon) >  1 else None

        score = 0

        if self.get_ability(my_pokemon) == "prankster":
            score += 30

        # Boosting moves
        if move.id in SETUP_MOVES:

            # dont setup if you are gonna die
            if is_going_to_faint and not all(self.isFaster(my_pokemon, opp, battle)
                    for opp in battle.opponent_active_pokemon
                     if opp is not None and not opp.fainted):
                return 0

            stats_boosted = SETUP_MOVES[move.id]

            # Check if ALL stats this move boosts are already at +4 or higher

            if all(my_pokemon.boosts.get(stat, 0) >= 4 for stat in stats_boosted):
                return 0     # Don't use it if we are already fully boosted

            # Base score for setup
            score += 70  # Increased from 50: setup is high-value in VGC

            # Bonus for boosting multiple stats (Dragon Dance, Quiver Dance, Calm Mind)
            if len(stats_boosted) >= 2:
                score += 30
            if len(stats_boosted) >= 3:
                score += 20

            # Bonus if we have good HP to survive setup turn
            if my_pokemon.current_hp_fraction > 0.6:
                score += 25  # Increased from 20
            elif my_pokemon.current_hp_fraction > 0.4:
                score += 10

            # Bonus if partner can protect / redirect
            if partner and not partner.fainted:
                partner_has_protect = any(m.id in PROTECT_MOVES for m in battle.available_moves[partner_slot])
                partner_has_redirect = any(m.id in ["followme", "ragepowder"] for m in battle.available_moves[partner_slot])
                if partner_has_protect or partner_has_redirect:
                    score += 20  # Partner can enable setup

            # Penalty if opponent has Taunt / Encore / Haze / Clear Smog users
            # (This is handled by opp tracking, but we can check known movepool)

            return score

        elif move.id == "tailwind":

            # dont use tailwind if it is already active or trickroom is active
            if SideCondition.TAILWIND in battle.side_conditions or Field.TRICK_ROOM in battle.fields:
                return 0

            # Tailwind is premium speed control in VGC
            score += 180  # Increased from 140: Tailwind is often game-winning

            # Extra value if we have slow, powerful partners that benefit
            if partner and not partner.fainted:
                partner_speed = self.get_stat(partner, "spe")
                opp_speeds = [self.get_stat(o, "spe") for o in battle.opponent_active_pokemon if o and not o.fainted]
                if opp_speeds and partner_speed < min(opp_speeds):
                    score += 40  # Partner is slower than both foes - huge benefit
                elif opp_speeds and partner_speed < max(opp_speeds):
                    score += 20  # Partner slower than one foe

            # Bonus if we're faster and can set it before opponent moves
            faster_count = sum(1 for o in battle.opponent_active_pokemon if o and not o.fainted and self.isFaster(my_pokemon, o, battle))
            if faster_count >= 1:
                score += 30  # Can set Tailwind immediately

        elif move.id in ["reflect", "lightscreen", "auroraveil"]:

            if  move.id == "auroraveil":
                if Weather.SNOW not in battle.weather and Weather.SNOWSCAPE not in battle.weather:
                    return 0
                if SideCondition.AURORA_VEIL in battle.side_conditions:
                    return 0
                score += 140  # Increased from 110: Aurora Veil covers both defenses
            elif move.id == "lightscreen":
                if SideCondition.LIGHT_SCREEN in battle.side_conditions:
                    return 0
                score += 100  # Increased from 80
            else:
                if SideCondition.REFLECT in battle.side_conditions:
                    return 0
                score += 100  # Increased from 80

            # Screens more valuable with setup sweepers
            if partner and not partner.fainted:
                partner_has_setup = any(m.id in SETUP_MOVES for m in battle.available_moves[partner_slot])
                if partner_has_setup:
                    score += 30

        elif move.id in ["followme", "ragepowder"]:

            if partner and not partner.fainted:

                if move.id == "ragepowder":
                    all_opponents_grass = all(
                        (opp.type_1 and opp.type_1 == PokemonType.GRASS) or (opp.type_2 and opp.type_2 == PokemonType.GRASS)
                        for opp in battle.opponent_active_pokemon if opp is not None and not opp.fainted
                    )

                    if all_opponents_grass:
                        return 0

                # Base value: redirecting attacks to bulky mon
                if self.calc_defensive_score(partner, battle)[0] > 30:
                    score += 180  # Increased from 145

                # More valuable if partner is frail but threatening
                partner_hp_pct = partner.current_hp_fraction * 100
                partner_offense = max(self.get_stat(partner, "atk"), self.get_stat(partner, "spa"))
                if partner_hp_pct < 60 and partner_offense > 150:
                    score += 50  # Protecting a glass cannon
                elif partner_hp_pct < 50:
                    score += 30  # Original bonus

                # Valuable if we're about to faint (last stand redirect)
                if is_going_to_faint:
                    score += 40  # Increased from 30

                # Bonus if partner has setup moves
                partner_has_setup = any(m.id in SETUP_MOVES for m in battle.available_moves[partner_slot])
                if partner_has_setup:
                    score += 35  # Enable partner setup

            return score

        elif move.id == "helpinghand":
            if partner and not partner.fainted:
                # Find partner's best damaging move
                best_dmg = 0
                for moves in battle.available_moves[partner_slot]:
                    for opp in battle.opponent_active_pokemon:
                        if opp is not None and not opp.fainted:
                            current_score = self.calculate_damage(partner, opp, moves, battle)
                            if current_score > best_dmg:
                                best_dmg = current_score

                if best_dmg > 0:
                    score = best_dmg * 1.8  # Increased from 1.5: Helping Hand = 1.5x damage, so value scales with damage

                    # Massive bonus if Helping Hand secures a KO that wasn't possible before
                    for opp in battle.opponent_active_pokemon:
                        if opp is not None and not opp.fainted:
                            opp_hp_pct = opp.current_hp_fraction * 100
                            if best_dmg < opp_hp_pct <= best_dmg * 1.5:  # HH turns non-KO into KO
                                score += 120  # KO-securing HH is premium
                                break

                    # Bonus if partner is faster (guaranteed hit)
                    if self.isFaster(partner, battle.opponent_active_pokemon[0], battle):
                        score += 20

                    # Small penalty since HH user does nothing this turn
                    score -= 10  # Reduced from 15

                    return score

            return 0

        elif move.id in ["raindance", "sunnyday", "snowscape", "sandstorm"]:
            weather_map = {
            "raindance": Weather.RAINDANCE,
            "sunnyday": Weather.SUNNYDAY,
            "snowscape": Weather.SNOWSCAPE,
            "sandstorm": Weather.SANDSTORM
            }

            if weather_map[move.id] in battle.weather:
                return 0 # Weather is already active

            score += 80  # Increased from 50: weather setting is valuable

            if partner and not partner.fainted:
                # Check if partner benefits from this weather
                partner_ability = self.get_ability(partner)
                weather_enum = weather_map[move.id]

                benefits = False
                if weather_enum == Weather.RAINDANCE and partner_ability in ["swiftswim", "dryskin", "raindish", "waterabsorb", "hydration"]:
                    benefits = True
                elif weather_enum == Weather.SUNNYDAY and partner_ability in ["chlorophyll", "solarpower", "flowergift", "harvest", "leafguard"]:
                    benefits = True
                elif weather_enum == Weather.SANDSTORM and partner_ability in ["sandrush", "sandforce", "sandveil", "overcoat", "magicguard"]:
                    benefits = True
                elif weather_enum == Weather.SNOWSCAPE and partner_ability in ["slushrush", "icebody", "snowcloak", "iceface"]:
                    benefits = True

                # Also check for weather-boosted moves
                for m in battle.available_moves[partner_slot]:
                    if weather_enum == Weather.RAINDANCE and m.type == PokemonType.WATER:
                        benefits = True
                    elif weather_enum == Weather.SUNNYDAY and m.type == PokemonType.FIRE:
                        benefits = True
                    elif weather_enum == Weather.SANDSTORM and m.type in [PokemonType.ROCK, PokemonType.GROUND, PokemonType.STEEL]:
                        benefits = True
                    elif weather_enum == Weather.SNOWSCAPE and m.type == PokemonType.ICE:
                        benefits = True

                if benefits:
                    score += 80  # Increased from 50: weather synergy is huge

            if battle.weather:
                score += 100  # Overwriting opponent's weather is valuable

            return score

        elif move.id in ["recover", "roost", "slackoff", "softboiled", "morningsun", "synthesis", "moonlight"]:
            if my_pokemon.current_hp_fraction >= 0.85:  # Slightly higher threshold
                return 0

            # Recovery more valuable on bulky Pokemon / win conditions
            base_score = 180 if my_pokemon.current_hp_fraction <= 0.4 else 130  # Increased from 150/100

            # Bonus if we're a win condition (high offense + setup)
            my_offense = max(self.get_stat(my_pokemon, "atk"), self.get_stat(my_pokemon, "spa"))
            has_setup = any(m.id in SETUP_MOVES for m in battle.available_moves[slot_index])
            if my_offense > 140 and has_setup:
                base_score += 30  # Keeping sweeper alive

            # Bonus if partner can cover us
            if partner and not partner.fainted:
                partner_has_protect = any(m.id in PROTECT_MOVES for m in battle.available_moves[partner_slot])
                partner_has_redirect = any(m.id in ["followme", "ragepowder"] for m in battle.available_moves[partner_slot])
                if partner_has_protect or partner_has_redirect:
                    base_score += 20

            return base_score

        elif move.id == "trickroom":

            score = 0 # reset score cause trickroom does not work with prankster

            # Trick Room value: we benefit if we're slower than opponents
            my_slower_count = sum(1 for opp in battle.opponent_active_pokemon if opp and not opp.fainted and not self.isFaster(my_pokemon, opp, battle))
            if my_slower_count >= 1:
                score += 80  # Increased from 50

            if partner and not partner.fainted:
                partner_slower_count = sum(1 for opp in battle.opponent_active_pokemon if opp and not opp.fainted and not self.isFaster(partner, opp, battle))
                if partner_slower_count >= 1:
                    score += 160  # Increased from 130: TR enabling partner is huge

                # Extra value if partner is very slow but powerful (TR sweeper)
                partner_speed = self.get_stat(partner, "spe")
                partner_offense = max(self.get_stat(partner, "atk"), self.get_stat(partner, "spa"))
                if partner_speed < 60 and partner_offense > 150:
                    score += 50  # Classic TR sweeper

            # Bonus if opponent has Tailwind up (counters it)
            if SideCondition.TAILWIND in battle.opponent_side_conditions:
                score += 60  # Anti-Tailwind tech

            # Penalty if we already have Trick Room
            if Field.TRICK_ROOM in battle.fields:
                return 0

            return score

        elif move.id in ["coaching", "decorate"]:

            if not partner or partner.fainted:
                return 0

            partner_atk = self.get_stat(partner, 'atk')
            partner_spa = self.get_stat(partner, "spa")

            if ((move.id == "coaching" and (partner_atk > partner_spa)) or
                (move.id == "decorate" and (partner_spa > partner_atk))):
                score += 100  # Increased from 80: boosting partner's offense is very strong

                if self.isFaster(my_pokemon, partner):
                    score += 20  # Increased from 15: acting first means boost applies immediately

                    if is_going_to_faint:
                        score += 15  # Increased from 10: last-turn boost

                # Extra value if partner can KO with the boost
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        for p_move in battle.available_moves[partner_slot]:
                            if p_move.base_power > 0:
                                # Estimate boosted damage
                                dmg = self.calculate_damage(partner, opp, p_move, battle)
                                if move.id == "coaching" and p_move.category == MoveCategory.PHYSICAL:
                                    dmg = dmg * 1.5
                                elif move.id == "decorate" and p_move.category == MoveCategory.SPECIAL:
                                    dmg = dmg * 2
                                if dmg >= opp.current_hp_fraction * 100:
                                    score += 50  # Boost secures KO
                                    break

            # print(f"score: {score} for {move}")  # Remove debug print
            return score

        return 40

    def opponent_targeting_status_score(self, my_pokemon, move, target, battle):
        """
        Calculate a score for using a status move
        Handles status-inflicting moves, stat-debuff moves, and disruption moves.
        """
        score = 0
        move_id = move.id
        
        # Category 1: Status-inflicting moves
        if move_id in self.STATUS_INFLICT:
            # Check if target already has a major status
            if target.status is not None:
                return 0

            # Powder moves: Spore, Sleep Powder, Stun Spore, Poison Powder
            if move_id in POWDER_MOVES:
                # Grass types, Overcoat, Safety Goggles are immune
                if (target.type_1 == PokemonType.GRASS or
                    target.type_2 == PokemonType.GRASS or
                    self.get_ability(target) == "overcoat" or
                    self.get_item(target) == "safetygoggles"):
                    return 0

                # Grounded targets under Electric Terrain or Misty Terrain are immune to sleep
                if move_id in ["spore", "sleeppowder"] and self.is_grounded(target):
                    if Field.ELECTRIC_TERRAIN in battle.fields or Field.MISTY_TERRAIN in battle.fields:
                        return 0

            # Burn: Will-O-Wisp
            elif move_id == "willowisp":
                # Fire types, Water Veil, Water Bubble, Thermal Exchange, Comatose, Purifying Salt
                if (target.type_1 == PokemonType.FIRE or
                    target.type_2 == PokemonType.FIRE or
                    self.get_ability(target) in ["waterveil", "waterbubble", "thermalexchange", "comatose", "purifyingsalt"]):
                    return 0

            # Paralysis: Thunder Wave, Stun Spore, Glare
            elif move_id in ["thunderwave", "stunspore", "glare"]:
                # Electric types, Limber are immune; Thunder Wave also fails on Ground types
                if (target.type_1 == PokemonType.ELECTRIC or
                    target.type_2 == PokemonType.ELECTRIC or
                    self.get_ability(target) == "limber"):
                    return 0

                if move_id == "thunderwave" and (target.type_1 == PokemonType.GROUND or target.type_2 == PokemonType.GROUND):
                    return 0

            # Poison/Toxic
            elif move_id in ["toxic", "poisonpowder"]:
                # Poison and Steel types, Immunity, Pastel Veil, Comatose, Purifying Salt
                if (target.type_1 == PokemonType.POISON or
                    target.type_2 == PokemonType.POISON or
                    target.type_1 == PokemonType.STEEL or
                    target.type_2 == PokemonType.STEEL or
                    self.get_ability(target) in ["immunity", "pastelveil", "comatose", "purifyingsalt"]):
                    return 0

            # Sleep moves (Hypnosis, Sleep Powder, etc. - but we already handled powder moves above)
            elif move_id in ["hypnosis", "sleeppowder", "spore"]:  # Note: spore/sleeppowder already handled in powder moves
                # Insomnia, Vital Spirit, Sweet Veil, Comatose, Purifying Salt
                if self.get_ability(target) in ["insomnia", "vitalspirit", "sweetveil", "comatose", "purifyingsalt"]:
                    return 0

                # Grounded targets under Electric Terrain or Misty Terrain are immune to sleep
                if self.is_grounded(target):
                    if Field.ELECTRIC_TERRAIN in battle.fields or Field.MISTY_TERRAIN in battle.fields:
                        return 0

            # Magic Bounce / Good as Gold immunity
            if self.get_ability(target) in ["magicbounce", "goodasgold"]:
                return 0

            # Prankster vs Dark-type immunity
            if self.get_ability(my_pokemon) == "prankster":
               if ((target.type_1 == PokemonType.DARK or target.type_2 == PokemonType.DARK) or
                   self.is_grounded(target) and Field.PSYCHIC_TERRAIN in battle.fields):
                    return 0
               else:
                    score += 30

            # Determine threat level of target
            threat_score = 0

            # Check offensive stats
            target_atk = self.get_stat(target, "atk")
            target_spa = self.get_stat(target, "spa")

            # Higher score for faster threats
            if self.isFaster(target, my_pokemon, battle):
                threat_score += 30  # Increased from 20

            # Higher score for stronger attackers
            threat_score += max(target_atk, target_spa) // 2  # Simple scaling

            # Additional threat: target can KO our active pokemon
            for my_mon in battle.active_pokemon:
                if my_mon and not my_mon.fainted:
                    for opp_move in self.opp_team_movepool.get(target.species.capitalize(), []):
                        try:
                            opp_move_obj = Move(opp_move, 9)
                            if opp_move_obj.base_power > 0:
                                dmg = self.calculate_damage(target, my_mon, opp_move_obj, battle)
                                if dmg >= my_mon.current_hp_fraction * 100:
                                    threat_score += 25  # Target can KO us
                                    break
                        except:
                            pass

            # Score based on move type
            if move_id in ["thunderwave", "glare", "stunspore"]:  # Paralysis
                # Paralysis scores higher on fast opponents and strong threats
                # Paralysis is premium in VGC: halves speed + 25% fail chance
                score += 80 + threat_score  # Increased from 50
                # Bonus for paralyzing fast threats (speed control)
                if self.isFaster(target, my_pokemon, battle):
                    score += 50  # Increased from 30: neutralizing speed is huge
                # Extra value if target is a setup sweeper (paralysis prevents setup)
                if any(self.get_ability(target) == a for a in ["speedboost", "unburden", "swiftswim", "chlorophyll", "sandrush", "slushrush"]):
                    score += 30

            elif move_id == "willowisp":  # Burn
                # Burn scores higher on physical attackers
                if target_atk > target_spa:
                    score += 90 + (target_atk // 2)  # Increased from 60
                    # Extra value vs physical setup sweepers
                    if target.boosts.get("atk", 0) > 0:
                        score += 40
                else:
                    score += 15  # Slightly increased from 10: chip damage still matters
                # No value on Guts targets (checked via ability)
                if self.get_ability(target) == "guts":
                    score = 0
                # No value on Fire types (already checked) or Flash Fire / Water Bubble
                if self.get_ability(target) in ["flashfire", "waterbubble"]:
                    score = 0

            elif move_id in ["spore", "sleeppowder", "hypnosis"]:  # Sleep
                # Sleep is highest on the biggest threat - completely neutralizes
                score += 100 + threat_score  # Increased from 70: sleep = 1-3 turns of nothing
                # Extra value if target is the only answer to our wincon
                # Bonus for Spore (100% accuracy) vs Sleep Powder (75%) vs Hypnosis (60%)
                if move_id == "spore":
                    score += 30
                elif move_id == "sleeppowder":
                    score += 10

            elif move_id in ["toxic", "poisonpowder"]:  # Poison/Toxic
                # Poison/toxic is the lowest value of the group but still useful
                score += 45 + (threat_score // 2)  # Increased from 30
                # Toxic more valuable on bulky targets that won't die soon
                target_hp = self.get_stat(target, "hp")
                if target_hp > 150:
                    score += 20  # Toxic on bulky mons = long-term pressure

            else:  # Other status moves
                score += 50 + (threat_score // 2)  # Increased from 40

            return max(0, score)

        # Category 2: Stat-debuff moves
        elif move_id in self.STAT_DEBUFF:
            
            # Check if target has abilities that make the move fail
            ability = self.get_ability(target)
            if ability in ["clearbody", "whitesmoke", "fullmetalbody", "mirrorarmor"]:
                return 0

            # Check for Defiant, Competitive, Contrary (which would boost the target)
            if ability in ["defiant", "competitive", "contrary"]:
                return 0

            # Attack-lowering moves also fail against Hyper Cutter
            if move_id in ["charm", "fake tears", "screech", "growl", "leer", "eerie impulse"] and ability == "hypercutter":
                return 0

            # Determine which stat(s) are being lowered
            if move_id == "charm":
                # Charm (-2 Atk) is best against high-Attack physical threats
                target_atk = self.get_stat(target, "atk")
                score += 80 + (target_atk // 2)  # Increased from 50

            elif move_id == "fake tears":
                # Fake Tears (-2 Sp. Def) is best when my side has special attackers
                my_active_pokemon = [p for p in battle.active_pokemon if p is not None and not p.fainted]
                if len(my_active_pokemon) >= 2:
                    my_spa_total = sum(self.get_stat(p, "spa") for p in my_active_pokemon)
                    my_atk_total = sum(self.get_stat(p, "atk") for p in my_active_pokemon)
                    if my_spa_total > my_atk_total:  # My side favors special attacks
                        target_spd = self.get_stat(target, "spd")
                        score += 80 + (target_spd // 2)  # Increased from 50
                    else:
                        # Still valuable if we have any special attackers
                        if my_spa_total > 0:
                            target_spd = self.get_stat(target, "spd")
                            score += 50 + (target_spd // 2)
                else:
                    # Fallback: just check if target has high SpD to lower
                    target_spd = self.get_stat(target, "spd")
                    score += 50 + (target_spd // 2)  # Increased from 30

            elif move_id in ["screech", "leer", "growl"]:
                # Screech/Leer/Growl-style scale by the relevant stat
                stat_map = {"screech": "def", "leer": "def", "growl": "atk"}
                stat = stat_map[move_id]
                target_stat = self.get_stat(target, stat)
                score += 60 + (target_stat // 2)  # Increased from 40

            elif move_id == "eerie impulse":
                # Eerie Impulse (-2 SpA)
                target_spa = self.get_stat(target, "spa")
                score += 60 + (target_spa // 2)  # Increased from 40

            elif move_id == "tickle":
                # Tickle lowers Atk and Def so we check both
                target_atk = self.get_stat(target, "atk")
                target_def = self.get_stat(target, "def")
                score += 50 + (target_atk // 4) + (target_def // 4)  # Increased from 30
            

            # Parting Shot: -1 Atk, -1 Spa + pivot
            elif move_id == "partingshot":
                target_atk = self.get_stat(target, "atk")
                target_spa = self.get_stat(target, "spa")
                score += 70 + (target_atk // 4) + (target_spa // 4)  # Base value for pivot + debuff


            # Scale by how threatening the target is (its offensive stats)
            threat_score = max(self.get_stat(target, "atk"), self.get_stat(target, "spa")) // 2
            score += threat_score

            # Bonus if target has positive boosts (removing them is high value)
            if hasattr(target, 'boosts') and target.boosts:
                positive_boosts = sum(boost for boost in target.boosts.values() if boost > 0)
                if positive_boosts > 0:
                    score += positive_boosts * 20  # Removing boosts is very valuable

            
            lowered_stats = self.STAT_DEBUFF.get(move_id, [])
            if lowered_stats:
                worst_drop = min(target.boosts.get(stat, 0) for stat in lowered_stats)
                score *= max(0, 1 - (abs(worst_drop) * 0.25)) if worst_drop < 0 else 1
                
            return max(0, score)

        # Category 3: Disruption moves
        elif move_id in ["taunt", "encore"]:
            move_id = move.id

            # Both disruption moves return 0 for an ally target (already handled above)
            # Both disruption moves return 0 if target has certain abilities
            if self.get_ability(target) in ["oblivious", "aromaveil", "goodasgold", "magicbounce"]:
                return 0

            if move_id == "taunt":
                # TAUNT: use it only when ALL of these are true:
                # 1. opposing target is known to be a Trick Room or Tailwind user
                # 2. it is NOT already Taunted
                # 3. it does not have Oblivious, Aroma Veil, Good as Gold, or Magic Bounce

                # Check if target is known to be Trick Room or Tailwind user
                is_trickroom_user = False
                is_tailwind_user = False

                # Method 1: Check opp_team_movepool for confirmed moves
                target_species = target.species.capitalize() if target.species else ""
                if target_species and target_species in self.opp_team_movepool:
                    movepool_entry = self.opp_team_movepool[target_species]
                    if "trickroom" in movepool_entry and movepool_entry["trickroom"].get("status") == 0:
                        is_trickroom_user = True
                    if "tailwind" in movepool_entry and movepool_entry["tailwind"].get("status") == 0:
                        is_tailwind_user = True

                # Method 2: Check species lists
                target_species_lower = target.species.lower() if target.species else ""
                if target_species_lower in trickroom_pokemon:
                    is_trickroom_user = True
                if target_species_lower in tailwind_pokemon:
                    is_tailwind_user = True

                if not (is_trickroom_user or is_tailwind_user):
                    return 0

                # Check if target is already Taunted
                if hasattr(target, 'effects') and Effect.TAUNT in target.effects:
                    return 0

                # Reduce value if that side's Tailwind or Trick Room is already active
                side_condition_modifier = 1.0
                if SideCondition.TAILWIND in battle.opponent_side_conditions:
                    side_condition_modifier *= 0.5  # Less useful if Tailwind already up
                if Field.TRICK_ROOM in battle.fields:
                    side_condition_modifier *= 0.5  # Less useful if Trick Room already active

                # Base score for Taunt - increased to reflect VGC importance
                score += 150  # Increased from 100: Taunt is premium disruption

                score *= side_condition_modifier

                return max(0, score)

            elif move_id == "encore":
                # Check if target is None or fainted
                if target is None or target.fainted:
                    return 0

                # Check if target.last_move is None
                if getattr(target, 'last_move', None) is None:
                    return 0

                # Check if I am NOT faster
                if not self.isFaster(my_pokemon, target, battle):
                    return 0

                # Check if target is already Encored
                if hasattr(target, 'effects') and Effect.ENCORE in target.effects:
                    return 0

                # Check if target has blocking ability
                ability = self.get_ability(target)
                if ability in ["oblivious", "aromaveil", "goodasgold", "magicbounce"]:
                    return 0

                # Check if last move is not in SETUP_MOVES and not in PROTECT_MOVES
                last_move_id = target.last_move.id
                if last_move_id not in SETUP_MOVES and last_move_id not in PROTECT_MOVES and last_move_id != "fakeout":
                    return 0

                # Otherwise, calculate HIGH score
                score = 180  # base score - increased from 130: Encore is game-changing in VGC
                if last_move_id in SETUP_MOVES:
                    # Check if target already has any positive boost
                    if hasattr(target, 'boosts') and target.boosts:
                        if any(boost > 0 for boost in target.boosts.values()):
                            score += 30  # Increased from 15: locking setup sweeper is huge
                # Extra value if target used Protect (wastes their turn completely)
                if last_move_id in PROTECT_MOVES:
                    score += 40  # Encore on Protect = free turns
                # Extra value if target used Fake Out (locks them into a one-time move)
                if last_move_id == "fakeout":
                    score += 30

                return score

        # If move doesn't fit any category, return 50 base value
        return 50 