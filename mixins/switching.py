class SwitchingMixin:
    """Helper function to choose the best switch for a specific slot in the current battle"""
    def choose_best_switch(self, slot_index, battle, exclude_mon=None):
        
        best_score = -float('inf')
        best_mon = None
        
        for pokemon in battle.available_switches[slot_index]:
            
            if pokemon.fainted or pokemon.current_hp_fraction == 0 or pokemon == exclude_mon:
                continue
            
            def_score, _, _ = self.calc_defensive_score(pokemon, battle)
            
            current_score = (pokemon.current_hp_fraction * 100) - def_score
            
            if current_score > best_score:
                best_score = current_score
                best_mon = pokemon
        
        if best_mon is None and battle.available_switches[slot_index]:
            for pokemon in battle.available_switches[slot_index]:
                if pokemon != exclude_mon and not pokemon.fainted:
                    return pokemon
        
        return best_mon
