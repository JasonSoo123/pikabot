from poke_env.battle.side_condition import SideCondition
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from poke_env.battle.target import Target
from poke_env.battle.effect import Effect
from poke_env.battle.move_category import MoveCategory
import math
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
        "charm", "growl", "tailwhip", "screech", "flash", "confide",
        "captivate", "leer", "sandattack", "stickyweb", "electroweb",
        "partingshot", "chillyreception", "sweetscent", "faketears",
        "eerieimpulse", "tickle", "scaryface", "mudsport", "mudslap"
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

            score += 50
            if my_pokemon.current_hp_fraction > 0.5:
                score += 20

            return score

        elif move.id == "tailwind":
            # dont use tailwind if it is already active or trickroom is active
            if SideCondition.TAILWIND in battle.side_conditions or Field.TRICK_ROOM in battle.fields:
                return 0
            return 120

        elif move.id in ["reflect", "lightscreen", "auroraveil"]:

            if  move.id == "auroraveil":
                if battle.weather not in Weather.SNOW and battle.weather not in Weather.SNOWSCAPE:
                    return 0
                if SideCondition.AURORA_VEIL in battle.side_conditions:
                    return 0
                return 110
            elif move.id == "lightscreen":
                if SideCondition.LIGHT_SCREEN in battle.side_conditions:
                    return 0
                return 80
            else:
                if SideCondition.REFLECT in battle.side_conditions:
                    return 0
                return 80

        elif move.id in ["followme", "ragepowder"]:

            if partner and not partner.fainted:

                if move.id == "ragepowder":
                    all_opponents_grass = all(
                        (opp.type_1 and opp.type_1 == PokemonType.GRASS) or (opp.type_2 and opp.type_2 == PokemonType.GRASS)
                        for opp in battle.opponent_active_pokemon if opp is not None and not opp.fainted
                    )

                    if all_opponents_grass:
                        return 0

                if self.calc_defensive_score(partner, battle) > 30:
                    score += 145

                if (partner.current_hp_fraction * 100) < 50:
                    score += 30

                if is_going_to_faint:
                    score += 30

            return score

        elif move.id == "helpinghand":
            if partner and not partner.fainted:
                score = 0
                for moves in battle.available_moves[partner_slot]:
                    for opp in battle.opponent_active_pokemon:
                        current_score = self.calculate_damage(partner, opp, moves, battle)
                        if current_score > score:
                            score = current_score

                score *= 1.5
                score -= 15
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

            score += 50

            if partner and not partner.fainted:
                score += 50

            if battle.weather:
                score += 100

            return score

        elif move.id in ["recover", "roost", "slackoff", "softboiled", "morningsun", "synthesis", "moonlight"]:
            if my_pokemon.current_hp_fraction >= 0.8:
                return 0
            return 150 if my_pokemon.current_hp_fraction <= 0.5 else 100

        elif move.id == "trickroom":

            score = 0 # reset score cause trickroom does not work with prankster

            if all(not self.isFaster(my_pokemon, opp, battle) for opp in battle.opponent_active_pokemon if opp is not None and not opp.fainted):
                score += 50

            if partner and not partner.fainted:
                if all(not self.isFaster(partner, opp, battle) for opp in battle.opponent_active_pokemon if opp is not None and not opp.fainted):
                    score += 130

            return score

        elif move.id in ["coaching", "decorate"]:

            if not partner or partner.fainted:
                return 0

            partner_atk = self.get_stat(partner, 'atk')
            partner_spa = self.get_stat(partner, "spa")

            if ((move.id == "coaching" and (partner_atk > partner_spa)) or
                (move.id == "decorate" and (partner_spa > partner_atk))):
                score += 80

                if self.isFaster(my_pokemon, partner):
                    score += 15

                    if is_going_to_faint:
                        score += 10
            print(f"score: {score} for {move}")
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
                threat_score += 20

            # Higher score for stronger attackers
            threat_score += max(target_atk, target_spa) // 2  # Simple scaling

            # Score based on move type
            if move_id in ["thunderwave", "glare", "stunspore"]:  # Paralysis
                # Paralysis scores higher on fast opponents and strong threats
                score += 50 + threat_score
                # Bonus for paralyzing fast threats
                if self.isFaster(target, my_pokemon, battle):
                    score += 30

            elif move_id == "willowisp":  # Burn
                # Burn scores higher on physical attackers
                if target_atk > target_spa:
                    score += 60 + (target_atk // 2)
                else:
                    score += 10  # Low value on special attackers
                # No value on Guts targets (checked via ability)
                if self.get_ability(target) == "guts":
                    score = 0

            elif move_id in ["spore", "sleeppowder", "hypnosis"]:  # Sleep
                # Sleep is highest on the biggest threat
                score += 70 + threat_score

            elif move_id in ["toxic", "poisonpowder"]:  # Poison/Toxic
                # Poison/toxic is the lowest value of the group
                score += 30 + (threat_score // 2)

            else:  # Other status moves
                score += 40 + (threat_score // 2)

            print(f"score: {score} for {move}")
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
                score += 50 + (target_atk // 2)

            elif move_id == "fake tears":
                # Fake Tears (-2 Sp. Def) is best when my side has special attackers
                my_active_pokemon = [p for p in battle.active_pokemon if p is not None and not p.fainted]
                if len(my_active_pokemon) >= 2:
                    my_spa_total = sum(self.get_stat(p, "spa") for p in my_active_pokemon)
                    my_atk_total = sum(self.get_stat(p, "atk") for p in my_active_pokemon)
                    if my_spa_total > my_atk_total:  # My side favors special attacks
                        target_spd = self.get_stat(target, "spd")
                        score += 50 + (target_spd // 2)
                else:
                    # Fallback: just check if target has high SpD to lower
                    target_spd = self.get_stat(target, "spd")
                    score += 30 + (target_spd // 2)

            elif move_id in ["screech", "leer", "growl"]:
                # Screech/Leer/Growl-style scale by the relevant stat
                stat_map = {"screech": "def", "leer": "def", "growl": "atk"}
                stat = stat_map[move_id]
                target_stat = self.get_stat(target, stat)
                score += 40 + (target_stat // 2)

            elif move_id == "eerie impulse":
                # Eerie Impulse (-2 SpA)
                target_spa = self.get_stat(target, "spa")
                score += 40 + (target_spa // 2)

            elif move_id == "tickle":
                # Tickle lowers Atk and Def so we check both
                target_atk = self.get_stat(target, "atk")
                target_def = self.get_stat(target, "def")
                score += 30 + (target_atk // 4) + (target_def // 4)

            # Scale by how threatening the target is (its offensive stats)
            threat_score = max(self.get_stat(target, "atk"), self.get_stat(target, "spa")) // 2
            score += threat_score

            print(f"score: {score} for {move}")
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
                # Note: poke-env may not expose this directly, so we'll skip this check
                # as per the limitation mentioned in the instructions
                pass

                # Reduce value if that side's Tailwind or Trick Room is already active
                side_condition_modifier = 1.0
                if SideCondition.TAILWIND in battle.side_conditions:
                    side_condition_modifier *= 0.5  # Less useful if Tailwind already up
                if Field.TRICK_ROOM in battle.fields:
                    side_condition_modifier *= 0.5  # Less useful if Trick Room already active

                # Base score for Taunt
                score += 60

                # Bonus for confirmed knowledge
                target_species = target.species.capitalize() if target.species else ""
                if target_species and target_species in self.opp_team_movepool:
                    movepool_entry = self.opp_team_movepool[target_species]
                    if ("trickroom" in movepool_entry and movepool_entry["trickroom"].get("status") == 0) or \
                       ("tailwind" in movepool_entry and movepool_entry["tailwind"].get("status") == 0):
                        score += 20  # Bonus for confirmed knowledge

                score *= side_condition_modifier

                print(f"score: {score} for {move}")
                return max(0, score)

            elif move_id == "encore":
                # ENCORE: use it only when ALL of these are true:
                # 1. I am faster than the target (self.isFaster already respects Trick Room)
                # 2. the target's last used move is known and is a power-boosting move
                #    (a setup move in SETUP_MOVES, or any move whose boosts raise the user's stats)
                #    or a Protect-style move (in PROTECT_MOVES)
                # 3. it does not have Oblivious, Aroma Veil, Good as Gold, or Magic Bounce

                # Check if I am faster than the target
                if not self.isFaster(my_pokemon, target, battle):
                    return 0

                # Check if target's last used move is known
                # This is a limitation - poke-env may not expose last used move directly
                # We'll need to check if we can access it through target or battle
                # For now, we'll return 0 if we can't determine this, as per instructions
                # "if poke-env does not expose it, say so, use the safest fallback (return 0 for Encore)"

                # Let's try to check if target has a last_move attribute
                last_move = getattr(target, 'last_move', None)
                if last_move is None:
                    # Try to get it from battle if possible
                    # This is speculative - we don't see a standard way
                    last_move = None

                if last_move is None:
                    # Safest fallback as per instructions
                    return 0

                # Check if last move is a power-boosting move or Protect-style move
                is_boosting_move = False

                # Check if it's a setup move
                if last_move.id in SETUP_MOVES:
                    is_boosting_move = True
                else:
                    # Check if it raises user's stats
                    if last_move.boosts and any(boost > 0 for boost in last_move.boosts.values()):
                        is_boosting_move = True

                # Check if it's a Protect-style move
                if last_move.id in PROTECT_MOVES:
                    is_boosting_move = True  # Protect counts as usable for Encore

                if not is_boosting_move:
                    return 0

                # Base score for Encore
                score += 50
                
                print(f"score: {score} for {move}")
                return max(0, score)

        # If move doesn't fit any category, return 0
        return 0