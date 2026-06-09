# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
Auxiliary graph training for Table Transformer structure recognition.

This model follows aux_graph_guided_table_structure_recognition.md:
- inference is the original image-only Table Transformer path
- training may receive targets and build a ground-truth graph branch
- auxiliary graph relation and feature-distillation losses train the visual branch

The current dataset exposes PASCAL VOC structure boxes, not explicit cell
row/column spans. Relation labels are therefore generated from normalized target
box geometry so the experiment can run on the existing Table Transformer data.
"""
import torch
import torch.nn.functional as F
from torch import nn

from util import box_ops
from util.misc import NestedTensor, nested_tensor_from_tensor_list

from .backbone import build_backbone
from .detr import DETR, MLP, PostProcess, SetCriterion
from .matcher import build_matcher
from .transformer import build_transformer


REL_SAME_ROW = 0
REL_SAME_COLUMN = 1
REL_RIGHT_NEIGHBOR = 2
REL_DOWN_NEIGHBOR = 3
NUM_AUX_RELATIONS = 4
REL_SELF = NUM_AUX_RELATIONS
NUM_EDGE_TYPES = NUM_AUX_RELATIONS + 1

AUX_RELATION_NAMES = {
    REL_SAME_ROW: "same_row",
    REL_SAME_COLUMN: "same_column",
    REL_RIGHT_NEIGHBOR: "right_neighbor",
    REL_DOWN_NEIGHBOR: "down_neighbor",
}

NODE_FEATURE_DIM = 12


def _get_arg(args, name, default):
    return getattr(args, name, default)


def _normalized_rank(values):
    if values.numel() == 0:
        return values
    order = torch.argsort(values)
    ranks = torch.empty_like(values)
    scale = max(values.numel() - 1, 1)
    ranks[order] = torch.arange(values.numel(), device=values.device, dtype=values.dtype) / scale
    return ranks


@torch.no_grad()
def build_aux_node_features(boxes):
    """
    Build the 12-dimensional node feature suggested by the auxiliary-graph note.

    Explicit logical row/column indices are unavailable in the current VOC
    labels, so row_index and col_index are normalized y/x-center ranks.
    row_span and col_span default to 1.
    """
    if boxes.numel() == 0:
        return boxes.new_zeros((0, NODE_FEATURE_DIM))

    boxes = boxes.clamp(0, 1)
    xyxy = box_ops.box_cxcywh_to_xyxy(boxes).clamp(0, 1)
    x1, y1, x2, y2 = xyxy.unbind(-1)
    cx, cy, width, height = boxes.unbind(-1)
    row_index = _normalized_rank(cy)
    col_index = _normalized_rank(cx)
    row_span = torch.ones_like(cx)
    col_span = torch.ones_like(cx)
    return torch.stack(
        [
            x1,
            y1,
            x2,
            y2,
            width,
            height,
            cx,
            cy,
            row_index,
            col_index,
            row_span,
            col_span,
        ],
        dim=-1,
    )


@torch.no_grad()
def build_aux_relation_labels(boxes, row_thr=0.5, col_thr=0.5, neighbor_eps=1e-4):
    """
    Generate same-row, same-column, right-neighbor, and down-neighbor labels.

    This geometry-based fallback approximates the logical relation generation in
    aux_graph_guided_table_structure_recognition.md for the existing structure
    object annotations.
    """
    device = boxes.device
    num_nodes = boxes.shape[0]
    labels = torch.zeros(
        (num_nodes, num_nodes, NUM_AUX_RELATIONS),
        dtype=torch.float32,
        device=device,
    )
    if num_nodes <= 1:
        return labels

    boxes = boxes.clamp(0, 1)
    boxes_xyxy = box_ops.box_cxcywh_to_xyxy(boxes).clamp(0, 1)
    x1, y1, x2, y2 = boxes_xyxy.unbind(-1)
    cx, cy = boxes[:, 0], boxes[:, 1]
    widths = (x2 - x1).clamp(min=1e-6)
    heights = (y2 - y1).clamp(min=1e-6)

    inter_x = (torch.minimum(x2[:, None], x2[None, :]) -
               torch.maximum(x1[:, None], x1[None, :])).clamp(min=0)
    inter_y = (torch.minimum(y2[:, None], y2[None, :]) -
               torch.maximum(y1[:, None], y1[None, :])).clamp(min=0)
    horizontal_overlap = inter_x / torch.minimum(widths[:, None], widths[None, :])
    vertical_overlap = inter_y / torch.minimum(heights[:, None], heights[None, :])
    not_self = ~torch.eye(num_nodes, dtype=torch.bool, device=device)

    same_row = (vertical_overlap > row_thr) & not_self
    same_column = (horizontal_overlap > col_thr) & not_self
    labels[..., REL_SAME_ROW] = same_row.float()
    labels[..., REL_SAME_COLUMN] = same_column.float()

    right_delta = cx[None, :] - cx[:, None]
    right_candidates = same_row & (right_delta > neighbor_eps)
    right_scores = right_delta.masked_fill(~right_candidates, float("inf"))
    right_dist, right_idx = right_scores.min(dim=1)
    right_valid = torch.isfinite(right_dist)
    if right_valid.any():
        src = torch.arange(num_nodes, device=device)[right_valid]
        labels[src, right_idx[right_valid], REL_RIGHT_NEIGHBOR] = 1.0

    down_delta = cy[None, :] - cy[:, None]
    down_candidates = same_column & (down_delta > neighbor_eps)
    down_scores = down_delta.masked_fill(~down_candidates, float("inf"))
    down_dist, down_idx = down_scores.min(dim=1)
    down_valid = torch.isfinite(down_dist)
    if down_valid.any():
        src = torch.arange(num_nodes, device=device)[down_valid]
        labels[src, down_idx[down_valid], REL_DOWN_NEIGHBOR] = 1.0

    return labels


@torch.no_grad()
def build_edge_index_from_relations(relation_labels, include_self_edges=True):
    device = relation_labels.device
    num_nodes = relation_labels.shape[0]
    edge_sources = []
    edge_targets = []
    edge_types = []

    for relation_id in range(NUM_AUX_RELATIONS):
        src, dst = relation_labels[..., relation_id].bool().nonzero(as_tuple=True)
        if src.numel() == 0:
            continue
        edge_sources.append(src)
        edge_targets.append(dst)
        edge_types.append(torch.full_like(src, relation_id, dtype=torch.long))

    if include_self_edges and num_nodes > 0:
        src = torch.arange(num_nodes, device=device)
        edge_sources.append(src)
        edge_targets.append(src)
        edge_types.append(torch.full_like(src, REL_SELF, dtype=torch.long))

    if not edge_sources:
        return (
            torch.empty((2, 0), dtype=torch.long, device=device),
            torch.empty((0,), dtype=torch.long, device=device),
        )

    src = torch.cat(edge_sources)
    dst = torch.cat(edge_targets)
    edge_type = torch.cat(edge_types)
    triples = torch.stack([src, dst, edge_type], dim=1)
    triples = torch.unique(triples, dim=0)
    return triples[:, :2].t().contiguous().long(), triples[:, 2].contiguous().long()


class RelationalGraphLayer(nn.Module):
    """Small dependency-free relational message passing layer."""

    def __init__(self, hidden_dim, num_edge_types=NUM_EDGE_TYPES, dropout=0.1):
        super().__init__()
        self.relation_proj = nn.ModuleList(
            nn.Linear(hidden_dim, hidden_dim, bias=False) for _ in range(num_edge_types)
        )
        self.out_proj = nn.Linear(hidden_dim, hidden_dim)
        self.dropout = nn.Dropout(dropout)
        self.norm_message = nn.LayerNorm(hidden_dim)
        self.ffn = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim * 2, hidden_dim),
        )
        self.norm_ffn = nn.LayerNorm(hidden_dim)

    def forward(self, x, edge_index, edge_type):
        if edge_index.numel() == 0:
            message_out = self.norm_message(x)
            return self.norm_ffn(message_out + self.dropout(self.ffn(message_out)))

        src_all, dst_all = edge_index
        aggregated = torch.zeros_like(x)
        counts = torch.zeros((x.shape[0], 1), dtype=x.dtype, device=x.device)
        for relation_id, relation_proj in enumerate(self.relation_proj):
            mask = edge_type == relation_id
            if not mask.any():
                continue
            src = src_all[mask]
            dst = dst_all[mask]
            message = relation_proj(x[src])
            aggregated.index_add_(0, dst, message)
            counts.index_add_(0, dst, torch.ones((dst.numel(), 1), dtype=x.dtype, device=x.device))

        aggregated = aggregated / counts.clamp(min=1.0)
        x = self.norm_message(x + self.dropout(self.out_proj(aggregated)))
        return self.norm_ffn(x + self.dropout(self.ffn(x)))


class AuxGraphTATR(nn.Module):
    """Table Transformer with a training-only auxiliary graph branch."""

    def __init__(
        self,
        backbone,
        transformer,
        num_classes,
        num_queries,
        aux_loss=False,
        graph_layers=2,
        graph_row_thr=0.5,
        graph_col_thr=0.5,
        graph_dropout=0.1,
        graph_include_self_edges=True,
    ):
        super().__init__()
        self.base = DETR(backbone, transformer, num_classes, num_queries, aux_loss=aux_loss)
        hidden_dim = transformer.d_model
        self.graph_row_thr = graph_row_thr
        self.graph_col_thr = graph_col_thr
        self.graph_include_self_edges = graph_include_self_edges

        self.graph_node_encoder = nn.Sequential(
            nn.Linear(NODE_FEATURE_DIM, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.graph_layers = nn.ModuleList(
            [
                RelationalGraphLayer(hidden_dim, dropout=graph_dropout)
                for _ in range(graph_layers)
            ]
        )
        self.relation_head = MLP(hidden_dim * 4, hidden_dim, NUM_AUX_RELATIONS, 3)
        self.visual_distill_proj = nn.Linear(hidden_dim, hidden_dim)
        self.graph_distill_proj = nn.Linear(hidden_dim, hidden_dim)

    def _graph_embeddings(self, target_boxes):
        node_features = build_aux_node_features(target_boxes)
        relation_labels = build_aux_relation_labels(
            target_boxes,
            row_thr=self.graph_row_thr,
            col_thr=self.graph_col_thr,
        )
        edge_index, edge_type = build_edge_index_from_relations(
            relation_labels,
            include_self_edges=self.graph_include_self_edges,
        )

        x = self.graph_node_encoder(node_features)
        for layer in self.graph_layers:
            x = layer(x, edge_index, edge_type)
        return x, relation_labels, edge_index, edge_type

    def _relation_logits(self, node_embeddings):
        num_nodes = node_embeddings.shape[0]
        if num_nodes == 0:
            return node_embeddings.new_zeros((0, 0, NUM_AUX_RELATIONS))

        source = node_embeddings[:, None, :].expand(num_nodes, num_nodes, -1)
        target = node_embeddings[None, :, :].expand(num_nodes, num_nodes, -1)
        pair_features = torch.cat(
            [source, target, source - target, source * target],
            dim=-1,
        )
        return self.relation_head(pair_features)

    def _build_graph_outputs(self, targets):
        graph_outputs = []
        for target in targets:
            target_boxes = target["boxes"].detach()
            node_embeddings, relation_labels, edge_index, edge_type = self._graph_embeddings(target_boxes)
            graph_outputs.append(
                {
                    "node_embeddings": node_embeddings,
                    "relation_logits": self._relation_logits(node_embeddings),
                    "relation_labels": relation_labels,
                    "edge_index": edge_index,
                    "edge_type": edge_type,
                }
            )
        return graph_outputs

    def forward(self, samples: NestedTensor, targets=None):
        if isinstance(samples, (list, torch.Tensor)):
            samples = nested_tensor_from_tensor_list(samples)
        features, pos = self.base.backbone(samples)

        src, mask = features[-1].decompose()
        assert mask is not None
        hs = self.base.transformer(
            self.base.input_proj(src),
            mask,
            self.base.query_embed.weight,
            pos[-1],
        )[0]

        outputs_class = self.base.class_embed(hs)
        outputs_coord = self.base.bbox_embed(hs).sigmoid()
        out = {"pred_logits": outputs_class[-1], "pred_boxes": outputs_coord[-1]}
        if self.base.aux_loss:
            out["aux_outputs"] = self.base._set_aux_loss(outputs_class, outputs_coord)

        if self.training and targets is not None:
            out["query_features"] = hs[-1]
            out["graph_aux_outputs"] = self._build_graph_outputs(targets)
        return out

    def compute_auxiliary_losses(self, outputs, targets, matcher):
        device = outputs["pred_logits"].device
        zero = outputs["pred_logits"].sum() * 0.0
        graph_outputs = outputs.get("graph_aux_outputs", None)
        if not graph_outputs:
            return {
                "loss_graph_aux": zero,
                "loss_distill": zero,
                "graph_relation_error": zero.detach(),
            }

        relation_losses = []
        relation_errors = []
        for graph_output in graph_outputs:
            logits = graph_output["relation_logits"]
            labels = graph_output["relation_labels"]
            num_nodes = labels.shape[0]
            if num_nodes <= 1:
                continue
            pair_mask = ~torch.eye(num_nodes, dtype=torch.bool, device=device)
            pair_mask = pair_mask.unsqueeze(-1).expand_as(labels)
            relation_losses.append(
                F.binary_cross_entropy_with_logits(logits[pair_mask], labels[pair_mask])
            )
            with torch.no_grad():
                predicted = logits[pair_mask].sigmoid() > 0.5
                relation_errors.append((predicted != labels[pair_mask].bool()).float().mean() * 100)

        if relation_losses:
            loss_graph_aux = torch.stack(relation_losses).mean()
            graph_relation_error = torch.stack(relation_errors).mean()
        else:
            loss_graph_aux = zero
            graph_relation_error = zero.detach()

        indices = matcher(
            {
                "pred_logits": outputs["pred_logits"],
                "pred_boxes": outputs["pred_boxes"],
            },
            targets,
        )
        distill_losses = []
        query_features = outputs["query_features"]
        for batch_idx, (src_idx, tgt_idx) in enumerate(indices):
            if src_idx.numel() == 0:
                continue
            graph_embeddings = graph_outputs[batch_idx]["node_embeddings"]
            if graph_embeddings.numel() == 0:
                continue
            src_idx = src_idx.to(device)
            tgt_idx = tgt_idx.to(device)
            visual = self.visual_distill_proj(query_features[batch_idx, src_idx])
            graph = self.graph_distill_proj(graph_embeddings[tgt_idx]).detach()
            distill_losses.append(F.mse_loss(visual, graph))

        loss_distill = torch.stack(distill_losses).mean() if distill_losses else zero
        return {
            "loss_graph_aux": loss_graph_aux,
            "loss_distill": loss_distill,
            "graph_relation_error": graph_relation_error.detach(),
        }


def build_aux_graph_tatr(args):
    if args.masks:
        raise ValueError("AuxGraphTATR currently supports bbox structure recognition only, not masks.")

    device = torch.device(args.device)
    backbone = build_backbone(args)
    transformer = build_transformer(args)
    model = AuxGraphTATR(
        backbone,
        transformer,
        num_classes=args.num_classes,
        num_queries=args.num_queries,
        aux_loss=args.aux_loss,
        graph_layers=_get_arg(args, "graph_layers", 2),
        graph_row_thr=_get_arg(args, "graph_row_thr", 0.5),
        graph_col_thr=_get_arg(args, "graph_col_thr", 0.5),
        graph_dropout=_get_arg(args, "graph_dropout", 0.1),
        graph_include_self_edges=_get_arg(args, "graph_include_self_edges", True),
    )

    matcher = build_matcher(args)
    weight_dict = {"loss_ce": args.ce_loss_coef, "loss_bbox": args.bbox_loss_coef}
    weight_dict["loss_giou"] = args.giou_loss_coef
    if args.aux_loss:
        aux_weight_dict = {}
        for i in range(args.dec_layers - 1):
            aux_weight_dict.update({k + f"_{i}": v for k, v in weight_dict.items()})
        weight_dict.update(aux_weight_dict)

    losses = ["labels", "boxes", "cardinality"]
    criterion = SetCriterion(
        args.num_classes,
        matcher=matcher,
        weight_dict=weight_dict,
        eos_coef=args.eos_coef,
        losses=losses,
        emphasized_weights=args.emphasized_weights,
    )
    criterion.to(device)
    postprocessors = {"bbox": PostProcess()}
    return model, criterion, postprocessors
