"""
Training and evaluation entrypoint for GraphTATR.

Run from this directory, mirroring the original Table Transformer scripts:
    python train_graph_tatr.py --data_type structure --config_file graph_tatr_config.json --data_root_dir /path/to/data
"""
import argparse
import json
import math
import os
import random
import sys
from datetime import datetime

import numpy as np
import torch

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DETR_DIR = os.path.abspath(os.path.join(THIS_DIR, "../detr"))
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)
sys.path.insert(0, THIS_DIR)
if DETR_DIR not in sys.path:
    sys.path.insert(1, DETR_DIR)
from models import build_graph_model
import util.misc as utils


DEFAULT_ARGS = {
    "lr": 5e-5,
    "lr_backbone": 1e-5,
    "batch_size": 2,
    "weight_decay": 1e-4,
    "epochs": 20,
    "lr_drop": 1,
    "lr_gamma": 0.9,
    "clip_max_norm": 0.1,
    "backbone": "resnet18",
    "num_classes": 6,
    "dilation": False,
    "position_embedding": "sine",
    "emphasized_weights": {},
    "enc_layers": 6,
    "dec_layers": 6,
    "dim_feedforward": 2048,
    "hidden_dim": 256,
    "dropout": 0.1,
    "nheads": 8,
    "num_queries": 125,
    "pre_norm": True,
    "masks": False,
    "aux_loss": False,
    "mask_loss_coef": 1,
    "dice_loss_coef": 1,
    "ce_loss_coef": 1,
    "bbox_loss_coef": 5,
    "giou_loss_coef": 2,
    "eos_coef": 0.4,
    "set_cost_class": 1,
    "set_cost_bbox": 5,
    "set_cost_giou": 2,
    "device": "cuda",
    "seed": 42,
    "start_epoch": 0,
    "num_workers": 1,
    "checkpoint_freq": 1,
    "mode": "train",
    "data_type": "structure",
    "model_load_path": None,
    "load_weights_only": False,
    "model_save_dir": None,
    "metrics_save_filepath": "",
    "debug_save_dir": "debug",
    "table_words_dir": None,
    "debug": False,
    "train_max_size": None,
    "val_max_size": None,
    "test_max_size": None,
    "eval_pool_size": 1,
    "eval_step": 1,
    "train_strategy": "graph_only",
    "lambda_graph": 1.0,
    "initial_loss_coef": 0.0,
    "graph_layers": 2,
    "graph_k": 8,
    "graph_row_thr": 0.5,
    "graph_col_thr": 0.5,
    "graph_dropout": 0.1,
    "graph_use_knn_edges": True,
    "graph_use_geometry_edges": True,
    "graph_bidirectional_knn": True,
    "graph_include_self_edges": True,
    "graph_use_bbox_features": False,
    "graph_use_class_features": False,
}


def add_bool_arg(parser, name):
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", dest=name, action="store_true")
    group.add_argument(f"--no_{name}", dest=name, action="store_false")
    parser.set_defaults(**{name: None})


