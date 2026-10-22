import functools
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Paranoia Layer 1: Safely import pytz with fallback resilience
try:
    import pytz
except ImportError:
    pytz = None
    logger.warning("pytz is not installed; timezone validation will use fallback mode.")

# Paranoia Layer 0: Safely import Google's phonenumbers library
try:
    import phonenumbers
    from phonenumbers import timezone as phone_timezone
except ImportError:
    phonenumbers = None
    phone_timezone = None
    logger.warning("phonenumbers is not installed; phone timezone inference will use fallback table.")

# ---------------------------------------------------------------------------
# Paranoia Layer 0: Built-in Geography-to-IANA Reference Mappings
# ---------------------------------------------------------------------------

# Poison / Non-geographical locations to ignore
POISON_LOCATIONS = {
    "remote", "worldwide", "global", "anywhere", "earth", "virtual",
    "home", "wfh", "n/a", "unknown", "null", "none", "work from home",
    "hybrid", "flexible", "tbd", "unspecified", "internet", "online",
    "cyberspace", "na", "n.a.", "not specified", "undisclosed", "any",
    "everywhere", "distributed", "remote only", "fully remote", "remote - any",
    "work from anywhere", "wfa", "global remote", "remote worldwide", "worldwide remote",
    "remote global", "remote - us", "remote us", "remote, us", "remote usa", "remote - usa"
}

# Common legacy/abbreviated timezone aliases mapped to standard IANA
ABBREV_TO_IANA = {
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "akst": "America/Anchorage",
    "akdt": "America/Anchorage",
    "hst": "Pacific/Honolulu",
    "gmt": "UTC",
    "utc": "UTC",
    "ist": "Asia/Kolkata",
    "bst": "Europe/London",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
    "awst": "Australia/Perth",
    "acst": "Australia/Adelaide",
    "acdt": "Australia/Adelaide",
    "nzst": "Pacific/Auckland",
    "nzdt": "Pacific/Auckland",
    "sgt": "Asia/Singapore",
    "jst": "Asia/Tokyo",
    "kst": "Asia/Seoul",
    "hkt": "Asia/Hong_Kong",
    "asia/calcutta": "Asia/Kolkata",
    "us/pacific": "America/Los_Angeles",
    "us/eastern": "America/New_York",
    "us/central": "America/Chicago",
    "us/mountain": "America/Denver",
    "us/arizona": "America/Phoenix",
    "us/alaska": "America/Anchorage",
    "us/hawaii": "Pacific/Honolulu",
}

# US States & Territories (2-letter postal codes & full names)
US_STATES: Dict[str, str] = {
    # Eastern Time (America/New_York)
    "ct": "America/New_York", "connecticut": "America/New_York",
    "de": "America/New_York", "delaware": "America/New_York",
    "fl": "America/New_York", "florida": "America/New_York",
    "ga": "America/New_York", "georgia": "America/New_York",
    "in": "America/New_York", "indiana": "America/New_York",
    "me": "America/New_York", "maine": "America/New_York",
    "md": "America/New_York", "maryland": "America/New_York",
    "ma": "America/New_York", "massachusetts": "America/New_York",
    "mi": "America/New_York", "michigan": "America/New_York",
    "nh": "America/New_York", "new hampshire": "America/New_York",
    "nj": "America/New_York", "new jersey": "America/New_York",
    "ny": "America/New_York", "new york": "America/New_York",
    "nc": "America/New_York", "north carolina": "America/New_York",
    "oh": "America/New_York", "ohio": "America/New_York",
    "pa": "America/New_York", "pennsylvania": "America/New_York",
    "ri": "America/New_York", "rhode island": "America/New_York",
    "sc": "America/New_York", "south carolina": "America/New_York",
    "vt": "America/New_York", "vermont": "America/New_York",
    "va": "America/New_York", "virginia": "America/New_York",
    "dc": "America/New_York", "district of columbia": "America/New_York",
    "washington dc": "America/New_York", "washington d.c.": "America/New_York",
    "wv": "America/New_York", "west virginia": "America/New_York",

    # Central Time (America/Chicago)
    "al": "America/Chicago", "alabama": "America/Chicago",
    "ar": "America/Chicago", "arkansas": "America/Chicago",
    "il": "America/Chicago", "illinois": "America/Chicago",
    "ia": "America/Chicago", "iowa": "America/Chicago",
    "ks": "America/Chicago", "kansas": "America/Chicago",
    "ky": "America/Chicago", "kentucky": "America/Chicago",
    "la": "America/Chicago", "louisiana": "America/Chicago",
    "mn": "America/Chicago", "minnesota": "America/Chicago",
    "ms": "America/Chicago", "mississippi": "America/Chicago",
    "mo": "America/Chicago", "missouri": "America/Chicago",
    "ne": "America/Chicago", "nebraska": "America/Chicago",
    "nd": "America/Chicago", "north dakota": "America/Chicago",
    "ok": "America/Chicago", "oklahoma": "America/Chicago",
    "sd": "America/Chicago", "south dakota": "America/Chicago",
    "tn": "America/Chicago", "tennessee": "America/Chicago",
    "tx": "America/Chicago", "texas": "America/Chicago",
    "wi": "America/Chicago", "wisconsin": "America/Chicago",

    # Mountain Time (America/Denver)
    "co": "America/Denver", "colorado": "America/Denver",
    "id": "America/Denver", "idaho": "America/Denver",
    "mt": "America/Denver", "montana": "America/Denver",
    "nm": "America/Denver", "new mexico": "America/Denver",
    "ut": "America/Denver", "utah": "America/Denver",
    "wy": "America/Denver", "wyoming": "America/Denver",

    # Arizona (No DST -> America/Phoenix)
    "az": "America/Phoenix", "arizona": "America/Phoenix",

    # Pacific Time (America/Los_Angeles)
    "ca": "America/Los_Angeles", "california": "America/Los_Angeles",
    "nv": "America/Los_Angeles", "nevada": "America/Los_Angeles",
    "or": "America/Los_Angeles", "oregon": "America/Los_Angeles",
    "wa": "America/Los_Angeles", "washington": "America/Los_Angeles",

    # Alaska & Hawaii
    "ak": "America/Anchorage", "alaska": "America/Anchorage",
    "hi": "Pacific/Honolulu", "hawaii": "Pacific/Honolulu",

    # US Territories
    "pr": "America/Puerto_Rico", "puerto rico": "America/Puerto_Rico",
    "gu": "Pacific/Guam", "guam": "Pacific/Guam",
    "vi": "America/St_Thomas", "virgin islands": "America/St_Thomas", "u.s. virgin islands": "America/St_Thomas",
}

# Canadian Provinces & Territories
CANADIAN_PROVINCES: Dict[str, str] = {
    "on": "America/Toronto", "ontario": "America/Toronto",
    "bc": "America/Vancouver", "british columbia": "America/Vancouver",
    "qc": "America/Montreal", "quebec": "America/Montreal",
    "ab": "America/Edmonton", "alberta": "America/Edmonton",
    "mb": "America/Winnipeg", "manitoba": "America/Winnipeg",
    "sk": "America/Regina", "saskatchewan": "America/Regina",
    "ns": "America/Halifax", "nova scotia": "America/Halifax",
    "nb": "America/Moncton", "new brunswick": "America/Moncton",
    "nl": "America/St_Johns", "newfoundland": "America/St_Johns", "newfoundland and labrador": "America/St_Johns",
    "pe": "America/Halifax", "prince edward island": "America/Halifax", "pei": "America/Halifax",
    "yt": "America/Whitehorse", "yukon": "America/Whitehorse",
    "nt": "America/Yellowknife", "northwest territories": "America/Yellowknife",
    "nu": "America/Iqaluit", "nunavut": "America/Iqaluit",
}

# Australian States & Territories
AUSTRALIAN_STATES: Dict[str, str] = {
    "nsw": "Australia/Sydney", "new south wales": "Australia/Sydney",
    "vic": "Australia/Melbourne", "victoria": "Australia/Melbourne",
    "qld": "Australia/Brisbane", "queensland": "Australia/Brisbane",
    "wa": "Australia/Perth", "western australia": "Australia/Perth",
    "sa": "Australia/Adelaide", "south australia": "Australia/Adelaide",
    "tas": "Australia/Hobart", "tasmania": "Australia/Hobart",
    "act": "Australia/Sydney", "australian capital territory": "Australia/Sydney",
    "nt": "Australia/Darwin", "northern territory": "Australia/Darwin",
}

