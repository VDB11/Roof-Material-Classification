import os
import math
import time
import json
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import config


def lat_lon_to_tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def meters_per_pixel(lat, zoom):
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)


def best_zoom(lat):
    output_px  = config.OUTPUT_INCHES * config.OUTPUT_DPI
    ground_m   = config.SCALE * config.OUTPUT_INCHES * 0.0254
    target_mpp = ground_m / output_px
    for z in range(21, 0, -1):
        if meters_per_pixel(lat, z) >= target_mpp:
            return z
    return 21


def tile_to_quadkey(x, y, zoom):
    quadkey = []
    for i in range(zoom, 0, -1):
        digit = 0
        mask  = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        quadkey.append(str(digit))
    return "".join(quadkey)


def build_tile_url(source, x, y, zoom, subdomain_index):
    fmt = source["url_format"]
    url = source["url"]
    if fmt == "google":
        s = source["subdomains"][subdomain_index % len(source["subdomains"])]
        return url.format(s=s, x=x, y=y, z=zoom)
    elif fmt == "esri":
        return url.format(z=zoom, y=y, x=x)
    elif fmt == "bing":
        s = source["subdomains"][subdomain_index % len(source["subdomains"])]
        q = tile_to_quadkey(x, y, zoom)
        return url.format(s=s, q=q)
    return url


def download_tile(args):
    source, x, y, zoom, subdomain_index = args
    url = build_tile_url(source, x, y, zoom, subdomain_index)
    for attempt in range(config.MAX_RETRIES):
        try:
            resp = requests.get(url, headers=source["headers"], timeout=10)
            resp.raise_for_status()
            return (x, y, Image.open(BytesIO(resp.content)).convert("RGB"))
        except Exception:
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(0.5)
    return (x, y, None)


def fetch_mosaic(source, lat, lon, zoom):
    mpp        = meters_per_pixel(lat, zoom)
    ground_m   = config.SCALE * config.OUTPUT_INCHES * 0.0254
    cx, cy     = lat_lon_to_tile(lat, lon, zoom)
    half_tiles = math.ceil((ground_m / 2.0) / (mpp * config.TILE_SIZE))

    x_min = cx - half_tiles
    x_max = cx + half_tiles
    y_min = cy - half_tiles
    y_max = cy + half_tiles

    tiles_x = x_max - x_min + 1
    tiles_y = y_max - y_min + 1
    mosaic  = Image.new("RGB", (tiles_x * config.TILE_SIZE, tiles_y * config.TILE_SIZE))

    tasks = [
        (source, tx, ty, zoom, i)
        for i, (ty, tx) in enumerate(
            (ty, tx)
            for ty in range(y_min, y_max + 1)
            for tx in range(x_min, x_max + 1)
        )
    ]

    failed = 0
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        futures = {executor.submit(download_tile, task): task for task in tasks}
        for future in as_completed(futures):
            x, y, tile = future.result()
            if tile is None:
                failed += 1
            else:
                col = x - x_min
                row = y - y_min
                mosaic.paste(tile, (col * config.TILE_SIZE, row * config.TILE_SIZE))

    if failed > (tiles_x * tiles_y) * 0.3:
        return None, mpp, x_min, y_min

    return mosaic, mpp, x_min, y_min


def fetch_building_polygon(lat, lon):
    d    = config.OSM_DIST / 111000
    bbox = f"{lat-d},{lon-d},{lat+d},{lon+d}"
    query = f"""
[out:json][timeout:25];
(
  way({bbox})["building"];
);
out geom;
"""
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data=query,
            headers={"User-Agent": "python"},
            timeout=30,
        )
        data = resp.json()
    except Exception as e:
        print(f"  Overpass API error: {e}")
        return None

    def centroid(coords):
        x = sum(p[0] for p in coords) / len(coords)
        y = sum(p[1] for p in coords) / len(coords)
        return x, y

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    target   = (lon, lat)
    best     = None
    best_dist = float("inf")

    for el in data.get("elements", []):
        if "geometry" in el:
            coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(coords) >= 3:
                c = centroid(coords)
                d = dist(c, target)
                if d < best_dist:
                    best      = coords
                    best_dist = d

    return best


def latlon_to_pixel(lat, lon, zoom, x_min, y_min):
    n      = 2 ** zoom
    tile_x = (lon + 180.0) / 360.0 * n
    tile_y = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n
    px     = int((tile_x - x_min) * config.TILE_SIZE)
    py     = int((tile_y - y_min) * config.TILE_SIZE)
    return px, py