def get_args():
    parser = argparse.ArgumentParser("GraphTATR training/evaluation")
    parser.add_argument("--data_root_dir", required=True, help="Root data directory for images and labels")
    parser.add_argument("--config_file", required=True, help="Path to JSON config")
    parser.add_argument("--data_type", choices=["detection", "structure"], default=None)
    parser.add_argument("--model_load_path", default=None, help="Baseline or GraphTATR checkpoint path")
    parser.add_argument("--load_weights_only", action="store_true", default=None)
    parser.add_argument("--model_save_dir", default=None)
    parser.add_argument("--metrics_save_filepath", default=None)
    parser.add_argument("--debug_save_dir", default=None)
    parser.add_argument("--table_words_dir", default=None)
    parser.add_argument("--mode", choices=["train", "eval"], default=None)
    parser.add_argument("--debug", action="store_true", default=None)
    parser.add_argument("--device", default=None)

    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--lr_backbone", type=float, default=None)
    parser.add_argument("--weight_decay", type=float, default=None)
    parser.add_argument("--lr_drop", type=int, default=None)
    parser.add_argument("--lr_gamma", type=float, default=None)
    parser.add_argument("--clip_max_norm", type=float, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--checkpoint_freq", type=int, default=None)
    parser.add_argument("--batch_size", type=int, default=None)
    parser.add_argument("--num_workers", type=int, default=None)
    parser.add_argument("--train_max_size", type=int, default=None)
    parser.add_argument("--val_max_size", type=int, default=None)
    parser.add_argument("--test_max_size", type=int, default=None)
    parser.add_argument("--eval_pool_size", type=int, default=None)
    parser.add_argument("--eval_step", type=int, default=None)
    parser.add_argument("--start_epoch", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument("--train_strategy", choices=["graph_only", "decoder_graph", "full"], default=None)
    parser.add_argument("--lambda_graph", type=float, default=None)
    parser.add_argument("--initial_loss_coef", type=float, default=None)
    parser.add_argument("--graph_layers", type=int, default=None)
    parser.add_argument("--graph_k", type=int, default=None)
    parser.add_argument("--graph_row_thr", type=float, default=None)
    parser.add_argument("--graph_col_thr", type=float, default=None)
    parser.add_argument("--graph_dropout", type=float, default=None)
    add_bool_arg(parser, "graph_use_knn_edges")
    add_bool_arg(parser, "graph_use_geometry_edges")
    add_bool_arg(parser, "graph_bidirectional_knn")
    add_bool_arg(parser, "graph_include_self_edges")
    add_bool_arg(parser, "graph_use_bbox_features")
    add_bool_arg(parser, "graph_use_class_features")

    cmd_args = vars(parser.parse_args())
    with open(cmd_args["config_file"], "rb") as infile:
        config_args = json.load(infile)

    merged_args = DEFAULT_ARGS.copy()
    merged_args.update(config_args)
    for key, value in cmd_args.items():
        if value is not None:
            merged_args[key] = value
    return argparse.Namespace(**merged_args)


def clean_state_dict_keys(state_dict):
    cleaned = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            key = key[len("module."):]
        cleaned[key] = value
    return cleaned


def extract_model_state(checkpoint):
    if isinstance(checkpoint, dict):
        if "model_state_dict" in checkpoint:
            return checkpoint["model_state_dict"]
        if "model" in checkpoint:
            return checkpoint["model"]
    return checkpoint


def load_model_checkpoint(model, model_load_path, device):
    checkpoint = torch.load(model_load_path, map_location=device)
    state_dict = clean_state_dict_keys(extract_model_state(checkpoint))
    model_state = model.state_dict()
    mapped_state = {}

    has_graph_keys = any(
        key.startswith("base.") or key.startswith("gnn_layers.") or key.startswith("refined_")
        for key in state_dict.keys()
    )

    for key, value in state_dict.items():
        if not torch.is_tensor(value):
            continue
        if key in model_state and model_state[key].shape == value.shape:
            mapped_state[key] = value
            continue

        if not has_graph_keys:
            base_key = f"base.{key}"
            if base_key in model_state and model_state[base_key].shape == value.shape:
                mapped_state[base_key] = value
            if key.startswith("class_embed."):
                refined_key = "refined_class_embed." + key[len("class_embed."):]
                if refined_key in model_state and model_state[refined_key].shape == value.shape:
                    mapped_state[refined_key] = value
            elif key.startswith("bbox_embed."):
                refined_key = "refined_bbox_embed." + key[len("bbox_embed."):]
                if refined_key in model_state and model_state[refined_key].shape == value.shape:
                    mapped_state[refined_key] = value

    model_state.update(mapped_state)
    model.load_state_dict(model_state, strict=True)
    print("Loaded {} tensors from {}".format(len(mapped_state), model_load_path))
    return checkpoint, has_graph_keys


def apply_train_strategy(model, strategy):
    for parameter in model.parameters():
        parameter.requires_grad_(True)

    if strategy == "full":
        return

    for parameter in model.base.parameters():
        parameter.requires_grad_(False)

    if strategy == "graph_only":
        return

    if strategy == "decoder_graph":
        for parameter in model.base.transformer.decoder.parameters():
            parameter.requires_grad_(True)
        for parameter in model.base.query_embed.parameters():
            parameter.requires_grad_(True)
        for parameter in model.base.class_embed.parameters():
            parameter.requires_grad_(True)
        for parameter in model.base.bbox_embed.parameters():
            parameter.requires_grad_(True)
        return

    raise ValueError(f"Unknown train_strategy: {strategy}")


def build_optimizer(args, model):
    param_dicts = [
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if "backbone" not in n and p.requires_grad
            ]
        },
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if "backbone" in n and p.requires_grad
            ],
            "lr": args.lr_backbone,
        },
    ]
    param_dicts = [group for group in param_dicts if len(group["params"]) > 0]
    return torch.optim.AdamW(param_dicts, lr=args.lr, weight_decay=args.weight_decay)


