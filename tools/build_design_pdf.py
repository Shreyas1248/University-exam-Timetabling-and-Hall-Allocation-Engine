import re
import textwrap
import unicodedata
from math import atan2, cos, sin, pi
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "design.md"
OUTPUT = ROOT / "docs" / "design.pdf"


def source_lines():
    lines = []
    in_mermaid = False
    mermaid_kind = ""
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if text.startswith("```mermaid"):
            in_mermaid = True
            mermaid_kind = ""
            continue
        if in_mermaid:
            if text == "```":
                in_mermaid = False
                title = (
                    "Domain model" if mermaid_kind == "classDiagram"
                    else "Exam lifecycle"
                )
                description = (
                    "Course and Student master records are connected by "
                    "enrolments. Exam Assignments map to HallAssignments; "
                    "physical Halls host them and Invigilators staff them."
                    if mermaid_kind == "classDiagram"
                    else "Registered -> Pending -> Scheduled -> Rescheduled "
                    "-> Finalized. If no feasible session exists, Pending "
                    "-> Unscheduled and the blocking rule is reported."
                )
                lines.extend([(12, title), (10, description)])
            elif text in ("classDiagram", "stateDiagram-v2"):
                mermaid_kind = text
            continue
        if not text:
            lines.append((0, ""))
        elif text.startswith("#"):
            size = 16 if raw.startswith("# ") else 12
            lines.append((size, text.lstrip("#").strip()))
        elif text.startswith("|"):
            if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", text):
                continue
            cells = [cell.strip() for cell in text.strip("|").split("|")]
            lines.append((9, "  |  ".join(cells)))
        elif text.startswith("- "):
            lines.append((10, "- " + text[2:]))
        else:
            lines.append((10, text))
    return lines


def page_content(lines):
    laid_out = []
    for size, text in lines:
        if not text:
            laid_out.append((size, ""))
            continue
        width = 60 if size >= 12 else 92
        for part in textwrap.wrap(
            text,
            width=width,
            subsequent_indent="   ",
            break_long_words=False,
            break_on_hyphens=False,
        ):
            laid_out.append((size, part))

    pages = []
    page = []
    y = 748
    for size, text in laid_out:
        step = 9 if size == 0 else (18 if size >= 12 else 13)
        if y - step < 55:
            pages.append(page)
            page = []
            y = 748
        page.append((size, text, y))
        y -= step
    if page:
        pages.append(page)
    return pages


def _pdf_text(text, x, y, size=9, font="F1"):
    plain = unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore"
    ).decode("ascii")
    escaped = plain.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET"


def _box(commands, x, y, width, height, title, attributes):
    commands.extend([
        "0.8 w",
        f"{x} {y} {width} {height} re S",
        f"{x} {y + height - 23} m {x + width} {y + height - 23} l S",
        _pdf_text(title, x + 8, y + height - 16, 11, "F2"),
    ])
    for index, attribute in enumerate(attributes):
        commands.append(
            _pdf_text(attribute, x + 8, y + height - 39 - index * 14, 8)
        )


def _arrow(start, end):
    x1, y1 = start
    x2, y2 = end
    commands = [f"{x1} {y1} m {x2} {y2} l S"]
    angle = atan2(y2 - y1, x2 - x1)
    for offset in (-pi / 6, pi / 6):
        x3 = x2 - 8 * cos(angle + offset)
        y3 = y2 - 8 * sin(angle + offset)
        commands.append(f"{x3:.1f} {y3:.1f} m {x2} {y2} l S")
    return commands


