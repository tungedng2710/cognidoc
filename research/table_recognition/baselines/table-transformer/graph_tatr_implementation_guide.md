# Hướng dẫn implement Graph-Enhanced Table Transformer cho Table Structure Recognition

## 1. Mục tiêu

Tài liệu này hướng dẫn cách bổ sung yếu tố graph vào mô hình **Table Transformer Structure Recognition** theo cách đơn giản nhất.

Mục tiêu không phải tạo mô hình SOTA, mà là đánh giá thực nghiệm:

> Nếu thêm graph feature vào Table Transformer thì kết quả table structure recognition tăng được bao nhiêu so với baseline?

Bài toán tập trung vào nhận diện cấu trúc bảng từ ảnh crop của bảng:

- `table row`
- `table column`
- `table column header`
- `table projected row header`
- `table spanning cell`

Không cần xử lý OCR, không cần khôi phục HTML hoàn chỉnh ở giai đoạn đầu.

---

## 2. Ý tưởng tổng quát

Table Transformer gốc hoạt động theo kiểu object detection:

```text
Input table image
    -> CNN backbone
    -> Transformer encoder
    -> Transformer decoder queries
    -> class + bbox prediction
```

Vấn đề là các thành phần bảng không độc lập. Row, column, header và spanning cell có quan hệ hình học rõ ràng với nhau:

- Các row thường xếp từ trên xuống.
- Các column thường xếp từ trái sang phải.
- Header thường nằm phía trên data region.
- Spanning cell thường overlap nhiều row hoặc nhiều column.
- Các bbox trong cùng một bảng thường có alignment tương đối đều.

Vì vậy ta thêm một module graph để học quan hệ giữa các object queries trước khi dự đoán kết quả cuối cùng.

Kiến trúc đơn giản nhất:

```text
Table image
    -> Table Transformer Structure Recognition
    -> Decoder query embeddings
    -> Build graph from predicted boxes/classes
    -> GNN refinement
    -> Refined class + refined bbox
```

---

## 3. Baseline cần có trước

Trước khi thêm graph, cần chạy được baseline Table Transformer.

Checkpoint đề xuất:

```text
microsoft/table-transformer-structure-recognition
```

Input:

```text
Ảnh crop của bảng
```

Output:

```text
class logits: [B, num_queries, num_classes + 1]
pred boxes:   [B, num_queries, 4]
```

Trong đó bbox thường ở dạng normalized:

```text
center_x, center_y, width, height
```

Baseline cần đánh giá được các chỉ số:

- mAP cho object detection.
- AP theo từng class: row, column, header, spanning cell.
- Optional: cell reconstruction accuracy nếu có bước hậu xử lý grid.

Ở giai đoạn đầu, chỉ cần so sánh mAP/AP là đủ.

---

## 4. Phiên bản graph đơn giản nhất

### 4.1. Vị trí thêm graph

Thêm graph sau Transformer decoder:

```text
Decoder hidden states -> GNN -> Prediction heads
```

Không sửa CNN backbone, encoder hoặc decoder gốc. Cách này dễ fine-tune từ checkpoint pretrained.

### 4.2. Node là gì?

Dùng cách đơn giản nhất:

> Mỗi decoder query là một node.

Nếu `num_queries = 100`, mỗi ảnh có 100 node.

Node feature gồm:

```text
node_feature_i = query_embedding_i + bbox_embedding_i + class_embedding_i
```

Trong đó:

- `query_embedding_i`: hidden state từ decoder.
- `bbox_i`: bbox dự đoán ban đầu của query.
- `class_prob_i`: xác suất class dự đoán ban đầu.

Cách đơn giản hóa khi implement:

```text
node_feature_i = query_embedding_i
```

Sau đó mới thử thêm bbox/class feature trong ablation.

### 4.3. Edge là gì?

Dùng graph đơn giản, không cần annotate edge thủ công.

Tạo edge tự động dựa trên bbox dự đoán hoặc bbox ground truth.

Dùng 3 loại edge là đủ:

1. `near`: hai bbox gần nhau.
2. `same_row_like`: hai bbox overlap mạnh theo trục y.
3. `same_col_like`: hai bbox overlap mạnh theo trục x.