def weighted_loss(loss_dict, weight_dict, coef=1.0):
    return coef * sum(loss_dict[k] * weight_dict[k] for k in loss_dict.keys() if k in weight_dict)


def train_one_epoch_graph(
    model,
    criterion,
    data_loader,
    optimizer,
    device,
    epoch,
    max_norm=0,
    max_batches_per_epoch=None,
    lambda_graph=1.0,
    initial_loss_coef=0.0,
    print_freq=100,
):
    model.train()
    criterion.train()
    metric_logger = utils.MetricLogger(delimiter="  ")
    metric_logger.add_meter("lr", utils.SmoothedValue(window_size=1, fmt="{value:.6f}"))
    metric_logger.add_meter("class_error", utils.SmoothedValue(window_size=1, fmt="{value:.2f}"))
    header = "Epoch: [{}]".format(epoch)

    batch_count = 0
    for samples, targets in metric_logger.log_every(data_loader, print_freq, header):
        batch_count += 1
        if max_batches_per_epoch is not None and batch_count > max_batches_per_epoch:
            break
        samples = samples.to(device)
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

        outputs = model(samples)
        refined_loss_dict = criterion(outputs, targets)
        weight_dict = criterion.weight_dict
        losses = weighted_loss(refined_loss_dict, weight_dict, lambda_graph)

        initial_loss_dict = None
        if initial_loss_coef > 0:
            initial_loss_dict = criterion(outputs["initial_outputs"], targets)
            losses = losses + weighted_loss(initial_loss_dict, weight_dict, initial_loss_coef)

        refined_loss_reduced = utils.reduce_dict(refined_loss_dict)
        refined_loss_scaled = {
            f"refined_{k}": v * weight_dict[k] * lambda_graph
            for k, v in refined_loss_reduced.items()
            if k in weight_dict
        }
        refined_loss_unscaled = {f"refined_{k}_unscaled": v for k, v in refined_loss_reduced.items()}
        total_loss_reduced = sum(refined_loss_scaled.values())

        log_values = {}
        log_values.update(refined_loss_scaled)
        log_values.update(refined_loss_unscaled)

        if initial_loss_dict is not None:
            initial_loss_reduced = utils.reduce_dict(initial_loss_dict)
            initial_loss_scaled = {
                f"initial_{k}": v * weight_dict[k] * initial_loss_coef
                for k, v in initial_loss_reduced.items()
                if k in weight_dict
            }
            initial_loss_unscaled = {f"initial_{k}_unscaled": v for k, v in initial_loss_reduced.items()}
            total_loss_reduced = total_loss_reduced + sum(initial_loss_scaled.values())
            log_values.update(initial_loss_scaled)
            log_values.update(initial_loss_unscaled)

        loss_value = total_loss_reduced.item()
        if not math.isfinite(loss_value):
            print("Loss is {}, stopping training".format(loss_value))
            print(refined_loss_reduced)
            sys.exit(1)

        optimizer.zero_grad()
        losses.backward()
        if max_norm > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
        optimizer.step()

        metric_logger.update(loss=loss_value, **log_values)
        metric_logger.update(class_error=refined_loss_reduced["class_error"])
        metric_logger.update(lr=optimizer.param_groups[0]["lr"])

    metric_logger.synchronize_between_processes()
    print("Averaged stats:", metric_logger)
    return {k: meter.global_avg for k, meter in metric_logger.meters.items()}


