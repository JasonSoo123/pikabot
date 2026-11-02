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

Whimsicott @ Focus Sash
Ability: Prankster
Level: 50
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Encore
- Tailwind
- Moonblast
- Taunt

Kingambit @ Black Glasses
Ability: Defiant
Level: 50
EVs: 32 HP / 2 Atk / 32 SpA
Quiet Nature
- Brick Break
- Dark Pulse
- Foul Play
- Focus Blast

Rotom-Heat @ Leftovers
Ability: Levitate
Level: 50
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Will-O-Wisp
- Protect
- Thunderbolt
- Overheat

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

import json
import os

class Teams:
    """Container for VGC team loading and formatting."""

    @staticmethod
    def _pokemon_to_showdown(poke: dict) -> str:
        """Convert a single pokemon dict to a Showdown format block."""
        lines = []
        lines.append(f"{poke['name']} @ {poke['item']}")
        lines.append(f"Ability: {poke['ability']}")
        lines.append("Level: 50")
        evs = poke.get('evs', [])
        stat_labels = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']
        ev_parts = [f"{ev} {label}" for ev, label in zip(evs, stat_labels) if ev > 0]
        if ev_parts:
            lines.append("EVs: " + " / ".join(ev_parts))
        lines.append(f"{poke['nature']} Nature")
        for move in poke.get('moves', []):
            lines.append(f"- {move}")
        return "\n".join(lines)

    @classmethod
    def load_vgc_teams(cls):
        """Load and parse top-50-vgc-teams.json into a list of Showdown team strings."""
        base_dir = os.path.dirname(__file__)
        json_path = os.path.join(base_dir, 'top-50-vgc-teams.json')
        with open(json_path, 'r') as f:
            data = json.load(f)
        team_strings = []
        for entry in data:
            # each entry has a 'team' key with list of 6 pokemon dicts
            pokemon_blocks = [cls._pokemon_to_showdown(p) for p in entry.get('team', [])]
            team_str = "\n\n".join(pokemon_blocks) + "\n"
            team_strings.append(team_str)
        return team_strings

# Global list of 50 VGC teams in Showdown format
VGC_TEAMS_LIST = Teams.load_vgc_teams()