# Major Global Metropolitan Areas (150+ worldwide tech & commercial hubs)
GLOBAL_METRO_AREAS: Dict[str, str] = {
    # US West Coast
    "san francisco": "America/Los_Angeles", "sf": "America/Los_Angeles",
    "san francisco bay area": "America/Los_Angeles", "bay area": "America/Los_Angeles",
    "san jose": "America/Los_Angeles", "silicon valley": "America/Los_Angeles",
    "oakland": "America/Los_Angeles", "berkeley": "America/Los_Angeles",
    "palo alto": "America/Los_Angeles", "mountain view": "America/Los_Angeles",
    "sunnyvale": "America/Los_Angeles", "santa clara": "America/Los_Angeles",
    "redwood city": "America/Los_Angeles", "san mateo": "America/Los_Angeles",
    "fremont": "America/Los_Angeles", "sacramento": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "san diego": "America/Los_Angeles", "irvine": "America/Los_Angeles",
    "santa monica": "America/Los_Angeles", "pasadena": "America/Los_Angeles",
    "long beach": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "greater seattle area": "America/Los_Angeles", "bellevue": "America/Los_Angeles",
    "redmond": "America/Los_Angeles", "tacoma": "America/Los_Angeles",
    "portland": "America/Los_Angeles", "las vegas": "America/Los_Angeles",
    "reno": "America/Los_Angeles",

    # US Mountain
    "denver": "America/Denver", "greater denver area": "America/Denver",
    "boulder": "America/Denver", "colorado springs": "America/Denver",
    "salt lake city": "America/Denver", "slc": "America/Denver",
    "provo": "America/Denver", "boise": "America/Denver",
    "phoenix": "America/Phoenix", "scottsdale": "America/Phoenix",
    "tempe": "America/Phoenix", "tucson": "America/Phoenix",
    "albuquerque": "America/Denver", "santa fe": "America/Denver",

    # US Central / Texas / Midwest
    "chicago": "America/Chicago", "greater chicago area": "America/Chicago",
    "austin": "America/Chicago", "greater austin area": "America/Chicago",
    "dallas": "America/Chicago", "dallas-fort worth": "America/Chicago", "dfw": "America/Chicago",
    "fort worth": "America/Chicago", "houston": "America/Chicago",
    "greater houston area": "America/Chicago", "san antonio": "America/Chicago",
    "minneapolis": "America/Chicago", "saint paul": "America/Chicago", "twin cities": "America/Chicago",
    "milwaukee": "America/Chicago", "madison": "America/Chicago",
    "st. louis": "America/Chicago", "st louis": "America/Chicago", "saint louis": "America/Chicago",
    "kansas city": "America/Chicago", "nashville": "America/Chicago",
    "memphis": "America/Chicago", "new orleans": "America/Chicago",
    "oklahoma city": "America/Chicago", "tulsa": "America/Chicago",
    "omaha": "America/Chicago", "des moines": "America/Chicago",

    # US East Coast
    "new york": "America/New_York", "new york city": "America/New_York", "nyc": "America/New_York",
    "greater new york city area": "America/New_York", "manhattan": "America/New_York",
    "brooklyn": "America/New_York", "queens": "America/New_York", "bronx": "America/New_York",
    "staten island": "America/New_York", "jersey city": "America/New_York",
    "hoboken": "America/New_York", "newark": "America/New_York",
    "boston": "America/New_York", "greater boston area": "America/New_York",
    "cambridge": "America/New_York", "philadelphia": "America/New_York", "philly": "America/New_York",
    "pittsburgh": "America/New_York", "washington": "America/New_York",
    "baltimore": "America/New_York", "atlanta": "America/New_York",
    "greater atlanta area": "America/New_York", "miami": "America/New_York",
    "greater miami area": "America/New_York", "orlando": "America/New_York",
    "tampa": "America/New_York", "tampa bay": "America/New_York",
    "charlotte": "America/New_York", "raleigh": "America/New_York",
    "durham": "America/New_York", "research triangle": "America/New_York",
    "detroit": "America/New_York", "ann arbor": "America/New_York",
    "cleveland": "America/New_York", "columbus": "America/New_York",
    "cincinnati": "America/New_York", "indianapolis": "America/New_York",
    "richmond": "America/New_York", "buffalo": "America/New_York",
    "hartford": "America/New_York", "providence": "America/New_York",

    # Canada
    "toronto": "America/Toronto", "greater toronto area": "America/Toronto", "gta": "America/Toronto",
    "mississauga": "America/Toronto", "waterloo": "America/Toronto", "kitchener": "America/Toronto",
    "ottawa": "America/Toronto", "montreal": "America/Montreal",
    "quebec city": "America/Montreal", "vancouver": "America/Vancouver",
    "greater vancouver": "America/Vancouver", "victoria": "America/Vancouver",
    "calgary": "America/Edmonton", "edmonton": "America/Edmonton",
    "winnipeg": "America/Winnipeg", "halifax": "America/Halifax",

    # UK & Ireland
    "london": "Europe/London", "greater london": "Europe/London", "greater london area": "Europe/London",
    "manchester": "Europe/London", "greater manchester": "Europe/London",
    "birmingham": "Europe/London", "leeds": "Europe/London",
    "glasgow": "Europe/London", "edinburgh": "Europe/London",
    "bristol": "Europe/London", "oxford": "Europe/London",
    "cambridge uk": "Europe/London", "liverpool": "Europe/London",
    "sheffield": "Europe/London", "newcastle": "Europe/London",
    "nottingham": "Europe/London", "belfast": "Europe/London",
    "cardiff": "Europe/London", "dublin": "Europe/Dublin",
    "greater dublin": "Europe/Dublin", "cork": "Europe/Dublin",
    "galway": "Europe/Dublin", "limerick": "Europe/Dublin",

    # Western & Central Europe
    "paris": "Europe/Paris", "greater paris area": "Europe/Paris",
    "lyon": "Europe/Paris", "marseille": "Europe/Paris",
    "toulouse": "Europe/Paris", "nice": "Europe/Paris",
    "nantes": "Europe/Paris", "bordeaux": "Europe/Paris",
    "lille": "Europe/Paris", "strasbourg": "Europe/Paris",
    "berlin": "Europe/Berlin", "munich": "Europe/Berlin",
    "frankfurt": "Europe/Berlin", "hamburg": "Europe/Berlin",
    "cologne": "Europe/Berlin", "koln": "Europe/Berlin",
    "stuttgart": "Europe/Berlin", "dusseldorf": "Europe/Berlin",
    "düsseldorf": "Europe/Berlin", "leipzig": "Europe/Berlin",
    "dortmund": "Europe/Berlin", "bonn": "Europe/Berlin",
    "heidelberg": "Europe/Berlin", "nuremberg": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam", "greater amsterdam area": "Europe/Amsterdam",
    "rotterdam": "Europe/Amsterdam", "the hague": "Europe/Amsterdam",
    "den haag": "Europe/Amsterdam", "utrecht": "Europe/Amsterdam",
    "eindhoven": "Europe/Amsterdam", "brussels": "Europe/Brussels",
    "antwerp": "Europe/Brussels", "ghent": "Europe/Brussels",
    "madrid": "Europe/Madrid", "barcelona": "Europe/Madrid",
    "valencia": "Europe/Madrid", "seville": "Europe/Madrid",
    "bilbao": "Europe/Madrid", "malaga": "Europe/Madrid",
    "rome": "Europe/Rome", "milan": "Europe/Rome",
    "turin": "Europe/Rome", "naples": "Europe/Rome",
    "bologna": "Europe/Rome", "florence": "Europe/Rome",
    "zurich": "Europe/Zurich", "zürich": "Europe/Zurich",
    "geneva": "Europe/Zurich", "genève": "Europe/Zurich",
    "basel": "Europe/Zurich", "bern": "Europe/Zurich",
    "lausanne": "Europe/Zurich", "vienna": "Europe/Vienna",
    "wien": "Europe/Vienna", "salzburg": "Europe/Vienna",
    "graz": "Europe/Vienna", "linz": "Europe/Vienna",
    "lisbon": "Europe/Lisbon", "porto": "Europe/Lisbon",

    # Northern & Eastern Europe
    "stockholm": "Europe/Stockholm", "gothenburg": "Europe/Stockholm",
    "malmo": "Europe/Stockholm", "malmö": "Europe/Stockholm",
    "oslo": "Europe/Oslo", "bergen": "Europe/Oslo",
    "trondheim": "Europe/Oslo", "stavanger": "Europe/Oslo",
    "copenhagen": "Europe/Copenhagen", "aarhus": "Europe/Copenhagen",
    "helsinki": "Europe/Helsinki", "espoo": "Europe/Helsinki",
    "tampere": "Europe/Helsinki", "warsaw": "Europe/Warsaw",
    "krakow": "Europe/Warsaw", "kraków": "Europe/Warsaw",
    "wroclaw": "Europe/Warsaw", "wrocław": "Europe/Warsaw",
    "gdansk": "Europe/Warsaw", "gdańsk": "Europe/Warsaw",
    "poznan": "Europe/Warsaw", "poznań": "Europe/Warsaw",
    "prague": "Europe/Prague", "brno": "Europe/Prague",
    "budapest": "Europe/Budapest", "bucharest": "Europe/Bucharest",
    "cluj-napoca": "Europe/Bucharest", "cluj": "Europe/Bucharest",
    "timisoara": "Europe/Bucharest", "athens": "Europe/Athens",
    "tallinn": "Europe/Tallinn", "riga": "Europe/Riga",
    "vilnius": "Europe/Vilnius", "kyiv": "Europe/Kyiv", "kiev": "Europe/Kyiv",
    "lviv": "Europe/Kyiv", "zagreb": "Europe/Zagreb",
    "belgrade": "Europe/Belgrade", "sofia": "Europe/Sofia",
    "bratislava": "Europe/Bratislava", "ljubljana": "Europe/Ljubljana",
    "reykjavik": "Atlantic/Reykjavik",

    # Asia - India & South Asia
    "bengaluru": "Asia/Kolkata", "bangalore": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata", "bombay": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "new delhi": "Asia/Kolkata", "ncr": "Asia/Kolkata",
    "gurgaon": "Asia/Kolkata", "gurugram": "Asia/Kolkata",
    "noida": "Asia/Kolkata", "greater noida": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata", "chennai": "Asia/Kolkata", "madras": "Asia/Kolkata",
    "pune": "Asia/Kolkata", "kolkata": "Asia/Kolkata", "calcutta": "Asia/Kolkata",
    "ahmedabad": "Asia/Kolkata", "jaipur": "Asia/Kolkata",
    "kochi": "Asia/Kolkata", "cochin": "Asia/Kolkata",
    "thiruvananthapuram": "Asia/Kolkata", "trivandrum": "Asia/Kolkata",
    "chandigarh": "Asia/Kolkata", "indore": "Asia/Kolkata",
    "dhaka": "Asia/Dhaka", "chittagong": "Asia/Dhaka",
    "karachi": "Asia/Karachi", "lahore": "Asia/Karachi", "islamabad": "Asia/Karachi",
    "colombo": "Asia/Colombo", "kathmandu": "Asia/Kathmandu",

    # Asia - East & Southeast Asia
    "tokyo": "Asia/Tokyo", "greater tokyo": "Asia/Tokyo",
    "osaka": "Asia/Tokyo", "kyoto": "Asia/Tokyo",
    "yokohama": "Asia/Tokyo", "nagoya": "Asia/Tokyo",
    "fukuoka": "Asia/Tokyo", "sapporo": "Asia/Tokyo",
    "seoul": "Asia/Seoul", "incheon": "Asia/Seoul",
    "busan": "Asia/Seoul", "daegu": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong",
    "taipei": "Asia/Taipei", "hsinchu": "Asia/Taipei", "kaohsiung": "Asia/Taipei",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai",
    "shenzhen": "Asia/Shanghai", "guangzhou": "Asia/Shanghai",
    "hangzhou": "Asia/Shanghai", "chengdu": "Asia/Shanghai",
    "wuhan": "Asia/Shanghai", "nanjing": "Asia/Shanghai",
    "bangkok": "Asia/Bangkok", "chiang mai": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta", "surabaya": "Asia/Jakarta", "bali": "Asia/Makassar",
    "kuala lumpur": "Asia/Kuala_Lumpur", "kl": "Asia/Kuala_Lumpur",
    "penang": "Asia/Kuala_Lumpur", "cyberjaya": "Asia/Kuala_Lumpur", "petaling jaya": "Asia/Kuala_Lumpur",
    "manila": "Asia/Manila", "makati": "Asia/Manila", "taguig": "Asia/Manila",
    "cebu": "Asia/Manila", "davao": "Asia/Manila",
    "ho chi minh city": "Asia/Ho_Chi_Minh", "saigon": "Asia/Ho_Chi_Minh",
    "hanoi": "Asia/Ho_Chi_Minh", "da nang": "Asia/Ho_Chi_Minh",

    # Oceania
    "sydney": "Australia/Sydney", "greater sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "greater melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide", "canberra": "Australia/Sydney",
    "gold coast": "Australia/Brisbane", "hobart": "Australia/Hobart",
    "auckland": "Pacific/Auckland", "wellington": "Pacific/Auckland",
    "christchurch": "Pacific/Auckland",

    # Middle East & Turkey
    "dubai": "Asia/Dubai", "abu dhabi": "Asia/Dubai", "sharjah": "Asia/Dubai",
    "tel aviv": "Asia/Jerusalem", "jerusalem": "Asia/Jerusalem",
    "haifa": "Asia/Jerusalem", "herzliya": "Asia/Jerusalem",
    "riyadh": "Asia/Riyadh", "jeddah": "Asia/Riyadh",
    "dammam": "Asia/Riyadh", "khobar": "Asia/Riyadh",
    "doha": "Asia/Qatar", "kuwait city": "Asia/Kuwait",
    "manama": "Asia/Bahrain", "muscat": "Asia/Muscat",
    "amman": "Asia/Amman", "beirut": "Asia/Beirut",
    "istanbul": "Europe/Istanbul", "ankara": "Europe/Istanbul", "izmir": "Europe/Istanbul",

    # Latin America
    "sao paulo": "America/Sao_Paulo", "são paulo": "America/Sao_Paulo",
    "rio de janeiro": "America/Sao_Paulo", "rio": "America/Sao_Paulo",
    "brasilia": "America/Sao_Paulo", "brasília": "America/Sao_Paulo",
    "belo horizonte": "America/Sao_Paulo", "curitiba": "America/Sao_Paulo",
    "porto alegre": "America/Sao_Paulo", "florianopolis": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "cordoba": "America/Argentina/Cordoba", "rosario": "America/Argentina/Buenos_Aires",
    "santiago": "America/Santiago", "valparaiso": "America/Santiago",
    "bogota": "America/Bogota", "bogotá": "America/Bogota",
    "medellin": "America/Bogota", "medellín": "America/Bogota",
    "cali": "America/Bogota", "lima": "America/Lima",
    "mexico city": "America/Mexico_City", "cdmx": "America/Mexico_City",
    "guadalajara": "America/Mexico_City", "monterrey": "America/Monterrey",
    "panama city": "America/Panama", "san juan": "America/Puerto_Rico",
    "montevideo": "America/Montevideo", "caracas": "America/Caracas",

    # Africa
    "cairo": "Africa/Cairo", "alexandria": "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg", "cape town": "Africa/Johannesburg",
    "durban": "Africa/Johannesburg", "pretoria": "Africa/Johannesburg",
    "nairobi": "Africa/Nairobi", "mombasa": "Africa/Nairobi",
    "lagos": "Africa/Lagos", "abuja": "Africa/Lagos",
    "accra": "Africa/Accra", "casablanca": "Africa/Casablanca",
    "rabat": "Africa/Casablanca", "addis ababa": "Africa/Addis_Ababa",
    "kigali": "Africa/Kigali", "kampala": "Africa/Kampala",
    "dar es salaam": "Africa/Dar_es_Salaam", "tunis": "Africa/Tunis",
}

