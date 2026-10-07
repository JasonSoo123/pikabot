from poke_env.battle.side_condition import SideCondition
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field

class SpeedMixin:
    """Helper function to check which pokemon is faster """
    def isFaster(self, my_pokemon, opp_pokemon, battle):
        
        my_speed = self.get_stat(my_pokemon, "spe")
        opp_speed = self.get_stat(opp_pokemon, "spe")
        
        my_item = self.get_item(my_pokemon)
        opp_item = self.get_item(opp_pokemon)
        
        my_ability = self.get_ability(my_pokemon)
        opp_ability = self.get_ability(opp_pokemon)
        
        if my_item == "choicescarf":
            my_speed *= 1.5
        if opp_item == "choicescarf":
            opp_speed *= 1.5
        
        if SideCondition.TAILWIND in battle.side_conditions:
            my_speed *= 2
        if SideCondition.TAILWIND in battle.opponent_side_conditions:
            opp_speed *= 2
        
        if battle.weather == Weather.RAINDANCE:
            if my_ability == "swiftswim":
                my_speed *= 2
            if opp_ability == "swiftswim":
                opp_speed *= 2
        
        elif battle.weather == Weather.SUNNYDAY:
            if my_ability == "chlorophyll":
                my_speed *= 2
            if opp_ability == "chlorophyll":
                opp_speed *= 2
            
        elif battle.weather == Weather.SANDSTORM:
            if my_ability == "sandrush":
                my_speed *= 2
            if opp_ability == "sandrush":
                opp_speed *= 2
            
        elif battle.weather == Weather.SNOWSCAPE:
            if my_ability == "slushrush":
                my_speed *= 2
            if opp_ability == "slushrush":
                opp_speed *= 2
         
        if self.item_used and my_ability == "unburden":
            my_speed *= 2
        
        # Check for trickroom speed order reverses
        if Field.TRICK_ROOM in battle.fields:
            return my_speed < opp_speed
        else:
            return my_speed > opp_speed
