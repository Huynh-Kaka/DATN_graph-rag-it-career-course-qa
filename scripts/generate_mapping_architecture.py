from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def draw_box(draw, rect, title, lines, fill, outline="#1f2937"):
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle(rect, radius=14, fill=fill, outline=outline, width=2)
    font_title = ImageFont.load_default()
    font_body = ImageFont.load_default()
    draw.text((x1 + 12, y1 + 10), title, fill="#111827", font=font_title)

    y = y1 + 34
    for line in lines:
        draw.text((x1 + 12, y), f"- {line}", fill="#111827", font=font_body)
        y += 16


def draw_arrow(draw, start, end, color="#2563eb"):
    draw.line([start, end], fill=color, width=3)
    ex, ey = end
    draw.polygon([(ex, ey), (ex - 10, ey - 6), (ex - 10, ey + 6)], fill=color)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_path = root / "design" / "xlsx_to_neo4j_architecture.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (1800, 980), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()

    draw.text((28, 22), "XLSX to Neo4j Data Mapping Architecture", fill="#0f172a", font=title_font)

    # Left: Excel source
    draw_box(
        draw,
        (40, 90, 560, 910),
        "Excel Workbook: bo du lieu.xlsx",
        [
            "career",
            "competency_type",
            "programming_language/framework/platform/tool/knowledge/softskill/certification",
            "career_competency_map",
            "subject/program/level/website/organization/instructor/subtitle",
            "course",
            "course_competency_map",
        ],
        fill="#ecfeff",
    )

    # Middle: ETL process
    draw_box(
        draw,
        (650, 150, 1180, 840),
        "Python ETL: scripts/ingest.py",
        [
            "Read sheets using openpyxl",
            "Normalize headers and rows",
            "Create Neo4j constraints (optional --reset-graph)",
            "UNWIND in batches (default 500)",
            "MERGE typed skill nodes + property color",
            "MERGE NEED_* / TEACH_* from map tables",
        ],
        fill="#eff6ff",
    )

    # Right: Graph model
    draw_box(
        draw,
        (1270, 90, 1760, 910),
        "Neo4j Graph",
        [
            "Nodes: Career, Industry, Taxonomy, CompetencyType",
            "Nodes: Knowledge, Tool, Platform, Framework, ...",
            "Nodes: Course, Subject, Program, Level",
            "Nodes: Website, Organization, Instructor, Subtitle",
            "Rels: IN_INDUSTRY, IN_TAXONOMY, OF_TYPE",
            "Rels: NEED_KNOW, NEED_TOOL, NEED_LANG, TEACH_*",
            "Rels: IN_SUBJECT, IN_PROGRAM, AT_LEVEL, ...",
        ],
        fill="#ecfdf5",
    )

    draw_arrow(draw, (560, 500), (650, 500))
    draw_arrow(draw, (1180, 500), (1270, 500))

    # Bottom execution flow
    draw.rounded_rectangle((80, 900, 1720, 960), radius=12, fill="#f8fafc", outline="#94a3b8", width=2)
    flow_text = (
        "Execution Flow: docker compose up -d neo4j  ->  "
        "python scripts/ingest.py --xlsx-path data/... --batch-size 500  ->  "
        "Validate in Neo4j Browser"
    )
    draw.text((98, 922), flow_text, fill="#0f172a", font=ImageFont.load_default())

    image.save(out_path)
    print(f"Generated architecture image: {out_path}")


if __name__ == "__main__":
    main()
