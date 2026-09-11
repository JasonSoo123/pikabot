import asyncio
import os
import json
import math
import random
from poke_env.player import Player, RandomPlayer
from poke_env.player.battle_order import DoubleBattleOrder
from poke_env.battle.side_condition import SideCondition
from poke_env.battle.move_category import MoveCategory
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from poke_env.battle.status import Status
from poke_env.battle.move import Move

EX_VGC_TEAM = '''
Incineroar @ Sitrus Berry  
Ability: Intimidate  
Level: 50  
EVs: 32 HP / 32 Atk / 2 SpD  
Adamant Nature  
- Darkest Lariat  
- Parting Shot
- Flare Blitz 
- Fake Out 

Blastoise @ Blastoisinite  
Ability: Torrent  
Level: 50  
EVs: 32 HP / 32 SpA / 2 Spe  
Modest Nature  
- Aura Sphere  
- Dark Pulse  
- Water Spout  
- Fake Out   

Basculegion (M) @ Focus Sash  
Ability: Adaptability  
Level: 50  
EVs: 32 HP / 32 Atk / 2 SpA  
Lonely Nature  
- Aqua Jet  
- Crunch  
- Flip Turn  
- Hydro Pump  

Kingambit @ Black Glasses  
Ability: Defiant  
Level: 50  
EVs: 32 HP / 2 Atk / 32 SpA  
Quiet Nature  
- Brick Break  
- Dark Pulse  
- Foul Play  
- Focus Blast  

Glimmora @ Leftovers  
Ability: Toxic Debris  
Level: 50  
EVs: 2 HP / 32 SpA / 32 Spe  
Timid Nature  
- Acid Armor  
- Dazzling Gleam  
- Earth Power  
- Energy Ball  

Aegislash @ Metal Coat  
Ability: Stance Change  
Level: 50  
EVs: 32 HP / 32 Atk / 2 SpD  
Adamant Nature  
- Shadow Sneak  
- King's Shield  
- Iron Head  
- Swords Dance

'''
# ------------------------ Opening stats json for info ----------------------- #
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
with open(DIRECTORY + '/champions-vgc-stats.json', 'r') as file:
    raw_vgc_data = json.load(file)
    POKEMON_VGC_DATA = raw_vgc_data.get('pokemon', raw_vgc_data)


fakeout_pokemon = []
tailwind_pokemon = []
trickroom_pokemon = []
PROTECT_MOVES = ["protect", "detect", "banefulbunker", "burningbulwark", "craftyshield", 
                 "kingsshield", "maxguard", "obtruct", "spikyshield", "silktrap"]
# -------------------------- getting fakeout_pokemon ------------------------- #
for pokemon_name, data in POKEMON_VGC_DATA.items():
    
    moves = data.get("Moves", {})
    
    if "fakeout" in moves and pokemon_name.lower() not in fakeout_pokemon:
        fakeout_pokemon.append(pokemon_name.lower())
    if "tailwind" in moves and pokemon_name.lower() not in tailwind_pokemon:
        tailwind_pokemon.append(pokemon_name.lower())
    if "trickroom" in moves and pokemon_name.lower() not in trickroom_pokemon:
        trickroom_pokemon.append(pokemon_name.lower())
# ---------------------------------- VGC bot --------------------------------- #
NON_SINGLE_TARGET = ["ALL_ADJACENT_FOES", "ALL_ADJACENT", "ALL", "SELF", "ADJACENT_ALLY_OR_SELF", "ALLY_SIDE",
                     "ALLY_TEAM", "SELF", "ADJACENT_ALLY", "SCRIPTED", "FOE_SIDE"]
