import re
import textwrap
import unicodedata
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


def build_pdf(pages):
    objects = []

    def add_object(value):
        body = value.encode("ascii") if isinstance(value, str) else value
        objects.append(body)
        return len(objects)

    add_object("<< /Type /Catalog /Pages 2 0 R >>")
    add_object("")
    font_id = add_object(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )
    page_ids = []
    for page_number, content in enumerate(pages, 1):
        commands = []
        for size, text, y in content:
            if not text:
                continue
            plain = unicodedata.normalize("NFKD", text).encode(
                "ascii", "ignore"
            ).decode("ascii")
            escaped = plain.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            font_size = 12 if size >= 12 else 9
            commands.append(
                f"BT /F1 {font_size} Tf 50 {y} Td ({escaped}) Tj ET"
            )
        commands.append(
            f"BT /F1 8 Tf 520 30 Td (Page {page_number} of {len(pages)}) Tj ET"
        )
        stream = "\n".join(commands).encode("ascii")
        page_id = len(objects) + 1
        stream_id = page_id + 1
        page_ids.append(page_id)
        add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {stream_id} 0 R >>"
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