Không nên thêm quá nhiều relation ở phiên bản đầu.

### 4.4. Công thức tạo edge

Với mỗi cặp bbox `box_i`, `box_j`:

```text
box = [cx, cy, w, h]
```

Chuyển về:

```text
[xmin, ymin, xmax, ymax]
```

Tính:

```text
horizontal_overlap = intersection_x / min(width_i, width_j)
vertical_overlap   = intersection_y / min(height_i, height_j)
center_distance    = distance(center_i, center_j)
```

Quy tắc đơn giản:

```text
if vertical_overlap > 0.5:
    add edge type same_row_like

if horizontal_overlap > 0.5:
    add edge type same_col_like

if center_distance in k nearest neighbors:
    add edge type near
```

Ban đầu nên dùng `k = 8` hoặc `k = 10` cho nearest neighbors.

---

## 5. Mô hình đề xuất

### 5.1. Baseline

```text
TableTransformerForObjectDetection
```

Output:

```text
logits, pred_boxes
```

### 5.2. Graph model

```text
TableTransformerForObjectDetection
    -> decoder hidden states
    -> graph construction
    -> 2-layer GNN
    -> refined logits + refined boxes
```

### 5.3. GNN nên dùng loại nào?

Để đơn giản, dùng một trong hai lựa chọn:

#### Option A: GAT

Dễ implement, không cần edge type phức tạp.

```text
node features -> GAT layer -> GAT layer -> refined node features
```

Phù hợp cho phiên bản đầu tiên.

#### Option B: R-GCN

Dùng nếu muốn tận dụng edge type:

- `near`
- `same_row_like`
- `same_col_like`

R-GCN phù hợp hơn về mặt ý tưởng, nhưng code phức tạp hơn GAT một chút.

Khuyến nghị:

> Bắt đầu với GAT. Nếu kết quả có tín hiệu tốt, thử R-GCN sau.

---

## 6. Cấu trúc thư mục đề xuất

```text
graph-tatr/
├── configs/
│   ├── baseline.yaml
│   └── graph_tatr.yaml
├── data/
│   ├── train.json
│   ├── val.json
│   └── images/
├── src/
│   ├── dataset.py
│   ├── model_baseline.py
│   ├── model_graph_tatr.py
│   ├── graph_builder.py
│   ├── train.py
│   ├── evaluate.py
│   └── utils_box.py
├── scripts/
│   ├── convert_annotations.py
│   ├── generate_graph_labels.py
│   └── run_ablation.sh
└── README.md
```

---

## 7. Format nhãn đơn giản

Không cần annotation graph thủ công lúc đầu.

Chỉ cần annotation object detection giống DETR/COCO-style.

Mỗi ảnh crop bảng có danh sách objects:

```json
{
  "image_id": "table_0001",
  "file_name": "table_0001.png",
  "width": 1000,
  "height": 600,
  "objects": [
    {
      "id": "row_0",
      "label": "table row",
      "bbox": [0, 0, 1000, 80]
    },
    {
      "id": "row_1",
      "label": "table row",
      "bbox": [0, 80, 1000, 160]
    },
    {
      "id": "col_0",
      "label": "table column",
      "bbox": [0, 0, 250, 600]
    },
    {
      "id": "col_1",
      "label": "table column",
      "bbox": [250, 0, 500, 600]
    },
    {
      "id": "header_0",
      "label": "table column header",
      "bbox": [0, 0, 1000, 80]
    }
  ]
}
```

Bbox dùng format:

```text
[xmin, ymin, xmax, ymax]
```

Khi đưa vào Table Transformer training, convert sang format normalized:

```text
[cx, cy, w, h]
```

---

## 8. Cách làm nhãn đơn giản

### 8.1. Nhãn cần có

Với mỗi ảnh bảng, annotate các vùng:

| Label | Ý nghĩa | Bắt buộc |
|---|---|---|
| `table row` | Toàn bộ vùng của một hàng | Có |
| `table column` | Toàn bộ vùng của một cột | Có |
| `table column header` | Vùng header cột | Có nếu bảng có header |
| `table projected row header` | Header dạng hàng, thường là cột đầu mô tả các dòng | Không bắt buộc |
| `table spanning cell` | Ô gộp nhiều hàng/cột | Có nếu xuất hiện |