def train(args, model, criterion, postprocessors, device, loaded_checkpoint=None, loaded_graph_checkpoint=False):
    from engine import evaluate
    from main import get_data

    print("loading data")
    dataloading_time = datetime.now()
    data_loader_train, data_loader_val, dataset_val, train_len = get_data(args)
    print("finished loading data in :", datetime.now() - dataloading_time)

    apply_train_strategy(model, args.train_strategy)
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print("train strategy:", args.train_strategy)
    print("trainable params: {} / {}".format(trainable_params, total_params))

    optimizer = build_optimizer(args, model)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer,
        step_size=args.lr_drop,
        gamma=args.lr_gamma,
    )

    resume_checkpoint = False
    if (
        loaded_checkpoint is not None
        and not args.load_weights_only
        and loaded_graph_checkpoint
        and isinstance(loaded_checkpoint, dict)
        and "optimizer_state_dict" in loaded_checkpoint
    ):
        optimizer.load_state_dict(loaded_checkpoint["optimizer_state_dict"])
        resume_checkpoint = True
        if "epoch" in loaded_checkpoint:
            args.start_epoch = loaded_checkpoint["epoch"] + 1
    elif (
        loaded_checkpoint is not None
        and not args.load_weights_only
        and not loaded_graph_checkpoint
        and isinstance(loaded_checkpoint, dict)
        and "optimizer_state_dict" in loaded_checkpoint
    ):
        print("Ignoring baseline optimizer state because it does not match GraphTATR parameters.")

    if args.model_save_dir:
        output_directory = args.model_save_dir
    elif args.model_load_path and resume_checkpoint:
        output_directory = os.path.split(args.model_load_path)[0]
    else:
        run_date = datetime.now().strftime("%Y%m%d%H%M%S")
        output_directory = os.path.join(args.data_root_dir, "output", "graph_tatr_" + run_date)

    os.makedirs(output_directory, exist_ok=True)
    print("Output directory:", output_directory)

    model_save_path = os.path.join(output_directory, "model.pth")
    model_best_save_path = os.path.join(output_directory, "model_best.pth")
    print("Output model path:", model_save_path)
    print("Best model path:", model_best_save_path)
    max_batches_per_epoch = int(train_len / args.batch_size)
    print("Max batches per epoch: {}".format(max_batches_per_epoch))
    print("Start training")

    start_time = datetime.now()
    best_val_ap = float("-inf")
    for epoch in range(args.start_epoch, args.epochs):
        print("-" * 100)
        epoch_timing = datetime.now()
        train_stats = train_one_epoch_graph(
            model,
            criterion,
            data_loader_train,
            optimizer,
            device,
            epoch,
            args.clip_max_norm,
            max_batches_per_epoch=max_batches_per_epoch,
            lambda_graph=args.lambda_graph,
            initial_loss_coef=args.initial_loss_coef,
            print_freq=1000,
        )
        print("Epoch completed in", datetime.now() - epoch_timing)

        lr_scheduler.step()
        val_stats, coco_evaluator = evaluate(
            model,
            criterion,
            postprocessors,
            data_loader_val,
            dataset_val,
            device,
            None,
        )
        print(
            "val: AP50: {:.3f}, AP75: {:.3f}, AP: {:.3f}, AR: {:.3f}".format(
                val_stats["coco_eval_bbox"][1],
                val_stats["coco_eval_bbox"][2],
                val_stats["coco_eval_bbox"][0],
                val_stats["coco_eval_bbox"][8],
            )
        )

        val_ap = val_stats["coco_eval_bbox"][0]
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "args": args.__dict__,
            "train_stats": train_stats,
            "val_stats": val_stats,
            "best_val_ap": max(best_val_ap, val_ap),
        }
        torch.save(checkpoint, model_save_path)
        if val_ap >= best_val_ap:
            best_val_ap = val_ap
            checkpoint["best_val_ap"] = best_val_ap
            torch.save(checkpoint, model_best_save_path)
            print("Saved new best checkpoint with val AP: {:.4f}".format(best_val_ap))

    print("Total training time:", datetime.now() - start_time)


def main():
    args = get_args()
    print(args.__dict__)
    print("-" * 100)

    if args.mode == "eval" and args.debug:
        print("Running evaluation/inference in DEBUG mode. Saving output to:", args.debug_save_dir)
        os.makedirs(args.debug_save_dir, exist_ok=True)

    seed = args.seed + utils.get_rank()
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    device = torch.device(args.device)
    print("loading GraphTATR model")
    model, criterion, postprocessors = build_graph_model(args)
    model.to(device)

    loaded_checkpoint = None
    loaded_graph_checkpoint = False
    if args.model_load_path:
        loaded_checkpoint, loaded_graph_checkpoint = load_model_checkpoint(model, args.model_load_path, device)

    if args.mode == "train":
        train(
            args,
            model,
            criterion,
            postprocessors,
            device,
            loaded_checkpoint=loaded_checkpoint,
            loaded_graph_checkpoint=loaded_graph_checkpoint,
        )
    elif args.mode == "eval":
        from eval import eval_coco
        from main import get_data

        data_loader_test, dataset_test = get_data(args)
        eval_coco(args, model, criterion, postprocessors, data_loader_test, dataset_test, device)


if __name__ == "__main__":
    main()
