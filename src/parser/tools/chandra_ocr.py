from transformers import AutoModelForImageTextToText, AutoProcessor
from chandra.model.hf import generate_hf
from chandra.model.schema import BatchInputItem
from chandra.output import parse_markdown
from PIL import Image
import torch

model = AutoModelForImageTextToText.from_pretrained(
    "datalab-to/chandra-ocr-2",
    dtype=torch.bfloat16,
    device_map="auto",
)
model.eval()
model.processor = AutoProcessor.from_pretrained("datalab-to/chandra-ocr-2")
model.processor.tokenizer.padding_side = "left"

batch = [
    BatchInputItem(
        image=Image.open("document.png"),
        prompt_type="ocr_layout"
    )
]

result = generate_hf(batch, model)[0]
markdown = parse_markdown(result.raw)
print(markdown)