Để đơn giản, giai đoạn đầu chỉ cần 3 label:

```text
table row
table column
table column header
```

Sau khi pipeline ổn, thêm:

```text
table spanning cell
table projected row header
```

### 8.2. Quy tắc annotate row

Mỗi row bbox nên bao phủ toàn bộ chiều ngang của bảng.

Ví dụ bảng có 4 hàng:

```text
row_0: từ y của hàng 1 đến y của hàng 2
row_1: từ y của hàng 2 đến y của hàng 3
row_2: từ y của hàng 3 đến y của hàng 4
row_3: từ y của hàng 4 đến đáy bảng
```

Không annotate từng cell là row. Row là cả dải ngang.

### 8.3. Quy tắc annotate column

Mỗi column bbox nên bao phủ toàn bộ chiều cao của bảng.

Ví dụ bảng có 3 cột:

```text
col_0: từ x trái bảng đến boundary cột 1
col_1: từ boundary cột 1 đến boundary cột 2
col_2: từ boundary cột 2 đến phải bảng
```

Column là cả dải dọc.

### 8.4. Quy tắc annotate column header

Column header là vùng header phía trên của bảng.

Nếu bảng có một dòng header:

```text
header bbox = bbox của dòng header
```

Nếu bảng có nhiều dòng header:

```text
header bbox = vùng bao toàn bộ các dòng header
```

Không cần annotate từng header cell ở phiên bản đầu.

### 8.5. Quy tắc annotate spanning cell

Spanning cell là ô gộp nhiều cột hoặc nhiều hàng.

Annotate bbox đúng vùng ô gộp:

```text
spanning cell bbox = vùng visual của ô merge
```

Nếu không chắc, có thể bỏ qua spanning cell ở phiên bản đầu để giảm nhiễu nhãn.

---

## 9. Sinh graph label tự động

Mục tiêu: không cần người annotate relation.

Từ object bbox ground truth, sinh relation pseudo-label.

Ví dụ:

```json
{
  "edges": [
    {
      "source": "row_0",
      "target": "row_1",
      "type": "near"
    },
    {
      "source": "row_0",
      "target": "header_0",
      "type": "same_row_like"
    },
    {
      "source": "col_0",
      "target": "col_1",
      "type": "near"
    }
  ]
}
```

Tuy nhiên, với kiến trúc đơn giản nhất, relation label không bắt buộc. Graph chỉ cần edge index để truyền message.

Có 2 chế độ build graph:

### Chế độ 1: Build graph từ prediction

Dùng bbox dự đoán ban đầu của Table Transformer để tạo edge.

Ưu điểm:

- Dùng được khi inference.
- End-to-end hơn.

Nhược điểm:

- Đầu training prediction còn nhiễu.

### Chế độ 2: Build graph từ ground truth khi training

Dùng bbox ground truth để tạo edge trong training.

Ưu điểm:

- Graph sạch hơn.
- Dễ học hơn lúc đầu.

Nhược điểm:

- Train/inference có mismatch.

Khuyến nghị thực nghiệm:

```text
Experiment 1: graph from predicted boxes
Experiment 2: graph from ground-truth boxes during training, predicted boxes during inference
```

Nếu chỉ muốn đơn giản nhất, dùng graph từ predicted boxes cho cả training và inference.

---

## 10. Pseudo-code build graph

