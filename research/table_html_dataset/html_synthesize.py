import argparse
import random
from pathlib import Path

from tqdm import tqdm


TOPICS = ["Doanh thu", "Tồn kho", "Thử nghiệm lâm sàng", "Khảo sát", "Sản xuất", "Ngân sách", "Chất lượng", "Vận chuyển"]
REGIONS = ["Miền Bắc", "Miền Nam", "Miền Trung", "Đông Bắc", "Tây Bắc", "Đông Nam Bộ", "Tây Nguyên", "Đồng bằng sông Cửu Long"]
METRICS = ["Thực hiện", "Kế hoạch", "Chênh lệch", "Quý 1", "Quý 2", "Quý 3", "Quý 4", "Ghi chú"]
STATUSES = ["Đã duyệt", "Đang chờ", "Chậm tiến độ", "Cần rà soát", "Hoàn thành", "Tạm dừng"]
RISK_LEVELS = ["Thấp", "Trung bình", "Cao"]


def make_cell(rng: random.Random, row: int, col: int) -> str:
    choices = [
        f"{rng.randint(10, 999):,}".replace(",", "."),
        f"{rng.uniform(1, 99):.1f}%".replace(".", ","),
        f"{rng.choice(REGIONS)}-{row + 1}",
        f"Rủi ro {rng.choice(RISK_LEVELS)}",
        rng.choice(STATUSES),
        f"Ghi chú dài cho mục {row + 1}.{col + 1}, nội dung có thể xuống dòng",
    ]
    return rng.choice(choices)


def synthesize_table(index: int, rng: random.Random) -> str:
    rows = rng.randint(18, 45)
    cols = rng.randint(6, 12)
    topic = rng.choice(TOPICS)
    table_class = "borderless" if rng.random() < 0.35 else "bordered"
    html = [
        "<style>",
        ".borderless th, .borderless td { border: 0 !important; border-bottom: 1px solid #e5e7eb !important; }",
        ".borderless { border-collapse: separate; border-spacing: 0 3px; }",
        ".borderless th { background: #f8fafc; }",
        "</style>",
        f'<table class="{table_class}"><caption>Báo cáo {topic.lower()} {index:03d}</caption>',
    ]
    html.append("<thead>")
    html.append(f'<tr><th rowspan="2">Nhóm</th><th rowspan="2">Hạng mục</th><th colspan="{cols}">Chỉ tiêu theo dõi</th></tr>')
    html.append("<tr>" + "".join(f"<th>{METRICS[c % len(METRICS)]}</th>" for c in range(cols)) + "</tr>")
    html.append("</thead><tbody>")
    r = 0
    while r < rows:
        span = min(rng.randint(2, 5), rows - r)
        html.append("<tr>")
        html.append(f'<td rowspan="{span}">Bộ phận {rng.choice(REGIONS)}</td>')
        html.append(f"<td>Mục {r + 1}</td>")
        c = 0
        while c < cols:
            if rng.random() < 0.08 and c < cols - 1:
                html.append(f'<td colspan="2">{make_cell(rng, r, c)}</td>')
                c += 1
            else:
                html.append(f"<td>{make_cell(rng, r, c)}</td>")
            c += 1
        html.append("</tr>")
        for rr in range(1, span):
            html.append(f"<tr><td>Mục {r + rr + 1}</td>")
            html.extend(f"<td>{make_cell(rng, r + rr, c)}</td>" for c in range(cols))
            html.append("</tr>")
        r += span
    html.append("</tbody></table>")
    return "\n".join(html)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create synthetic complicated table HTML samples.")
    parser.add_argument("--output-dir", type=Path, default=Path("synthetic_html"))
    parser.add_argument("--num-samples", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for i in tqdm(range(args.num_samples), desc="Synthesizing HTML"):
        (args.output_dir / f"table_{i:04d}.html").write_text(synthesize_table(i, rng), encoding="utf-8")


if __name__ == "__main__":
    main()
