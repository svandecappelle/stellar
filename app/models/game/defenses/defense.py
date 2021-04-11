from enum import Enum


class DefenseType(Enum):
    FlackCannon = {
        "name": "FlackCannon",
        "base_cost": {
            "mater": 3000,
            "credits": 50,
            "energy": 0,
            "population": 1
        },
        "integrity": 2000,
        "requirements": {}
    }
    MissileBattery = {
        "name": "MissileBattery",
        "base_cost": {
            "mater": 3500,
            "credits": 150,
            "energy": 0,
            "population": 2
        },
        "integrity": 2000,
        "requirements": {}
    }
    LaserArtillery = {
        "name": "LaserArtillery",
        "base_cost": {
            "mater": 2400,
            "credits": 600,
            "energy": 1,
            "population": 1
        },
        "integrity": 8000,
        "requirements": {
        	"technologies": {
        		"laser": 5
        	}
        }
    }
    IonArtillery = {
        "name": "IonArtillery",
        "base_cost": {
            "mater": 3500,
            "credits": 1000,
            "energy": 5,
            "population": 2
        },
        "integrity": 12000,
        "requirements": {
        	"technologies": {
        		"atom": 8
        	}
        }
    }
    Coilgun = {
        "name": "Coilgun",
        "base_cost": {
            "mater": 5000,
            "credits": 2000,
            "energy": 5,
            "population": 3
        },
        "integrity": 20000,
        "requirements": {
        	"technologies": {
        		"atom": 8,
        		"chemistry": 6
        	}
        }
    }
    Shield = {
    	"name": "Shield",
    	"base_cost": {
    		"mater": 10000,
    		"credits": 10000,
    		"energy": 100,
    		"population": 5
    	},
    	"integrity": 200000,
        "requirements": {
        	"technologies": {
        		"energy": 8
        	}
        }
    }

    def duration(self, factory):
    	return self.value["integrity"] / 2500 * (1 + factory.level)

    @property
    def cost(self):
        return self.value["base_cost"]
