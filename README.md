# Satellite Roof Material Classifier

Classifies roof materials from satellite imagery using coordinates. Downloads aerial images via Google/ESRI/Bing tile sources, optionally crops to building footprint using OpenStreetMap, and classifies the roof material using RemoteCLIP.

## Setup

```bash
pip install -r requirements.txt
```

## Project Structure

```
├── config.py                    # All configuration
├── download_satellite_image.py  # Download + classify pipeline
├── rooftop_classifier.py        # RemoteCLIP classifier
├── main.py                      # FastAPI server
├── requirements.txt
├── coordinates.json             # Input coordinates
└── satellite_outputs/           # Downloaded images + results
```

## Configuration

Edit `config.py`:

| Parameter | Description |
|---|---|
| `INPUT_JSON` | Path to coordinates JSON file |
| `OUTPUT_DIR` | Directory to save images and results |
| `CLASSIFY` | `True` to classify after download, `False` to only download |
| `OSM_DIST` | Search radius (meters) for building footprint lookup |
| `LABELS` | Roof material classes |

## Input Format

`coordinates.json`:
```json
{
    "facility1": [39.7357, -87.3941],
    "facility2": [12.9008, 77.5932]
}
```

## Usage

### Command Line

```bash
python download_satellite_image.py
```

### API Server

```bash
uvicorn main:app --reload --port 8000
```

**Single coordinate:**
```
GET http://localhost:8000/?lat=39.7357&lon=-87.3941
```

Response:
```json
{"roof_material": "Metal Roofing"}
```

**Bulk coordinates:**
```bash
curl -X POST "http://localhost:8000/bulk" -F "file=@coordinates.json"
```

Response:
```json
{
  "facility1": {"facility1_roof_material": "Metal Roofing"},
  "facility2": {"facility2_roof_material": "Bare Concrete / RCC"}
}
```

## Output

- Individual images saved to `satellite_outputs/<name>.jpg`
- Classification results saved to `satellite_outputs/classification_results.json`

## Roof Material Classes

1. Asphalt Shingles
2. Metal Roofing
3. Clay Tile
4. Concrete Tile
5. Slate
6. Thatch
7. Bituminous / Tar
8. Membrane (TPO/EPDM)
9. Fibre Cement Sheet
10. Bare Concrete / RCC

## Notes

- Model: RemoteCLIP (ViT-B-32), trained specifically on satellite and aerial imagery
- Building footprints fetched from OpenStreetMap via Overpass API
- Falls back to full image if no building footprint is found
- First run downloads model weights (~350MB), cached locally after that
- CPU-only, expect 30-60 seconds per image for classification