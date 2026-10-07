from pikabot.data_loader import POKEMON_VGC_DATA

class OpponentTrackerMixin:
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