# Country Names & ISO-2/ISO-3 Codes to Default National Timezones
COUNTRIES: Dict[str, str] = {
    # North America
    "united states": "America/New_York", "us": "America/New_York", "usa": "America/New_York",
    "united states of america": "America/New_York", "u.s.": "America/New_York", "u.s.a.": "America/New_York",
    "canada": "America/Toronto", "ca": "America/Toronto", "can": "America/Toronto",
    "mexico": "America/Mexico_City", "mx": "America/Mexico_City", "mex": "America/Mexico_City",

    # Europe
    "united kingdom": "Europe/London", "uk": "Europe/London", "gb": "Europe/London", "gbr": "Europe/London",
    "great britain": "Europe/London", "england": "Europe/London", "scotland": "Europe/London", "wales": "Europe/London",
    "germany": "Europe/Berlin", "de": "Europe/Berlin", "deu": "Europe/Berlin", "deutschland": "Europe/Berlin",
    "france": "Europe/Paris", "fr": "Europe/Paris", "fra": "Europe/Paris",
    "ireland": "Europe/Dublin", "ie": "Europe/Dublin", "irl": "Europe/Dublin",
    "netherlands": "Europe/Amsterdam", "nl": "Europe/Amsterdam", "nld": "Europe/Amsterdam", "holland": "Europe/Amsterdam",
    "switzerland": "Europe/Zurich", "ch": "Europe/Zurich", "che": "Europe/Zurich",
    "spain": "Europe/Madrid", "es": "Europe/Madrid", "esp": "Europe/Madrid", "españa": "Europe/Madrid",
    "italy": "Europe/Rome", "it": "Europe/Rome", "ita": "Europe/Rome", "italia": "Europe/Rome",
    "sweden": "Europe/Stockholm", "se": "Europe/Stockholm", "swe": "Europe/Stockholm", "sverige": "Europe/Stockholm",
    "norway": "Europe/Oslo", "no": "Europe/Oslo", "nor": "Europe/Oslo", "norge": "Europe/Oslo",
    "denmark": "Europe/Copenhagen", "dk": "Europe/Copenhagen", "dnk": "Europe/Copenhagen", "danmark": "Europe/Copenhagen",
    "finland": "Europe/Helsinki", "fi": "Europe/Helsinki", "fin": "Europe/Helsinki", "suomi": "Europe/Helsinki",
    "poland": "Europe/Warsaw", "pl": "Europe/Warsaw", "pol": "Europe/Warsaw", "polska": "Europe/Warsaw",
    "austria": "Europe/Vienna", "at": "Europe/Vienna", "aut": "Europe/Vienna", "österreich": "Europe/Vienna",
    "belgium": "Europe/Brussels", "be": "Europe/Brussels", "bel": "Europe/Brussels", "belgique": "Europe/Brussels",
    "portugal": "Europe/Lisbon", "pt": "Europe/Lisbon", "prt": "Europe/Lisbon",
    "czech republic": "Europe/Prague", "czechia": "Europe/Prague", "cz": "Europe/Prague", "cze": "Europe/Prague",
    "hungary": "Europe/Budapest", "hu": "Europe/Budapest", "hun": "Europe/Budapest",
    "romania": "Europe/Bucharest", "ro": "Europe/Bucharest", "rou": "Europe/Bucharest",
    "greece": "Europe/Athens", "gr": "Europe/Athens", "grc": "Europe/Athens",
    "turkey": "Europe/Istanbul", "turkiye": "Europe/Istanbul", "türkiye": "Europe/Istanbul", "tr": "Europe/Istanbul", "tur": "Europe/Istanbul",
    "estonia": "Europe/Tallinn", "ee": "Europe/Tallinn", "est": "Europe/Tallinn",
    "latvia": "Europe/Riga", "lv": "Europe/Riga", "lva": "Europe/Riga",
    "lithuania": "Europe/Vilnius", "lt": "Europe/Vilnius", "ltu": "Europe/Vilnius",
    "ukraine": "Europe/Kyiv", "ua": "Europe/Kyiv", "ukr": "Europe/Kyiv",
    "croatia": "Europe/Zagreb", "hr": "Europe/Zagreb", "hrv": "Europe/Zagreb",
    "serbia": "Europe/Belgrade", "rs": "Europe/Belgrade", "srb": "Europe/Belgrade",
    "slovakia": "Europe/Bratislava", "sk": "Europe/Bratislava", "svk": "Europe/Bratislava",
    "slovenia": "Europe/Ljubljana", "si": "Europe/Ljubljana", "svn": "Europe/Ljubljana",
    "bulgaria": "Europe/Sofia", "bg": "Europe/Sofia", "bgr": "Europe/Sofia",
    "luxembourg": "Europe/Luxembourg", "lu": "Europe/Luxembourg", "lux": "Europe/Luxembourg",
    "iceland": "Atlantic/Reykjavik", "is": "Atlantic/Reykjavik", "isl": "Atlantic/Reykjavik",
    "malta": "Europe/Malta", "mt": "Europe/Malta", "mlt": "Europe/Malta",
    "cyprus": "Asia/Nicosia", "cy": "Asia/Nicosia", "cyp": "Asia/Nicosia",

    # Asia & Pacific
    "india": "Asia/Kolkata", "in": "Asia/Kolkata", "ind": "Asia/Kolkata", "bharat": "Asia/Kolkata",
    "australia": "Australia/Sydney", "au": "Australia/Sydney", "aus": "Australia/Sydney",
    "japan": "Asia/Tokyo", "jp": "Asia/Tokyo", "jpn": "Asia/Tokyo", "nippon": "Asia/Tokyo",
    "singapore": "Asia/Singapore", "sg": "Asia/Singapore", "sgp": "Asia/Singapore",
    "south korea": "Asia/Seoul", "korea": "Asia/Seoul", "kr": "Asia/Seoul", "kor": "Asia/Seoul", "republic of korea": "Asia/Seoul",
    "china": "Asia/Shanghai", "cn": "Asia/Shanghai", "chn": "Asia/Shanghai", "prc": "Asia/Shanghai",
    "taiwan": "Asia/Taipei", "tw": "Asia/Taipei", "twn": "Asia/Taipei",
    "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong", "hkg": "Asia/Hong_Kong",
    "new zealand": "Pacific/Auckland", "nz": "Pacific/Auckland", "nzl": "Pacific/Auckland",
    "indonesia": "Asia/Jakarta", "id": "Asia/Jakarta", "idn": "Asia/Jakarta",
    "malaysia": "Asia/Kuala_Lumpur", "my": "Asia/Kuala_Lumpur", "mys": "Asia/Kuala_Lumpur",
    "philippines": "Asia/Manila", "ph": "Asia/Manila", "phl": "Asia/Manila",
    "thailand": "Asia/Bangkok", "th": "Asia/Bangkok", "tha": "Asia/Bangkok",
    "vietnam": "Asia/Ho_Chi_Minh", "vn": "Asia/Ho_Chi_Minh", "vnm": "Asia/Ho_Chi_Minh", "viet nam": "Asia/Ho_Chi_Minh",
    "pakistan": "Asia/Karachi", "pk": "Asia/Karachi", "pak": "Asia/Karachi",
    "bangladesh": "Asia/Dhaka", "bd": "Asia/Dhaka", "bgd": "Asia/Dhaka",
    "sri lanka": "Asia/Colombo", "lk": "Asia/Colombo", "lka": "Asia/Colombo",
    "nepal": "Asia/Kathmandu", "np": "Asia/Kathmandu", "npl": "Asia/Kathmandu",

    # Middle East
    "israel": "Asia/Jerusalem", "il": "Asia/Jerusalem", "isr": "Asia/Jerusalem",
    "united arab emirates": "Asia/Dubai", "uae": "Asia/Dubai", "ae": "Asia/Dubai", "are": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh", "sa": "Asia/Riyadh", "sau": "Asia/Riyadh",
    "qatar": "Asia/Qatar", "qa": "Asia/Qatar", "qat": "Asia/Qatar",
    "kuwait": "Asia/Kuwait", "kw": "Asia/Kuwait", "kwt": "Asia/Kuwait",
    "bahrain": "Asia/Bahrain", "bh": "Asia/Bahrain", "bhr": "Asia/Bahrain",
    "oman": "Asia/Muscat", "om": "Asia/Muscat", "omn": "Asia/Muscat",
    "jordan": "Asia/Amman", "jo": "Asia/Amman", "jor": "Asia/Amman",
    "lebanon": "Asia/Beirut", "lb": "Asia/Beirut", "lbn": "Asia/Beirut",

    # Latin America
    "brazil": "America/Sao_Paulo", "br": "America/Sao_Paulo", "bra": "America/Sao_Paulo", "brasil": "America/Sao_Paulo",
    "argentina": "America/Argentina/Buenos_Aires", "ar": "America/Argentina/Buenos_Aires", "arg": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago", "cl": "America/Santiago", "chl": "America/Santiago",
    "colombia": "America/Bogota", "co": "America/Bogota", "col": "America/Bogota",
    "peru": "America/Lima", "pe": "America/Lima", "per": "America/Lima",
    "panama": "America/Panama", "pa": "America/Panama", "pan": "America/Panama",
    "costa rica": "America/Costa_Rica", "cr": "America/Costa_Rica", "cri": "America/Costa_Rica",
    "uruguay": "America/Montevideo", "uy": "America/Montevideo", "ury": "America/Montevideo",
    "venezuela": "America/Caracas", "ve": "America/Caracas", "ven": "America/Caracas",
    "puerto rico": "America/Puerto_Rico", "pr": "America/Puerto_Rico", "pri": "America/Puerto_Rico",

    # Africa
    "south africa": "Africa/Johannesburg", "za": "Africa/Johannesburg", "zaf": "Africa/Johannesburg",
    "nigeria": "Africa/Lagos", "ng": "Africa/Lagos", "nga": "Africa/Lagos",
    "kenya": "Africa/Nairobi", "ke": "Africa/Nairobi", "ken": "Africa/Nairobi",
    "egypt": "Africa/Cairo", "eg": "Africa/Cairo", "egy": "Africa/Cairo",
    "ghana": "Africa/Accra", "gh": "Africa/Accra", "gha": "Africa/Accra",
    "morocco": "Africa/Casablanca", "ma": "Africa/Casablanca", "mar": "Africa/Casablanca",
    "ethiopia": "Africa/Addis_Ababa", "et": "Africa/Addis_Ababa", "eth": "Africa/Addis_Ababa",
    "rwanda": "Africa/Kigali", "rw": "Africa/Kigali", "rwa": "Africa/Kigali",
    "uganda": "Africa/Kampala", "ug": "Africa/Kampala", "uga": "Africa/Kampala",
    "tanzania": "Africa/Dar_es_Salaam", "tz": "Africa/Dar_es_Salaam", "tza": "Africa/Dar_es_Salaam",
    "tunisia": "Africa/Tunis", "tn": "Africa/Tunis", "tun": "Africa/Tunis",
}

