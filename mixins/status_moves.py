from poke_env.battle.side_condition import SideCondition
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from pikabot.constants import SETUP_MOVES

class StatusMoveMixin:
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
            # Python's all() function returns True only if every check in the loop is True
            if all(my_pokemon.boosts.get(stat, 0) >= 4 for stat in stats_boosted):
                return 0     # Don't use it if we are already fully boosted
    
            score += 80
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
                        
            return score
        
        return 40
