"""Isolated, non-production Qt library/details experiment. No personal profile.

Requires PySide6-Essentials in a separate venv. It does not implement importing,
OCR, persistence, recovery, or the complete Tk app; timings are not app parity.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=50_000)
    parser.add_argument('--repetitions', type=int, default=100)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    import PySide6
    from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer
    from PySide6.QtGui import QAccessible, QColor, QIcon, QPixmap
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                  QSplitter, QLineEdit, QListView, QLabel, QPushButton)
    qt_import_ms = (time.perf_counter() - started) * 1000
    from core.library_view_model import LibraryViewIndex
    from tools.benchmark_catalog import synthetic_catalog
    from tools.benchmark_ui import process_metrics

    prepared_start = time.perf_counter()
    rows = synthetic_catalog(args.size)
    prepared = LibraryViewIndex(rows)
    prepared_ms = (time.perf_counter() - prepared_start) * 1000
    app = QApplication([])
    icons = []
    for color in ('#557859', '#577f96', '#bc9357', '#597f7a'):
        pixmap = QPixmap(144, 206)
        pixmap.fill(QColor(color))
        icons.append(QIcon(pixmap))

    class Model(QAbstractListModel):
        def __init__(self):
            super().__init__()
            self.rows = prepared.filter()

        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)

        def data(self, index, role=Qt.ItemDataRole.DisplayRole):
            if not index.isValid() or index.row() >= len(self.rows):
                return None
            row = self.rows[index.row()]
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
                return row['titulo'] + '\n' + row['autor_mostrar']
            if role == Qt.ItemDataRole.DecorationRole:
                return icons[index.row() % 4]
            if role == Qt.ItemDataRole.ToolTipRole:
                return row['ruta']

        def search(self, query):
            filtered = prepared.filter(query)
            self.beginResetModel()
            self.rows = filtered
            self.endResetModel()

    window = QWidget()
    window.setWindowTitle('ManageYourLibrary — Qt experimental aislado')
    window.resize(1280, 820)
    layout = QVBoxLayout(window)
    search = QLineEdit()
    search.setPlaceholderText('Buscar en mi biblioteca…')
    search.setAccessibleName('Buscar en mi biblioteca')
    search.setMinimumHeight(48)
    layout.addWidget(search)
    splitter = QSplitter()
    layout.addWidget(splitter)
    sidebar = QWidget()
    sidebar_layout = QVBoxLayout(sidebar)
    for label in ('Biblioteca', 'Autores', 'Series', 'Etiquetas', 'Favoritos', 'Importar'):
        sidebar_layout.addWidget(QPushButton(label))
    sidebar_layout.addStretch()
    splitter.addWidget(sidebar)
    view = QListView()
    view.setAccessibleName('Biblioteca de prueba')
    view.setUniformItemSizes(True)
    view.setViewMode(QListView.ViewMode.IconMode)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setMovement(QListView.Movement.Static)
    view.setLayoutMode(QListView.LayoutMode.Batched)
    view.setBatchSize(250)
    view.setIconSize(QSize(144, 206))
    view.setGridSize(QSize(174, 266))
    model = Model()
    view.setModel(model)
    splitter.addWidget(view)
    details = QWidget()
    detail_layout = QVBoxLayout(details)
    title = QLabel('Selecciona un libro')
    title.setWordWrap(True)
    detail_layout.addWidget(title)
    path = QLineEdit()
    path.setReadOnly(True)
    path.setAccessibleName('Ruta completa')
    detail_layout.addWidget(path)
    favorite = QPushButton('Favorito (prueba sin persistencia)')
    favorite.setCheckable(True)
    detail_layout.addWidget(favorite)
    detail_layout.addStretch()
    open_button = QPushButton('Abrir (desactivado en la prueba)')
    open_button.setEnabled(False)
    detail_layout.addWidget(open_button)
    splitter.addWidget(details)
    splitter.setSizes([200, 740, 340])
    search.textChanged.connect(model.search)

    def selected(current, previous):
        if current.isValid() and current.row() < len(model.rows):
            row = model.rows[current.row()]
            title.setText(row['titulo'] + '\n' + row['autor_mostrar'])
            path.setText(row['ruta'])
    view.selectionModel().currentChanged.connect(selected)
    dark = False

    def theme():
        nonlocal dark
        dark = not dark
        bg, fg, card = ('#22201e', '#eee5d9', '#302b27') if dark else ('#f8f6f1', '#2d2a27', '#fffdf9')
        app.setStyleSheet(f'QWidget {{background:{bg};color:{fg};font-size:14px;}} '
                           f'QLineEdit,QPushButton {{background:{card};border:1px solid #9b8270;'
                           'border-radius:8px;padding:8px;} QListView {border:0;}')
    theme()
    window.show()
    if args.preview:
        return app.exec()
    measurements, heartbeats = {}, []
    previous = time.perf_counter()

    def heartbeat():
        nonlocal previous
        now = time.perf_counter()
        heartbeats.append((now - previous) * 1000)
        previous = now
    timer = QTimer()
    timer.timeout.connect(heartbeat)
    timer.start(16)
    tasks = []
    for index in range(args.repetitions):
        tasks.extend([
            ('search', lambda index=index: search.setText('Title 4242' if index % 2 else '')),
            ('selection', lambda: view.setCurrentIndex(model.index(min(4, max(0, model.rowCount()-1)), 0))),
            ('resize', lambda index=index: splitter.setSizes([200, 640 if index % 2 else 740, 340])),
            ('theme', theme),
        ])
    cpu_start = time.process_time()
    run_start = time.perf_counter()

    def run_next():
        if tasks:
            name, callback = tasks.pop(0)
            start = time.perf_counter()
            callback()
            measurements.setdefault(name, []).append((time.perf_counter() - start) * 1000)
            QTimer.singleShot(120, run_next)
            return
        accessible = {}
        for name, widget in [('search', search), ('favorite', favorite), ('library', view), ('path', path)]:
            interface = QAccessible.queryAccessibleInterface(widget)
            accessible[name] = {'role': str(interface.role()), 'name': interface.text(QAccessible.Text.Name)} if interface else None
        report = {'framework': 'Qt isolated prototype, NOT feature parity', 'qt_version': PySide6.__version__,
                  'size': args.size, 'qt_import_ms': round(qt_import_ms, 2), 'prepare_ms': round(prepared_ms, 2),
                  'callbacks': {name: {'samples': len(values), 'median_ms': round(statistics.median(values), 2),
                    'p95_ms': round(sorted(values)[int((len(values)-1)*.95)], 2), 'max_ms': round(max(values), 2)}
                    for name, values in measurements.items()}, 'heartbeat_max_ms': round(max(heartbeats, default=0), 2),
                  'process_cpu_seconds': round(time.process_time()-cpu_start, 2),
                  'interaction_seconds': round(time.perf_counter()-run_start, 2), 'memory': process_metrics(),
                  'accessible_qt_interfaces': accessible, 'widget_count': len(window.findChildren(QWidget)),
                  'shared_cover_images': len(icons), 'model_rows': args.size,
                  'not_tested': ['NVDA/VoiceOver', 'packaged Qt runtime', 'full app workflows', 'cold cover extraction']}
        print(json.dumps(report), flush=True)
        if args.output:
            args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        app.quit()
    QTimer.singleShot(750, run_next)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