# International Phone Dial Codes (sorted descending by length of prefix)
PHONE_DIAL_CODES: List[Tuple[str, str]] = [
    # 4-digit prefixes (+1xxx area codes or specific territories)
    ("+1340", "America/St_Thomas"),   # US Virgin Islands
    ("+1787", "America/Puerto_Rico"), # Puerto Rico
    ("+1939", "America/Puerto_Rico"), # Puerto Rico
    ("+1671", "Pacific/Guam"),        # Guam

    # 3-digit prefixes
    ("+971", "Asia/Dubai"),           # UAE
    ("+972", "Asia/Jerusalem"),       # Israel
    ("+974", "Asia/Qatar"),           # Qatar
    ("+966", "Asia/Riyadh"),          # Saudi Arabia
    ("+965", "Asia/Kuwait"),          # Kuwait
    ("+973", "Asia/Bahrain"),         # Bahrain
    ("+968", "Asia/Muscat"),          # Oman
    ("+962", "Asia/Amman"),           # Jordan
    ("+961", "Asia/Beirut"),          # Lebanon
    ("+353", "Europe/Dublin"),        # Ireland
    ("+358", "Europe/Helsinki"),      # Finland
    ("+351", "Europe/Lisbon"),        # Portugal
    ("+352", "Europe/Luxembourg"),    # Luxembourg
    ("+354", "Atlantic/Reykjavik"),   # Iceland
    ("+356", "Europe/Malta"),         # Malta
    ("+357", "Asia/Nicosia"),         # Cyprus
    ("+420", "Europe/Prague"),        # Czechia
    ("+421", "Europe/Bratislava"),    # Slovakia
    ("+380", "Europe/Kyiv"),          # Ukraine
    ("+385", "Europe/Zagreb"),        # Croatia
    ("+381", "Europe/Belgrade"),      # Serbia
    ("+386", "Europe/Ljubljana"),     # Slovenia
    ("+359", "Europe/Sofia"),         # Bulgaria
    ("+372", "Europe/Tallinn"),       # Estonia
    ("+371", "Europe/Riga"),          # Latvia
    ("+370", "Europe/Vilnius"),       # Lithuania
    ("+886", "Asia/Taipei"),          # Taiwan
    ("+852", "Asia/Hong_Kong"),       # Hong Kong
    ("+880", "Asia/Dhaka"),           # Bangladesh
    ("+977", "Asia/Kathmandu"),       # Nepal
    ("+234", "Africa/Lagos"),         # Nigeria
    ("+254", "Africa/Nairobi"),       # Kenya
    ("+250", "Africa/Kigali"),        # Rwanda
    ("+256", "Africa/Kampala"),       # Uganda
    ("+255", "Africa/Dar_es_Salaam"), # Tanzania
    ("+212", "Africa/Casablanca"),    # Morocco
    ("+216", "Africa/Tunis"),         # Tunisia
    ("+251", "Africa/Addis_Ababa"),   # Ethiopia
    ("+233", "Africa/Accra"),         # Ghana
    ("+507", "America/Panama"),       # Panama
    ("+506", "America/Costa_Rica"),   # Costa Rica
    ("+598", "America/Montevideo"),   # Uruguay

    # 2-digit prefixes
    ("+44", "Europe/London"),         # UK
    ("+49", "Europe/Berlin"),         # Germany
    ("+33", "Europe/Paris"),          # France
    ("+31", "Europe/Amsterdam"),      # Netherlands
    ("+32", "Europe/Brussels"),       # Belgium
    ("+34", "Europe/Madrid"),         # Spain
    ("+39", "Europe/Rome"),           # Italy
    ("+41", "Europe/Zurich"),         # Switzerland
    ("+43", "Europe/Vienna"),         # Austria
    ("+46", "Europe/Stockholm"),      # Sweden
    ("+47", "Europe/Oslo"),           # Norway
    ("+45", "Europe/Copenhagen"),     # Denmark
    ("+48", "Europe/Warsaw"),         # Poland
    ("+36", "Europe/Budapest"),       # Hungary
    ("+40", "Europe/Bucharest"),      # Romania
    ("+30", "Europe/Athens"),         # Greece
    ("+90", "Europe/Istanbul"),       # Turkey
    ("+91", "Asia/Kolkata"),          # India
    ("+61", "Australia/Sydney"),      # Australia
    ("+81", "Asia/Tokyo"),            # Japan
    ("+82", "Asia/Seoul"),            # South Korea
    ("+65", "Asia/Singapore"),        # Singapore
    ("+86", "Asia/Shanghai"),         # China
    ("+64", "Pacific/Auckland"),      # New Zealand
    ("+62", "Asia/Jakarta"),          # Indonesia
    ("+60", "Asia/Kuala_Lumpur"),     # Malaysia
    ("+63", "Asia/Manila"),           # Philippines
    ("+66", "Asia/Bangkok"),          # Thailand
    ("+84", "Asia/Ho_Chi_Minh"),      # Vietnam
    ("+92", "Asia/Karachi"),          # Pakistan
    ("+94", "Asia/Colombo"),          # Sri Lanka
    ("+55", "America/Sao_Paulo"),     # Brazil
    ("+52", "America/Mexico_City"),   # Mexico
    ("+54", "America/Argentina/Buenos_Aires"), # Argentina
    ("+56", "America/Santiago"),      # Chile
    ("+57", "America/Bogota"),        # Colombia
    ("+51", "America/Lima"),          # Peru
    ("+58", "America/Caracas"),       # Venezuela
    ("+27", "Africa/Johannesburg"),   # South Africa
    ("+20", "Africa/Cairo"),          # Egypt

    # 1-digit prefix
    ("+1", "America/New_York"),       # US / Canada default
]

