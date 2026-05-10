GTFS_FOLDER = "data/gtfs"

METRO_DEFAULT_SPEED_KMPH = 45.0
BUS_DEFAULT_SPEED_KMPH = 18.0

MAX_WALK_KM = 1.0
MAX_AUTO_CONNECTOR_KM = 5.0

MODE_SWITCH_TIME_MIN = 3.0
MODE_SWITCH_COST = 5.0

# Airport-specific configuration
AIRPORT_NODE_NAMES = [
    "Kempegowda International Airport (BLR)",
]

# Modes that are allowed to arrive directly at the airport terminal.
AIRPORT_RESTRICTED_FINAL_MODES = {"bus", "cab", "walk"}

