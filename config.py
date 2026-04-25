INPUT_JSON    = "../coordinates.json"
OUTPUT_DIR    = "../satellite_outputs"
SCALE         = 921
OUTPUT_INCHES = 6
OUTPUT_DPI    = 300
MAX_RETRIES   = 1
TILE_SIZE     = 256
MAX_WORKERS   = 8

CLASSIFY      = True
OSM_DIST      = 150

LABELS = [
    "asphalt shingles roof viewed from above",
    "metal roofing viewed from above",
    "clay tile roof viewed from above",
    "concrete tile roof viewed from above",
    "slate roof viewed from above",
    "thatch organic roof viewed from above",
    "bituminous tar gravel roof viewed from above",
    "membrane TPO EPDM white flat roof viewed from above",
    "fibre cement corrugated sheet roof viewed from above",
    "bare concrete RCC flat roof viewed from above",
]

SOURCES = [
    {
        "name": "google",
        "url": "https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "subdomains": ["0", "1", "2", "3"],
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
        "url_format": "google",
    },
    {
        "name": "esri",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "subdomains": None,
        "headers": {},
        "url_format": "esri",
    },
    {
        "name": "bing",
        "url": "https://ecn.t{s}.tiles.virtualearth.net/tiles/a{q}.jpeg?g=1",
        "subdomains": ["0", "1", "2", "3"],
        "headers": {"User-Agent": "Mozilla/5.0"},
        "url_format": "bing",
    },
]