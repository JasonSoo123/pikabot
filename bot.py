from poke_env.player import Player, RandomPlayer
from poke_env.player.battle_order import DoubleBattleOrder
from pikabot.mixins.opponent_tracker import OpponentTrackerMixin
from pikabot.mixins.pokemon_info import PokemonInfoMixin
from pikabot.mixins.speed import SpeedMixin
from pikabot.mixins.damage import DamageMixin
from pikabot.mixins.status_moves import StatusMoveMixin
from pikabot.mixins.ordering import OrderingMixin
from pikabot.mixins.switching import SwitchingMixin

class PikaBot(OpponentTrackerMixin, PokemonInfoMixin, SpeedMixin, DamageMixin, StatusMoveMixin, OrderingMixin, SwitchingMixin, Player):
    def __init__(self, *args, **kwargs):
        # This safely passes all configuration arguments (team, format, etc.) to the parent class
        super().__init__(*args, **kwargs)
        
        # Initialize opp team move pool attribute
        self.opp_team_movepool = {}
        self.mega = False
        self.protect_last_turn = [False, False]
        self.item_used = [False, False]
    def choose_move(self, battle):
    
        # Update clam bot data on opponnent
        self.update_opponent_knowledge(battle)
        
        # Light check for item used
        for index, pokemon in enumerate(battle.active_pokemon):
            if pokemon is not None and pokemon.item is None:
                self.item_used[index] = True
            else:
                self.item_used[index] = False
        
        # If there is a force switch
        if any(battle.force_switch):
            left_switch = None
            right_switch = None
            
            # Double forced switch
            if battle.force_switch[0] and battle.force_switch[1]:
                
                best_left_mon = self.choose_best_switch(0, battle)
                best_right_mon = self.choose_best_switch(1, battle, exclude_mon=best_left_mon)
                
                if best_left_mon:
                    left_switch = self.create_order(best_left_mon)
                if best_right_mon:
                    right_switch = self.create_order(best_right_mon)
                
                if left_switch and right_switch:
                    return DoubleBattleOrder(left_switch, right_switch)
                elif left_switch:
                    return left_switch
                elif right_switch:
                    return right_switch
            
            # Left forced switch    
            elif battle.force_switch[0]:
                best_left_mon = self.choose_best_switch(0, battle)
                if best_left_mon:
                    return self.create_order(best_left_mon)
            
            # Right forced switch
            elif battle.force_switch[1]:
                best_right_mon = self.choose_best_switch(1, battle)
                if best_right_mon:
                    return self.create_order(best_right_mon)
            
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