```python
import torch


def box_cxcywh_to_xyxy(boxes):
    cx, cy, w, h = boxes.unbind(-1)
    x1 = cx - 0.5 * w
    y1 = cy - 0.5 * h
    x2 = cx + 0.5 * w
    y2 = cy + 0.5 * h
    return torch.stack([x1, y1, x2, y2], dim=-1)


def interval_overlap(a1, a2, b1, b2):
    inter = torch.clamp(torch.minimum(a2, b2) - torch.maximum(a1, b1), min=0)
    return inter


def build_graph_from_boxes(boxes, k=8, row_thr=0.5, col_thr=0.5):
    """
    boxes: Tensor[num_queries, 4], normalized cxcywh
    return:
        edge_index: LongTensor[2, num_edges]
        edge_type: LongTensor[num_edges]

    edge_type:
        0 = near
        1 = same_row_like
        2 = same_col_like
    """
    boxes_xyxy = box_cxcywh_to_xyxy(boxes)
    x1, y1, x2, y2 = boxes_xyxy.unbind(-1)
    widths = torch.clamp(x2 - x1, min=1e-6)
    heights = torch.clamp(y2 - y1, min=1e-6)

    centers = boxes[:, :2]
    dist = torch.cdist(centers, centers)

    edges = []
    edge_types = []
    n = boxes.shape[0]

    # kNN edges
    knn = dist.topk(k=k + 1, largest=False).indices[:, 1:]
    for i in range(n):
        for j in knn[i].tolist():
            edges.append([i, j])
            edge_types.append(0)

    # overlap-based edges
    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            inter_x = interval_overlap(x1[i], x2[i], x1[j], x2[j])
            inter_y = interval_overlap(y1[i], y2[i], y1[j], y2[j])

            h_overlap = inter_x / torch.minimum(widths[i], widths[j])
            v_overlap = inter_y / torch.minimum(heights[i], heights[j])

            if v_overlap > row_thr:
                edges.append([i, j])
                edge_types.append(1)

            if h_overlap > col_thr:
                edges.append([i, j])
                edge_types.append(2)

    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    edge_type = torch.tensor(edge_types, dtype=torch.long)

    return edge_index, edge_type
```

---

## 11. Pseudo-code model GraphTATR

Ví dụ tối giản:

```python
import torch
import torch.nn as nn
from transformers import TableTransformerForObjectDetection


class SimpleGNNLayer(nn.Module):
    def __init__(self, hidden_dim):
        super().__init__()
        self.msg = nn.Linear(hidden_dim, hidden_dim)
        self.update = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim)
        )

    def forward(self, x, edge_index):
        # x: [N, D]
        src, dst = edge_index
        messages = self.msg(x[src])

        agg = torch.zeros_like(x)
        agg.index_add_(0, dst, messages)

        deg = torch.zeros(x.size(0), device=x.device)
        deg.index_add_(0, dst, torch.ones_like(dst, dtype=torch.float))
        agg = agg / deg.clamp(min=1).unsqueeze(-1)

        out = self.update(torch.cat([x, agg], dim=-1))
        return out


class GraphTATR(nn.Module):
    def __init__(self, checkpoint, num_classes):
        super().__init__()
        self.base = TableTransformerForObjectDetection.from_pretrained(
            checkpoint,
            ignore_mismatched_sizes=True
        )

        hidden_dim = self.base.config.d_model

        self.gnn1 = SimpleGNNLayer(hidden_dim)
        self.gnn2 = SimpleGNNLayer(hidden_dim)

        self.class_head = nn.Linear(hidden_dim, num_classes + 1)
        self.bbox_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 4),
            nn.Sigmoid()
        )

    def forward(self, pixel_values, pixel_mask=None):
        outputs = self.base.model(
            pixel_values=pixel_values,
            pixel_mask=pixel_mask
        )

        # [B, Q, D]
        query_features = outputs.last_hidden_state

        # initial prediction from original heads
        init_logits = self.base.class_labels_classifier(query_features)
        init_boxes = self.base.bbox_predictor(query_features).sigmoid()

        batch_logits = []
        batch_boxes = []

        for b in range(query_features.size(0)):
            x = query_features[b]
            boxes = init_boxes[b].detach()

            edge_index, edge_type = build_graph_from_boxes(boxes)
            edge_index = edge_index.to(x.device)

            x = self.gnn1(x, edge_index)
            x = self.gnn2(x, edge_index)

            refined_logits = self.class_head(x)
            refined_boxes = self.bbox_head(x)

            batch_logits.append(refined_logits)
            batch_boxes.append(refined_boxes)

        return {
            "logits": torch.stack(batch_logits, dim=0),
            "pred_boxes": torch.stack(batch_boxes, dim=0),
            "init_logits": init_logits,
            "init_boxes": init_boxes
        }
```

