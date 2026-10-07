import json
import time
import requests
import os
from bs4 import BeautifulSoup

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
with open(DIRECTORY + '/champions-vgc-stats.json', 'r') as file:
    raw_vgc_data = json.load(file)
    POKEMON_VGC_DATA = raw_vgc_data.get('pokemon', raw_vgc_data)
    
SUPPORT_ITEMS = ['Sitrus Berry', 'Leftovers', 'Light Clay', 'Mental Herb']

def get_pokemon_evs(pokemon, nature, item):
    
    if not POKEMON_VGC_DATA or not pokemon or not nature:
        return [0, 0, 0, 0, 0, 0]
    
    pokemon_entry = POKEMON_VGC_DATA.get(pokemon)
    
    if pokemon_entry is None:
        # Prints a warning so you know exactly which name mismatched
        print(f"Warning: '{pokemon}' not found in stats file. Defaulting to 0 EVs.")
        return [0, 0, 0, 0, 0, 0]
    
    spreads_dict = pokemon_entry.get('Spreads', {})
    
    matching_spreads = {}
    for spread_str, raw_count in spreads_dict.items():
        if ":" in spread_str:
            spread_nature, _ = spread_str.split(":", 1)
            if spread_nature.strip().lower() == nature.lower():
                matching_spreads[spread_str] = raw_count
                
    if not matching_spreads:
        return [0, 0, 0, 0, 0, 0]
    
    if item in SUPPORT_ITEMS:
        # Strategy A: Highest defensive bulk sum (HP + Def + SpD)
        best_spread_str = None
        max_defense_sum = -1
        
        for spread_str in matching_spreads.keys():
            _, ev_part = spread_str.split(":", 1)
            evs = [int(x) for x in ev_part.split("/")]
            
            # Sum mapping directly to: evs[0]=HP, evs[2]=Def, evs[4]=SpD
            defensive_sum = evs[0] + evs[2] + evs[4]
            
            if defensive_sum > max_defense_sum:
                max_defense_sum = defensive_sum
                best_spread_str = spread_str
    else:
        # Strategy B: Fallback directly to highest raw usage value
        best_spread_str = max(matching_spreads, key=matching_spreads.get)
        
    _, final_ev_string = best_spread_str.split(":", 1)
    return [int(x) for x in final_ev_string.split("/")]

def scrape_top_50_vgc():
    base_url = "https://limitlessvgc.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Step 1: Track pagination to collect exactly 50 team URLs
    team_links = []
    # 25 entries per page means we need page 1 and page 2
    for page_num in [1, 2]:
        page_url = f"{base_url}/teams?page={page_num}"
        print(f"Index Mapping: Collecting endpoints from page {page_num}...")
        
        try:
            res = requests.get(page_url, headers=headers, timeout=15)
            res.raise_for_status()
        except Exception as e:
            print(f"Could not read index page {page_num}: {e}")
            continue

        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table")
        if not table:
            continue

        for a_tag in table.find_all("a", href=True):
            href = a_tag["href"]
            # Save structural team links while avoiding duplication
            if "/teams/" in href and href not in team_links and href != "/teams":
                team_links.append(base_url + href)

    # Slice strictly to the top 50 matches 
    target_links = team_links[:50]
    print(f"Successfully mapped out structural links for top {len(target_links)} teams.")
    
    all_teams_json = []

    # Step 2: Traverse into each individual link sequentially
    for index, url in enumerate(target_links):
        print(f"[{index + 1}/50] Extraction Deep-Dive -> {url}")

        for attempt in range(3):
            try:
                team_res = requests.get(url, headers=headers, timeout=10)
                if team_res.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(2)
        else:
            print(f"Skipping link index {index + 1} due to network failure.")
            continue

        team_soup = BeautifulSoup(team_res.text, "html.parser")
        pokemon_containers = team_soup.find_all("div", class_="pkmn")
        
        if not pokemon_containers:
            continue

        structured_team = []
        for pkmn_box in pokemon_containers:
            # Name Extraction from structural node layout
            name_div = pkmn_box.find("div", class_="name")
            name = name_div.text.strip() if name_div else "Unknown"

            # Item Extraction
            item_div = pkmn_box.find("div", class_="item")
            item = item_div.text.strip() if item_div else ""

            # Ability Extraction (Clean out title tag noise)
            ability_div = pkmn_box.find("div", class_="ability")
            ability = ""
            if ability_div:
                ability = ability_div.text.replace("Ability:", "").strip()

            # Nature Extraction
            nature_div = pkmn_box.find("div", class_="nature")
            nature = ""
            if nature_div:
                nature = nature_div.text.replace("Nature", "").strip()

            # Moveset Array Unpacking
            moves_list = pkmn_box.find("ul", class_="moves")
            moves = []
            if moves_list:
                moves = [li.text.strip() for li in moves_list.find_all("li")]
            
            if name == 'Eternal Flower Floette':
                if item == "floettite":
                    name = 'Floette-Mega'
                else:
                    name = 'Floette-Eternal'
            elif name in item:
                name += '-Mega'
                if "Charizard" in name or "Mewtwo" in name or "Raichu" in name:
                    if item.endswith('Y'):
                        name += '-Y'
                    else:
                        name += '-X'
                elif "Absol" in name or "Lucario" in name or "Garchomp" in name:
                    if item.endswith('Z'):
                        name += '-Z'
            elif name == "Lycanroc Dusk":
                name = "Lycanroc-Dusk"
            elif "Rotom" in name:
                if "Wash" in name:
                    name = "Rotom-Wash"
                elif "Mow" in name:
                    name = "Rotom-Mow"
                elif "Heat" in name:
                    name = "Rotom-Heat"
                elif "Fan" in name:
                    name = "Rotom-Fan"
                elif "Frost" in name:
                    name = "Rotom-Frost"
            elif "Alolan" in name:
                name = name.split()[-1]
                name += '-Alola'
            elif "Galarian" in name:
                name = name.split()[-1]
                name += '-Galar'
            elif "Hisuian" in name:
                name = name.split()[-1]
                name += '-Hisui'
            elif "Paldean" in name:
                name = name.split()[-1]
                name += '-Paldea'
                if "Tauros" in name:
                    if "Aqua" in name:
                        name += '-Aqua'
                    else:
                        name += '-Blaze'
                        
            evs_array = get_pokemon_evs(pokemon=name, nature=nature, item=item)
            
            # Compile object properties
            pokemon_data = {
                "name": name,
                "item": item,
                "ability": ability,
                "nature": nature,
                "moves": moves,
                "evs" : evs_array
            }
            structured_team.append(pokemon_data)

        if structured_team:
            all_teams_json.append({"team": structured_team})

        # 1.5-second crawl delay prevents the host server from triggering anti-bot protections
        time.sleep(1.5)

    # Save finalized structured results array directly to a local file
    output_file = DIRECTORY + "/top-50-vgc-teams.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_teams_json, f, indent=2, ensure_ascii=False)

    print(f"\nCompleted! Generated {len(all_teams_json)} teams into '{output_file}'.")


if __name__ == "__main__":
    scrape_top_50_vgc()