def crop_to_polygon(mosaic, coords, zoom, x_min, y_min):
    pixel_coords = [latlon_to_pixel(lat, lon, zoom, x_min, y_min) for lon, lat in coords]

    xs     = [p[0] for p in pixel_coords]
    ys     = [p[1] for p in pixel_coords]
    left   = max(0, min(xs))
    right  = min(mosaic.width, max(xs))
    top    = max(0, min(ys))
    bottom = min(mosaic.height, max(ys))

    if right <= left or bottom <= top:
        return None

    mask = Image.new("L", mosaic.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(pixel_coords, fill=255)

    masked = Image.new("RGB", mosaic.size, (0, 0, 0))
    masked.paste(mosaic, mask=mask)
    return masked.crop((left, top, right, bottom))


def crop_and_resample(mosaic, lat, lon, zoom, mpp, x_min, y_min):
    output_px = int(config.OUTPUT_INCHES * config.OUTPUT_DPI)
    ground_m  = config.SCALE * config.OUTPUT_INCHES * 0.0254
    needed_px = int(ground_m / mpp)

    n      = 2 ** zoom
    cx, cy = lat_lon_to_tile(lat, lon, zoom)
    frac_x = (lon + 180.0) / 360.0 * n - cx
    frac_y = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n - cy

    center_px_x = (cx - x_min) * config.TILE_SIZE + int(frac_x * config.TILE_SIZE)
    center_px_y = (cy - y_min) * config.TILE_SIZE + int(frac_y * config.TILE_SIZE)

    left   = center_px_x - needed_px // 2
    top    = center_px_y - needed_px // 2
    right  = left + needed_px
    bottom = top  + needed_px

    cropped   = mosaic.crop((left, top, right, bottom))
    resampled = cropped.resize((output_px, output_px), Image.LANCZOS)
    return resampled

def process_facility(name, lat, lon, processor=None, model=None):
    zoom     = best_zoom(lat)
    out_path = os.path.join(config.OUTPUT_DIR, f"{name}.jpg")

    mosaic, mpp, x_min, y_min = None, None, None, None
    for source in config.SOURCES:
        print(f"  Trying source: {source['name']}")
        mosaic, mpp, x_min, y_min = fetch_mosaic(source, lat, lon, zoom)
        if mosaic is not None:
            break
        print(f"  Source {source['name']} failed, trying next...")

    if mosaic is None:
        print(f"  All sources failed for {name}")
        return False

    full_image = crop_and_resample(mosaic, lat, lon, zoom, mpp, x_min, y_min)
    full_image.save(out_path, "JPEG", quality=95, dpi=(config.OUTPUT_DPI, config.OUTPUT_DPI))
    print(f"  Saved: {out_path}")

    if not config.CLASSIFY:
        return True

    print(f"  Fetching building footprint from Overpass...")
    coords = fetch_building_polygon(lat, lon)

    if coords:
        print(f"  Building footprint found, cropping...")
        classify_img = crop_to_polygon(mosaic, coords, zoom, x_min, y_min)
        if classify_img is None:
            print(f"  Crop failed, using full image")
            classify_img = full_image
    else:
        print(f"  No building found, using full image")
        classify_img = full_image

    from rooftop_classifier import classify_image
    prediction = classify_image(classify_img, processor, model)
    print(f"{name}_roof_material: {prediction}")

    return prediction


def main():
    with open(config.INPUT_JSON, "r") as f:
        facilities = json.load(f)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    processor, model = None, None
    if config.CLASSIFY:
        from rooftop_classifier import load_model
        print("Loading OpenClip model...")
        processor, model = load_model()
        print("Model loaded.\n")

    total       = len(facilities)
    success     = 0
    all_results = {}

    for i, (name, coords) in enumerate(facilities.items(), 1):
        lat, lon = coords[0], coords[1]
        print(f"[{i}/{total}] Processing: {name} ({lat}, {lon})")
        result = process_facility(name, lat, lon, processor, model)

        if result is False:
            continue

        success += 1

        if config.CLASSIFY and isinstance(result, str):
            all_results[name] = {f"{name}_roof_material": result}

    if config.CLASSIFY and all_results:
        out_json = os.path.join(config.OUTPUT_DIR, "classification_results.json")
        with open(out_json, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to {out_json}")

    print(f"\nDone: {success}/{total} facilities processed")

if __name__ == "__main__":
    main()