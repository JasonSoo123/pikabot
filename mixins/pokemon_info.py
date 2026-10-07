import math
from pikabot.data_loader import POKEMON_VGC_DATA

class PokemonInfoMixin:
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
    """Helper function to check if the pokemon is on the ground or not"""
    def is_grounded(self, pokemon):
        if pokemon is None:
            return True
    
        # Flying types are not grounded
        if (pokemon.type_1 and pokemon.type_1.name == "FLYING") or \
        (pokemon.type_2 and pokemon.type_2.name == "FLYING"):
            return False
        
        # Levitate ability is not grounded
        if pokemon.ability and pokemon.ability.lower() == "levitate":
            return False
        
        # Air Balloon item is not grounded
        if pokemon.item and pokemon.item.lower() == "airballoon":
            return False
        
        return True
