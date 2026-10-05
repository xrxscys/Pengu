import sys
import tempfile
from itertools import count
from pathlib import Path

from pypdf import PdfReader
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from core.pdf_merge import merge_pdfs


class WorkerSignals(QObject):
    finished = Signal(object)  # the function's return value
    failed = Signal(str)       # the error message


class Worker(QRunnable):
    """Runs a function on a background thread so the window never freezes."""

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except Exception as e:
            self.signals.failed.emit(str(e))
        else:
            self.signals.finished.emit(result)


def describe_pdf(path) -> str:
    """Short note shown next to a file in the list: page count or a problem."""
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return "🔒 password protected"
        pages = len(reader.pages)
        return f"{pages} page" if pages == 1 else f"{pages} pages"
    except Exception:
        return "⚠ can't read this file"


class PdfListWidget(QListWidget):
    """A file list that accepts PDFs dropped from Explorer and can be
    reordered by dragging items within it."""

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAcceptDrops(True)

    def add_files(self, paths):
        """Add PDF files to the list; returns how many non-PDFs were skipped."""
        skipped = 0
        for path in paths:
            path = Path(path).resolve()
            if path.suffix.lower() != ".pdf" or not path.is_file():
                skipped += 1
                continue
            item = QListWidgetItem(f"{path.name}  —  {describe_pdf(path)}")
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.addItem(item)
        return skipped

    def paths(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    # Files dragged in from outside arrive as URLs; drags within the list
    # (reordering) are handled by QListWidget itself.
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.add_files(url.toLocalFile() for url in event.mimeData().urls())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class PdfPreview(QWidget):
    """Shows every page of one PDF, scrollable, fitted to the panel width."""

    def __init__(self):
        super().__init__()
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.view)
        self.clear()

    def show_file(self, path, heading):
        self.document.close()
        error = self.document.load(str(path))
        if error == QPdfDocument.Error.IncorrectPassword:
            self.clear(f"{heading}\n🔒 This PDF is password protected and can't be previewed.")
        elif error != QPdfDocument.Error.None_:
            self.clear(f"{heading}\n⚠ This file can't be previewed: it may be damaged or not a real PDF.")
        else:
            pages = self.document.pageCount()
            self.title.setText(f"<b>{heading}</b> — {pages} page{'s' if pages != 1 else ''}")

    def clear(self, message="Select a file to preview it."):
        self.document.close()
        self.title.setText(message)

    def mark_out_of_date(self):
        if "out of date" not in self.title.text():
            self.title.setText(self.title.text() +
                               "<br><span style='color:#b36b00'>⚠ Out of date: the list has changed. "
                               "Click Preview merged result again.</span>")


class MergeTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.showing_merged = False
        self.preview_dir = tempfile.TemporaryDirectory(prefix="toolkit_preview_",
                                                       ignore_cleanup_errors=True)
        self.preview_counter = count(1)

        self.file_list = PdfListWidget()
        model = self.file_list.model()
        for sig in (model.rowsInserted, model.rowsRemoved, model.rowsMoved):
            sig.connect(self.on_list_changed)
        self.file_list.itemSelectionChanged.connect(self.on_selection_changed)

        self.add_btn = QPushButton("Add PDFs…")
        self.remove_btn = QPushButton("Remove")
        self.clear_btn = QPushButton("Clear")
        self.up_btn = QPushButton("Move up")
        self.down_btn = QPushButton("Move down")
        self.swap_btn = QPushButton("Swap")
        self.swap_btn.setToolTip("Select exactly two files to swap their positions.")
        self.preview_btn = QPushButton("Preview merged result")
        self.merge_btn = QPushButton("Merge and save…")
        self.merge_btn.setMinimumHeight(36)
        self.status = QLabel("")
        self.preview = PdfPreview()

        self.add_btn.clicked.connect(self.browse)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.file_list.clear)
        self.up_btn.clicked.connect(lambda: self.move_selected(-1))
        self.down_btn.clicked.connect(lambda: self.move_selected(1))
        self.swap_btn.clicked.connect(self.swap_selected)
        self.preview_btn.clicked.connect(self.preview_merged)
        self.merge_btn.clicked.connect(self.merge)

        file_buttons = QHBoxLayout()
        for btn in (self.add_btn, self.remove_btn, self.clear_btn):
            file_buttons.addWidget(btn)
        order_buttons = QHBoxLayout()
        for btn in (self.up_btn, self.down_btn, self.swap_btn):
            order_buttons.addWidget(btn)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Drag PDF files here or click Add PDFs. "
                      "Drag items, or use the buttons below, to set the order.")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)
        left_layout.addWidget(self.file_list)
        left_layout.addLayout(file_buttons)
        left_layout.addLayout(order_buttons)
        left_layout.addWidget(self.preview_btn)
        left_layout.addWidget(self.merge_btn)
        left_layout.addWidget(self.status)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.preview)
        splitter.setSizes([380, 520])

        QVBoxLayout(self).addWidget(splitter)
        self.update_buttons()

    # ----- list state -----

    def on_list_changed(self, *_):
        if self.showing_merged:
            self.preview.mark_out_of_date()
        elif self.file_list.count() == 0:
            self.preview.clear()
        self.update_buttons()

    def on_selection_changed(self):
        selected = self.file_list.selectedItems()
        if len(selected) == 1:
            item = selected[0]
            self.showing_merged = False
            self.preview.show_file(item.data(Qt.UserRole), Path(item.data(Qt.UserRole)).name)
        self.update_buttons()

    def update_buttons(self):
        busy = self.worker is not None
        selected = len(self.file_list.selectedItems())
        enough_files = self.file_list.count() >= 2
        self.add_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and selected > 0)
        self.clear_btn.setEnabled(not busy and self.file_list.count() > 0)
        self.up_btn.setEnabled(not busy and selected == 1)
        self.down_btn.setEnabled(not busy and selected == 1)
        self.swap_btn.setEnabled(not busy and selected == 2)
        self.preview_btn.setEnabled(not busy and enough_files)
        self.merge_btn.setEnabled(not busy and enough_files)
        self.file_list.setEnabled(not busy)

    # ----- list editing -----

    def browse(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", "", "PDF files (*.pdf)")
        self.file_list.add_files(files)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def move_selected(self, step):
        row = self.file_list.currentRow()
        new_row = row + step
        if row < 0 or not 0 <= new_row < self.file_list.count():
            return
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(new_row, item)
        self.file_list.setCurrentRow(new_row)

    def swap_selected(self):
        rows = sorted(self.file_list.row(i) for i in self.file_list.selectedItems())
        if len(rows) != 2:
            return
        first, second = rows
        # Taking items out briefly leaves one selected, which would switch the
        # preview to that single file; mute selection signals during the swap.
        self.file_list.blockSignals(True)
        second_item = self.file_list.takeItem(second)
        first_item = self.file_list.takeItem(first)
        self.file_list.insertItem(first, second_item)
        self.file_list.insertItem(second, first_item)
        first_item.setSelected(True)
        second_item.setSelected(True)
        self.file_list.blockSignals(False)
        self.update_buttons()

    # ----- merging -----

    def preview_merged(self):
        output = Path(self.preview_dir.name) / f"preview_{next(self.preview_counter)}.pdf"
        self.run_merge(self.file_list.paths(), output, self.on_preview_ready, "Building preview…")

    def merge(self):
        inputs = self.file_list.paths()
        start_dir = str(Path(inputs[0]).parent / "merged.pdf")
        output, _ = QFileDialog.getSaveFileName(self, "Save merged PDF as", start_dir, "PDF files (*.pdf)")
        if not output:
            return  # user cancelled
        output = Path(output).with_suffix(".pdf")

        # Writing over one of the inputs while it's being read would corrupt it.
        if any(output.resolve() == Path(p).resolve() for p in inputs):
            QMessageBox.warning(self, "Choose another name",
                                "The merged file can't replace one of the PDFs being merged.")
            return

        self.run_merge(inputs, output, self.on_saved, f"Merging {len(inputs)} files…")

    def run_merge(self, inputs, output, on_done, message):
        self.worker = Worker(merge_pdfs, inputs, str(output))
        self.worker.signals.finished.connect(on_done)
        self.worker.signals.failed.connect(self.on_failed)
        self.status.setText(message)
        self.update_buttons()
        QThreadPool.globalInstance().start(self.worker)

    def on_preview_ready(self, output_path):
        self.worker = None
        self.file_list.clearSelection()
        self.showing_merged = True
        self.preview.show_file(output_path, "Merged result (not saved yet)")
        self.status.setText("Preview ready. Click Merge and save… to keep it.")
        self.update_buttons()

    def on_saved(self, output_path):
        self.worker = None
        self.update_buttons()
        self.status.setText(f"✓ Saved: {output_path}")
        reply = QMessageBox.information(
            self, "Done", f"Merged PDF saved:\n{output_path}\n\nOpen it now?",
            QMessageBox.Open | QMessageBox.Close,
        )
        if reply == QMessageBox.Open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path)))

    def on_failed(self, message):
        self.worker = None
        self.update_buttons()
        self.status.setText("✗ Merge failed")
        QMessageBox.critical(self, "Merge failed", message)


class ComingSoonTab(QWidget):
    def __init__(self, text):
        super().__init__()
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: gray;")
        QVBoxLayout(self).addWidget(label)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Local File Toolkit")
        self.resize(960, 600)

        tabs = QTabWidget()
        tabs.addTab(ComingSoonTab("Word / Excel → PDF\n\nComing soon (Step 5.3)"), "Convert to PDF")
        tabs.addTab(ComingSoonTab("PDF → Word / Excel\n\nComing soon (Step 5.4)"), "Convert from PDF")
        self.merge_tab = MergeTab()
        tabs.addTab(self.merge_tab, "Merge PDFs")
        tabs.addTab(ComingSoonTab("Files → Markdown\n\nComing soon (Step 5.2)"), "Convert to Markdown")
        tabs.setCurrentWidget(self.merge_tab)
        self.setCentralWidget(tabs)


def launch():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
