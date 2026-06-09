# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
Graph-enhanced DETR model for Table Transformer structure recognition.

The graph stage follows graph_tatr_implementation_guide.md:
- decoder queries are graph nodes
- edges are built from initial predicted boxes
- a small GNN refines decoder node features
- final class and box heads predict the refined detections
"""
import torch
import torch.nn.functional as F
from torch import nn

from util.misc import NestedTensor, nested_tensor_from_tensor_list

from .backbone import build_backbone
from .detr import DETR, MLP, PostProcess, SetCriterion
from .matcher import build_matcher
from .transformer import build_transformer


EDGE_NEAR = 0
EDGE_SAME_ROW_LIKE = 1
EDGE_SAME_COL_LIKE = 2
EDGE_SELF = 3
NUM_EDGE_TYPES = 4


def _get_arg(args, name, default):
    return getattr(args, name, default)


def box_cxcywh_to_xyxy(boxes):
    cx, cy, w, h = boxes.unbind(-1)
    return torch.stack(
        [
            cx - 0.5 * w,
            cy - 0.5 * h,
            cx + 0.5 * w,
            cy + 0.5 * h,
        ],
        dim=-1,
    )


def _append_edges(edge_sources, edge_targets, edge_types, src, dst, edge_type):
    if src.numel() == 0:
        return
    edge_sources.append(src)
    edge_targets.append(dst)
    edge_types.append(torch.full_like(src, int(edge_type), dtype=torch.long))


@torch.no_grad()
def build_graph_from_boxes(
    boxes,
    k=8,
    row_thr=0.5,
    col_thr=0.5,
    use_knn_edges=True,
    use_geometry_edges=True,
    bidirectional_knn=True,
    include_self_edges=True,
):
    """
    Build a query graph from normalized cxcywh boxes.

    Returns:
        edge_index: LongTensor[2, num_edges], source nodes then destination nodes
        edge_type: LongTensor[num_edges]
    """
    device = boxes.device
    num_nodes = boxes.shape[0]
    if num_nodes == 0:
        empty_index = torch.empty((2, 0), dtype=torch.long, device=device)
        empty_type = torch.empty((0,), dtype=torch.long, device=device)
        return empty_index, empty_type

    boxes = boxes.clamp(0, 1)
    edge_sources = []
    edge_targets = []
    edge_types = []

    if use_knn_edges and num_nodes > 1 and k > 0:
        k_eff = min(int(k), num_nodes - 1)
        centers = boxes[:, :2]
        dist = torch.cdist(centers, centers)
        self_mask = torch.eye(num_nodes, dtype=torch.bool, device=device)
        dist = dist.masked_fill(self_mask, float("inf"))
        knn = dist.topk(k=k_eff, largest=False).indices

        src = torch.arange(num_nodes, device=device).view(-1, 1).expand_as(knn).reshape(-1)
        dst = knn.reshape(-1)
        _append_edges(edge_sources, edge_targets, edge_types, src, dst, EDGE_NEAR)
        if bidirectional_knn:
            _append_edges(edge_sources, edge_targets, edge_types, dst, src, EDGE_NEAR)

    if use_geometry_edges and num_nodes > 1:
        boxes_xyxy = box_cxcywh_to_xyxy(boxes)
        x1, y1, x2, y2 = boxes_xyxy.unbind(-1)
        widths = (x2 - x1).clamp(min=1e-6)
        heights = (y2 - y1).clamp(min=1e-6)

        inter_x = (torch.minimum(x2[:, None], x2[None, :]) -
                   torch.maximum(x1[:, None], x1[None, :])).clamp(min=0)
        inter_y = (torch.minimum(y2[:, None], y2[None, :]) -
                   torch.maximum(y1[:, None], y1[None, :])).clamp(min=0)

        horizontal_overlap = inter_x / torch.minimum(widths[:, None], widths[None, :])
        vertical_overlap = inter_y / torch.minimum(heights[:, None], heights[None, :])
        not_self = ~torch.eye(num_nodes, dtype=torch.bool, device=device)

        row_src, row_dst = ((vertical_overlap > row_thr) & not_self).nonzero(as_tuple=True)
        col_src, col_dst = ((horizontal_overlap > col_thr) & not_self).nonzero(as_tuple=True)
        _append_edges(edge_sources, edge_targets, edge_types, row_src, row_dst, EDGE_SAME_ROW_LIKE)
        _append_edges(edge_sources, edge_targets, edge_types, col_src, col_dst, EDGE_SAME_COL_LIKE)

    if include_self_edges:
        src = torch.arange(num_nodes, device=device)
        _append_edges(edge_sources, edge_targets, edge_types, src, src, EDGE_SELF)

    if not edge_sources:
        empty_index = torch.empty((2, 0), dtype=torch.long, device=device)
        empty_type = torch.empty((0,), dtype=torch.long, device=device)
        return empty_index, empty_type

    src = torch.cat(edge_sources)
    dst = torch.cat(edge_targets)
    edge_type = torch.cat(edge_types)

    triples = torch.stack([src, dst, edge_type], dim=1)
    triples = torch.unique(triples, dim=0)
    edge_index = triples[:, :2].t().contiguous()
    edge_type = triples[:, 2].contiguous()
    return edge_index.long(), edge_type.long()


def edge_softmax(scores, dst, num_nodes):
    """Softmax over incoming edges for each destination node."""
    weights = torch.zeros_like(scores)
    for node_id in torch.unique(dst):
        mask = dst == node_id
        weights[mask] = F.softmax(scores[mask], dim=0)
    return weights


class GraphAttentionLayer(nn.Module):
    """Small dependency-free graph attention layer for query refinement."""

    def __init__(self, hidden_dim, dropout=0.1, num_edge_types=NUM_EDGE_TYPES):
        super().__init__()
        self.node_proj = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.attn_src = nn.Parameter(torch.empty(hidden_dim))
        self.attn_dst = nn.Parameter(torch.empty(hidden_dim))
        self.edge_bias = nn.Embedding(num_edge_types, 1)
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
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.node_proj.weight)
        nn.init.xavier_uniform_(self.out_proj.weight)
        nn.init.zeros_(self.out_proj.bias)
        nn.init.xavier_uniform_(self.attn_src.unsqueeze(0))
        nn.init.xavier_uniform_(self.attn_dst.unsqueeze(0))
        nn.init.zeros_(self.edge_bias.weight)

    def forward(self, x, edge_index, edge_type):
        if edge_index.numel() == 0:
            message_out = self.norm_message(x)
            return self.norm_ffn(message_out + self.dropout(self.ffn(message_out)))

        src, dst = edge_index
        h = self.node_proj(x)
        scores = (h[src] * self.attn_src).sum(dim=-1) + (h[dst] * self.attn_dst).sum(dim=-1)
        scores = scores + self.edge_bias(edge_type).squeeze(-1)
        scores = F.leaky_relu(scores, negative_slope=0.2)

        weights = edge_softmax(scores, dst, x.shape[0])
        messages = h[src] * self.dropout(weights).unsqueeze(-1)
        aggregated = torch.zeros_like(x)
        aggregated.index_add_(0, dst, messages)

        x = self.norm_message(x + self.dropout(self.out_proj(aggregated)))
        return self.norm_ffn(x + self.dropout(self.ffn(x)))


class GraphTATR(nn.Module):
    """Table Transformer with a post-decoder graph refinement module."""

    def __init__(
        self,
        backbone,
        transformer,
        num_classes,
        num_queries,
        aux_loss=False,
        graph_layers=2,
        graph_k=8,
        graph_row_thr=0.5,
        graph_col_thr=0.5,
        graph_use_knn_edges=True,
        graph_use_geometry_edges=True,
        graph_bidirectional_knn=True,
        graph_include_self_edges=True,
        graph_dropout=0.1,
        graph_use_bbox_features=False,
        graph_use_class_features=False,
    ):
        super().__init__()
        self.base = DETR(backbone, transformer, num_classes, num_queries, aux_loss=aux_loss)
        hidden_dim = transformer.d_model
        self.num_classes = num_classes

        self.graph_k = graph_k
        self.graph_row_thr = graph_row_thr
        self.graph_col_thr = graph_col_thr
        self.graph_use_knn_edges = graph_use_knn_edges
        self.graph_use_geometry_edges = graph_use_geometry_edges
        self.graph_bidirectional_knn = graph_bidirectional_knn
        self.graph_include_self_edges = graph_include_self_edges
        self.graph_use_bbox_features = graph_use_bbox_features
        self.graph_use_class_features = graph_use_class_features

        self.bbox_feature_embed = MLP(4, hidden_dim, hidden_dim, 2) if graph_use_bbox_features else None
        self.class_feature_embed = (
            nn.Linear(num_classes + 1, hidden_dim) if graph_use_class_features else None
        )
        self.gnn_layers = nn.ModuleList(
            [GraphAttentionLayer(hidden_dim, dropout=graph_dropout) for _ in range(graph_layers)]
        )
        self.refined_class_embed = nn.Linear(hidden_dim, num_classes + 1)
        self.refined_bbox_embed = MLP(hidden_dim, hidden_dim, 4, 3)
        self.initialize_refinement_heads_from_base()

    def initialize_refinement_heads_from_base(self):
        self.refined_class_embed.load_state_dict(self.base.class_embed.state_dict())
        self.refined_bbox_embed.load_state_dict(self.base.bbox_embed.state_dict())

    def _node_features(self, query_features, init_logits, init_boxes):
        node_features = query_features
        if self.bbox_feature_embed is not None:
            node_features = node_features + self.bbox_feature_embed(init_boxes.detach())
        if self.class_feature_embed is not None:
            class_probs = init_logits.detach().softmax(dim=-1)
            node_features = node_features + self.class_feature_embed(class_probs)
        return node_features

    def forward(self, samples: NestedTensor):
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

        init_logits_all = self.base.class_embed(hs)
        init_boxes_all = self.base.bbox_embed(hs).sigmoid()
        init_logits = init_logits_all[-1]
        init_boxes = init_boxes_all[-1]

        query_features = hs[-1]
        node_features = self._node_features(query_features, init_logits, init_boxes)
        refined_features = []
        for batch_idx in range(node_features.shape[0]):
            edge_index, edge_type = build_graph_from_boxes(
                init_boxes[batch_idx].detach(),
                k=self.graph_k,
                row_thr=self.graph_row_thr,
                col_thr=self.graph_col_thr,
                use_knn_edges=self.graph_use_knn_edges,
                use_geometry_edges=self.graph_use_geometry_edges,
                bidirectional_knn=self.graph_bidirectional_knn,
                include_self_edges=self.graph_include_self_edges,
            )
            x = node_features[batch_idx]
            for layer in self.gnn_layers:
                x = layer(x, edge_index, edge_type)
            refined_features.append(x)
        refined_features = torch.stack(refined_features, dim=0)

        outputs_class = self.refined_class_embed(refined_features)
        outputs_coord = self.refined_bbox_embed(refined_features).sigmoid()

        initial_outputs = {"pred_logits": init_logits, "pred_boxes": init_boxes}
        if self.base.aux_loss:
            initial_outputs["aux_outputs"] = self.base._set_aux_loss(init_logits_all, init_boxes_all)

        return {
            "pred_logits": outputs_class,
            "pred_boxes": outputs_coord,
            "initial_outputs": initial_outputs,
        }


def build_graph_tatr(args):
    if args.masks:
        raise ValueError("GraphTATR currently supports bbox structure recognition only, not masks.")

    device = torch.device(args.device)
    backbone = build_backbone(args)
    transformer = build_transformer(args)
    model = GraphTATR(
        backbone,
        transformer,
        num_classes=args.num_classes,
        num_queries=args.num_queries,
        aux_loss=args.aux_loss,
        graph_layers=_get_arg(args, "graph_layers", 2),
        graph_k=_get_arg(args, "graph_k", 8),
        graph_row_thr=_get_arg(args, "graph_row_thr", 0.5),
        graph_col_thr=_get_arg(args, "graph_col_thr", 0.5),
        graph_use_knn_edges=_get_arg(args, "graph_use_knn_edges", True),
        graph_use_geometry_edges=_get_arg(args, "graph_use_geometry_edges", True),
        graph_bidirectional_knn=_get_arg(args, "graph_bidirectional_knn", True),
        graph_include_self_edges=_get_arg(args, "graph_include_self_edges", True),
        graph_dropout=_get_arg(args, "graph_dropout", 0.1),
        graph_use_bbox_features=_get_arg(args, "graph_use_bbox_features", False),
        graph_use_class_features=_get_arg(args, "graph_use_class_features", False),
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
