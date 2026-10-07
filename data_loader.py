import os
import json
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
with open(DIRECTORY + '/champions-vgc-stats.json', 'r') as file:
    raw_vgc_data = json.load(file)
    POKEMON_VGC_DATA = raw_vgc_data.get('pokemon', raw_vgc_data)


fakeout_pokemon = []
tailwind_pokemon = []
trickroom_pokemon = []

for pokemon_name, data in POKEMON_VGC_DATA.items():
    
    moves = data.get("Moves", {})
    
    if "fakeout" in moves and pokemon_name.lower() not in fakeout_pokemon:
        fakeout_pokemon.append(pokemon_name.lower())
    if "tailwind" in moves and pokemon_name.lower() not in tailwind_pokemon:
        tailwind_pokemon.append(pokemon_name.lower())
    if "trickroom" in moves and pokemon_name.lower() not in trickroom_pokemon:
        trickroom_pokemon.append(pokemon_name.lower())
