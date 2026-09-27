from pathlib import Path

from pypdf import PdfWriter


def merge_pdfs(pdf_paths: list[str], output_path: str = "merged.pdf") -> Path:
    if not pdf_paths:
        raise ValueError("No PDF files given.")

    writer = PdfWriter()
    for path in pdf_paths:
        if not Path(path).exists():
            raise FileNotFoundError(path)
        writer.append(path)  # append() preserves bookmarks; add_page() does not

    output_path = Path(output_path)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path