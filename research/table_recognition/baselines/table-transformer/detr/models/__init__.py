# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from .detr import build
from .detr_multi import build as build_multi
from .aux_graph_tatr import build_aux_graph_tatr
from .graph_tatr import build_graph_tatr


def build_model(args):
    return build(args)

def build_model_multi(args):
    return build_multi(args)

def build_graph_model(args):
    return build_graph_tatr(args)

def build_aux_graph_model(args):
    return build_aux_graph_tatr(args)