# ---------------------------------------------------------------------------
# Country Name & Alias to ISO 3166-1 alpha-2 Region Codes (for phone parsing)
# ---------------------------------------------------------------------------
COUNTRY_TO_ISO2: Dict[str, str] = {
    # North America
    "united states": "US", "us": "US", "usa": "US", "united states of america": "US", "u.s.": "US", "u.s.a.": "US",
    "canada": "CA", "ca": "CA", "can": "CA",
    "mexico": "MX", "mx": "MX", "mex": "MX",

    # Europe
    "united kingdom": "GB", "uk": "GB", "gb": "GB", "gbr": "GB", "great britain": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "germany": "DE", "de": "DE", "deu": "DE", "deutschland": "DE",
    "france": "FR", "fr": "FR", "fra": "FR",
    "ireland": "IE", "ie": "IE", "irl": "IE",
    "netherlands": "NL", "nl": "NL", "nld": "NL", "holland": "NL",
    "switzerland": "CH", "ch": "CH", "che": "CH",
    "spain": "ES", "es": "ES", "esp": "ES", "españa": "ES",
    "italy": "IT", "it": "IT", "ita": "IT", "italia": "IT",
    "sweden": "SE", "se": "SE", "swe": "SE", "sverige": "SE",
    "norway": "NO", "no": "NO", "nor": "NO", "norge": "NO",
    "denmark": "DK", "dk": "DK", "dnk": "DK", "danmark": "DK",
    "finland": "FI", "fi": "FI", "fin": "FI", "suomi": "FI",
    "poland": "PL", "pl": "PL", "pol": "PL", "polska": "PL",
    "austria": "AT", "at": "AT", "aut": "AT", "österreich": "AT",
    "belgium": "BE", "be": "BE", "bel": "BE", "belgique": "BE",
    "portugal": "PT", "pt": "PT", "prt": "PT",
    "czech republic": "CZ", "czechia": "CZ", "cz": "CZ", "cze": "CZ",
    "hungary": "HU", "hu": "HU", "hun": "HU",
    "romania": "RO", "ro": "RO", "rou": "RO",
    "greece": "GR", "gr": "GR", "grc": "GR",
    "turkey": "TR", "turkiye": "TR", "türkiye": "TR", "tr": "TR", "tur": "TR",
    "estonia": "EE", "ee": "EE", "est": "EE",
    "latvia": "LV", "lv": "LV", "lva": "LV",
    "lithuania": "LT", "lt": "LT", "ltu": "LT",
    "ukraine": "UA", "ua": "UA", "ukr": "UA",
    "croatia": "HR", "hr": "HR", "hrv": "HR",
    "serbia": "RS", "rs": "RS", "srb": "RS",
    "slovakia": "SK", "sk": "SK", "svk": "SK",
    "slovenia": "SI", "si": "SI", "svn": "SI",
    "bulgaria": "BG", "bg": "BG", "bgr": "BG",
    "luxembourg": "LU", "lu": "LU", "lux": "LU",
    "iceland": "IS", "is": "IS", "isl": "IS",
    "malta": "MT", "mt": "MT", "mlt": "MT",
    "cyprus": "CY", "cy": "CY", "cyp": "CY",

    # Asia & Pacific
    "india": "IN", "in": "IN", "ind": "IN", "bharat": "IN",
    "australia": "AU", "au": "AU", "aus": "AU",
    "japan": "JP", "jp": "JP", "jpn": "JP", "nippon": "JP",
    "singapore": "SG", "sg": "SG", "sgp": "SG",
    "south korea": "KR", "korea": "KR", "kr": "KR", "kor": "KR",
    "china": "CN", "cn": "CN", "chn": "CN",
    "taiwan": "TW", "tw": "TW", "twn": "TW",
    "hong kong": "HK", "hk": "HK", "hkg": "HK",
    "new zealand": "NZ", "nz": "NZ", "nzl": "NZ",
    "indonesia": "ID", "id": "ID", "idn": "ID",
    "malaysia": "MY", "my": "MY", "mys": "MY",
    "philippines": "PH", "ph": "PH", "phl": "PH",
    "thailand": "TH", "th": "TH", "tha": "TH",
    "vietnam": "VN", "vn": "VN", "vnm": "VN",
    "pakistan": "PK", "pk": "PK", "pak": "PK",
    "bangladesh": "BD", "bd": "BD", "bgd": "BD",
    "sri lanka": "LK", "lk": "LK", "lka": "LK",
    "nepal": "NP", "np": "NP", "npl": "NP",

    # Middle East
    "israel": "IL", "il": "IL", "isr": "IL",
    "united arab emirates": "AE", "uae": "AE", "ae": "AE", "are": "AE",
    "saudi arabia": "SA", "sa": "SA", "sau": "SA",
    "qatar": "QA", "qa": "QA", "qat": "QA",
    "kuwait": "KW", "kw": "KW", "kwt": "KW",
    "bahrain": "BH", "bh": "BH", "bhr": "BH",
    "oman": "OM", "om": "OM", "omn": "OM",
    "jordan": "JO", "jo": "JO", "jor": "JO",
    "lebanon": "LB", "lb": "LB", "lbn": "LB",

    # Latin America
    "brazil": "BR", "br": "BR", "bra": "BR", "brasil": "BR",
    "argentina": "AR", "ar": "AR", "arg": "AR",
    "chile": "CL", "cl": "CL", "chl": "CL",
    "colombia": "CO", "co": "CO", "col": "CO",
    "peru": "PE", "pe": "PE", "per": "PE",
    "panama": "PA", "pa": "PA", "pan": "PA",
    "costa rica": "CR", "cr": "CR", "cri": "CR",
    "uruguay": "UY", "uy": "UY", "ury": "UY",
    "venezuela": "VE", "ve": "VE", "ven": "VE",
    "puerto rico": "PR", "pr": "PR", "pri": "PR",

    # Africa
    "south africa": "ZA", "za": "ZA", "zaf": "ZA",
    "nigeria": "NG", "ng": "NG", "nga": "NG",
    "kenya": "KE", "ke": "KE", "ken": "KE",
    "egypt": "EG", "eg": "EG", "egy": "EG",
    "ghana": "GH", "gh": "GH", "gha": "GH",
    "morocco": "MA", "ma": "MA", "mar": "MA",
    "ethiopia": "ET", "et": "ET", "eth": "ET",
    "rwanda": "RW", "rw": "RW", "rwa": "RW",
    "uganda": "UG", "ug": "UG", "uga": "UG",
    "tanzania": "TZ", "tz": "TZ", "tza": "TZ",
    "tunisia": "TN", "tn": "TN", "tun": "TN",
}

