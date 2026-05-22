# VLM OCR Fine-Tuning And Inference

This folder contains scripts for fine-tuning and running OCR with `unsloth/Qwen3.5-0.8B`.

- `finetune.py` fine-tunes the model on the Hugging Face dataset `5CD-AI/Viet-Handwriting-OCR-v2`.
- `predict.py` runs OCR inference on a local image with the saved LoRA adapter.
- `convert_to_ollama.py` exports the fine-tuned adapter to GGUF and writes an Ollama `Modelfile`.

## Install

From the repository root:

```bash
pip install --upgrade --force-reinstall --no-cache-dir unsloth unsloth_zoo
pip install -U datasets trl accelerate pillow torchvision
```

When working locally, activate the project conda environment first:

```bash
conda activate tungn197
```

## Run OCR On An Image

After fine-tuning, the default adapter path is:

```text
research/VLM/qwen35_08b_ocr_lora/
```

Run prediction from this folder:

```bash
cd research/VLM
python predict.py path/to/image.png
```

Write the OCR text to a file:

```bash
python predict.py path/to/image.png --output-file ocr.txt
```

Use a different adapter or Hugging Face model id:

```bash
python predict.py path/to/image.png --model-dir qwen35_08b_ocr_lora
```

For deterministic OCR, the default decoding uses greedy generation with `--temperature 0.0`.
For longer pages, increase the generated token budget:

```bash
python predict.py path/to/image.png --max-new-tokens 1024
```

Useful prediction arguments:

```text
--model-dir
--prompt
--max-seq-length
--max-new-tokens
--temperature
--top-p
--load-in-4bit
--output-file
```

If `predict.py --help` works but prediction fails with a missing dependency error, install the VLM dependencies from the install section above in the active Python environment.

## Convert For Ollama

`convert_to_ollama.py` merges the LoRA adapter, exports GGUF files, and writes a `Modelfile` that Ollama can load.

```bash
cd research/VLM
python convert_to_ollama.py
```

By default, the script reads:

```text
qwen35_08b_ocr_lora/
```

It writes the merged model to:

```text
qwen35_08b_ocr_ollama/
```

and writes GGUF/Ollama files to:

```text
qwen35_08b_ocr_ollama_gguf/
```

Create the Ollama model after conversion:

```bash
ollama create cognidoc-ocr:latest -f qwen35_08b_ocr_ollama_gguf/Modelfile
```

Or let the script run `ollama create`:

```bash
python convert_to_ollama.py --create-ollama --ollama-model cognidoc-ocr:latest
```

Use another quantization level:

```bash
python convert_to_ollama.py --quantization q8_0
```

Common quantization values:

```text
q4_k_m
q5_k_m
q8_0
f16
not_quantized
fast_quantized
quantized
```

If the output folders already exist, pass `--overwrite`.

By default, the script uses the local llama.cpp converter under `/root/.unsloth/llama.cpp`.
This avoids a known Unsloth failure where the downloaded upstream converter imports a separate `conversion` module during introspection. The script also writes a patched converter copy named `convert_hf_to_gguf_cognidoc.py` so the local Qwen3.5 OCR tokenizer hash is recognized as `qwen35`.
To force Unsloth's download path, pass `--download-converter`.

Ollama compatibility depends on llama.cpp/Ollama support for the model architecture. If conversion fails with an unsupported architecture message, the model cannot be exported to Ollama until the upstream GGUF converter supports that architecture.

On the current server, `ollama create cognidoc-ocr:latest` succeeds but `ollama run cognidoc-ocr:latest` fails because Ollama's GGUF runtime loader reports:

```text
unknown model architecture: 'qwen35'
```

That means the generated GGUF is present and readable, but this Ollama runtime cannot execute `qwen35` GGUF models yet. Use `predict.py` for local inference, or run the GGUF with a llama.cpp build that supports `qwen35`. Ollama's experimental safetensors import also is not a working workaround here because this Linux build tries to use the MLX runner.

## Train From Scratch

```bash
cd research/VLM
python finetune.py
```

The script writes LoRA checkpoints and the final adapter to:

```text
qwen35_08b_ocr_lora/
```

Checkpoints are saved every 100 steps, for example:

```text
qwen35_08b_ocr_lora/checkpoint-1700/
```

## Resume From A Checkpoint

Pass the checkpoint folder as an argument:

```bash
cd research/VLM
python finetune.py qwen35_08b_ocr_lora/checkpoint-1700
```

Equivalent named argument:

```bash
python finetune.py --resume-from-checkpoint qwen35_08b_ocr_lora/checkpoint-1700
```

The checkpoint path must be an existing folder. Training resumes optimizer, scheduler, trainer state, and model adapter state from that checkpoint.

## Configure Training

Common settings can be changed from the command line:

```bash
python finetune.py \
  --output-dir qwen35_08b_ocr_lora \
  --per-device-train-batch-size 1 \
  --gradient-accumulation-steps 8 \
  --num-train-epochs 3 \
  --learning-rate 1e-4 \
  --save-steps 100 \
  --eval-steps 100
```

Resume while changing training settings:

```bash
python finetune.py \
  --resume-from-checkpoint qwen35_08b_ocr_lora/checkpoint-1700 \
  --per-device-train-batch-size 2 \
  --gradient-accumulation-steps 4
```

Useful arguments:

```text
--dataset-id
--model-name
--output-dir
--max-seq-length
--num-train-epochs
--per-device-train-batch-size
--gradient-accumulation-steps
--learning-rate
--warmup-ratio
--lr-scheduler-type
--optim
--weight-decay
--max-grad-norm
--logging-steps
--eval-steps
--save-steps
--seed
--dataset-num-proc
--lora-r
--lora-alpha
--lora-dropout
--resume-from-checkpoint
```

## Main Defaults

Default values in `finetune.py`:

```python
DEFAULT_DATASET_ID = "5CD-AI/Viet-Handwriting-OCR-v2"
DEFAULT_MODEL_NAME = "unsloth/Qwen3.5-0.8B"
DEFAULT_OUTPUT_DIR = "qwen35_08b_ocr_lora"
DEFAULT_MAX_SEQ_LENGTH = 2048
```

The dataset is expected to have `train` and `test` splits with these columns:

```text
image
text
```
