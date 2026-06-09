"""
Generate GraphTATR pseudo-labels from PASCAL VOC table-structure annotations.

The generated graph follows the edge construction described by GraphTATR:
- nodes are table-structure objects from the XML annotation
- edge type 0: near, from k nearest box centers
- edge type 1: same_row_like, from strong vertical overlap
- edge type 2: same_col_like, from strong horizontal overlap
- edge type 3: self

This script does not change the original VOC labels. It writes sidecar JSON files
that can be used for graph-supervised experiments or debugging ground-truth graph
construction.
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


CLASS_MAP = {
    "table": 0,
    "table column": 1,
    "table row": 2,
    "table column header": 3,
    "table projected row header": 4,
    "table spanning cell": 5,
    "no object": 6,
}

EDGE_TYPE_NAMES = {
    0: "near",
    1: "same_row_like",
    2: "same_col_like",
    3: "self",
}

SCHEMA_VERSION = "graph-tatr-pseudo-labels-v1"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate GraphTATR graph pseudo-labels for a VOC structure dataset."
    )
    parser.add_argument(
        "--data-root",
        required=True,
        type=Path,
        help="Dataset root containing images/, train/, val/, test/, and *_filelist.txt.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to <data-root>/graph_labels.",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "val", "test"],
        help="Dataset splits to process.",
    )
    parser.add_argument("--k", type=int, default=8, help="k for near kNN edges.")
    parser.add_argument(
        "--row-thr",
        type=float,
        default=0.5,
        help="Vertical overlap threshold for same_row_like edges.",
    )
    parser.add_argument(
        "--col-thr",
        type=float,
        default=0.5,
        help="Horizontal overlap threshold for same_col_like edges.",
    )
    parser.add_argument(
        "--no-knn-edges",
        action="store_true",
        help="Disable near kNN edges.",
    )
    parser.add_argument(
        "--no-geometry-edges",
        action="store_true",
        help="Disable same_row_like and same_col_like edges.",
    )
    parser.add_argument(
        "--no-bidirectional-knn",
        action="store_true",
        help="Do not add reverse near edges.",
    )
    parser.add_argument(
        "--no-self-edges",
        action="store_true",
        help="Do not add self-loop edges.",
    )
    parser.add_argument(
        "--include-edge-objects",
        action="store_true",
        help="Also write verbose edge objects with relation names.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Fail if a filelist entry is missing instead of skipping it.",
    )
    return parser.parse_args()


def read_split_xml_paths(data_root, split, fail_on_missing=False):
    split_dir = data_root / split
    filelist_path = data_root / f"{split}_filelist.txt"
    if filelist_path.exists():
        names = []
        with filelist_path.open("r", encoding="utf-8") as infile:
            for line in infile:
                name = Path(line.strip()).name
                if not name:
                    continue
                if not name.endswith(".xml"):
                    name = f"{Path(name).stem}.xml"
                names.append(name)
    else:
        names = sorted(path.name for path in split_dir.glob("*.xml"))

    xml_paths = []
    missing = []
    for name in names:
        xml_path = split_dir / name
        if xml_path.exists():
            xml_paths.append(xml_path)
        else:
            missing.append(str(xml_path))

    if missing and fail_on_missing:
        raise FileNotFoundError(
            "Missing XML files from filelist:\n" + "\n".join(missing[:20])
        )
    if missing:
        print(f"[{split}] skipped {len(missing)} missing XML file(s)")
    return xml_paths


def require_text(element, path, xml_path):
    found = element.find(path)
    if found is None or found.text is None:
        raise ValueError(f"{xml_path}: missing required XML field {path}")
    return found.text


def parse_float(element, path, xml_path):
    return float(require_text(element, path, xml_path))


def parse_int(element, path, xml_path):
    return int(float(require_text(element, path, xml_path)))


def read_voc_xml(xml_path):
    root = ET.parse(xml_path).getroot()
    filename = require_text(root, "filename", xml_path)
    width = parse_int(root, "size/width", xml_path)
    height = parse_int(root, "size/height", xml_path)

    objects = []
    for idx, object_elem in enumerate(root.findall("object")):
        label = require_text(object_elem, "name", xml_path)
        if label not in CLASS_MAP:
            raise ValueError(f"{xml_path}: unsupported label {label!r}")

        bbox = [
            parse_float(object_elem, "bndbox/xmin", xml_path),
            parse_float(object_elem, "bndbox/ymin", xml_path),
            parse_float(object_elem, "bndbox/xmax", xml_path),
            parse_float(object_elem, "bndbox/ymax", xml_path),
        ]
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ValueError(f"{xml_path}: invalid bbox for object {idx}: {bbox}")

        objects.append(
            {
                "node_id": f"obj_{idx:04d}",
                "index": idx,
                "label": label,
                "class_id": CLASS_MAP[label],
                "bbox": [round(value, 4) for value in bbox],
                "bbox_norm_cxcywh": xyxy_to_norm_cxcywh(bbox, width, height),
                "area": round((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 4),
            }
        )

    return {
        "filename": filename,
        "width": width,
        "height": height,
        "objects": objects,
    }


def xyxy_to_norm_cxcywh(bbox, width, height):
    xmin, ymin, xmax, ymax = bbox
    cx = ((xmin + xmax) / 2.0) / width
    cy = ((ymin + ymax) / 2.0) / height
    w = (xmax - xmin) / width
    h = (ymax - ymin) / height
    return [round(cx, 8), round(cy, 8), round(w, 8), round(h, 8)]


def clamp01(value):
    return max(0.0, min(1.0, value))


def cxcywh_to_xyxy(box):
    cx, cy, w, h = [clamp01(value) for value in box]
    return [
        cx - 0.5 * w,
        cy - 0.5 * h,
        cx + 0.5 * w,
        cy + 0.5 * h,
    ]


def center_distance(box_a, box_b):
    return math.dist(box_a[:2], box_b[:2])


def interval_overlap(a1, a2, b1, b2):
    return max(0.0, min(a2, b2) - max(a1, b1))


def add_edge(edges, source, target, edge_type):
    edges.add((int(source), int(target), int(edge_type)))


def build_graph_from_norm_boxes(
    boxes,
    k=8,
    row_thr=0.5,
    col_thr=0.5,
    use_knn_edges=True,
    use_geometry_edges=True,
    bidirectional_knn=True,
    include_self_edges=True,
):
    num_nodes = len(boxes)
    edges = set()

    if use_knn_edges and num_nodes > 1 and k > 0:
        k_eff = min(int(k), num_nodes - 1)
        for source, source_box in enumerate(boxes):
            distances = []
            for target, target_box in enumerate(boxes):
                if source == target:
                    continue
                distances.append((center_distance(source_box, target_box), target))
            distances.sort(key=lambda item: (item[0], item[1]))
            for _, target in distances[:k_eff]:
                add_edge(edges, source, target, 0)
                if bidirectional_knn:
                    add_edge(edges, target, source, 0)

    if use_geometry_edges and num_nodes > 1:
        boxes_xyxy = [cxcywh_to_xyxy(box) for box in boxes]
        widths = [max(box[2] - box[0], 1e-6) for box in boxes_xyxy]
        heights = [max(box[3] - box[1], 1e-6) for box in boxes_xyxy]

        for source, source_box in enumerate(boxes_xyxy):
            for target, target_box in enumerate(boxes_xyxy):
                if source == target:
                    continue

                inter_x = interval_overlap(
                    source_box[0],
                    source_box[2],
                    target_box[0],
                    target_box[2],
                )
                inter_y = interval_overlap(
                    source_box[1],
                    source_box[3],
                    target_box[1],
                    target_box[3],
                )
                horizontal_overlap = inter_x / min(widths[source], widths[target])
                vertical_overlap = inter_y / min(heights[source], heights[target])

                if vertical_overlap > row_thr:
                    add_edge(edges, source, target, 1)
                if horizontal_overlap > col_thr:
                    add_edge(edges, source, target, 2)

    if include_self_edges:
        for node_idx in range(num_nodes):
            add_edge(edges, node_idx, node_idx, 3)

    return sorted(edges, key=lambda edge: (edge[0], edge[1], edge[2]))


def make_graph_label(data_root, split, xml_path, args):
    annotation = read_voc_xml(xml_path)
    record_id = xml_path.stem
    objects = annotation["objects"]
    boxes = [obj["bbox_norm_cxcywh"] for obj in objects]
    edges = build_graph_from_norm_boxes(
        boxes,
        k=args.k,
        row_thr=args.row_thr,
        col_thr=args.col_thr,
        use_knn_edges=not args.no_knn_edges,
        use_geometry_edges=not args.no_geometry_edges,
        bidirectional_knn=not args.no_bidirectional_knn,
        include_self_edges=not args.no_self_edges,
    )

    edge_index = [
        [source for source, _, _ in edges],
        [target for _, target, _ in edges],
    ]
    edge_type = [edge_type for _, _, edge_type in edges]

    graph_label = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "split": split,
        "source_xml": str(xml_path.relative_to(data_root)),
        "image": {
            "file_name": f"images/{annotation['filename']}",
            "width": annotation["width"],
            "height": annotation["height"],
        },
        "class_map": CLASS_MAP,
        "edge_type_names": {str(key): value for key, value in EDGE_TYPE_NAMES.items()},
        "graph_config": {
            "k": args.k,
            "row_thr": args.row_thr,
            "col_thr": args.col_thr,
            "use_knn_edges": not args.no_knn_edges,
            "use_geometry_edges": not args.no_geometry_edges,
            "bidirectional_knn": not args.no_bidirectional_knn,
            "include_self_edges": not args.no_self_edges,
            "bbox_source": "ground_truth",
            "bbox_format_for_graph": "cxcywh_norm",
        },
        "target": {
            "labels": [obj["class_id"] for obj in objects],
            "boxes": boxes,
            "boxes_format": "cxcywh_norm",
        },
        "nodes": objects,
        "edge_index": edge_index,
        "edge_type": edge_type,
    }

    if args.include_edge_objects:
        graph_label["edges"] = [
            {
                "source": source,
                "target": target,
                "type": edge_type,
                "relation": EDGE_TYPE_NAMES[edge_type],
            }
            for source, target, edge_type in edges
        ]

    return graph_label


def json_dump(path, payload, pretty=False):
    with path.open("w", encoding="utf-8") as outfile:
        if pretty:
            json.dump(payload, outfile, indent=2, sort_keys=True)
            outfile.write("\n")
        else:
            json.dump(payload, outfile, separators=(",", ":"), sort_keys=True)
            outfile.write("\n")


def write_schema(output_dir, args):
    schema = {
        "schema_version": SCHEMA_VERSION,
        "description": "GraphTATR pseudo-labels generated from PASCAL VOC table-structure annotations.",
        "node_source": "VOC object annotations",
        "target": {
            "labels": "List[int], Table Transformer structure class IDs.",
            "boxes": "List[[cx, cy, w, h]], normalized by image width/height.",
        },
        "edge_index": "[[source_node_indices], [target_node_indices]]",
        "edge_type": "List[int], aligned with edge_index columns.",
        "class_map": CLASS_MAP,
        "edge_type_names": {str(key): value for key, value in EDGE_TYPE_NAMES.items()},
        "default_graph_config": {
            "k": args.k,
            "row_thr": args.row_thr,
            "col_thr": args.col_thr,
            "use_knn_edges": not args.no_knn_edges,
            "use_geometry_edges": not args.no_geometry_edges,
            "bidirectional_knn": not args.no_bidirectional_knn,
            "include_self_edges": not args.no_self_edges,
        },
    }
    json_dump(output_dir / "schema.json", schema, pretty=True)


def main():
    args = parse_args()
    data_root = args.data_root.resolve()
    output_dir = (args.output_dir or (data_root / "graph_labels")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_schema(output_dir, args)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "data_root": str(data_root),
        "output_dir": str(output_dir),
        "splits": {},
        "total_files": 0,
        "total_nodes": 0,
        "total_edges": 0,
        "edge_type_names": {str(key): value for key, value in EDGE_TYPE_NAMES.items()},
    }

    for split in args.splits:
        split_output_dir = output_dir / split
        split_output_dir.mkdir(parents=True, exist_ok=True)

        xml_paths = read_split_xml_paths(
            data_root, split, fail_on_missing=args.fail_on_missing
        )
        split_filelist = []
        node_label_counts = Counter()
        edge_type_counts = Counter()
        split_node_count = 0
        split_edge_count = 0

        for xml_path in xml_paths:
            graph_label = make_graph_label(data_root, split, xml_path, args)
            output_path = split_output_dir / f"{xml_path.stem}.json"
            json_dump(output_path, graph_label, pretty=args.pretty)
            split_filelist.append(f"{xml_path.stem}.json")

            node_label_counts.update(node["label"] for node in graph_label["nodes"])
            edge_type_counts.update(graph_label["edge_type"])
            split_node_count += len(graph_label["nodes"])
            split_edge_count += len(graph_label["edge_type"])

        with (output_dir / f"{split}_filelist.txt").open("w", encoding="utf-8") as outfile:
            for name in split_filelist:
                outfile.write(f"{name}\n")

        split_summary = {
            "files": len(split_filelist),
            "nodes": split_node_count,
            "edges": split_edge_count,
            "node_label_counts": dict(sorted(node_label_counts.items())),
            "edge_type_counts": {
                EDGE_TYPE_NAMES[key]: value
                for key, value in sorted(edge_type_counts.items())
            },
        }
        summary["splits"][split] = split_summary
        summary["total_files"] += split_summary["files"]
        summary["total_nodes"] += split_summary["nodes"]
        summary["total_edges"] += split_summary["edges"]

        print(
            f"[{split}] files={split_summary['files']} "
            f"nodes={split_summary['nodes']} edges={split_summary['edges']}"
        )

    json_dump(output_dir / "summary.json", summary, pretty=True)
    print(
        "wrote graph labels to {} (files={}, nodes={}, edges={})".format(
            output_dir,
            summary["total_files"],
            summary["total_nodes"],
            summary["total_edges"],
        )
    )


if __name__ == "__main__":
    main()