Ghi chú:

- Đây là pseudo-code tối giản, chưa bao gồm loss DETR Hungarian matching.
- Trong implementation thật, nên tái sử dụng loss function của Hugging Face/DETR nếu có thể.
- Có thể train graph head trước, sau đó fine-tune toàn bộ model.

---

## 12. Loss function đơn giản

Dùng lại DETR loss cho output sau GNN:

```text
L = CE(class) + L1(box) + GIoU(box)
```

Nếu muốn ổn định hơn:

```text
L = L_initial + L_refined
```

Trong đó:

```text
L_initial: loss từ output gốc của Table Transformer
L_refined: loss từ output sau GNN
```

Tổng loss:

```text
L = L_initial + lambda_graph * L_refined
```

Giá trị khởi đầu:

```text
lambda_graph = 1.0
```

Nếu graph làm training không ổn định, dùng:

```text
lambda_graph = 0.5
```

---

## 13. Chiến lược training đơn giản

### Stage 1: Train baseline

Fine-tune Table Transformer gốc trên dataset.

```text
model = table-transformer-structure-recognition
train = normal DETR training
```

Lưu kết quả:

```text
baseline_mAP
baseline_AP_row
baseline_AP_column
baseline_AP_header
baseline_AP_spanning_cell
```

### Stage 2: Freeze base, train graph head

Freeze backbone + transformer của Table Transformer.

Chỉ train:

```text
GNN layers
refined class head
refined bbox head
```

Mục tiêu: kiểm tra graph module có đem thêm thông tin hữu ích không.

### Stage 3: Fine-tune end-to-end

Unfreeze một phần hoặc toàn bộ model.

Có thể thử:

```text
A. unfreeze decoder + graph
B. unfreeze full model + graph
```

Không nên bắt đầu bằng full fine-tune vì dễ nhiễu và khó biết graph có thật sự giúp không.

---

## 14. Các thí nghiệm ablation cần chạy

Mục tiêu chính là đo graph feature tăng bao nhiêu so với baseline.

Nên chạy tối thiểu các cấu hình sau:

| Experiment | Mô tả |
|---|---|
| E0 | Baseline Table Transformer |
| E1 | Baseline + GNN, node feature chỉ dùng decoder embedding |
| E2 | Baseline + GNN, node feature dùng decoder embedding + bbox embedding |
| E3 | Baseline + GNN, edge chỉ dùng kNN |
| E4 | Baseline + GNN, edge dùng kNN + same-row-like + same-col-like |
| E5 | Baseline + GNN, freeze base |
| E6 | Baseline + GNN, fine-tune decoder + graph |

Bảng kết quả mong muốn:

| Model | mAP | AP row | AP column | AP header | AP span | Ghi chú |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | TATR gốc |
| + GNN kNN | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | Edge đơn giản |
| + GNN geometry edges | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | kNN + overlap |
| + GNN fine-tune decoder | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | Unfreeze decoder |

Chỉ cần kết quả tăng nhẹ nhưng ổn định là đủ chứng minh graph có ích.

Ví dụ kỳ vọng thực tế:

```text
Baseline mAP: 0.78
GraphTATR mAP: 0.80
Improvement: +2.0 points
```

Không nên kỳ vọng tăng quá lớn nếu dataset nhỏ hoặc annotation còn nhiễu.

---

## 15. Metric đánh giá

### 15.1. Object detection metric

Bắt buộc:

```text
mAP@[0.50:0.95]
AP@0.50
AP per class
```

AP per class rất quan trọng vì graph có thể chỉ giúp một số class:

- Row/column có thể tăng ít vì baseline đã mạnh.
- Header/spanning cell có thể tăng nhiều hơn vì cần context.

### 15.2. Structure-level metric

Nếu có thời gian, thêm metric đơn giản:

```text
row_count_accuracy
column_count_accuracy
header_detection_f1
spanning_cell_f1
```

Ví dụ:

```text
row_count_accuracy = số bảng predict đúng số row / tổng số bảng
column_count_accuracy = số bảng predict đúng số column / tổng số bảng
```

Không bắt buộc phải dùng TEDS ở giai đoạn đầu vì cần reconstruct HTML khá phức tạp.

