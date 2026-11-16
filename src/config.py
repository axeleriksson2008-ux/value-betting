"""Settings for live odds collection (phase 3). Edit here to change leagues/books/budget."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots"      # raw API responses (committed by GitHub Actions)
API_LOG = ROOT / "data" / "api_calls.csv"       # one line per API call (cost, credits left)
DB_PATH = ROOT / "data" / "odds.sqlite"         # built from snapshots, not committed
TEAM_MAP = ROOT / "config" / "team_names.csv"   # Odds API name -> football-data name (edit by hand)
CACHE_DIR = ROOT / "data" / "cache"              # cached event lists (free endpoint)
EVENTS_CACHE_HOURS = 6

API_HOST = "https://api.the-odds-api.com"

# The Odds API sport key -> football-data league code (None = no historical data for the model)
LEAGUES = {
    "soccer_epl": "E0",
    "soccer_efl_champ": "E1",
    "soccer_spain_la_liga": "SP1",
    "soccer_italy_serie_a": "I1",
    "soccer_germany_bundesliga": "D1",
    "soccer_france_ligue_one": "F1",
    "soccer_sweden_allsvenskan": "SWE",
    "soccer_sweden_superettan": None,
    "soccer_norway_eliteserien": "NOR",
    "soccer_denmark_superliga": "DNK",
}

# Max 10 bookmakers = 1 credit per market per call.
SHARP_BOOKS = ["pinnacle", "betfair_ex_eu"]
SWEDISH_BOOKS = ["svenskaspel_se", "unibet_se", "betsson", "nordicbet", "atg_se",
                 "leovegas_se", "expekt_se", "betmgm_se"]
BOOKMAKERS = SHARP_BOOKS + SWEDISH_BOOKS
assert len(BOOKMAKERS) <= 10, "more than 10 bookmakers doubles the cost"

MARKETS = ["h2h"]  # each extra market (e.g. "totals") costs one more credit per call

EXCHANGE_COMMISSION = {"betfair_ex_eu": 0.05}

# --- when to fetch (runs every hour) ---
EARLY_WINDOW_HOURS = 36      # take one "early" snapshot when a match is < 36 h away ...
EARLY_MIN_GAP_HOURS = 20     # ... and the league has no snapshot from the last 20 h
CLOSE_WINDOW_MINUTES = 75    # "closing" snapshot: last run before kick-off (cron is hourly)

# --- credit budget (free plan: 500 / month) ---
MONTHLY_CREDITS = 500
RESERVE_FOR_CLOSING = 60     # below this many credits left, only closing snapshots are taken
STOP_BELOW = 5               # below this, nothing is fetched

# --- staking ---
KELLY_FRACTION = 0.25
MAX_STAKE_SHARE = 0.02       # never more than 2 % of the bankroll on one bet
VALUE_THRESHOLD = 0.02       # list bets with value >= 2 % against Pinnacle's fair price