# ---------------------------------------------------------------------------
# Fallback North American Numbering Plan (NANP) 3-digit Area Code Mappings
# Used when phonenumbers library is missing or fails on an area code lookup.
# ---------------------------------------------------------------------------
NANP_AREA_CODES: Dict[str, str] = {
    # Pacific Time (America/Los_Angeles)
    "206": "America/Los_Angeles", "209": "America/Los_Angeles", "213": "America/Los_Angeles",
    "253": "America/Los_Angeles", "310": "America/Los_Angeles", "323": "America/Los_Angeles",
    "360": "America/Los_Angeles", "408": "America/Los_Angeles", "415": "America/Los_Angeles",
    "425": "America/Los_Angeles", "442": "America/Los_Angeles", "503": "America/Los_Angeles",
    "509": "America/Los_Angeles", "510": "America/Los_Angeles", "530": "America/Los_Angeles",
    "541": "America/Los_Angeles", "559": "America/Los_Angeles", "562": "America/Los_Angeles",
    "564": "America/Los_Angeles", "619": "America/Los_Angeles", "626": "America/Los_Angeles",
    "628": "America/Los_Angeles", "650": "America/Los_Angeles", "657": "America/Los_Angeles",
    "661": "America/Los_Angeles", "669": "America/Los_Angeles", "702": "America/Los_Angeles",
    "707": "America/Los_Angeles", "714": "America/Los_Angeles", "725": "America/Los_Angeles",
    "747": "America/Los_Angeles", "760": "America/Los_Angeles", "775": "America/Los_Angeles",
    "805": "America/Los_Angeles", "818": "America/Los_Angeles", "820": "America/Los_Angeles",
    "831": "America/Los_Angeles", "840": "America/Los_Angeles", "858": "America/Los_Angeles",
    "909": "America/Los_Angeles", "916": "America/Los_Angeles", "925": "America/Los_Angeles",
    "949": "America/Los_Angeles", "951": "America/Los_Angeles", "971": "America/Los_Angeles",
    # Canadian Pacific (America/Vancouver)
    "604": "America/Vancouver", "778": "America/Vancouver", "236": "America/Vancouver",
    "672": "America/Vancouver", "250": "America/Vancouver",

    # Mountain Time (America/Denver)
    "303": "America/Denver", "307": "America/Denver", "385": "America/Denver",
    "406": "America/Denver", "435": "America/Denver", "505": "America/Denver",
    "575": "America/Denver", "719": "America/Denver", "720": "America/Denver",
    "801": "America/Denver", "970": "America/Denver",
    # Canadian Mountain (America/Edmonton)
    "403": "America/Edmonton", "587": "America/Edmonton", "825": "America/Edmonton", "780": "America/Edmonton",

    # Arizona Time - No DST (America/Phoenix)
    "480": "America/Phoenix", "520": "America/Phoenix", "602": "America/Phoenix",
    "623": "America/Phoenix", "928": "America/Phoenix",

    # Central Time (America/Chicago)
    "205": "America/Chicago", "210": "America/Chicago", "214": "America/Chicago",
    "217": "America/Chicago", "218": "America/Chicago", "224": "America/Chicago",
    "225": "America/Chicago", "251": "America/Chicago", "254": "America/Chicago",
    "256": "America/Chicago", "262": "America/Chicago", "281": "America/Chicago",
    "308": "America/Chicago", "309": "America/Chicago", "312": "America/Chicago",
    "314": "America/Chicago", "316": "America/Chicago", "318": "America/Chicago",
    "319": "America/Chicago", "320": "America/Chicago", "325": "America/Chicago",
    "331": "America/Chicago", "334": "America/Chicago", "346": "America/Chicago",
    "361": "America/Chicago", "402": "America/Chicago", "405": "America/Chicago",
    "409": "America/Chicago", "414": "America/Chicago", "417": "America/Chicago",
    "430": "America/Chicago", "432": "America/Chicago", "469": "America/Chicago",
    "479": "America/Chicago", "501": "America/Chicago", "504": "America/Chicago",
    "507": "America/Chicago", "512": "America/Chicago", "515": "America/Chicago",
    "531": "America/Chicago", "534": "America/Chicago", "539": "America/Chicago",
    "563": "America/Chicago", "573": "America/Chicago", "601": "America/Chicago",
    "605": "America/Chicago", "608": "America/Chicago", "612": "America/Chicago",
    "615": "America/Chicago", "618": "America/Chicago", "620": "America/Chicago",
    "629": "America/Chicago", "630": "America/Chicago", "636": "America/Chicago",
    "641": "America/Chicago", "651": "America/Chicago", "660": "America/Chicago",
    "662": "America/Chicago", "682": "America/Chicago", "701": "America/Chicago",
    "708": "America/Chicago", "712": "America/Chicago", "713": "America/Chicago",
    "715": "America/Chicago", "731": "America/Chicago", "737": "America/Chicago",
    "763": "America/Chicago", "769": "America/Chicago", "773": "America/Chicago",
    "779": "America/Chicago", "806": "America/Chicago", "815": "America/Chicago",
    "816": "America/Chicago", "817": "America/Chicago", "830": "America/Chicago",
    "832": "America/Chicago", "847": "America/Chicago", "870": "America/Chicago",
    "901": "America/Chicago", "903": "America/Chicago", "913": "America/Chicago",
    "918": "America/Chicago", "920": "America/Chicago", "931": "America/Chicago",
    "936": "America/Chicago", "940": "America/Chicago", "952": "America/Chicago",
    "956": "America/Chicago", "972": "America/Chicago", "979": "America/Chicago",
    "985": "America/Chicago",
    # Canadian Central (America/Winnipeg)
    "204": "America/Winnipeg", "431": "America/Winnipeg", "306": "America/Regina", "639": "America/Regina",

    # Eastern Time (America/New_York)
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "227": "America/New_York", "229": "America/New_York",
    "231": "America/New_York", "234": "America/New_York", "239": "America/New_York",
    "240": "America/New_York", "248": "America/New_York", "252": "America/New_York",
    "267": "America/New_York", "269": "America/New_York", "272": "America/New_York",
    "276": "America/New_York", "301": "America/New_York", "302": "America/New_York",
    "304": "America/New_York", "305": "America/New_York", "315": "America/New_York",
    "321": "America/New_York", "330": "America/New_York", "336": "America/New_York",
    "339": "America/New_York", "347": "America/New_York", "351": "America/New_York",
    "352": "America/New_York", "386": "America/New_York", "401": "America/New_York",
    "404": "America/New_York", "407": "America/New_York", "410": "America/New_York",
    "412": "America/New_York", "413": "America/New_York", "419": "America/New_York",
    "434": "America/New_York", "440": "America/New_York", "443": "America/New_York",
    "445": "America/New_York", "470": "America/New_York", "475": "America/New_York",
    "478": "America/New_York", "484": "America/New_York", "508": "America/New_York",
    "513": "America/New_York", "516": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "561": "America/New_York", "567": "America/New_York",
    "570": "America/New_York", "571": "America/New_York", "585": "America/New_York",
    "586": "America/New_York", "603": "America/New_York", "607": "America/New_York",
    "609": "America/New_York", "610": "America/New_York", "614": "America/New_York",
    "617": "America/New_York", "631": "America/New_York", "646": "America/New_York",
    "678": "America/New_York", "680": "America/New_York", "681": "America/New_York",
    "703": "America/New_York", "704": "America/New_York", "706": "America/New_York",
    "716": "America/New_York", "717": "America/New_York", "718": "America/New_York",
    "724": "America/New_York", "727": "America/New_York", "732": "America/New_York",
    "740": "America/New_York", "754": "America/New_York", "757": "America/New_York",
    "770": "America/New_York", "772": "America/New_York", "774": "America/New_York",
    "781": "America/New_York", "786": "America/New_York", "802": "America/New_York",
    "803": "America/New_York", "804": "America/New_York", "813": "America/New_York",
    "814": "America/New_York", "828": "America/New_York", "838": "America/New_York",
    "843": "America/New_York", "845": "America/New_York", "848": "America/New_York",
    "854": "America/New_York", "856": "America/New_York", "857": "America/New_York",
    "860": "America/New_York", "862": "America/New_York", "863": "America/New_York",
    "864": "America/New_York", "865": "America/New_York", "878": "America/New_York",
    "904": "America/New_York", "908": "America/New_York", "910": "America/New_York",
    "912": "America/New_York", "914": "America/New_York", "917": "America/New_York",
    "919": "America/New_York", "929": "America/New_York", "937": "America/New_York",
    "941": "America/New_York", "947": "America/New_York", "954": "America/New_York",
    "959": "America/New_York", "973": "America/New_York", "978": "America/New_York",
    "980": "America/New_York", "984": "America/New_York", "989": "America/New_York",
    # Canadian Eastern (America/Toronto / Montreal)
    "416": "America/Toronto", "647": "America/Toronto", "437": "America/Toronto",
    "905": "America/Toronto", "289": "America/Toronto", "365": "America/Toronto",
    "742": "America/Toronto", "613": "America/Toronto", "343": "America/Toronto",
    "753": "America/Toronto", "519": "America/Toronto", "226": "America/Toronto",
    "548": "America/Toronto", "705": "America/Toronto", "249": "America/Toronto",
    "807": "America/Toronto", "514": "America/Montreal", "438": "America/Montreal",
    "263": "America/Montreal", "450": "America/Montreal", "579": "America/Montreal",
    "354": "America/Montreal", "418": "America/Montreal", "581": "America/Montreal",
    "367": "America/Montreal", "819": "America/Montreal", "873": "America/Montreal",

    # Canadian Atlantic (America/Halifax)
    "902": "America/Halifax", "782": "America/Halifax", "506": "America/Halifax",

    # Canadian Newfoundland (America/St_Johns)
    "709": "America/St_Johns",

    # Alaska Time (America/Anchorage)
    "907": "America/Anchorage",

    # Hawaii Time (Pacific/Honolulu)
    "808": "Pacific/Honolulu",
}


