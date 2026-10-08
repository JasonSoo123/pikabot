import math
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from poke_env.battle.status import Status
from poke_env.battle.side_condition import SideCondition
from poke_env.battle.move import Move
from pikabot.constants import NON_SINGLE_TARGET

class DamageMixin:
    """Helper function to calculate damage of attacking pokemon v. defending/opp pokemon"""
    def calculate_damage(self, attacker, defender, move, battle):
        
        # if non damaging move return 0
        if move.base_power == 0 and move.id not in ["superfang", "naturesmadness", "ruination"]:
            return 0
        
        # Fixed damage conditions
        def_hp = self.get_stat(defender, 'hp')
        atk_hp = self.get_stat(attacker, 'hp')
        if move.id in ["superfang", "naturesmadness", "ruination"]:
            return (defender.current_hp_fraction / 2) * 100
        
        if move.id == "finalgambit":
            return (atk_hp / def_hp) * 100
        
        if move.id == "endeavor":
            fixed_dmg = max(0, def_hp - atk_hp)
            return (fixed_dmg / def_hp) * 100
        
        # Get abilities
        atk_ability = self.get_ability(attacker)
        def_ability = self.get_ability(defender)
        
        # Get items
        atk_item = self.get_item(attacker)
        def_item = self.get_item(defender)
        
        # Choosing what type of stat to look for
        atk_stat_name= 'atk' if move.category == MoveCategory.PHYSICAL else 'spa'
        def_stat_name = 'def' if atk_stat_name == 'atk' else 'spd'
        
        # Get stats
        atk_stat = self.get_stat(attacker, atk_stat_name)
        def_stat = self.get_stat(defender, def_stat_name)
        
        # If defender is rock type and in sandstorm boost spdef by 50%
        if PokemonType.ROCK in defender.types and Weather.SANDSTORM in battle.weather and def_stat_name == "spd":
            def_stat *= 1.5
        
        # If defender is ice type and in snow boost def by 50%
        if (PokemonType.ICE in defender.types and (Weather.SNOWSCAPE in battle.weather 
                        or Weather.SNOW in battle.weather)  and def_stat_name == "def"):
            def_stat *= 1.5 
        
        # If attacker has solar power in the sun boost spatk by 50%
        if Weather.SUNNYDAY in battle.weather and atk_ability == "solarpower" and atk_stat_name == "spa":
            atk_stat *= 1.5
        
         # If burned and physical move w/o guts and w guts      
        if move.category == MoveCategory.PHYSICAL and attacker.status == Status.BRN and atk_ability != "guts":
            atk_stat *= 0.5
        elif move.category == MoveCategory.PHYSICAL and attacker.status == Status.BRN and atk_ability == "guts":
            atk_stat *= 1.5
        
        # Battle items to consider
        if def_item == "assaultvest" and def_stat_name == "spd":
            def_stat *= 1.5
        
        if atk_item == "choiceband" and atk_stat_name == "atk":
            atk_stat *= 1.5
        
        elif atk_item == "choicespecs" and atk_stat_name == "spa":
            atk_stat *= 1.5
        
        # Calculate damage without multipliers
        
        base_power = move.base_power
        
        # Special scaling base_power moves
        if move.id in ["eruption", "waterspout", "dragonenergy"]:
            base_power = max(1, math.floor(150 * attacker.current_hp_fraction))
        
        elif move.id in ["crushgrip", "wringout"]:
            base_power = math.floor(120 * defender.current_hp_fraction) + 1
            
                          
        damage = math.floor(math.floor(22 * base_power * atk_stat / def_stat) / 50) + 2
        
        move_type = move.type
        
        # Modifiers for abilities
        if move_type == PokemonType.NORMAL and atk_ability == "aerilate":
            move_type = PokemonType.FLYING
            damage *= 1.2
        
        elif move_type == PokemonType.NORMAL and atk_ability == "pixilate":
            move_type = PokemonType.FAIRY
            damage *= 1.2
        
        elif move_type == PokemonType.NORMAL and atk_ability == "refrigerate":
            move_type = PokemonType.ICE
            damage *= 1.2
        
        elif move_type == PokemonType.NORMAL and atk_ability == "galvanize":
            move_type = PokemonType.ELECTRIC
            damage *= 1.2
        
        elif atk_ability == "normalize":
            move_type = PokemonType.NORMAL
            damage *= 1.2
        
        elif atk_ability == "strongjaw" and "bite" in move.flags:
            damage *= 1.5
        
        elif atk_ability == "toughclaws" and "contact" in move.flags:
            damage *= 1.3
        
        elif atk_ability == "ironfist" and "punch" in move.flags:
            damage *= 1.2
        
        elif atk_ability == "sheerforce" and move.secondary:
            damage *= 1.3
        
        elif atk_ability == "reckless" and move.recoil is not None and move.recoil > 0:
            damage *= 1.2
        
        if def_ability == "bulletproof" and ("ball" in move.flags or "bomb" in move.flags):
            damage *= 0
        
        elif def_ability == "soundproof" and "sound" in move.flags:
            damage *= 0
        
        elif def_ability == "wonderguard" and defender.damage_multiplier(move_type) < 2:
            damage *= 0
        
        # Multipler if its a spread move
        if move.target.name in NON_SINGLE_TARGET:
            damage *= 0.75
        
        # Multiplier if STAB (Same Type Attack Bonus)
        if move_type in attacker.types:
            if atk_ability == "adaptability":
                damage *= 2
            else:
                damage *= 1.5
        
        # Consider screens (Grouped so they don't stack)
        ignores_screens = move.id in ["brickbreak", "psychicfangs", "ragingbull"] or atk_ability == "infiltrator"
        
        if not ignores_screens:
            if move.category == MoveCategory.PHYSICAL:
                if SideCondition.REFLECT in battle.opponent_side_conditions or SideCondition.AURORA_VEIL in battle.opponent_side_conditions:
                    damage *= 0.67
            elif move.category == MoveCategory.SPECIAL:
                if SideCondition.LIGHT_SCREEN in battle.opponent_side_conditions or SideCondition.AURORA_VEIL in battle.opponent_side_conditions:
                    damage *= 0.67
            
        # Type multiplier
        damage *= defender.damage_multiplier(move_type)
        
        # Technician boost
        if atk_ability == "technician" and move.base_power <= 60:
            damage *= 1.5
        
        # Life orb boost
        if atk_item == "lifeorb":
            damage *= 1.3
            
        # If move is water type
        if move_type == PokemonType.WATER:
            
            # Weather check
            if Weather.RAINDANCE in battle.weather:
                damage *= 1.5
            elif Weather.SUNNYDAY in battle.weather:
                damage *= 0.5
    
            if atk_item in ["mysticwater", "splashplate" ,"waveincense" ,"seaincense"]:
                damage *= 1.2
                
            if atk_ability == "waterbubble":
                damage *= 2
                
            if def_ability in ["waterabsorb", "dryskin", "stormdrain"]:
                damage *= 0
                
        # If move is fire type        
        elif move_type == PokemonType.FIRE:
            
            # Weather check
            if Weather.RAINDANCE in battle.weather:
                damage *= 0.5
            elif Weather.SUNNYDAY in battle.weather:
                damage *= 1.5
                
            if atk_item in ["charcoal", "flameplate"]:
                damage *= 1.2
                
            if def_ability == "waterbubble":
                damage *= 0.5
            elif def_ability == "flashfire":
                damage *= 0
        
        # If move is grass type
        elif move_type == PokemonType.GRASS:
            
            # Grassy terrian check
            if Field.GRASSY_TERRAIN in battle.fields:
                damage *= 1.3
                
            if atk_item in ["miracleseed", "meadowplate", "roseincense"]:
                damage *= 1.2
                
            if def_ability == "sapsipper":
                damage *= 0
        
        # If move is bug type        
        elif move_type == PokemonType.BUG:
            
            if atk_item in ["silverpowder", "insectplate"]:
                damage *= 1.2
        
        # If move is dark type 
        elif move_type == PokemonType.DARK:
            
            if atk_item in ["blackglasses", "dreadplate"]:
                damage *= 1.2
                
            if atk_ability == "darkaura" or def_ability == "darkaura":
                damage *= 1.33
        
        # If move is dragon type         
        elif move_type == PokemonType.DRAGON:
           
           # Misty terrian check
            if Field.MISTY_TERRAIN in battle.fields:
                damage *= 0.5
                
            if atk_item in ["dragonfang", "dracoplate"]:
                damage *= 1.2
                
            if atk_ability == "dragonsmaw":
                damage *= 1.5
        
        # If move is electric type 
        elif move_type == PokemonType.ELECTRIC:
            
            # Electric terrian check
            if Field.ELECTRIC_TERRAIN in battle.fields:
                damage *= 1.3
                
            if atk_item in ["magnet", "zapplate"]:
                damage *= 1.2
                
            if atk_ability == "transistor":
                damage *= 1.3
                
            if def_ability in ["voltabsorb", "lightningrod", "motordrive"]:
                damage *= 0
        
        # If move is fairy type 
        elif move_type == PokemonType.FAIRY:
            
            if atk_item in ["fairyfeather", "pixieplate"]:
                damage *= 1.2
                
            if atk_ability == "fairyaura" or def_ability == "fairyaura":
                damage *= 1.33
        
        # If move is fighting type 
        elif move_type == PokemonType.FIGHTING:
            
            if atk_item in ["blackbelt", "fistplate"]:
                damage *= 1.2
        
        # If move is flying type 
        elif move_type == PokemonType.FLYING:
            
            if atk_item in ["sharpbeak", "skyplate"]:
                damage *= 1.2
        
        # If move is ghost type 
        elif move_type == PokemonType.GHOST:
            
            if atk_item in ["spelltag", "spookyplate"]:
                damage *= 1.2
        
        # If move is ground type 
        elif move_type == PokemonType.GROUND:
            
            if atk_item in ["softsand",  "earthplate"]:
                damage *= 1.2
                
            if atk_ability == "sandforce" and Weather.SANDSTORM in battle.weather:
                damage *= 1.3
                
            if def_ability == "levitate" or def_ability == "eartheater":
                damage *= 0
        
        # If move is ice type
        elif move_type == PokemonType.ICE:
            
            if atk_item in ["nevermeltice", "icicleplate"]:
                damage *= 1.2
        
        # If move is normal type
        elif move_type == PokemonType.NORMAL:
            
            if atk_item in ["silkscarf", "blankplate"]:
                damage *= 1.2
        
        # If move is poison type
        elif move_type == PokemonType.POISON:
            
            if atk_item in ["poisonbarb", "toxicplate"]:
                damage *= 1.2
        
        # If move is psychic type
        elif move_type == PokemonType.PSYCHIC:
            
            # Psychic terrian check
            if Field.PSYCHIC_TERRAIN in battle.fields:
                damage *= 1.3
            
            if atk_item in ["twistedspoon", "mindplate", "oddincense"]:
                damage *= 1.2
        
        # If move is rock type
        elif move_type == PokemonType.ROCK:
            
            if atk_item in ["hardstone", "stoneplate", "rockincense"]:
                damage *= 1.2
                
            if atk_ability == "rockpayload":
                damage *= 1.5
            elif atk_ability == "sandforce" and Weather.SANDSTORM in battle.weather:
                damage *= 1.3
        
        elif move_type == PokemonType.STEEL:
            
            if atk_item in ["metalcoat", "ironplate"]:
                damage *= 1.2
                
            if atk_ability in ["steelworker", "steelyspirit"]:
                damage *= 1.5
            elif atk_ability == "sandforce" and Weather.SANDSTORM in battle.weather:
                damage *= 1.3
                
        # Random roll average (0.85 - 1)
        damage = math.floor(damage * 0.925)
        
        damage_percentage = (damage / def_hp) * 100
        # print(f"move: {move.id} did {damage_percentage} to {defender.species}")
        return damage_percentage
    
    """Helper function to calculate defensive score for defensive moves such as protect or switching"""
    def calc_defensive_score(self, my_pokemon, battle):
        most_damage = -1
        highest_damaging_move = None
        opp_pokemon = None
        for opp in battle.opponent_active_pokemon:

            if opp is not None and not opp.fainted:
                for move in self.opp_team_movepool[opp.species.capitalize()]:
    
                    try:
                        move_obj = Move(move, 9)
                    except Exception as e:
                        print(f"Failed to create move '{move}': {e}")
                        continue
                  
                    damage = self.calculate_damage(opp, my_pokemon, move_obj, battle)
                    
                    if damage > most_damage:
                        most_damage = damage
                        highest_damaging_move = move_obj
                        opp_pokemon = opp
                    
        return most_damage, highest_damaging_move, opp_pokemon
    
    """Helper function to calculate self status move score"""
