import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="toolkit",
        description="Local File Toolkit — convert and merge files locally.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("merge", help="Merge several PDFs into one")
    p.add_argument("inputs", nargs="+", help="PDF files, in order")
    p.add_argument("-o", "--output", default="merged.pdf")

    p = sub.add_parser("to-md", help="Convert files to Markdown")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-d", "--outdir", default=None)

    p = sub.add_parser("to-pdf", help="Convert Word/Excel files to PDF")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-d", "--outdir", default=None)

    p = sub.add_parser("from-pdf", help="Convert PDFs to Word or Excel")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--to", choices=["word", "excel"], required=True)
    p.add_argument("-d", "--outdir", default=None)

    args = parser.parse_args()

    if args.command == "merge":
        from core.pdf_merge import merge_pdfs
        print(f"Saved: {merge_pdfs(args.inputs, args.output)}")
        return

    if args.command == "to-md":
        from core.to_markdown import convert_to_markdown as fn
    elif args.command == "to-pdf":
        from core.pdf_convert import office_to_pdf as fn
    else:
        from core.from_pdf import pdf_to_word, pdf_to_excel
        fn = pdf_to_word if args.to == "word" else pdf_to_excel

    for path in args.inputs:
        try:
            print(f"✓ {path} -> {fn(path, args.outdir)}")
        except Exception as e:
            print(f"✗ {path} failed: {e}")


if __name__ == "__main__":
    main()