class LocationTimezoneService:
    """
    Paranoia Framework Location & Timezone Inference Engine:
    - Layer 0: Normalizes geography strings (NFKC, lowercase, punctuation stripping).
    - Layer 1: Resolves via City/Metro -> State/Province -> Country -> Phone dial code hierarchy.
    - Layer 2: Validates with pytz.timezone to guarantee standard IANA compliance.
    - LRU Cache: @functools.lru_cache(maxsize=4096) eliminates redundant inference (<0.01ms).
    """

    @staticmethod
    def normalize_text(text: Any) -> str:
        """
        Paranoia Layer 0: Unicode NFKC normalization, lowercase, stripping whitespace
        and non-printable characters.
        """
        if not text:
            return ""
        val = unicodedata.normalize("NFKC", str(text)).strip().lower()
        # Remove control characters / NUL bytes
        return "".join(ch for ch in val if ch.isprintable() or ch in ("\n", "\t", " "))

    @staticmethod
    def validate_iana_timezone(tz_name: Optional[str]) -> Optional[str]:
        """
        Paranoia Layer 2: Verifies if a timezone string is a valid IANA timezone.
        Returns the canonical timezone string if valid, otherwise None.
        """
        if not tz_name or not isinstance(tz_name, str):
            return None
        cleaned = tz_name.strip()
        if not cleaned:
            return None

        # Check aliases/abbreviations first (e.g. PST -> America/Los_Angeles)
        lower_cleaned = cleaned.lower()
        if lower_cleaned in ABBREV_TO_IANA:
            cleaned = ABBREV_TO_IANA[lower_cleaned]

        if pytz is not None:
            try:
                tz_obj = pytz.timezone(cleaned)
                return getattr(tz_obj, "zone", cleaned)
            except Exception:
                return None
        else:
            # Fallback when pytz is missing: check presence of standard IANA slash or UTC
            if "/" in cleaned or cleaned.upper() == "UTC":
                return cleaned
            return None

    @staticmethod
    def _clean_phone(phone: Optional[str], country_hint: Optional[str] = None) -> Optional[str]:
        """
        Cleans and standardizes an international phone number string.
        Paranoia Layer 1 & 2: Prevents 10-digit US/Canada numbers (e.g. 415, 917, 330)
        from inverting into European/Asian country dial codes (+41 Switzerland, +91 India, +33 France).
        Also handles domestic trunk prefixes (e.g. 0 in UK, FR, DE, IN) when country_hint is provided.
        """
        if not phone:
            return None
        raw = str(phone).strip()
        if not raw:
            return None
        
        # Strip common trailing extension markers like 'ext 123', 'x45', 'post 12'
        raw = re.sub(r"(?i)\s*(?:ext|x|post)[\s.:]*\d+.*$", "", raw).strip()

        digits_only = re.sub(r"\D", "", raw)
        if not digits_only:
            return None

        norm_c = LocationTimezoneService.normalize_text(country_hint) if country_hint else ""

        # Normalize 00 international prefix to +
        if raw.startswith("00"):
            raw = "+" + raw[2:].lstrip()
            digits_only = digits_only[2:]

        # If raw starts with '+', check for false '+' prepended to 10-digit US numbers
        if raw.startswith("+"):
            # Paranoia Layer 2 Check:
            # Did a CRM or script prepend '+' to a 10-digit US number?
            # e.g. '+4155550199' (415 San Francisco area code -> mistaken for +41 Switzerland)
            # or '+9175550199' (917 New York area code -> mistaken for +91 India)
            # or '+3305550199' (330 Ohio area code -> mistaken for +33 France)
            if len(digits_only) == 10 and digits_only[0] in "23456789":
                if norm_c in ("united states", "us", "usa", "canada", "ca"):
                    return "+1" + digits_only
                # If no country hint or ambiguous country:
                if not norm_c:
                    if phonenumbers is not None:
                        try:
                            direct_obj = phonenumbers.parse("+" + digits_only, None)
                            if not phonenumbers.is_valid_number(direct_obj):
                                us_obj = phonenumbers.parse("+1" + digits_only, None)
                                if phonenumbers.is_valid_number(us_obj):
                                    return "+1" + digits_only
                        except Exception:
                            pass
                    # Fallback check against known NANP area codes
                    if digits_only[:3] in NANP_AREA_CODES:
                        return "+1" + digits_only

            return "+" + digits_only

        # If phone did NOT explicitly start with + or 00:
        if norm_c:
            if norm_c in ("united states", "us", "usa", "canada", "ca"):
                if len(digits_only) == 10 and digits_only[0] in "23456789":
                    return "+1" + digits_only
                if len(digits_only) == 11 and digits_only.startswith("1"):
                    return "+" + digits_only
            elif norm_c in ("india", "in", "ind", "bharat"):
                if len(digits_only) == 10 and digits_only[0] in "6789":
                    return "+91" + digits_only
                if len(digits_only) == 11 and digits_only.startswith("0"):
                    return "+91" + digits_only[1:]
                if len(digits_only) == 12 and digits_only.startswith("91"):
                    return "+" + digits_only
            elif norm_c in ("united kingdom", "uk", "gb", "great britain", "england", "scotland", "wales"):
                if digits_only.startswith("0") and len(digits_only) in (10, 11):
                    return "+44" + digits_only[1:]
                if len(digits_only) == 10:
                    return "+44" + digits_only
                if len(digits_only) == 12 and digits_only.startswith("44"):
                    return "+" + digits_only
            elif norm_c in ("france", "fr", "fra"):
                if digits_only.startswith("0") and len(digits_only) == 10:
                    return "+33" + digits_only[1:]
                if len(digits_only) == 9:
                    return "+33" + digits_only
                if len(digits_only) == 11 and digits_only.startswith("33"):
                    return "+" + digits_only
            elif norm_c in ("germany", "de", "deu", "deutschland"):
                if digits_only.startswith("0") and len(digits_only) >= 10:
                    return "+49" + digits_only[1:]
                if len(digits_only) >= 11 and digits_only.startswith("49"):
                    return "+" + digits_only
            elif norm_c in ("australia", "au", "aus"):
                if digits_only.startswith("0") and len(digits_only) == 10:
                    return "+61" + digits_only[1:]
                if len(digits_only) == 9:
                    return "+61" + digits_only
                if len(digits_only) == 11 and digits_only.startswith("61"):
                    return "+" + digits_only
            elif norm_c in ("switzerland", "ch", "che"):
                if digits_only.startswith("0") and len(digits_only) == 10:
                    return "+41" + digits_only[1:]
                if len(digits_only) == 9:
                    return "+41" + digits_only
                if len(digits_only) == 11 and digits_only.startswith("41"):
                    return "+" + digits_only

        # 10-digit North American Numbering Plan (NANP): Area code [2-9]xx (when no non-US country specified)
        if len(digits_only) == 10 and digits_only[0] in "23456789":
            return "+1" + digits_only

        # 11-digit NANP number starting with 1
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return "+" + digits_only

        # Fallback for international numbers lacking leading plus
        if len(digits_only) >= 11:
            return "+" + digits_only

        return None

    @classmethod
    def resolve_phone_timezone(
        cls,
        phone: Optional[str],
        country_hint: Optional[str] = None,
        location_hint: Optional[str] = None
    ) -> Optional[str]:
        """
        Paranoia Layer 0, 1 & 2: Resolves an IANA timezone from a phone number using:
        - Google phonenumbers library with regional and validation checks.
        - Geographic country/state/city context to disambiguate area codes vs dial codes.
        - Hardened NANP area code fallback table for US/Canada.
        - International dial code fallback table.
        """
        if not phone:
            return None
        raw_phone = str(phone).strip()
        if not raw_phone:
            return None

        # Clean trailing extension markers
        raw_phone = re.sub(r"(?i)\s*(?:ext|x|post)[\s.:]*\d+.*$", "", raw_phone).strip()
        if raw_phone.startswith("00"):
            raw_phone = "+" + raw_phone[2:].lstrip()
        digits = re.sub(r"\D", "", raw_phone)
        if not digits:
            return None

        norm_c = cls.normalize_text(country_hint) if country_hint else ""
        norm_l = cls.normalize_text(location_hint) if location_hint else ""

        # Determine ISO-2 region hint
        region_hint = None
        if norm_c and norm_c in COUNTRY_TO_ISO2:
            region_hint = COUNTRY_TO_ISO2[norm_c]

        if not region_hint and norm_l and norm_l not in POISON_LOCATIONS:
            tokens = [t.strip() for t in re.split(r"[\,\;\/\|\-\(\)\[\]]", norm_l) if t.strip()]
            for t in tokens:
                if t in US_STATES:
                    region_hint = "US"
                    break
                elif t in CANADIAN_PROVINCES:
                    region_hint = "CA"
                    break
                elif t in AUSTRALIAN_STATES:
                    region_hint = "AU"
                    break
                elif t in COUNTRY_TO_ISO2:
                    region_hint = COUNTRY_TO_ISO2[t]
                    break
                elif t in GLOBAL_METRO_AREAS:
                    metro_tz = GLOBAL_METRO_AREAS[t]
                    if metro_tz.startswith("America/"):
                        region_hint = "US"
                    elif metro_tz.startswith("Europe/London"):
                        region_hint = "GB"
                    elif metro_tz.startswith("Europe/Paris"):
                        region_hint = "FR"
                    elif metro_tz.startswith("Europe/Berlin"):
                        region_hint = "DE"
                    elif metro_tz.startswith("Asia/Kolkata"):
                        region_hint = "IN"
                    elif metro_tz.startswith("Australia/"):
                        region_hint = "AU"
                    break

        cleaned_phone = cls._clean_phone(raw_phone, country_hint=norm_c)

        # -------------------------------------------------------------------
        # Paranoia Layer 0: phonenumbers Library Inference
        # -------------------------------------------------------------------
        if phonenumbers is not None and phone_timezone is not None:
            candidates: List[Tuple[str, Optional[str]]] = []
            if cleaned_phone:
                candidates.append((cleaned_phone, None))
            if region_hint:
                candidates.append((raw_phone, region_hint))
            if not region_hint and len(digits) == 10 and digits[0] in "23456789":
                candidates.append((raw_phone, "US"))
            candidates.append((raw_phone, None))

            for p_candidate, r_candidate in candidates:
                try:
                    parsed = phonenumbers.parse(p_candidate, r_candidate)
                    if phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed):
                        tzs = [
                            tz for tz in phone_timezone.time_zones_for_number(parsed)
                            if tz and tz != "Etc/Unknown"
                        ]
                        if tzs:
                            # Prioritize major canonical timezones for multi-territory codes
                            selected_tz = None
                            if "Europe/London" in tzs:
                                selected_tz = "Europe/London"
                            elif "America/Anchorage" in tzs:
                                selected_tz = "America/Anchorage"
                            elif "Asia/Kolkata" in tzs or "Asia/Calcutta" in tzs:
                                selected_tz = "Asia/Kolkata"
                            else:
                                for cand in tzs:
                                    val = cls.validate_iana_timezone(cand)
                                    if val:
                                        selected_tz = val
                                        break
                            if selected_tz:
                                val = cls.validate_iana_timezone(selected_tz)
                                if val:
                                    return val
                except Exception:
                    continue

        # -------------------------------------------------------------------
        # Paranoia Layer 1: Built-in NANP & International Table Fallback
        # -------------------------------------------------------------------
        if cleaned_phone:
            clean_digits = re.sub(r"\D", "", cleaned_phone)
            # If +1 (US / Canada)
            if cleaned_phone.startswith("+1") and len(clean_digits) >= 4:
                area_code = clean_digits[1:4]
                if area_code in NANP_AREA_CODES:
                    val = cls.validate_iana_timezone(NANP_AREA_CODES[area_code])
                    if val:
                        return val

            # Check international dial codes
            for prefix, dial_tz in PHONE_DIAL_CODES:
                if cleaned_phone.startswith(prefix):
                    val = cls.validate_iana_timezone(dial_tz)
                    if val:
                        return val

        return None

    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def infer_timezone(
        location: Optional[str],
        country: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Optional[str]:
        """
        Paranoia Layer 1 & 2: Infers an IANA timezone from location, country, and/or phone.
        Hierarchy: City/Metro -> State/Province -> Country -> Phone Dial Code.
        Decorated with LRU cache so repeated calls across thousands of leads resolve in <0.01ms.
        """
        norm_loc = LocationTimezoneService.normalize_text(location)
        norm_country = LocationTimezoneService.normalize_text(country)

        # 1. Poison location filter
        is_loc_poison = (not norm_loc) or (norm_loc in POISON_LOCATIONS)

        # Extract tokens/segments if location is not pure poison
        tokens: List[str] = []
        if not is_loc_poison:
            # Split on common delimiters: comma, semicolon, slash, pipe, dash, brackets
            raw_tokens = re.split(r"[\,\;\/\|\-\(\)\[\]]", norm_loc)
            for t in raw_tokens:
                cleaned_token = t.strip()
                if cleaned_token and cleaned_token not in POISON_LOCATIONS:
                    # Strip 5-digit US zip codes or postal codes from token
                    token_without_zip = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", cleaned_token).strip()
                    tokens.append(token_without_zip if token_without_zip else cleaned_token)

        # Context indicators for state disambiguation (e.g. IN for India vs Indiana, DE for Germany vs Delaware)
        is_india_context = (norm_country in ("india", "in", "ind", "bharat")) or any(
            t in ("india", "bharat") for t in tokens
        )
        is_germany_context = (norm_country in ("germany", "de", "deu", "deutschland")) or any(
            t in ("germany", "deutschland") for t in tokens
        )
        is_australia_context = (norm_country in ("australia", "au", "aus")) or any(
            t in ("australia", "aus") for t in tokens
        )
        is_canada_context = (norm_country in ("canada", "ca", "can")) or any(
            t in ("canada", "can") for t in tokens
        )

        # -------------------------------------------------------------------
        # Phase 1: City / Metropolitan Area Matching
        # -------------------------------------------------------------------
        if tokens:
            # 1a. Exact token match against GLOBAL_METRO_AREAS
            for token in tokens:
                if token in GLOBAL_METRO_AREAS:
                    validated = LocationTimezoneService.validate_iana_timezone(GLOBAL_METRO_AREAS[token])
                    if validated:
                        return validated

                # Strip "greater ... area", "metro area", " area"
                simplified_token = re.sub(r"^(?:greater\s+)", "", token)
                simplified_token = re.sub(r"\s+(?:metro(?:politan)?\s+area|area|city)$", "", simplified_token).strip()
                if simplified_token and simplified_token in GLOBAL_METRO_AREAS:
                    validated = LocationTimezoneService.validate_iana_timezone(GLOBAL_METRO_AREAS[simplified_token])
                    if validated:
                        return validated

            # 1b. Check whole-phrase / full location against GLOBAL_METRO_AREAS
            if norm_loc in GLOBAL_METRO_AREAS:
                validated = LocationTimezoneService.validate_iana_timezone(GLOBAL_METRO_AREAS[norm_loc])
                if validated:
                    return validated

            # 1c. Substring word boundary search for high-confidence city names (>= 4 chars)
            for city_name, city_tz in GLOBAL_METRO_AREAS.items():
                if len(city_name) >= 4 and city_name in norm_loc:
                    if re.search(r"\b" + re.escape(city_name) + r"\b", norm_loc):
                        validated = LocationTimezoneService.validate_iana_timezone(city_tz)
                        if validated:
                            return validated

        # -------------------------------------------------------------------
        # Phase 2: State / Province Matching
        # -------------------------------------------------------------------
        if tokens:
            for token in tokens:
                # Canadian Provinces
                if token in CANADIAN_PROVINCES:
                    # 'ca' token: if Canada context, 'ca' is Canada (handled in country)
                    if token != "ca" or is_canada_context:
                        validated = LocationTimezoneService.validate_iana_timezone(CANADIAN_PROVINCES[token])
                        if validated:
                            return validated

                # Australian States
                if token in AUSTRALIAN_STATES:
                    # 'wa' token: if Australia context or Western Australia explicitly
                    if token != "wa" or is_australia_context:
                        validated = LocationTimezoneService.validate_iana_timezone(AUSTRALIAN_STATES[token])
                        if validated:
                            return validated

                # US States
                if token in US_STATES:
                    # Disambiguation:
                    # 'de' in Germany context is Germany
                    if token == "de" and is_germany_context:
                        continue
                    # 'in' in India context is India
                    if token == "in" and is_india_context:
                        continue
                    # 'wa' in Australia context is Western Australia
                    if token == "wa" and is_australia_context:
                        continue

                    validated = LocationTimezoneService.validate_iana_timezone(US_STATES[token])
                    if validated:
                        return validated

            # Full state name search within normalized location text
            for state_name, state_tz in US_STATES.items():
                if len(state_name) > 3 and state_name in norm_loc:
                    if re.search(r"\b" + re.escape(state_name) + r"\b", norm_loc):
                        validated = LocationTimezoneService.validate_iana_timezone(state_tz)
                        if validated:
                            return validated

            for prov_name, prov_tz in CANADIAN_PROVINCES.items():
                if len(prov_name) > 3 and prov_name in norm_loc:
                    if re.search(r"\b" + re.escape(prov_name) + r"\b", norm_loc):
                        validated = LocationTimezoneService.validate_iana_timezone(prov_tz)
                        if validated:
                            return validated

            for aus_name, aus_tz in AUSTRALIAN_STATES.items():
                if len(aus_name) > 3 and aus_name in norm_loc:
                    if re.search(r"\b" + re.escape(aus_name) + r"\b", norm_loc):
                        validated = LocationTimezoneService.validate_iana_timezone(aus_tz)
                        if validated:
                            return validated

        # -------------------------------------------------------------------
        # Phase 3: Phone Dial Code / Regional Area Code Matching (Granular)
        # -------------------------------------------------------------------
        # High-precision phone resolution (with area code mapping & country anchor)
        # resolves the lead's exact regional timezone before coarse national fallback.
        phone_tz = LocationTimezoneService.resolve_phone_timezone(
            phone=phone,
            country_hint=norm_country or country,
            location_hint=norm_loc or location
        )
        if phone_tz:
            return phone_tz

        # -------------------------------------------------------------------
        # Phase 4: Coarse Country Matching (National Fallback)
        # -------------------------------------------------------------------
        # 4a. Check explicit country argument
        if norm_country and norm_country not in POISON_LOCATIONS:
            if norm_country in COUNTRIES:
                validated = LocationTimezoneService.validate_iana_timezone(COUNTRIES[norm_country])
                if validated:
                    return validated

        # 4b. Check tokens in location for country match
        if tokens:
            for token in tokens:
                if token in COUNTRIES:
                    validated = LocationTimezoneService.validate_iana_timezone(COUNTRIES[token])
                    if validated:
                        return validated

            # Full country name search in location
            for c_name, c_tz in COUNTRIES.items():
                if len(c_name) > 3 and c_name in norm_loc:
                    if re.search(r"\b" + re.escape(c_name) + r"\b", norm_loc):
                        validated = LocationTimezoneService.validate_iana_timezone(c_tz)
                        if validated:
                            return validated

        return None

    @classmethod
    def get_or_resolve_lead_timezone(
        cls,
        lead: Dict[str, Any],
        supabase: Any = None
    ) -> Optional[str]:
        """
        Paranoia Framework Lead-Level Timezone Resolver:
        - Layer 0: If lead.get("timezone") is already valid IANA, returns directly.
        - Layer 1 (Environmental): Checks location_timezone_cache in Supabase (with fallback).
        - Layer 1 (Inference): Evaluates location, p_location, city, state, country, phone.
        - Layer 2 (Human Paranoia): Validates with pytz.timezone. If inferred, safely caches
          result in location_timezone_cache and updates lead table in Supabase.
        """
        if not lead or not isinstance(lead, dict):
            return None

        # 1. Check existing lead timezone
        raw_tz = lead.get("timezone")
        if raw_tz:
            valid_existing = cls.validate_iana_timezone(raw_tz)
            if valid_existing:
                return valid_existing

        # 2. Extract potential location attributes
        raw_location = lead.get("location") or lead.get("p_location") or ""
        city = lead.get("city") or ""
        state = lead.get("state") or ""
        country = lead.get("country") or ""
        phone = lead.get("phone") or lead.get("phone_number") or ""

        # Compose best candidate location string
        candidate_loc = raw_location
        if not candidate_loc:
            parts = [p.strip() for p in (city, state) if p and str(p).strip()]
            candidate_loc = ", ".join(parts) if parts else ""

        norm_loc = cls.normalize_text(candidate_loc)

        # 3. Check Supabase location_timezone_cache
        if supabase is not None and norm_loc and norm_loc not in POISON_LOCATIONS:
            try:
                res = supabase.table("location_timezone_cache").select(
                    "iana_timezone, resolution_status"
                ).eq("normalized_location", norm_loc).execute()
                if res and getattr(res, "data", None) and len(res.data) > 0:
                    row = res.data[0]
                    if row.get("resolution_status") == "resolved" and row.get("iana_timezone"):
                        valid_cached = cls.validate_iana_timezone(row["iana_timezone"])
                        if valid_cached:
                            return valid_cached
                    elif row.get("resolution_status") == "unresolved":
                        return None
            except Exception as cache_read_err:
                logger.debug(f"location_timezone_cache read failed: {cache_read_err}")

        # 4. Infer via multi-tier inference engine
        inferred_tz = cls.infer_timezone(
            location=candidate_loc if candidate_loc else None,
            country=country if country else None,
            phone=phone if phone else None
        )

        # 5. Persist to cache & update lead if Supabase is available
        if supabase is not None and norm_loc and norm_loc not in POISON_LOCATIONS:
            try:
                cache_payload = {
                    "normalized_location": norm_loc,
                    "iana_timezone": inferred_tz,
                    "resolution_status": "resolved" if inferred_tz else "unresolved"
                }
                supabase.table("location_timezone_cache").upsert(
                    cache_payload, on_conflict="normalized_location"
                ).execute()
            except Exception as cache_write_err:
                logger.debug(f"location_timezone_cache write failed: {cache_write_err}")

        lead_id = lead.get("id")
        if supabase is not None and lead_id and inferred_tz:
            try:
                supabase.table("leads").update({"timezone": inferred_tz}).eq("id", lead_id).execute()
            except Exception as lead_update_err:
                logger.debug(f"Failed to update lead {lead_id} timezone: {lead_update_err}")

        return inferred_tz