class ClamBot(Player):
    
    def __init__(self, *args, **kwargs):
        # This safely passes all configuration arguments (team, format, etc.) to the parent class
        super().__init__(*args, **kwargs)
        
        # Initialize opp team move pool attribute
        self.opp_team_movepool = {}
        self.mega = False
        self.protect_last_turn = [False, False]
    
    """Register opp pokemon into the dict"""    
    def register_opp_pokemon(self, pokemon_name):
        formatted_name = pokemon_name.capitalize()
        
        if formatted_name not in self.opp_team_movepool:
            self.opp_team_movepool[formatted_name] = {}
            
            
            pokemon_data = POKEMON_VGC_DATA.get(formatted_name, {})
            moves_dict = pokemon_data.get("Moves", {})
            
            # Sort the dictionary by usage count (highest to lowest) and slice the top 4
            top_moves = sorted(moves_dict.items(), key=lambda item: item[1], reverse=True)[:4]
            
            for move_name, usage_prob in top_moves:
                self.opp_team_movepool[formatted_name][move_name] = {
                    "status": 1,         # 1 = Unconfirmed
                    "prob": usage_prob   # Store the raw usage count/prob to know which to drop later
                }
       
    """Updates the tracker when an opponent reveals a move."""
    def record_revealed_move(self, pokemon_name, move_name):
        formatted_name = pokemon_name.capitalize()
        
        # Safety check: ensure the pokemon is registered
        if formatted_name not in self.opp_team_movepool:
            self.register_opp_pokemon(pokemon_name)
            
        tracked_moves = self.opp_team_movepool[formatted_name]
        
        # If the move is already in our predicted pool, lock it in as confirmed (0)
        if move_name in tracked_moves:
            tracked_moves[move_name]["status"] = 0
            tracked_moves[move_name]["prob"] = float('inf') # Ensure it never gets dropped
            
        else:
            # The move wasn't predicted. If we already have 4 moves, we must drop one.
            if len(tracked_moves) >= 4:
                
                # Filter out the moves that are still unconfirmed (status == 1)
                unconfirmed_moves = {m: data for m, data in tracked_moves.items() if data["status"] == 1}
                
                if unconfirmed_moves:
                    # Find the unconfirmed move with the lowest probability score
                    move_to_drop = min(unconfirmed_moves, key=lambda m: unconfirmed_moves[m]["prob"])
                    del tracked_moves[move_to_drop]
            
            # Add the newly revealed move as confirmed
            tracked_moves[move_name] = {
                "status": 0,
                "prob": float('inf')
            }
    
    """Call this at the start of every turn to keep the dictionary updated."""
    def update_opponent_knowledge(self, battle):
        # Loop through all opponent pokemon that have been revealed
        for opp_mon in battle.opponent_team.values():
            
            # 1. Register the pokemon if we haven't seen it yet
            self.register_opp_pokemon(opp_mon.species)
            
            # 2. In poke-env, a pokemon object automatically logs moves in its .moves dictionary 
            # once they are revealed in battle. We can sync that with our custom tracker!
            for revealed_move in opp_mon.moves:
                self.record_revealed_move(opp_mon.species, revealed_move)
    
    """Returns an ability for the pokemon"""
    def get_ability(self, pokemon):
        if pokemon.ability is not None:
            return pokemon.ability
        else:
            pokemon_data = POKEMON_VGC_DATA.get(pokemon.species.capitalize(), {})
            if "Abilities" in pokemon_data:
                abilities_dict = pokemon_data["Abilities"]
                
                if abilities_dict:
                    return max(abilities_dict, key=abilities_dict.get)
        
        return None
    
    """Return the stat for the pokemon + boosts"""
    def get_stat(self, pokemon, stat):
        base_stat = pokemon.base_stats.get(stat, 0)
        boosts = pokemon.boosts.get(stat, 0)
        raw_stat = 0
        
        actual_stat = pokemon.stats.get(stat)
        
        if actual_stat is not None and actual_stat != 0:
            # If it's your Pokemon, get the exact unboosted stat
            raw_stat = actual_stat
        else:
            # If it's an opponent, estimate it using JSON
            pokemon_data = POKEMON_VGC_DATA.get(pokemon.species.capitalize(), {})
            spreads_dict = pokemon_data.get("Spreads", {})
            
            if spreads_dict:
                top_spread = max(spreads_dict, key=spreads_dict.get)
                nature, sp_string = top_spread.split(":")
                sp_list = [int(x) for x in sp_string.split("/")]
                nature_modifier = 1
                
                if stat == "hp":
                    raw_stat = base_stat + 75 + sp_list[0]
                
                elif stat == "atk":
                    if nature in ["Lonely", "Adamant", "Naughty", "Brave"]: nature_modifier = 1.1
                    elif nature in ["Bold", "Modest", "Calm", "Timid"]: nature_modifier = 0.9
                    
                    raw_stat = math.floor((base_stat + 20 + sp_list[1]) * nature_modifier)
                
                elif stat == "def":
                    if nature in ["Bold", "Impish", "Lax", "Relaxed"]: nature_modifier = 1.1
                    elif nature in ["Lonely", "Mild", "Gentle", "Hasty"]: nature_modifier = 0.9
                    
                    raw_stat = math.floor((base_stat + 20 + sp_list[2]) * nature_modifier)
                 
                elif stat == "spa":
                    if nature in ["Modest", "Mild", "Rash", "Quiet"]: nature_modifier = 1.1
                    elif nature in ["Adamant", "Impish", "Careful", "Jolly"]: nature_modifier = 0.9
                    
                    raw_stat = math.floor((base_stat + 20 + sp_list[3]) * nature_modifier)
                 
                elif stat == "spd":
                    if nature in ["Calm", "Gentle", "Careful", "Sassy"]: nature_modifier = 1.1
                    elif nature in ["Naughty", "Lax", "Rash", "Naive"]: nature_modifier = 0.9
                    
                    raw_stat = math.floor((base_stat + 20 + sp_list[4]) * nature_modifier)
                 
                else: # Speed
                    if nature in ["Timid", "Hasty", "Jolly", "Naive"]: nature_modifier = 1.1
                    elif nature in ["Brave", "Relaxed", "Quiet", "Sassy"]: nature_modifier = 0.9
        
                    raw_stat = math.floor((base_stat + 20 + sp_list[5]) * nature_modifier) 
            else:    
                # Safe Fallback
                raw_stat = base_stat + 75 if stat == "hp" else base_stat + 20
        
        # 2. Apply Boosts to the Raw Stat
        if stat == "hp":
            return raw_stat # HP cannot be boosted so return 
            
        if boosts >= 0:
            return math.floor(raw_stat * ((2 + boosts) / 2))
        else:
            return math.floor(raw_stat * (2 / (2 - boosts)))
    
    """Return item for the pokemon"""
    def get_item(self, pokemon):
        if pokemon.item is not None:
            return pokemon.item
        else:
            pokemon_data = POKEMON_VGC_DATA.get(pokemon.species.capitalize(), {})
            if "Items" in pokemon_data:
                item_dict = pokemon_data["Items"]
                
                if item_dict:
                    return max(item_dict, key=item_dict.get)
        return None
    
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
        if PokemonType.ROCK in defender.types and battle.weather == Weather.SANDSTORM and def_stat_name == "spd":
            def_stat *= 1.5
        
        # If defender is ice type and in snow boost def by 50%
        if PokemonType.ICE in defender.types and battle.weather == Weather.SNOWSCAPE and def_stat_name == "def":
            def_stat *= 1.5 
        
        # If attacker has solar power in the sun boost spatk by 50%
        if battle.weather == Weather.SUNNYDAY and atk_ability == "solarpower" and atk_stat_name == "spa":
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
            if battle.weather == Weather.RAINDANCE:
                damage *= 1.5
            elif battle.weather == Weather.SUNNYDAY:
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
            if battle.weather == Weather.RAINDANCE:
                damage *= 0.5
            elif battle.weather == Weather.SUNNYDAY:
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
                
            if atk_ability == "sandforce" and battle.weather == Weather.SANDSTORM:
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
            elif atk_ability == "sandforce" and battle.weather == Weather.SANDSTORM:
                damage *= 1.3
        
        elif move_type == PokemonType.STEEL:
            
            if atk_item in ["metalcoat", "ironplate"]:
                damage *= 1.2
                
            if atk_ability in ["steelworker", "steelyspirit"]:
                damage *= 1.5
            elif atk_ability == "sandforce" and battle.weather == Weather.SANDSTORM:
                damage *= 1.3
                
        # Random roll average (0.85 - 1)
        damage = math.floor(damage * 0.925)
        
        damage_percentage = (damage / def_hp) * 100
        print(f"move: {move.id} did {damage_percentage} to {defender.species}")
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
    
    """Helper function to choose the best order for a specific pokemon in the current battle"""
    def choose_best_order(self, pokemon, battle, available_moves):
        best_score = -1
        best_order = None
        
        # Mega Evolution
        slot_index = battle.active_pokemon.index(pokemon)
        should_mega = False
        
        if not self.mega:
            should_mega = battle.can_mega_evolve[slot_index]
            
            if should_mega:
                self.mega = True
        
        def_score, most_threatning_move, most_threat_opp = self.calc_defensive_score(pokemon, battle)
                
        for move in available_moves:
            
            # --- Spread / Multi-Target Moves / Status / (NON-SINGLE TARGET DMGING MOVES) ---
            if move.target.name in NON_SINGLE_TARGET:
                current_score = 0
                # Tailwind conditions
                
                # Protect conditions
                if move.id in PROTECT_MOVES:
                    print(f"it used a protect move the score is: {def_score}")
                    current_score = def_score
                    
                    if self.protect_last_turn[slot_index]:
                        print("used it last turn")
                        current_score -= 40
                
                for opp in battle.opponent_active_pokemon:
                    if opp is not None and not opp.fainted:
                        current_score += self.calculate_damage(pokemon, opp, move, battle)
                        current_score -= math.floor((100 - math.floor(move.accuracy * 100))/2) # Accuracy
                    
                if current_score > best_score:
                    
                    if move.id in PROTECT_MOVES:
                        self.protect_last_turn[slot_index] = True
                    else:
                        self.protect_last_turn[slot_index] = False
                    
                    best_score = current_score
                    best_order = self.create_order(move, move_target=0, mega=should_mega)
                    
            # --- Single Target Moves ---
            else:
                # Loop through both opponents to see which one we hit harder
                for i, opp in enumerate(battle.opponent_active_pokemon):
                    
                    if opp is not None and not opp.fainted:
                        
                        current_score = self.calculate_damage(pokemon, opp, move, battle)
                        current_score -= math.floor((100 - math.floor(move.accuracy * 100))/2) # Accuracy
                        
                        if move.id == "fakeout":
                            current_score *= 500
                            
                        if current_score > best_score:
                            
                            self.protect_last_turn[slot_index] = False
                            best_score = current_score
                            
                            # In poke-env: Target 1 is opponent's left (index 0). Target 2 is opponent's right (index 1)
                            target = i + 1 
                            best_order = self.create_order(move, move_target=target, mega=should_mega)
        
        
        current_score = 0
        current_hp_percent = pokemon.current_hp_fraction * 100
        is_going_to_faint = def_score >= current_hp_percent
        takes_alot_dmg = def_score > 80
        switch_target = -1
                
        
        
        print(f"best order is: {best_order}")         
        return best_order
    
        
    def choose_move(self, battle):

        self.update_opponent_knowledge(battle)
        # If there is a force switch
        if any(battle.force_switch):
            left_switch = None
            right_switch = None
            if battle.force_switch[0] and battle.available_switches[0]:
                left_switch = self.create_order(battle.available_switches[0][0])
            if battle.force_switch[1] and battle.available_switches[1]:
                right_switch = self.create_order(battle.available_switches[1][0])
            if left_switch and right_switch:
                return DoubleBattleOrder(left_switch, right_switch)
            elif left_switch:
                return left_switch
            elif right_switch:
                return right_switch
            
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
    
    def teampreview(self, battle):
        return self.random_teampreview(battle)
      

async def main():
    player1 = ClamBot(
        battle_format="gen9championsvgc2026regma",
        team=EX_VGC_TEAM
    )
    
    player2 = RandomPlayer(
        battle_format="gen9championsvgc2026regma",
        team=EX_VGC_TEAM
    )

    # Set n_battles=1 so you can see it complete a single match
    await player1.battle_against(player2, n_battles=1)

if __name__ == "__main__":
    asyncio.run(main())