def _diagram_streams(page_numbers, total_pages):
    domain = [
        _pdf_text("Domain Class Diagram", 50, 750, 16, "F2"),
        _pdf_text("Core records and their relationships", 50, 728, 10),
    ]
    _box(domain, 40, 560, 200, 125, "Course", [
        "course_code, department, semester",
        "credits, duration, exam_type",
    ])
    _box(domain, 372, 560, 200, 125, "Student", [
        "student_id, register_number",
        "programme, semester, needs/consent",
    ])
    _box(domain, 40, 340, 200, 125, "Assignment", [
        "course_code, date, session",
        "duration, enrolled students",
    ])
    _box(domain, 372, 340, 200, 125, "HallAssignment", [
        "date, session, hall_id",
        "courses, seats, extended_end",
    ])
    _box(domain, 40, 120, 200, 125, "Hall", [
        "hall_id, capacity, rows, columns",
        "building, floor",
    ])
    _box(domain, 372, 120, 200, 125, "Invigilator", [
        "invigilator_id, department",
        "weekly limit, unavailable dates",
    ])
    domain.extend(_arrow((240, 625), (372, 625)))
    domain.extend([
        _pdf_text("enrolments", 276, 636, 8),
    ])
    domain.extend(_arrow((140, 560), (140, 465)))
    domain.extend([
        _pdf_text("scheduled as", 149, 510, 8),
    ])
    domain.extend(_arrow((240, 402), (372, 402)))
    domain.extend([
        _pdf_text("allocated into", 276, 413, 8),
    ])
    domain.extend(_arrow((240, 220), (372, 360)))
    domain.extend([
        _pdf_text("hosts", 288, 290, 8),
    ])
    domain.extend(_arrow((472, 340), (472, 245)))
    domain.extend([
        _pdf_text("staffed by", 481, 287, 8),
        _pdf_text("Many-to-many enrolment; one course per assignment; a session "
                  "assignment may use multiple halls.", 50, 82, 9),
        _pdf_text(f"Page {page_numbers[0]} of {total_pages}", 520, 30, 8),
    ])

    state = [
        _pdf_text("Exam Lifecycle State Diagram", 50, 750, 16, "F2"),
        _pdf_text("A change command rebuilds only the affected session(s).", 50, 728, 10),
    ]
    states = [
        (40, 610, "Registered"),
        (240, 610, "Pending"),
        (440, 610, "Scheduled"),
        (240, 430, "Unscheduled"),
        (440, 430, "Rescheduled"),
        (240, 250, "Finalized"),
    ]
    for x, y, label in states:
        state.extend([
            "0.8 w",
            f"{x} {y} 135 55 re S",
            _pdf_text(label, x + 14, y + 22, 10, "F2"),
        ])
    state.extend(_arrow((175, 637), (240, 637)))
    state.append(_pdf_text("validate", 184, 647, 8))
    state.extend(_arrow((375, 637), (440, 637)))
    state.append(_pdf_text("hard rules pass", 378, 647, 8))
    state.extend(_arrow((307, 610), (307, 485)))
    state.append(_pdf_text("no feasible slot", 315, 535, 8))
    state.extend(_arrow((507, 610), (507, 485)))
    state.append(_pdf_text("POSTPONE", 515, 535, 8))
    state.extend(_arrow((307, 430), (307, 305)))
    state.append(_pdf_text("reported", 315, 365, 8))
    state.extend(_arrow((440, 457), (375, 278)))
    state.append(_pdf_text("complete", 400, 355, 8))
    state.extend([
        "1 w",
        "472 665 m 472 696 l 550 696 l 550 665 l S",
        _pdf_text("late registration / hall closure", 468, 704, 8),
        _pdf_text(f"Page {page_numbers[1]} of {total_pages}", 520, 30, 8),
    ])
    state.extend(_arrow((550, 675), (540, 665)))
    return ["\n".join(domain).encode("ascii"), "\n".join(state).encode("ascii")]


def build_pdf(pages):
    objects = []

    def add_object(value):
        body = value.encode("ascii") if isinstance(value, str) else value
        objects.append(body)
        return len(objects)

    add_object("<< /Type /Catalog /Pages 2 0 R >>")
    add_object("")
    regular_font_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )
    bold_font_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    )
    page_ids = []
    total_pages = len(pages) + 2
    for page_number, content in enumerate(pages, 1):
        commands = []
        for size, text, y in content:
            if not text:
                continue
            font_size = 12 if size >= 12 else 9
            font = "F2" if size >= 12 else "F1"
            commands.append(_pdf_text(text, 50, y, font_size, font))
        commands.append(_pdf_text(
            f"Page {page_number} of {total_pages}", 520, 30, 8
        ))
        stream = "\n".join(commands).encode("ascii")
        page_id = len(objects) + 1
        stream_id = page_id + 1
        page_ids.append(page_id)
        add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {regular_font_id} 0 R "
            f"/F2 {bold_font_id} 0 R >> >> "
            f"/Contents {stream_id} 0 R >>"
        )
        add_object(
            b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"\nendstream"
        )

    diagram_pages = _diagram_streams(
        (len(pages) + 1, len(pages) + 2), total_pages
    )
    for stream in diagram_pages:
        page_id = len(objects) + 1
        stream_id = page_id + 1
        page_ids.append(page_id)
        add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {regular_font_id} 0 R "
            f"/F2 {bold_font_id} 0 R >> >> /Contents {stream_id} 0 R >>"
        )
        add_object(
            b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"\nendstream"
        )

    objects[1] = (
        "<< /Type /Pages /Kids ["
        + " ".join(f"{page_id} 0 R" for page_id in page_ids)
        + f"] /Count {len(page_ids)} >>"
    ).encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return pdf


def main():
    pdf = build_pdf(page_content(source_lines()))
    if not pdf.startswith(b"%PDF-1.4") or not pdf.rstrip().endswith(b"%%EOF"):
        raise ValueError("Generated design PDF failed its structure check")
    OUTPUT.write_bytes(pdf)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
