import os
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

import config
from rooftop_classifier import load_model, classify_image
from download_satellite_image import (
    best_zoom, fetch_mosaic, fetch_building_polygon,
    crop_to_polygon, crop_and_resample
)

MODEL_STATE = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading SigLIP model...")
    processor, model = load_model()
    MODEL_STATE["processor"] = processor
    MODEL_STATE["model"]     = model
    print("Model loaded.")
    yield
    MODEL_STATE.clear()


app = FastAPI(lifespan=lifespan)


def run_pipeline(name, lat, lon):
    processor = MODEL_STATE["processor"]
    model     = MODEL_STATE["model"]

    zoom = best_zoom(lat)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUT_DIR, f"{name}.jpg")

    mosaic, mpp, x_min, y_min = None, None, None, None
    for source in config.SOURCES:
        mosaic, mpp, x_min, y_min = fetch_mosaic(source, lat, lon, zoom)
        if mosaic is not None:
            break

    if mosaic is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch satellite image for {name}")

    full_image = crop_and_resample(mosaic, lat, lon, zoom, mpp, x_min, y_min)
    full_image.save(out_path, "JPEG", quality=95, dpi=(config.OUTPUT_DPI, config.OUTPUT_DPI))

    coords = fetch_building_polygon(lat, lon)
    if coords:
        classify_img = crop_to_polygon(mosaic, coords, zoom, x_min, y_min)
        if classify_img is None:
            classify_img = full_image
    else:
        classify_img = full_image

    prediction = classify_image(classify_img, processor, model)
    return prediction


@app.get("/")
def classify_single(lat: float, lon: float):
    prediction = run_pipeline("single", lat, lon)
    return {"roof_material": prediction}


@app.post("/bulk")
async def classify_bulk(file: UploadFile = File(...)):
    content = await file.read()
    try:
        facilities = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    results     = {}
    all_results = {}

    for name, coords in facilities.items():
        lat, lon = coords[0], coords[1]
        try:
            prediction = run_pipeline(name, lat, lon)
            results[name]     = {f"{name}_roof_material": prediction}
            all_results[name] = {f"{name}_roof_material": prediction}
            print(f"{name}_roof_material: {prediction}")
        except Exception as e:
            results[name] = {f"{name}_roof_material": f"error: {str(e)}"}

    out_json = os.path.join(config.OUTPUT_DIR, "classification_results.json")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)

    return JSONResponse(content=results)