---

## 16. Cách chia dataset

Dataset nhỏ vẫn có thể làm ablation.

Gợi ý:

```text
train: 70%
val:   15%
test:  15%
```

Nếu dữ liệu ít:

```text
train: 80%
val:   10%
test:  10%
```

Không để các crop từ cùng một document xuất hiện ở cả train và test. Nếu không, kết quả sẽ bị optimistic.

Nên split theo document trước, sau đó mới lấy table crop.

---

## 17. Checklist annotation

Trước khi train, kiểm tra:

- [ ] Bbox không vượt khỏi ảnh.
- [ ] `xmin < xmax`, `ymin < ymax`.
- [ ] Row bbox phủ ngang gần hết bảng.
- [ ] Column bbox phủ dọc gần hết bảng.
- [ ] Header bbox nằm trong vùng bảng.
- [ ] Class label thống nhất tên.
- [ ] Không trộn format `xyxy` và `xywh`.
- [ ] Khi normalize bbox, dùng đúng width/height của ảnh crop.

Các lỗi annotation thường làm model graph tệ đi:

- Row chỉ annotate quanh text, không phủ cả hàng.
- Column chỉ annotate quanh text, không phủ cả cột.
- Header annotate từng cell lẻ nhưng training lại kỳ vọng header region.
- Spanning cell annotate không nhất quán.

---

## 18. Quy trình thực nghiệm đề xuất

```text
Step 1: Chuẩn bị table crop images
Step 2: Annotate row/column/header boxes
Step 3: Convert annotation sang DETR format
Step 4: Fine-tune Table Transformer baseline
Step 5: Evaluate baseline
Step 6: Thêm graph module sau decoder
Step 7: Train graph module với base frozen
Step 8: Evaluate GraphTATR
Step 9: Fine-tune decoder + graph nếu cần
Step 10: So sánh metric và viết ablation report
```

---

## 19. Kết quả cần báo cáo

Report nên có các bảng sau.

### 19.1. Overall result

| Model | mAP | AP@50 | AP row | AP column | AP header | AP span |
|---|---:|---:|---:|---:|---:|---:|
| Baseline TATR |  |  |  |  |  |  |
| GraphTATR |  |  |  |  |  |  |
| Difference |  |  |  |  |  |  |

### 19.2. Ablation graph construction

| Graph edge | mAP | AP header | AP span | Ghi chú |
|---|---:|---:|---:|---|
| No graph |  |  |  | Baseline |
| kNN only |  |  |  | Gần nhau theo center |
| Row/col overlap |  |  |  | Dùng geometry relation |
| kNN + row/col overlap |  |  |  | Full simple graph |

### 19.3. Training strategy

| Strategy | mAP | Ghi chú |
|---|---:|---|
| Freeze base, train graph only |  | Kiểm tra graph head |
| Fine-tune decoder + graph |  | Cân bằng ổn định/hiệu quả |
| Fine-tune full model |  | Có thể overfit nếu data nhỏ |

---

## 20. Kết luận triển khai

Cách đơn giản nhất để thêm graph feature vào Table Transformer là:

```text
Dùng decoder queries làm graph nodes.
Dùng bbox prediction để tạo graph edges tự động.
Dùng GNN 2 layer để refine node embeddings.
Dự đoán lại class và bbox sau GNN.
So sánh với baseline bằng mAP/AP per class.
```

Phiên bản đầu tiên không cần:

- OCR.
- HTML reconstruction.
- Relation annotation thủ công.
- Graph Transformer phức tạp.
- Cell-level semantic parsing.

Chỉ cần chứng minh graph giúp cải thiện nhận diện cấu trúc hình học của bảng.

Nếu kết quả tăng rõ ở `header` hoặc `spanning cell`, đây là tín hiệu tốt vì các class này phụ thuộc nhiều vào context và quan hệ giữa object hơn row/column thông thường.

---

## 21. Tên mô hình đề xuất

Có thể đặt tên thử nghiệm là:

```text
GraphTATR: Graph-Enhanced Table Transformer for Table Structure Recognition
```

Hoặc ngắn hơn:

```text
TATR-GNN
```
