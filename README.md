# Pengu
A local-first desktop tool for converting between Office documents, PDFs, and Markdown. Everything runs on the user's own machine; no file is ever uploaded anywhere.

# Local File Toolkit

Convert between Word, Excel, PDF and Markdown, and merge PDFs — on your own computer.

**This tool runs entirely on your machine. No file is ever uploaded anywhere.**
There is no telemetry and no network access.

## Features
- Word / Excel → PDF
- PDF → Word or Excel
- Merge PDFs
- PDF, Word, Excel, PowerPoint → Markdown

## Requirements
- Python 3.12
- [LibreOffice](https://www.libreoffice.org/download/download/) (for Word/Excel → PDF), installed separately

## Setup
```
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## License
AGPL-3.0 — see [LICENSE](LICENSE). Third-party licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).