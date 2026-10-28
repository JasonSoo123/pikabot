class SwitchingMixin:
    """Helper function to choose the best switch for a specific slot in the current battle"""
    def choose_best_switch(self, slot_index, battle, exclude_mon=None):
        """
        Choose the best switch for a slot.

        Args:
            slot_index: 0 for left, 1 for right
            battle: Current battle state
            exclude_mon: Either a Pokemon object or a species name (str) to exclude.
                        If str, excludes any Pokemon with that species name.
        """
        # Normalize exclude_mon to species name for comparison
        exclude_species = None
        if exclude_mon is not None:
            if isinstance(exclude_mon, str):
                exclude_species = exclude_mon.lower()
            else:
                # It's a Pokemon object
                exclude_species = exclude_mon.species.lower() if exclude_mon.species else None

        best_score = -float('inf')
        best_mon = None

        for pokemon in battle.available_switches[slot_index]:
            if pokemon.fainted or pokemon.current_hp_fraction == 0:
                continue

            # Exclude by species name (not object identity)
            if exclude_species and pokemon.species and pokemon.species.lower() == exclude_species:
                continue

            def_score, _, _ = self.calc_defensive_score(pokemon, battle)

            current_score = (pokemon.current_hp_fraction * 100) - def_score

            if current_score > best_score:
                best_score = current_score
                best_mon = pokemon

        if best_mon is None and battle.available_switches[slot_index]:
            for pokemon in battle.available_switches[slot_index]:
                if pokemon.fainted or pokemon.current_hp_fraction == 0:
                    continue
                if exclude_species and pokemon.species and pokemon.species.lower() == exclude_species:
                    continue
                return pokemon

        return best_mon
