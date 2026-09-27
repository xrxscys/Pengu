import pytest
from pypdf import PdfReader, PdfWriter

from core.pdf_merge import merge_pdfs


def make_pdf(path, pages):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)


def test_merge_combines_all_pages(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2)
    b = make_pdf(tmp_path / "b.pdf", 3)
    out = merge_pdfs([a, b], tmp_path / "merged.pdf")
    assert len(PdfReader(out).pages) == 5


def test_merge_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        merge_pdfs([str(tmp_path / "nope.pdf")], tmp_path / "out.pdf")


def test_merge_empty_list_raises(tmp_path):
    with pytest.raises(ValueError):
        merge_pdfs([], tmp_path / "out.pdf")