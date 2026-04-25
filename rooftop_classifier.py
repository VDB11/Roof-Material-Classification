import open_clip
import torch
from PIL import Image
from huggingface_hub import hf_hub_download
import config

LABEL_MAP = {
    "asphalt shingles roof viewed from above"              : "Asphalt Shingles",
    "metal roofing viewed from above"                      : "Metal Roofing",
    "clay tile roof viewed from above"                     : "Clay Tile",
    "concrete tile roof viewed from above"                 : "Concrete Tile",
    "slate roof viewed from above"                         : "Slate",
    "thatch organic roof viewed from above"                : "Thatch",
    "bituminous tar gravel roof viewed from above"         : "Bituminous / Tar",
    "membrane TPO EPDM white flat roof viewed from above"  : "Membrane (TPO/EPDM)",
    "fibre cement corrugated sheet roof viewed from above" : "Fibre Cement Sheet",
    "bare concrete RCC flat roof viewed from above"        : "Bare Concrete / RCC",
}


def load_model():
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    checkpoint_path = hf_hub_download("chendelong/RemoteCLIP", "RemoteCLIP-ViT-B-32.pt", cache_dir="checkpoints")
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint)
    model.eval()
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    return (model, preprocess, tokenizer), None


def classify_image(image, processor_tuple, _model):
    model, preprocess, tokenizer = processor_tuple

    image_tensor = preprocess(image).unsqueeze(0)
    text_tokens  = tokenizer(config.LABELS)

    with torch.no_grad():
        image_features = model.encode_image(image_tensor)
        text_features  = model.encode_text(text_tokens)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        text_features  = text_features / text_features.norm(dim=-1, keepdim=True)
        probs = (image_features @ text_features.T).softmax(dim=-1)

    results = sorted(zip(config.LABELS, probs[0].tolist()), key=lambda x: x[1], reverse=True)
    top     = results[0][0]
    return LABEL_MAP.get(top, top)