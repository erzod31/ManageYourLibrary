"""Modern, adaptive workspace shell for the Tkinter desktop application."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

import library_core as core
from core.cover_service import CoverService
from core.library_view_model import (
    FAVORITE_TAGS,
    LibraryViewIndex,
    cover_grid_positions,
    display_item,
    item_is_favorite,
    provenance_lines,
)
from rounded_widgets import RoundedButton, RoundedCard
from ui.icon_palette import create_icon

TEXT = {
    "es": {
        "brand": "Mi biblioteca",
        "library": "Biblioteca",
        "import": "Importar",
        "reviews": "Revisiones",
        "favorites": "Favoritos",
        "activity": "Actividad",
        "settings": "Configuración",
        "library_subtitle": "Explora, busca y organiza tu colección.",
        "import_subtitle": "Añade archivos con análisis, revisión y cambios recuperables.",
        "reviews_subtitle": "Resuelve duplicados y metadatos que necesitan una decisión.",
        "activity_subtitle": "Sigue las tareas actuales y consulta el registro técnico.",
        "settings_subtitle": "Privacidad, OCR, idioma e integraciones locales.",
        "search": "Buscar por título, autor, formato o ruta",
        "all_formats": "Todos los formatos",
        "covers": "Portadas",
        "table": "Tabla",
        "covers_tip": "Mostrar la biblioteca como una cuadrícula de portadas.",
        "table_tip": "Mostrar la biblioteca como una tabla navegable.",
        "details_tip": "Mostrar u ocultar los detalles del libro seleccionado.",
        "books": "Libros",
        "authors": "Autores",
        "formats": "Formatos",
        "missing": "Sin autor",
        "empty_library": "La biblioteca está vacía o todavía no se ha indexado.",
        "empty_hint": "Selecciona Importar para añadir libros de forma segura.",
        "first_library_hint": "Elige dónde guardar tu biblioteca. No se analizará ninguna carpeta hasta que la selecciones.",
        "choose_library": "Elegir carpeta de biblioteca",
        "showing": "Mostrando {shown} de {total}",
        "previous": "Anterior",
        "next": "Siguiente",
        "details": "Detalles",
        "no_selection": "Selecciona un libro para ver sus detalles.",
        "open": "Abrir",
        "title": "Título",
        "author": "Autor",
        "edit_metadata": "Editar metadatos",
        "lookup_metadata": "Buscar en la web",
        "save_metadata": "Guardar corrección",
        "manual_edit_help": "Estos cambios actualizan el catálogo. El archivo no se renombra ni se mueve.",
        "tags": "Etiquetas",
        "saved_metadata": "Corrección guardada en el catálogo.",
        "favorite_add": "Añadir a favoritos",
        "favorite_active": "Favorito",
        "favorite_added": "Libro añadido a favoritos.",
        "favorite_removed": "Libro eliminado de favoritos.",
        "path": "Ubicación",
        "size": "Tamaño",
        "format": "Formato",
        "import_title": "Importar y organizar",
        "step_select": "1  Seleccionar",
        "step_analyze": "2  Analizar",
        "step_review": "3  Revisar",
        "step_organize": "4  Organizar",
        "step_select_help": "Elige archivos",
        "step_analyze_help": "Identidad y OCR",
        "step_review_help": "Decide conflictos",
        "step_organize_help": "Aplica cambios",
        "safe_import": "Los cambios se previsualizan, se registran y pueden deshacerse.",
        "review_duplicates": "Duplicados de la biblioteca",
        "review_duplicates_help": "Compara contenido real y separa coincidencias exactas de posibles ediciones.",
        "scan_now": "Analizar biblioteca",
        "compare_folders": "Comparar carpetas",
        "metadata_review": "Metadatos y nombres",
        "metadata_review_help": "Busca información fiable y deja los casos dudosos para revisión humana.",
        "technical_log": "Registro técnico",
        "clear_log": "Limpiar registro",
        "operation_settings": "Análisis y privacidad",
        "provider_health": "Estado de proveedores",
        "save_settings": "Guardar configuración",
        "settings_saved": "Configuración guardada.",
        "local_ai": "IA local opcional",
        "local_ai_help": "Administra el modelo local sin enviar el contenido OCR a terceros.",
        "ready": "Listo",
        "working": "Operación en curso",
        "review_count": "{count} grupos encontrados",
        "grid_unavailable": "No se pudo crear una miniatura",
        "brand_tagline": "Lee. Descubre. Conserva.",
        "all": "Todos",
        "other_formats": "Otros",
        "sort_by": "Ordenar por:",
        "sort_recent": "Más recientes",
        "sort_title": "Título A–Z",
        "show_activity": "Ver actividad",
        "copy_path": "Copiar ruta",
        "show_folder": "Mostrar en carpeta",
        "identity": "Identidad",
        "edition": "Edición",
        "file_data": "Archivo",
        "provenance": "Procedencia",
        "no_provenance": "Datos obtenidos del archivo y su nombre. Sin procedencia detallada todavía.",
        "theme": "Apariencia",
        "theme_system": "Usar tema de Windows",
        "theme_light": "Claro",
        "theme_dark": "Oscuro",
        "isbn": "ISBN",
        "language": "Idioma",
        "publisher": "Editorial",
        "year": "Año",
        "series": "Series",
        "confidence": "Confianza",
        "pending_reviews": "{count} pendientes",
        "resume_reviews": "Continuar pendientes",
        "library_tip": "Explora y busca todos los libros de tu catálogo.",
        "authors_tip": "Agrupa la colección por autor y facilita su búsqueda.",
        "series_tip": "Muestra los libros que forman parte de una serie.",
        "tags_tip": "Explora la colección mediante sus etiquetas.",
        "favorites_tip": "Reúne los libros marcados como favoritos.",
        "import_tip": "Añade libros y organiza cada incorporación de forma segura.",
        "reviews_tip": "Resuelve duplicados y metadatos que necesitan confirmación.",
        "authors_subtitle": "Explora la colección organizada por autores.",
        "series_subtitle": "Continúa sagas y colecciones en el orden correcto.",
        "tags_subtitle": "Encuentra libros por temas y etiquetas.",
        "favorites_subtitle": "Accede rápidamente a tus libros favoritos.",
    },
    "en": {
        "brand": "My library", "library": "Library", "import": "Import", "reviews": "Reviews", "favorites": "Favorites",
        "activity": "Activity", "settings": "Settings", "library_subtitle": "Browse, search, and organize your collection.",
        "import_subtitle": "Add files with analysis, review, and recoverable changes.",
        "reviews_subtitle": "Resolve duplicates and metadata that require a decision.",
        "activity_subtitle": "Follow current jobs and inspect the technical log.",
        "settings_subtitle": "Privacy, OCR, language, and local integrations.",
        "search": "Search by title, author, format, or path", "all_formats": "All formats",
        "covers": "Covers", "table": "Table", "books": "Books", "authors": "Authors",
        "covers_tip": "Show the library as a cover grid.",
        "table_tip": "Show the library as a navigable table.",
        "details_tip": "Show or hide details for the selected book.",
        "formats": "Formats", "missing": "Missing author", "empty_library": "The library is empty or has not been indexed yet.",
        "empty_hint": "Choose Import to add books safely.", "showing": "Showing {shown} of {total}",
        "first_library_hint": "Choose where to keep your library. No folder is scanned until you select it.",
        "choose_library": "Choose library folder",
        "previous": "Previous", "next": "Next", "details": "Details", "no_selection": "Select a book to view its details.",
        "open": "Open", "title": "Title", "author": "Author", "edit_metadata": "Edit metadata", "path": "Location", "size": "Size", "format": "Format",
        "lookup_metadata": "Search the web", "save_metadata": "Save correction",
        "manual_edit_help": "These changes update the catalog. The file is not renamed or moved.",
        "tags": "Tags", "saved_metadata": "Correction saved to the catalog.",
        "favorite_add": "Add to favorites", "favorite_active": "Favorite",
        "favorite_added": "Book added to favorites.", "favorite_removed": "Book removed from favorites.",
        "import_title": "Import and organize", "step_select": "1  Select", "step_analyze": "2  Analyze",
        "step_review": "3  Review", "step_organize": "4  Organize", "step_select_help": "Choose files",
        "step_analyze_help": "Identity and OCR", "step_review_help": "Resolve conflicts", "step_organize_help": "Apply changes",
        "safe_import": "Changes are previewed, journaled, and undoable.", "review_duplicates": "Library duplicates",
        "review_duplicates_help": "Compare real content and distinguish exact copies from possible editions.",
        "scan_now": "Analyze library", "compare_folders": "Compare folders", "metadata_review": "Metadata and names",
        "metadata_review_help": "Find reliable information and leave uncertain cases for human review.",
        "technical_log": "Technical log", "clear_log": "Clear log", "operation_settings": "Analysis and privacy",
        "provider_health": "Provider health", "save_settings": "Save settings", "settings_saved": "Settings saved.",
        "local_ai": "Optional local AI", "local_ai_help": "Manage the local model without sending OCR content to third parties.",
        "ready": "Ready", "working": "Operation in progress", "review_count": "{count} groups found",
        "grid_unavailable": "A thumbnail could not be created",
        "brand_tagline": "Read. Discover. Preserve.", "all": "All", "other_formats": "Other",
        "sort_by": "Sort by:", "sort_recent": "Most recent", "sort_title": "Title A–Z",
        "show_activity": "View activity", "copy_path": "Copy path", "show_folder": "Show in folder",
        "identity": "Identity", "edition": "Edition", "file_data": "File", "provenance": "Provenance",
        "no_provenance": "Data obtained from the file and its name. Detailed provenance is not available yet.",
        "theme": "Appearance", "theme_system": "Use Windows theme", "theme_light": "Light", "theme_dark": "Dark",
        "isbn": "ISBN", "language": "Language", "publisher": "Publisher", "year": "Year", "series": "Series",
        "confidence": "Confidence", "pending_reviews": "{count} pending",
        "resume_reviews": "Continue pending",
        "library_tip": "Browse and search all the books in your catalog.",
        "authors_tip": "Group the collection by author and search it easily.",
        "series_tip": "Show the books that belong to a series.",
        "tags_tip": "Explore the collection through its tags.",
        "favorites_tip": "Bring together the books marked as favorites.",
        "import_tip": "Add books and organize each import safely.",
        "reviews_tip": "Resolve duplicates and metadata that need confirmation.",
        "authors_subtitle": "Explore the collection organized by author.",
        "series_subtitle": "Continue series and collections in the right order.",
        "tags_subtitle": "Find books by subject and tag.",
        "favorites_subtitle": "Quick access to your favorite books.",
    },
    "fr": {
        "brand": "Ma bibliothèque", "library": "Bibliothèque", "import": "Importer", "reviews": "Révisions", "favorites": "Favoris",
        "activity": "Activité", "settings": "Paramètres", "library_subtitle": "Parcourez, recherchez et organisez votre collection.",
        "import_subtitle": "Ajoutez des fichiers avec analyse, révision et changements récupérables.",
        "reviews_subtitle": "Résolvez les doublons et les métadonnées à confirmer.",
        "activity_subtitle": "Suivez les tâches et consultez le journal technique.",
        "settings_subtitle": "Confidentialité, OCR, langue et intégrations locales.",
        "search": "Rechercher par titre, auteur, format ou chemin", "all_formats": "Tous les formats",
        "covers": "Couvertures", "table": "Tableau", "books": "Livres", "authors": "Auteurs",
        "covers_tip": "Afficher la bibliothèque sous forme de grille de couvertures.",
        "table_tip": "Afficher la bibliothèque sous forme de tableau navigable.",
        "details_tip": "Afficher ou masquer les détails du livre sélectionné.",
        "formats": "Formats", "missing": "Sans auteur", "empty_library": "La bibliothèque est vide ou n'est pas encore indexée.",
        "empty_hint": "Choisissez Importer pour ajouter des livres en toute sécurité.", "showing": "Affichage de {shown} sur {total}",
        "first_library_hint": "Choisissez le dossier de votre bibliothèque. Aucun dossier n'est analysé avant votre sélection.",
        "choose_library": "Choisir la bibliothèque",
        "previous": "Précédent", "next": "Suivant", "details": "Détails", "no_selection": "Sélectionnez un livre pour voir ses détails.",
        "open": "Ouvrir", "title": "Titre", "author": "Auteur", "edit_metadata": "Modifier les métadonnées", "path": "Emplacement", "size": "Taille", "format": "Format",
        "lookup_metadata": "Rechercher sur le web", "save_metadata": "Enregistrer la correction",
        "manual_edit_help": "Ces changements mettent à jour le catalogue. Le fichier n’est ni renommé ni déplacé.",
        "tags": "Étiquettes", "saved_metadata": "Correction enregistrée dans le catalogue.",
        "favorite_add": "Ajouter aux favoris", "favorite_active": "Favori",
        "favorite_added": "Livre ajouté aux favoris.", "favorite_removed": "Livre retiré des favoris.",
        "import_title": "Importer et organiser", "step_select": "1  Sélectionner", "step_analyze": "2  Analyser",
        "step_review": "3  Réviser", "step_organize": "4  Organiser", "step_select_help": "Choisir les fichiers",
        "step_analyze_help": "Identité et OCR", "step_review_help": "Décider les conflits", "step_organize_help": "Appliquer",
        "safe_import": "Les changements sont prévisualisés, journalisés et annulables.", "review_duplicates": "Doublons de la bibliothèque",
        "review_duplicates_help": "Compare le contenu réel et sépare les copies exactes des éditions possibles.",
        "scan_now": "Analyser la bibliothèque", "compare_folders": "Comparer les dossiers", "metadata_review": "Métadonnées et noms",
        "metadata_review_help": "Recherche des informations fiables et réserve les cas incertains à une décision humaine.",
        "technical_log": "Journal technique", "clear_log": "Effacer le journal", "operation_settings": "Analyse et confidentialité",
        "provider_health": "État des fournisseurs", "save_settings": "Enregistrer", "settings_saved": "Paramètres enregistrés.",
        "local_ai": "IA locale facultative", "local_ai_help": "Gérez le modèle local sans envoyer le contenu OCR à des tiers.",
        "ready": "Prêt", "working": "Opération en cours", "review_count": "{count} groupes trouvés",
        "grid_unavailable": "Impossible de créer la miniature",
        "brand_tagline": "Lire. Découvrir. Conserver.", "all": "Tous", "other_formats": "Autres",
        "sort_by": "Trier par :", "sort_recent": "Plus récents", "sort_title": "Titre A–Z",
        "show_activity": "Voir l’activité", "copy_path": "Copier le chemin", "show_folder": "Afficher le dossier",
        "identity": "Identité", "edition": "Édition", "file_data": "Fichier", "provenance": "Provenance",
        "no_provenance": "Données obtenues du fichier et de son nom. La provenance détaillée n’est pas encore disponible.",
        "theme": "Apparence", "theme_system": "Utiliser le thème Windows", "theme_light": "Clair", "theme_dark": "Sombre",
        "isbn": "ISBN", "language": "Langue", "publisher": "Éditeur", "year": "Année", "series": "Série",
        "confidence": "Confiance", "pending_reviews": "{count} en attente",
        "resume_reviews": "Continuer les révisions",
        "library_tip": "Parcourez et recherchez tous les livres de votre catalogue.",
        "authors_tip": "Regroupez la collection par auteur et recherchez-la facilement.",
        "series_tip": "Affichez les livres appartenant à une série.",
        "tags_tip": "Explorez la collection à l’aide de ses étiquettes.",
        "favorites_tip": "Regroupez les livres marqués comme favoris.",
        "import_tip": "Ajoutez des livres et organisez chaque importation en toute sécurité.",
        "reviews_tip": "Résolvez les doublons et les métadonnées à confirmer.",
        "authors_subtitle": "Explorez la collection organisée par auteur.",
        "series_subtitle": "Suivez les séries et collections dans le bon ordre.",
        "tags_subtitle": "Trouvez des livres par sujet et étiquette.",
        "favorites_subtitle": "Accédez rapidement à vos livres favoris.",
    },
    "zh": {
        "brand": "我的图书馆", "library": "图书馆", "import": "导入", "reviews": "待审核", "favorites": "收藏",
        "activity": "活动", "settings": "设置", "library_subtitle": "浏览、搜索并整理你的收藏。",
        "import_subtitle": "通过分析、审核和可恢复操作添加文件。", "reviews_subtitle": "处理重复项和需要确认的元数据。",
        "activity_subtitle": "跟踪当前任务并查看技术日志。", "settings_subtitle": "隐私、OCR、语言和本地集成。",
        "search": "按标题、作者、格式或路径搜索", "all_formats": "所有格式", "covers": "封面", "table": "表格",
        "covers_tip": "以封面网格显示图书馆。", "table_tip": "以可导航表格显示图书馆。",
        "details_tip": "显示或隐藏所选图书的详细信息。",
        "books": "图书", "authors": "作者", "formats": "格式", "missing": "缺少作者",
        "empty_library": "图书馆为空或尚未建立索引。", "empty_hint": "选择“导入”以安全添加图书。",
        "first_library_hint": "选择图书馆文件夹。选择之前不会扫描任何文件夹。",
        "choose_library": "选择图书馆文件夹",
        "showing": "显示 {shown}/{total}", "previous": "上一页", "next": "下一页", "details": "详情",
        "no_selection": "选择一本书以查看详情。", "open": "打开", "title": "标题", "author": "作者", "edit_metadata": "编辑元数据", "path": "位置",
        "lookup_metadata": "在线搜索", "save_metadata": "保存更正",
        "manual_edit_help": "这些更改只更新目录，不会重命名或移动文件。", "tags": "标签", "saved_metadata": "更正已保存到目录。",
        "favorite_add": "添加到收藏", "favorite_active": "已收藏",
        "favorite_added": "已添加到收藏。", "favorite_removed": "已从收藏中移除。",
        "size": "大小", "format": "格式", "import_title": "导入并整理", "step_select": "1  选择",
        "step_analyze": "2  分析", "step_review": "3  审核", "step_organize": "4  整理",
        "step_select_help": "选择文件", "step_analyze_help": "身份与 OCR", "step_review_help": "处理冲突",
        "step_organize_help": "应用更改", "safe_import": "所有更改均可预览、记录和撤销。",
        "review_duplicates": "图书馆重复项", "review_duplicates_help": "比较真实内容，区分完全副本与可能的不同版本。",
        "scan_now": "分析图书馆", "compare_folders": "比较文件夹", "metadata_review": "元数据与名称",
        "metadata_review_help": "查找可靠信息，并将不确定案例留给人工审核。", "technical_log": "技术日志",
        "clear_log": "清除日志", "operation_settings": "分析与隐私", "provider_health": "提供商状态",
        "save_settings": "保存设置", "settings_saved": "设置已保存。", "local_ai": "可选本地 AI",
        "local_ai_help": "管理本地模型，不会将 OCR 内容发送给第三方。", "ready": "就绪",
        "working": "操作进行中", "review_count": "找到 {count} 组", "grid_unavailable": "无法创建缩略图",
        "brand_tagline": "阅读。发现。珍藏。", "all": "全部", "other_formats": "其他",
        "sort_by": "排序：", "sort_recent": "最近添加", "sort_title": "标题 A–Z",
        "show_activity": "查看活动", "copy_path": "复制路径", "show_folder": "在文件夹中显示",
        "identity": "身份", "edition": "版本", "file_data": "文件", "provenance": "来源",
        "no_provenance": "数据来自文件及其名称。尚无详细来源信息。",
        "theme": "外观", "theme_system": "使用 Windows 主题", "theme_light": "浅色", "theme_dark": "深色",
        "isbn": "ISBN", "language": "语言", "publisher": "出版社", "year": "年份", "series": "系列",
        "confidence": "置信度", "pending_reviews": "{count} 项待处理",
        "resume_reviews": "继续待处理项目",
        "library_tip": "浏览并搜索目录中的所有图书。",
        "authors_tip": "按作者整理并快速搜索藏书。",
        "series_tip": "显示属于同一系列的图书。",
        "tags_tip": "通过标签浏览藏书。",
        "favorites_tip": "集中显示标记为收藏的图书。",
        "import_tip": "安全地添加图书并整理每次导入。",
        "reviews_tip": "处理重复项和需要确认的元数据。",
        "authors_subtitle": "浏览按作者整理的藏书。",
        "series_subtitle": "按正确顺序继续阅读系列与套书。",
        "tags_subtitle": "按主题和标签查找图书。",
        "favorites_subtitle": "快速访问收藏的图书。",
    },
}


def _text(key: str, **params) -> str:
    language = core.IDIOMA_ACTUAL if core.IDIOMA_ACTUAL in TEXT else "en"
    value = TEXT[language].get(key, TEXT["en"].get(key, key))
    return value.format(**params) if params else value


def full_display_path(value) -> str:
    """Return a stable absolute path for the book details panel."""
    try:
        return str(Path(value).expanduser().resolve(strict=False))
    except (OSError, RuntimeError, TypeError, ValueError):
        return str(value or "")


def wheel_units(delta) -> int:
    """Normalize Windows/macOS wheel deltas to a useful Tk scroll step."""
    try:
        value = int(delta)
    except (TypeError, ValueError):
        return 0
    if value == 0:
        return 0
    magnitude = max(1, abs(value) // 120)
    return -magnitude if value > 0 else magnitude


def interactive_cursor(enabled) -> str:
    """Return a truthful cursor for controls whose state can change."""
    return "hand2" if enabled else "arrow"


def build_workspace(app):
    workspace = Workspace(app)
    app.workspace = workspace
    workspace.build()
    return workspace


class Workspace:
    PAGE_SIZE = 30
    LIBRARY_SCOPES = {"library", "authors", "series", "tags", "favorites"}
    PAGE_SHORTCUTS = (
        ("<Alt-Key-1>", "library"),
        ("<Alt-Key-2>", "import"),
        ("<Alt-Key-3>", "reviews"),
        ("<Alt-Key-4>", "activity"),
        ("<Alt-Key-5>", "settings"),
    )

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.pages = {}
        self.nav_buttons = {}
        self.nav_icon_names = {}
        self.current_page = "library"
        self.library_scope = "library"
        self.view_mode = "covers"
        self.grid_page = 0
        self.filtered_items = []
        self.item_by_iid = {}
        self.selected_item = None
        self.cover_images = {}
        self.cover_pending = set()
        self.cover_pending_lock = threading.Lock()
        self.cover_generation = 0
        self.cover_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cover-preview")
        self.dynamic_cards = []
        self.dynamic_buttons = []
        self.dynamic_labels = []
        self.dynamic_muted_labels = []
        self._cover_card_pool = []
        self._cover_render_paths = ()
        self._empty_library_frame = None
        self._table_items = None
        self._table_after = None
        self._table_generation = 0
        self.cover_service = CoverService(core.APP_DATA / "ui_thumbnails", size=(144, 206))
        self.frames = []
        self.cards = []
        self.labels = []
        self.muted_labels = []
        self.secondary_buttons = []
        self.primary_buttons = []
        self.entries = []
        self._refresh_after = None
        self.search_placeholder_active = False
        self.active_format = "all"
        self._cover_columns = 0
        self._cover_resize_after = None
        self._cover_scroll_after = None
        self._pending_cover_columns = None
        self.rounded_cards = []
        self._sidebar_compact = False
        self._responsive_after = None
        self._responsive_band = None
        self.details_visible = True
        self._details_width = 340
        self._detail_wrap = None
        self._sidebar_resize_after = None
        self.page_scroll_canvases = {}
        self._icon_cache = {}
        self._icon_bindings = []
        self._tooltip_after = None
        self._tooltip_window = None
        self._tooltip_widgets = set()
        self.detail_metadata_buttons = []
        self.detail_tag_buttons = []

    def build(self):
        self.root.geometry("1280x820")
        self.root.minsize(760, 560)
        self.root.configure(bg="#f8f6f1")
        self.app.style = ttk.Style()
        try:
            self.app.style.theme_use("clam")
        except Exception:
            pass

        self.shell = tk.PanedWindow(
            self.root,
            orient="horizontal",
            sashwidth=7,
            sashrelief="flat",
            bd=0,
            relief="flat",
            # Reused cards and frame-coalesced relayout allow live sash motion.
            opaqueresize=True,
            showhandle=False,
            sashcursor="sb_h_double_arrow",
        )
        self.shell.pack(fill="both", expand=True)

        self._build_sidebar()
        self._build_main()
        self._build_pages()
        self._build_activity_strip()
        self.show_page("library")
        self.app.aplicar_tema()
        self.root.bind("<Control-k>", self.focus_search, add="+")
        self.root.bind("<Control-f>", self.focus_search, add="+")
        self.root.bind("<Control-z>", lambda _event: self.app.deshacer_ultima_accion(), add="+")
        self.root.bind("<F5>", lambda _event: self.refresh_library(), add="+")
        self.root.bind("<F2>", lambda _event: self.review_selected_metadata(), add="+")
        for sequence, page in self.PAGE_SHORTCUTS:
            self.root.bind(sequence, lambda _event, name=page: self.show_page(name), add="+")
        self.root.bind_all("<ButtonPress-1>", self.app._cerrar_popups_click_externo, add="+")
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel, add="+")
        self.root.bind_all("<Button-4>", lambda event: self._on_linux_wheel(event, -1), add="+")
        self.root.bind_all("<Button-5>", lambda event: self._on_linux_wheel(event, 1), add="+")
        self.root.bind("<Configure>", self.app._seguir_popup_idioma, add="+")
        self.root.bind("<Configure>", self._schedule_responsive_layout, add="+")
        self.root.after_idle(lambda: self.shell.sash_place(0, 240, 0))
        self.root.after_idle(self._restore_details_width)

    def _icon_photo(self, name, color=None, size=24):
        colors = getattr(self.app, "tema_actual", {})
        resolved = color or colors.get("text", "#2d2a27")
        key = (name, resolved, int(size))
        icon = self._icon_cache.get(key)
        if icon is None:
            icon = create_icon(name, resolved, size=int(size), master=self.root)
            self._icon_cache[key] = icon
        return icon

    def _bind_button_icon(self, button, icon_name, role="secondary", size=24):
        self._icon_bindings.append((button, icon_name, role, int(size)))
        return button

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.shell, width=240, bd=0, highlightthickness=1)
        self.sidebar.pack_propagate(False)
        self.shell.add(self.sidebar, minsize=76, width=240, stretch="never")
        self.sidebar.bind("<Configure>", self._schedule_sidebar_layout, add="+")
        self.cards.append(self.sidebar)

        brand = tk.Frame(self.sidebar, bd=0)
        brand.pack(fill="x", padx=18, pady=(20, 24))
        self.cards.append(brand)
        self.brand_icon_label = tk.Label(
            brand,
            image=self._icon_photo("library", "#a9573e", size=28),
            bd=0,
        )
        self.brand_icon_label.pack(side="left", anchor="n", padx=(0, 10))
        self.labels.append(self.brand_icon_label)
        self.brand_copy = tk.Frame(brand, bd=0)
        self.brand_copy.pack(side="left", fill="x", expand=True)
        self.cards.append(self.brand_copy)
        self.brand_label = tk.Label(self.brand_copy, text=_text("brand"), font=("Georgia", 15), anchor="w", bd=0)
        self.brand_label.pack(fill="x")
        self.labels.append(self.brand_label)
        self.brand_tagline = tk.Label(self.brand_copy, text=_text("brand_tagline"), font=("Georgia", 8), anchor="w", bd=0)
        self.brand_tagline.pack(fill="x", pady=(2, 0))
        self.muted_labels.append(self.brand_tagline)

        navigation = tk.Frame(self.sidebar, bd=0)
        navigation.pack(fill="x", padx=10)
        self.cards.append(navigation)
        for page, key, icon_name in [
            ("library", "library", "library"),
            ("authors", "authors", "author"),
            ("series", "series", "series"),
            ("tags", "tags", "tag"),
            ("favorites", "favorites", "favorite"),
            ("import", "import", "import"),
            ("reviews", "reviews", "reviews"),
        ]:
            button = RoundedButton(
                navigation,
                text=_text(key),
                image=self._icon_photo(icon_name, "#2d2a27"),
                command=lambda name=page: self.show_page(name),
                anchor="w",
                width=212,
                height=44,
                radius=8,
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", pady=1)
            self.nav_buttons[page] = button
            self.nav_icon_names[page] = icon_name
            self._bind_nav_tooltip(button, f"{key}_tip")

        spacer = tk.Frame(self.sidebar, bd=0)
        spacer.pack(fill="both", expand=True)
        self.cards.append(spacer)
        self.library_summary = tk.Label(
            self.sidebar,
            text="",
            justify="left",
            anchor="w",
            font=("Segoe UI", 9),
            bd=0,
        )
        self.library_summary.pack(fill="x", padx=20, pady=(0, 12))
        self.muted_labels.append(self.library_summary)
        self.app.btn_configuracion = RoundedButton(
            self.sidebar,
            text=_text("settings"),
            image=self._icon_photo("settings", "#2d2a27"),
            command=lambda: self.show_page("settings"),
            anchor="w",
            width=212,
            height=42,
            radius=8,
            font=("Segoe UI", 9),
        )
        self.app.btn_configuracion.pack(fill="x", padx=10, pady=(0, 4))
        self.nav_buttons["settings"] = self.app.btn_configuracion
        self.nav_icon_names["settings"] = "settings"
        self.app.btn_tema = RoundedButton(
            self.sidebar,
            text=core.tr("dark_mode"),
            image=self._icon_photo("moon", "#2d2a27"),
            command=self.app.alternar_tema,
            anchor="w",
            width=212,
            height=42,
            radius=8,
            font=("Segoe UI", 9),
        )
        self.app.btn_tema.pack(fill="x", padx=10, pady=(0, 14))
        self.secondary_buttons.append(self.app.btn_tema)
        self._update_review_count()

    def _bind_nav_tooltip(self, widget, text_key):
        self._tooltip_widgets.add(widget)
        widget.bind(
            "<Enter>",
            lambda event, key=text_key: self._schedule_tooltip(event.widget, key),
            add="+",
        )
        widget.bind("<Leave>", self._hide_tooltip, add="+")
        widget.bind(
            "<FocusIn>",
            lambda event, key=text_key: self._schedule_tooltip(event.widget, key),
            add="+",
        )
        widget.bind("<FocusOut>", self._hide_tooltip, add="+")
        widget.bind("<ButtonPress-1>", self._hide_tooltip, add="+")

    def _schedule_tooltip(self, widget, text_key):
        self._hide_tooltip()
        self._tooltip_after = self.root.after(
            450,
            lambda: self._show_tooltip(widget, text_key),
        )

    def _show_tooltip(self, widget, text_key):
        self._tooltip_after = None
        try:
            if not widget.winfo_exists():
                return
            colors = getattr(self.app, "tema_actual", {})
            tip = tk.Toplevel(self.root)
            tip.withdraw()
            tip.overrideredirect(True)
            tip.configure(cursor="arrow")
            try:
                tip.attributes("-topmost", True)
            except tk.TclError:
                pass
            try:
                # On Windows this makes the explanatory popup transparent to
                # pointer input, avoiding leave/enter flicker at its edge.
                tip.attributes("-disabled", True)
            except tk.TclError:
                pass
            label = tk.Label(
                tip,
                text=_text(text_key),
                justify="left",
                wraplength=250,
                padx=10,
                pady=7,
                bd=1,
                relief="solid",
                bg=colors.get("card", "#fffdf9"),
                fg=colors.get("text", "#2d2a27"),
                highlightbackground=colors.get("border", "#ddd4cc"),
                font=("Segoe UI", 8),
                cursor="arrow",
            )
            label.pack()
            tip.update_idletasks()
            x = widget.winfo_rootx() + widget.winfo_width() + 8
            y = widget.winfo_rooty() + max(0, (widget.winfo_height() - tip.winfo_reqheight()) // 2)
            x = min(x, tip.winfo_screenwidth() - tip.winfo_reqwidth() - 8)
            y = min(y, tip.winfo_screenheight() - tip.winfo_reqheight() - 8)
            tip.geometry(f"+{max(8, x)}+{max(8, y)}")
            tip.deiconify()
            self._tooltip_window = tip
        except tk.TclError:
            self._tooltip_window = None

    def _hide_tooltip(self, _event=None):
        if self._tooltip_after is not None:
            try:
                self.root.after_cancel(self._tooltip_after)
            except tk.TclError:
                pass
            self._tooltip_after = None
        if self._tooltip_window is not None:
            try:
                self._tooltip_window.destroy()
            except tk.TclError:
                pass
            self._tooltip_window = None

    def _build_main(self):
        self.main = tk.Frame(self.shell, bd=0, highlightthickness=0)
        self.shell.add(self.main, minsize=520, stretch="always")
        self.frames.append(self.main)

        self.topbar = tk.Frame(self.main, height=64, bd=0)
        self.topbar.pack(fill="x", padx=20, pady=(12, 6))
        self.topbar.pack_propagate(False)
        self.frames.append(self.topbar)

        heading = tk.Frame(self.topbar, bd=0)
        heading.pack(side="left", fill="both", expand=True)
        self.frames.append(heading)
        self.app.label_titulo = tk.Label(heading, text="", font=("Georgia", 18), anchor="w", bd=0)
        self.app.label_titulo.pack(anchor="w")
        self.labels.append(self.app.label_titulo)
        self.app.label_subtitulo = tk.Label(heading, text="", font=("Segoe UI", 9), anchor="w", bd=0)
        self.app.label_subtitulo.pack(anchor="w", pady=(3, 0))
        self.muted_labels.append(self.app.label_subtitulo)

        self.app.idioma_var = tk.StringVar(value=core.LANGUAGE_NAMES.get(core.IDIOMA_ACTUAL, "English"))
        self.app.btn_idioma = self._button(
            self.topbar,
            f"{self.app.idioma_var.get()}  ▼",
            self.app.abrir_menu_idioma,
        )
        self.app.btn_idioma.pack(side="right", padx=(8, 0), pady=8)
        self.app.label_idioma = tk.Label(self.topbar, text=core.tr("language"), font=("Segoe UI", 9), bd=0)
        self.muted_labels.append(self.app.label_idioma)

        self.page_host = tk.Frame(self.main, bd=0, highlightthickness=0)
        self.page_host.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.frames.append(self.page_host)

    def _build_pages(self):
        self._build_library_page()
        self._build_import_page()
        self._build_reviews_page()
        self._build_activity_page()
        self._build_settings_page()

    def _new_page(self, name):
        page = tk.Frame(self.page_host, bd=0, highlightthickness=0)
        self.pages[name] = page
        self.frames.append(page)
        return page

    def _new_scrollable_page(self, name):
        viewport = self._new_page(name)
        canvas = tk.Canvas(viewport, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        content = tk.Frame(canvas, bd=0, highlightthickness=0)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content._wheel_target = canvas
        content.bind(
            "<Configure>",
            lambda _event, target=canvas: target.configure(scrollregion=target.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event, target=canvas, item=window: target.itemconfigure(item, width=event.width),
        )
        self.page_scroll_canvases[name] = canvas
        self.frames.extend((content,))
        return content

    def _build_library_page(self):
        page = self._new_page("library")
        toolbar = tk.Frame(page, bd=0)
        toolbar.pack(fill="x", pady=(0, 12))
        toolbar.grid_columnconfigure(0, weight=1)
        self.frames.append(toolbar)

        self.search_shell = RoundedCard(toolbar, radius=18, padding=2, min_height=64)
        self.search_shell.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        self.rounded_cards.append((self.search_shell, "entry"))
        search_box = self.search_shell.inner
        self.search_icon = tk.Canvas(
            search_box,
            width=28,
            height=28,
            bd=0,
            highlightthickness=0,
        )
        self.search_icon.pack(side="left", padx=(16, 7))
        self._draw_search_icon()
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_box,
            textvariable=self.search_var,
            relief="flat",
            bd=0,
            font=("Segoe UI", 13),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=16)
        self.entries.append(self.search_entry)
        self.search_shortcut = tk.Label(search_box, text="Ctrl+K", font=("Segoe UI", 8), bd=0, padx=8, pady=4)
        self.search_shortcut.pack(side="right", padx=(0, 12))
        self.muted_labels.append(self.search_shortcut)
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        self.search_entry.bind("<FocusIn>", self._clear_search_placeholder)
        self.search_entry.bind("<FocusOut>", self._restore_search_placeholder)
        self._show_search_placeholder()

        filter_bar = tk.Frame(toolbar, bd=0)
        filter_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.frames.append(filter_bar)
        self.format_var = tk.StringVar(value=_text("all_formats"))
        self.format_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.format_var,
            state="readonly",
            width=18,
            style="Library.TCombobox",
        )
        self.format_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_library(reset_page=True))
        self.filter_buttons = {}
        for key, value in (("all", "all"), ("EPUB", "EPUB"), ("PDF", "PDF"), ("other_formats", "other")):
            button = self._button(filter_bar, _text(key) if key in {"all", "other_formats"} else key, lambda selected=value: self.set_format_filter(selected))
            button.pack(side="left", padx=(0, 7), ipadx=5)
            self.filter_buttons[value] = button
        self.app.btn_agregar = self._button(filter_bar, core.tr("add_books"), self.start_import, primary=True, icon="import")
        self.app.btn_agregar.pack(side="right", padx=(8, 0), ipadx=4)
        self.cover_button = self._button(
            filter_bar,
            "",
            lambda: self.set_view("covers"),
            icon="grid",
            accessible_name=_text("covers"),
        )
        self.cover_button.pack(side="right", padx=(6, 0), ipadx=2)
        self._bind_nav_tooltip(self.cover_button, "covers_tip")
        self.table_button = self._button(
            filter_bar,
            "",
            lambda: self.set_view("table"),
            icon="list",
            accessible_name=_text("table"),
        )
        self.table_button.pack(side="right", padx=(6, 0), ipadx=2)
        self._bind_nav_tooltip(self.table_button, "table_tip")
        self.details_button = self._button(
            filter_bar,
            "",
            self.toggle_details,
            icon="details",
            accessible_name=_text("details"),
        )
        self.details_button.pack(side="right", padx=(6, 0), ipadx=2)
        self._bind_nav_tooltip(self.details_button, "details_tip")
        self.sort_var = tk.StringVar(value=_text("sort_recent"))
        self.sort_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.sort_var,
            values=(_text("sort_recent"), _text("sort_title")),
            state="readonly",
            width=14,
            style="Library.TCombobox",
        )
        self.sort_combo.pack(side="right", padx=(6, 0), ipady=4)
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_library(reset_page=True))
        self.sort_label = tk.Label(filter_bar, text=_text("sort_by"), font=("Segoe UI", 9), bd=0)
        self.sort_label.pack(side="right", padx=(0, 2))
        self.labels.append(self.sort_label)
        self.stats_frame = tk.Frame(page, bd=0)
        self.frames.append(self.stats_frame)
        self.stat_values = {}
        for column, key in enumerate(("books", "authors", "formats", "missing")):
            card = tk.Frame(self.stats_frame, bd=1, highlightthickness=1, padx=12, pady=9)
            card.grid(row=0, column=column, sticky="ew", padx=(0, 8) if key != "missing" else 0)
            self.stats_frame.grid_columnconfigure(column, weight=1, uniform="library_stats")
            self.cards.append(card)
            value = tk.Label(card, text="0", font=("Segoe UI", 16, "bold"), anchor="w", bd=0)
            value.pack(anchor="w")
            label = tk.Label(card, text=_text(key), font=("Segoe UI", 8), anchor="w", bd=0)
            label.pack(anchor="w")
            self.labels.append(value)
            self.muted_labels.append(label)
            self.stat_values[key] = (value, label)

        self.library_panes = tk.PanedWindow(
            page,
            orient="horizontal",
            sashwidth=7,
            sashrelief="flat",
            bd=0,
            relief="flat",
            opaqueresize=True,
            showhandle=False,
            sashcursor="sb_h_double_arrow",
        )
        self.library_panes.pack(fill="both", expand=True)
        self.frames.append(self.library_panes)
        self.library_content = tk.Frame(self.library_panes, bd=0)
        self.details_shell = RoundedCard(
            self.library_panes,
            radius=18,
            padding=1,
            min_height=480,
            auto_height=False,
        )
        self.rounded_cards.append((self.details_shell, "card"))
        self.details_shell.configure(width=self._details_width)
        self.details_panel = self.details_shell.inner
        self.details_panel.configure(bd=0, padx=22, pady=16)
        self.details_panel.bind("<Configure>", self._on_details_resize, add="+")
        self.library_panes.add(self.library_content, minsize=320, stretch="always")
        self.library_panes.add(self.details_shell, minsize=250, stretch="never")
        self.frames.append(self.library_content)
        self.cards.append(self.details_panel)
        self._build_library_views()
        self._build_details_panel()

    def _draw_search_icon(self, colors=None):
        colors = colors or getattr(self.app, "tema_actual", {})
        background = colors.get("entry_bg", "#fffdf9")
        foreground = colors.get("accent", "#a9573e")
        try:
            self.search_icon.configure(bg=background)
            self.search_icon.delete("all")
            self.search_icon.create_oval(
                4,
                4,
                17,
                17,
                outline=foreground,
                width=2,
            )
            self.search_icon.create_line(
                15,
                15,
                23,
                23,
                fill=foreground,
                width=2,
                capstyle="round",
            )
        except tk.TclError:
            pass

    def _build_library_views(self):
        self.cover_view = tk.Frame(self.library_content, bd=0)
        self.frames.append(self.cover_view)
        self.cover_canvas = tk.Canvas(self.cover_view, highlightthickness=0, bd=0)
        self.cover_scrollbar = ttk.Scrollbar(self.cover_view, orient="vertical", command=self.cover_canvas.yview)
        self.cover_canvas.configure(yscrollcommand=self.cover_scrollbar.set)
        self.cover_scrollbar.pack(side="right", fill="y")
        self.cover_canvas.pack(side="left", fill="both", expand=True)
        self.cover_inner = tk.Frame(self.cover_canvas, bd=0)
        self.frames.append(self.cover_inner)
        self.cover_window = self.cover_canvas.create_window((0, 0), window=self.cover_inner, anchor="nw")
        self.cover_inner.bind("<Configure>", self._schedule_cover_scrollregion)
        self.cover_canvas.bind("<Configure>", self._on_cover_resize)
        self.cover_inner._wheel_target = self.cover_canvas

        self.table_view = tk.Frame(self.library_content, bd=0)
        self.frames.append(self.table_view)
        columns = ("title", "author", "format", "size", "path")
        self.tree = ttk.Treeview(self.table_view, columns=columns, show="headings", selectmode="browse")
        for column, title_key, width in [
            ("title", "title", 240), ("author", "author", 150), ("format", "format", 75),
            ("size", "size", 85), ("path", "path", 340),
        ]:
            self.tree.heading(column, text=_text(title_key))
            self.tree.column(column, width=width, minwidth=60, stretch=column in {"title", "path"})
        y_scroll = ttk.Scrollbar(self.table_view, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(self.table_view, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.table_view.grid_rowconfigure(0, weight=1)
        self.table_view.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Return>", lambda _event: self.open_selected())
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())

        self.pagination = tk.Frame(self.library_content, bd=0)
        self.pagination.pack(side="bottom", fill="x", pady=(8, 0))
        self.frames.append(self.pagination)
        self.page_previous = self._button(self.pagination, _text("previous"), lambda: self.change_page(-1))
        self.page_previous.pack(side="left")
        self.page_label = tk.Label(self.pagination, text="", font=("Segoe UI", 9), bd=0)
        self.page_label.pack(side="left", padx=12)
        self.muted_labels.append(self.page_label)
        self.page_next = self._button(self.pagination, _text("next"), lambda: self.change_page(1))
        self.page_next.pack(side="left")

    def _build_details_panel(self):
        self.details_heading = tk.Label(self.details_panel, text=_text("details"), font=("Segoe UI", 9), anchor="w", bd=0)
        self.details_heading.pack(fill="x")
        self.muted_labels.append(self.details_heading)
        self.details_cover = tk.Label(
            self.details_panel,
            text="▣",
            font=("Georgia", 18),
            width=16,
            height=1,
            bd=0,
            anchor="center",
        )
        self.details_cover.pack(pady=(12, 14))
        self.details_cover._item_path = ""
        self.labels.append(self.details_cover)
        self.detail_title = tk.Label(self.details_panel, text=_text("no_selection"), font=("Georgia", 16), wraplength=280, justify="left", anchor="w", bd=0)
        self.detail_title.pack(fill="x")
        self.labels.append(self.detail_title)

        primary_metadata = tk.Frame(self.details_panel, bd=0)
        primary_metadata.pack(fill="x", pady=(7, 5))
        primary_metadata.grid_columnconfigure(0, weight=1)
        self.cards.append(primary_metadata)
        self.detail_author = self._detail_metadata_button(
            primary_metadata, "author", lambda: self._filter_selected_metadata("authors", "autor_mostrar"),
        )
        self.detail_author.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.detail_favorite = self._detail_metadata_button(
            primary_metadata, "favorite", self.toggle_selected_favorite,
        )
        self.detail_favorite.grid(row=0, column=1, sticky="e")

        self.detail_series = self._detail_metadata_button(
            self.details_panel, "series", lambda: self._filter_selected_metadata("series", "serie_mostrar"),
        )

        self.detail_tags = tk.Frame(self.details_panel, bd=0)
        self.detail_tags.grid_columnconfigure(0, weight=1)
        self.detail_tags.grid_columnconfigure(1, weight=1)
        self.cards.append(self.detail_tags)
        for index in range(4):
            button = self._detail_metadata_button(self.detail_tags, "tag", lambda position=index: self._filter_selected_tag(position))
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 5) if index % 2 == 0 else 0, pady=(0, 5))
            button.grid_remove()
            self.detail_tag_buttons.append(button)

        self.detail_separator = tk.Frame(self.details_panel, height=1, bd=0)
        self.detail_separator.pack(fill="x", pady=(0, 14))
        self.frames.append(self.detail_separator)

        self.detail_group_headings = {}
        self.detail_group_values = {}
        for key in ("edition", "file_data", "provenance"):
            heading = tk.Label(
                self.details_panel, text=_text(key), font=("Segoe UI", 9, "bold"),
                justify="left", anchor="w", bd=0,
            )
            heading.pack(fill="x", pady=(0 if key == "identity" else 9, 3))
            self.labels.append(heading)
            value = tk.Label(
                self.details_panel, text="", font=("Segoe UI", 8),
                justify="left", anchor="nw", wraplength=286, bd=0,
            )
            value.pack(fill="x")
            self.muted_labels.append(value)
            self.detail_group_headings[key] = heading
            self.detail_group_values[key] = value

        path_actions = tk.Frame(self.details_panel, bd=0)
        path_actions.pack(fill="x", pady=(7, 12))
        self.cards.append(path_actions)
        self.copy_path_button = self._button(path_actions, _text("copy_path"), self.copy_selected_path, icon="more")
        self.copy_path_button.pack(side="left", padx=(0, 6))
        self.show_folder_button = self._button(path_actions, _text("show_folder"), self.show_selected_folder, icon="folder")
        self.show_folder_button.pack(side="left")
        self.open_button = self._button(self.details_panel, _text("open"), self.open_selected, primary=True, icon="open")
        self.open_button.pack(fill="x", pady=(0, 6))
        self.metadata_button = self._button(self.details_panel, _text("edit_metadata"), self.edit_selected_metadata, icon="edit")
        self.metadata_button.pack(fill="x", pady=(0, 6))
        self.lookup_metadata_button = self._button(self.details_panel, _text("lookup_metadata"), self.review_selected_metadata, icon="search")
        self.lookup_metadata_button.pack(fill="x")
        self.open_button.configure(state="disabled")
        self.metadata_button.configure(state="disabled")
        self.lookup_metadata_button.configure(state="disabled")
        self.copy_path_button.configure(state="disabled")
        self.show_folder_button.configure(state="disabled")

    def _build_import_page(self):
        page = self._new_scrollable_page("import")
        step_frame = tk.Frame(page, bd=0)
        step_frame.pack(fill="x", pady=(0, 12))
        self.frames.append(step_frame)
        self.import_steps = []
        for index, (title_key, help_key) in enumerate([
            ("step_select", "step_select_help"), ("step_analyze", "step_analyze_help"),
            ("step_review", "step_review_help"), ("step_organize", "step_organize_help"),
        ]):
            card = tk.Frame(step_frame, bd=1, highlightthickness=1, padx=12, pady=10)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8) if index < 3 else 0)
            self.cards.append(card)
            title = tk.Label(card, text=_text(title_key), font=("Segoe UI", 10, "bold"), anchor="w", bd=0)
            title.pack(anchor="w")
            help_label = tk.Label(card, text=_text(help_key), font=("Segoe UI", 8), anchor="w", bd=0)
            help_label.pack(anchor="w", pady=(3, 0))
            self.labels.append(title)
            self.muted_labels.append(help_label)
            self.import_steps.append((card, title, help_label, title_key, help_key))

        route_card = self._card(page)
        route_card.pack(fill="x", pady=(0, 10))
        self.app.label_biblioteca_activa = self._label(route_card, core.tr("library_active"), bold=True)
        self.app.label_biblioteca_activa.pack(anchor="w")
        self.app.label_biblioteca_help = self._muted(route_card, core.tr("library_help"))
        self.app.label_biblioteca_help.pack(anchor="w", pady=(3, 10))
        route_row = tk.Frame(route_card, bd=0)
        route_row.pack(fill="x")
        self.cards.append(route_row)
        self.app.label_ruta = self._label(route_row, core.tr("route"), bold=True)
        self.app.label_ruta.pack(side="left", padx=(0, 8))
        self.app.biblioteca_var = tk.StringVar(value=str(core.FINAL) if core.biblioteca_configurada() else "")
        self.app.entry_biblioteca = tk.Entry(route_row, textvariable=self.app.biblioteca_var, font=("Segoe UI", 10), relief="flat", bd=1)
        self.app.entry_biblioteca.pack(side="left", fill="x", expand=True, ipady=8)
        self.app.entry_biblioteca.bind("<Return>", self.app.aplicar_ruta_desde_cuadro)
        self.entries.append(self.app.entry_biblioteca)
        self.app.btn_elegir_biblioteca = self._button(route_row, "…", self.app.elegir_biblioteca)
        self.app.btn_elegir_biblioteca.pack(side="left", padx=(8, 0))
        self.app.label_indice = self._muted(route_card, "")
        self.app.label_indice.pack(anchor="w", pady=(10, 0))

        action_card = self._card(page)
        action_card.pack(fill="x", pady=(0, 10))
        self.app.label_acciones = self._label(action_card, core.tr("actions"), bold=True)
        self.app.label_acciones.pack(anchor="w", pady=(0, 8))
        self.safe_import_label = self._muted(action_card, _text("safe_import"))
        self.safe_import_label.pack(anchor="w", pady=(0, 12))
        actions = tk.Frame(action_card, bd=0)
        actions.pack(fill="x")
        self.cards.append(actions)
        self.app.btn_agregar_import = self._button(actions, core.tr("add_books"), self.start_import, primary=True, icon="import")
        self.app.btn_agregar_import.pack(side="left", padx=(0, 8))
        self.app.btn_biblioteca = self._button(actions, core.tr("open_library"), self.app.abrir_biblioteca, icon="folder")
        self.app.btn_biblioteca.pack(side="left")
        self.set_import_step(0)

    def _build_reviews_page(self):
        page = self._new_scrollable_page("reviews")
        duplicate_card = self._card(page)
        duplicate_card.pack(fill="x", pady=(0, 10))
        self._label(duplicate_card, _text("review_duplicates"), bold=True).pack(anchor="w")
        self._muted(duplicate_card, _text("review_duplicates_help"), wrap=760).pack(anchor="w", pady=(5, 12))
        row = tk.Frame(duplicate_card, bd=0)
        row.pack(fill="x")
        self.cards.append(row)
        self.scan_button = self._button(row, _text("scan_now"), self.scan_library_duplicates, primary=True, icon="search")
        self.scan_button.pack(side="left", padx=(0, 8))
        self.resume_reviews_button = self._button(row, _text("resume_reviews"), self.resume_pending_reviews, icon="reviews")
        self.resume_reviews_button.pack(side="left", padx=(0, 8))
        self.app.btn_dobles_carpeta = self._button(row, _text("compare_folders"), self.app.comprobar_dobles_en_carpeta, icon="folder")
        self.app.btn_dobles_carpeta.pack(side="left")
        self.review_result_label = self._muted(row, "")
        self.review_result_label.pack(side="right")

        metadata_card = self._card(page)
        metadata_card.pack(fill="x", pady=(0, 10))
        self._label(metadata_card, _text("metadata_review"), bold=True).pack(anchor="w")
        self._muted(metadata_card, _text("metadata_review_help"), wrap=760).pack(anchor="w", pady=(5, 12))
        self.app.btn_metadatos = self._button(metadata_card, core.tr("metadata"), self.app.abrir_selector_metadatos, primary=True, icon="search")
        self.app.btn_metadatos.pack(anchor="w")

    def _build_activity_page(self):
        page = self._new_page("activity")
        controls = tk.Frame(page, bd=0)
        controls.pack(fill="x", pady=(0, 8))
        self.frames.append(controls)
        self.app.btn_undo = self._button(controls, core.tr("undo_last_action"), self.app.deshacer_ultima_accion, icon="undo")
        self.app.btn_undo.pack(side="left", padx=(0, 8))
        clear_button = self._button(controls, _text("clear_log"), self.app.limpiar)
        clear_button.pack(side="left")
        self.app.label_registro = self._label(controls, _text("technical_log"), bold=True)
        self.app.label_registro.pack(side="right")
        log_card = self._card(page, padding=10)
        log_card.pack(fill="both", expand=True)
        self.app.texto = ScrolledText(log_card, font=("Consolas", 9), wrap="word", relief="flat", bd=0)
        self.app.texto.pack(fill="both", expand=True)

    def _build_settings_page(self):
        page = self._new_scrollable_page("settings")
        config = core.cargar_configuracion_operacion()
        settings_card = self._card(page)
        settings_card.pack(fill="x", pady=(0, 10))
        self._label(settings_card, _text("operation_settings"), bold=True).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ocr_label = self._label(settings_card, core.tr("ocr_pages"), bold=False)
        ocr_label.grid(row=1, column=0, sticky="w", pady=7, padx=(0, 24))
        self.ocr_pages_var = tk.IntVar(value=config["ocr_max_pages"])
        self.ocr_spinbox = tk.Spinbox(settings_card, from_=1, to=200, textvariable=self.ocr_pages_var, width=8, font=("Segoe UI", 10))
        self.ocr_spinbox.grid(row=1, column=1, sticky="w", pady=7)
        self.offline_var = tk.BooleanVar(value=config["offline_mode"])
        self.offline_check = tk.Checkbutton(settings_card, text=core.tr("offline_mode"), variable=self.offline_var, font=("Segoe UI", 10), bd=0)
        self.offline_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=7)
        self.theme_label = self._label(settings_card, _text("theme"), bold=False)
        self.theme_label.grid(row=3, column=0, sticky="w", pady=7, padx=(0, 24))
        theme_values = (_text("theme_system"), _text("theme_light"), _text("theme_dark"))
        theme_key = getattr(self.app, "theme_preference", config.get("theme", "system"))
        theme_index = {"system": 0, "light": 1, "dark": 2}.get(theme_key, 0)
        self.theme_var = tk.StringVar(value=theme_values[theme_index])
        self.theme_combo = ttk.Combobox(
            settings_card,
            textvariable=self.theme_var,
            values=theme_values,
            state="readonly",
            width=23,
            style="Library.TCombobox",
        )
        self.theme_combo.grid(row=3, column=1, sticky="w", pady=7)
        self.provider_heading = self._label(settings_card, _text("provider_health"), bold=True)
        self.provider_heading.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self.provider_label = self._muted(settings_card, "", wrap=760)
        self.provider_label.grid(row=5, column=0, columnspan=2, sticky="w")
        save_button = self._button(settings_card, _text("save_settings"), self.save_settings, primary=True)
        save_button.grid(row=6, column=0, columnspan=2, sticky="w", pady=(16, 0))

        ai_card = self._card(page)
        ai_card.pack(fill="x")
        self._label(ai_card, _text("local_ai"), bold=True).pack(anchor="w")
        self._muted(ai_card, _text("local_ai_help"), wrap=760).pack(anchor="w", pady=(5, 12))
        self.app.btn_ia_local = self._button(ai_card, core.tr("ai_reinforce"), self.app.abrir_panel_ia_local)
        self.app.btn_ia_local.pack(anchor="w")
        self.refresh_provider_health()

    def _build_activity_strip(self):
        self.page_host.pack_forget()
        strip = tk.Frame(self.main, height=50, bd=1, highlightthickness=1)
        strip.pack(side="bottom", fill="x", padx=24, pady=(0, 14))
        strip.pack_propagate(False)
        self.cards.append(strip)
        self.app.label_estado_titulo = tk.Label(strip, text=core.tr("status_title"), font=("Segoe UI", 9, "bold"), bd=0)
        self.app.label_estado_titulo.pack(side="left", padx=(12, 6))
        self.labels.append(self.app.label_estado_titulo)
        self.app.label_estado = tk.Label(strip, text=core.tr("initializing"), font=("Segoe UI", 9), anchor="w", bd=0)
        self.app.label_estado.pack(side="left", fill="x", expand=True)
        self.muted_labels.append(self.app.label_estado)
        for widget in (strip, self.app.label_estado_titulo, self.app.label_estado):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event: self.show_page("activity"), add="+")
        self.app.progreso_var = tk.DoubleVar(value=0)
        self.app.barra_progreso = ttk.Progressbar(strip, variable=self.app.progreso_var, maximum=100, mode="determinate", style="Visual.Horizontal.TProgressbar", length=180)
        self.app.barra_progreso.pack(side="left", padx=8)
        self.app.label_estado_tiempo = tk.Label(strip, text="", font=("Segoe UI", 9, "bold"), bd=0)
        self.app.label_estado_tiempo.pack(side="left", padx=(0, 8))
        self.labels.append(self.app.label_estado_tiempo)
        self.app.btn_cancelar_operacion = self._button(strip, core.tr("cancel"), self.app.cancelar_operacion)
        self.app.btn_cancelar_operacion.pack(side="right", padx=8, pady=7)
        self.app.btn_cancelar_operacion.configure(state="disabled")
        self.page_host.pack(side="top", fill="both", expand=True, padx=24, pady=(0, 10))

    def _button(
        self,
        parent,
        text,
        command,
        primary=False,
        image=None,
        icon=None,
        accessible_name=None,
    ):
        if icon is not None:
            image = self._icon_photo(icon, size=24)
        width = max(54, min(220, 30 + len(str(text)) * 8 + (28 if image else 0)))
        button = RoundedButton(
            parent,
            text=text,
            command=command,
            image=image or "",
            width=width,
            height=38,
            radius=8,
            font=("Segoe UI", 9, "bold" if primary else "normal"),
            accessible_name=accessible_name or text,
        )
        (self.primary_buttons if primary else self.secondary_buttons).append(button)
        if icon is not None:
            self._bind_button_icon(button, icon, "primary" if primary else "secondary")
        return button

    def _detail_metadata_button(self, parent, icon_name, command):
        button = tk.Button(
            parent,
            text="",
            image=self._icon_photo(icon_name, size=18),
            compound="left",
            command=command,
            anchor="w",
            padx=8,
            pady=5,
            bd=0,
            relief="flat",
            highlightthickness=1,
            cursor="hand2",
            takefocus=True,
            font=("Segoe UI", 9),
        )
        button._detail_icon = icon_name
        button._detail_accent = False
        self.detail_metadata_buttons.append(button)
        return button

    def _apply_detail_metadata_theme(self, colors):
        for button in self.detail_metadata_buttons:
            try:
                accent = bool(getattr(button, "_detail_accent", False))
                foreground = colors.get("accent" if accent else "text", "#a9573e" if accent else "#2d2a27")
                background = colors.get("quiet_active" if accent else "quiet_bg", "#e8ded6" if accent else "#f0ece7")
                button.configure(
                    bg=background,
                    fg=foreground,
                    activebackground=colors.get("button_active", "#eee6df"),
                    activeforeground=foreground,
                    disabledforeground=colors.get("disabled_text", "#aaa19a"),
                    highlightbackground=colors.get("accent" if accent else "border", "#a9573e" if accent else "#ded8d0"),
                    highlightcolor=colors.get("accent", "#a9573e"),
                    image=self._icon_photo(button._detail_icon, foreground, size=18),
                )
            except tk.TclError:
                pass

    @staticmethod
    def _set_button_theme(button, background, foreground, border, active, disabled_background, disabled_foreground):
        if isinstance(button, RoundedButton):
            button.set_theme(background, foreground, border, active, disabled_background, disabled_foreground)
            return
        button.configure(
            bg=background,
            fg=foreground,
            activebackground=active,
            activeforeground=foreground,
            disabledforeground=disabled_foreground,
            highlightbackground=border,
        )

    def _card(self, parent, padding=16):
        shell = RoundedCard(parent, radius=12, padding=padding, min_height=44)
        self.rounded_cards.append((shell, "card"))
        card = shell.inner
        card.pack = shell.pack
        card.grid = shell.grid
        card.place = shell.place
        card.pack_forget = shell.pack_forget
        card.grid_forget = shell.grid_forget
        card.place_forget = shell.place_forget
        self.cards.append(card)
        return card

    def _label(self, parent, text, bold=False):
        label = tk.Label(parent, text=text, font=("Segoe UI", 11, "bold" if bold else "normal"), bd=0, anchor="w")
        self.labels.append(label)
        return label

    def _muted(self, parent, text, wrap=None):
        label = tk.Label(parent, text=text, font=("Segoe UI", 9), bd=0, anchor="w", justify="left", wraplength=wrap or 0)
        self.muted_labels.append(label)
        return label

    def show_page(self, name):
        target_page = "library" if name in self.LIBRARY_SCOPES else name
        if target_page not in self.pages:
            return
        if getattr(self, "_visible_page", None) == target_page and self.current_page == name:
            return
        if getattr(self, "_visible_page", None) != target_page:
            for page in self.pages.values():
                page.pack_forget()
            self.pages[target_page].pack(fill="both", expand=True)
            self._visible_page = target_page
        was_library = self.current_page in self.LIBRARY_SCOPES
        if was_library and target_page != "library":
            self.release_cover_images()
        self.current_page = name
        if name in self.LIBRARY_SCOPES:
            self.library_scope = name
        if target_page == "library":
            self.topbar.pack_forget()
        elif not self.topbar.winfo_manager():
            self.topbar.pack(side="top", fill="x", padx=20, pady=(12, 6), before=self.page_host)
        self._update_navigation_state()
        self._update_heading()
        if target_page == "library":
            self.refresh_library(reset_page=True)
        elif name == "settings":
            self.refresh_provider_health()
        if name in {"reviews", "activity"}:
            self._update_review_count()

    def _update_review_count(self):
        try:
            count = core.duplicate_review_store().pending_count()
        except Exception:
            count = 0
        self.pending_review_count = count
        button = self.nav_buttons.get("reviews")
        if button is not None:
            label = "" if self._sidebar_compact else _text("reviews")
            if count:
                label = str(count) if self._sidebar_compact else f"{label}  ({count})"
            button.configure(text=label)
        if hasattr(self, "review_result_label"):
            self.review_result_label.configure(text=_text("pending_reviews", count=count) if count else "")
        if hasattr(self, "resume_reviews_button"):
            self.resume_reviews_button.configure(state="normal" if count else "disabled")

    def _schedule_responsive_layout(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self._responsive_after is not None:
            try:
                self.root.after_cancel(self._responsive_after)
            except tk.TclError:
                pass
        self._responsive_after = self.root.after(90, self._apply_responsive_layout)

    def _schedule_sidebar_layout(self, _event=None):
        if self._sidebar_resize_after is not None:
            try:
                self.root.after_cancel(self._sidebar_resize_after)
            except tk.TclError:
                pass
        self._sidebar_resize_after = self.root.after(50, self._apply_sidebar_layout)

    def _apply_sidebar_layout(self):
        self._sidebar_resize_after = None
        try:
            width = self.sidebar.winfo_width()
        except tk.TclError:
            return
        compact = width < 154
        if compact == self._sidebar_compact:
            return
        self._sidebar_compact = compact
        if compact:
            self.brand_copy.pack_forget()
            self.library_summary.pack_forget()
        else:
            self.brand_copy.pack(side="left", fill="x", expand=True)
            self.library_summary.pack(fill="x", padx=20, pady=(0, 12), before=self.app.btn_configuracion)
        self._refresh_navigation_labels()

    def _apply_responsive_layout(self):
        self._responsive_after = None
        width = max(1, self.root.winfo_width())
        band = "narrow" if width < 900 else "wide"
        if band != self._responsive_band:
            self._responsive_band = band
            self._set_details_visible(band == "wide")

    def _refresh_navigation_labels(self):
        labels = {
            "library": "library",
            "authors": "authors",
            "series": "series",
            "tags": "tags",
            "favorites": "favorites",
            "import": "import",
            "reviews": "reviews",
            "settings": "settings",
        }
        for page, key in labels.items():
            button = self.nav_buttons.get(page)
            if button is None:
                continue
            button.configure(text="" if self._sidebar_compact else _text(key))
        theme_icon = "sun" if self.app.modo_oscuro else "moon"
        self.app.btn_tema.configure(
            text=("" if self._sidebar_compact else (core.tr("light_mode") if self.app.modo_oscuro else core.tr("dark_mode"))),
            image=self._icon_photo(theme_icon),
        )
        self._update_review_count()

    def _set_details_visible(self, visible):
        panes = {str(value) for value in self.library_panes.panes()}
        present = str(self.details_shell) in panes
        if visible and not present:
            self.library_panes.add(self.details_shell, minsize=250, stretch="never")
            self.root.after_idle(self._restore_details_width)
        elif not visible and present:
            try:
                self._details_width = max(250, self.details_shell.winfo_width())
            except tk.TclError:
                pass
            self.library_panes.forget(self.details_shell)
        self.details_visible = bool(visible)

    def _restore_details_width(self):
        try:
            total = self.library_panes.winfo_width()
            split = max(320, total - self._details_width - int(self.library_panes.cget("sashwidth")))
            self.library_panes.sash_place(0, split, 0)
        except (tk.TclError, ValueError):
            pass

    def _on_details_resize(self, event):
        width = max(160, event.width)
        try:
            wrap = max(150, ((width - 48) // 8) * 8)
            if wrap != self._detail_wrap:
                self._detail_wrap = wrap
                self.detail_title.configure(wraplength=wrap)
                for value in self.detail_group_values.values():
                    value.configure(wraplength=wrap)
        except (AttributeError, tk.TclError):
            pass

    def _wheel_candidates(self, event):
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root) or event.widget
        except (AttributeError, tk.TclError):
            widget = getattr(event, "widget", None)
        candidates = []
        current = widget
        while current is not None:
            target = getattr(current, "_wheel_target", None)
            if target is not None and target not in candidates:
                candidates.append(target)
            if isinstance(current, (tk.Canvas, tk.Text, tk.Listbox, ttk.Treeview)) and current not in candidates:
                candidates.append(current)
            current = getattr(current, "master", None)
        page_target = self.page_scroll_canvases.get(self.current_page)
        if page_target is not None and page_target not in candidates:
            candidates.append(page_target)
        return candidates

    @staticmethod
    def _target_can_scroll(target, units, horizontal=False):
        try:
            view = target.xview() if horizontal else target.yview()
            if len(view) < 2 or view == (0.0, 1.0):
                return False
            return view[0] > 0.0 if units < 0 else view[1] < 1.0
        except (AttributeError, tk.TclError, TypeError):
            return False

    def _scroll_under_pointer(self, event, units, horizontal=False):
        if not units:
            return None
        for target in self._wheel_candidates(event):
            if not self._target_can_scroll(target, units, horizontal=horizontal):
                continue
            try:
                command = target.xview_scroll if horizontal else target.yview_scroll
                command(units, "units")
                return "break"
            except (AttributeError, tk.TclError):
                continue
        return None

    def _on_mousewheel(self, event):
        if isinstance(getattr(event, "widget", None), (tk.Text, tk.Listbox, ttk.Treeview)):
            return None
        return self._scroll_under_pointer(event, wheel_units(getattr(event, "delta", 0)))

    def _on_shift_mousewheel(self, event):
        if isinstance(getattr(event, "widget", None), (tk.Text, tk.Listbox, ttk.Treeview)):
            return None
        return self._scroll_under_pointer(
            event,
            wheel_units(getattr(event, "delta", 0)),
            horizontal=True,
        )

    def _on_linux_wheel(self, event, units):
        return self._scroll_under_pointer(event, units)

    def toggle_details(self):
        self._set_details_visible(not self.details_visible)

    def _update_heading(self):
        keys = {
            "library": ("library", "library_subtitle"),
            "authors": ("authors", "authors_subtitle"),
            "series": ("series", "series_subtitle"),
            "tags": ("tags", "tags_subtitle"),
            "favorites": ("favorites", "favorites_subtitle"),
            "import": ("import_title", "import_subtitle"),
            "reviews": ("reviews", "reviews_subtitle"),
            "activity": ("activity", "activity_subtitle"),
            "settings": ("settings", "settings_subtitle"),
        }
        title_key, subtitle_key = keys[self.current_page]
        self.app.label_titulo.configure(text=_text(title_key))
        self.app.label_subtitulo.configure(text=_text(subtitle_key))

    def _update_navigation_state(self):
        colors = getattr(self.app, "tema_actual", {})
        for page, button in self.nav_buttons.items():
            active = page == self.current_page
            background = colors.get("quiet_active" if active else "card", "#e8ded6" if active else "#fffdf9")
            foreground = colors.get("accent" if active else "text", "#a9573e" if active else "#2d2a27")
            self._set_button_theme(
                button,
                background,
                foreground,
                background,
                colors.get("button_active", "#eee6df"),
                colors.get("button_disabled", "#f1ede8"),
                colors.get("disabled_text", "#aaa19a"),
            )
            icon_name = self.nav_icon_names.get(page)
            button.configure(
                font=("Segoe UI", 10, "bold" if active else "normal"),
                image=self._icon_photo(icon_name, foreground) if icon_name else "",
            )

    def _refresh_bound_icons(self, colors):
        for button, icon_name, role, size in self._icon_bindings:
            try:
                color = colors["primary_text"] if role == "primary" else colors["text"]
                button.configure(image=self._icon_photo(icon_name, color, size=size))
            except (KeyError, tk.TclError):
                pass
        try:
            self.brand_icon_label.configure(image=self._icon_photo("library", colors["accent"], size=28))
            theme_icon = "sun" if self.app.modo_oscuro else "moon"
            self.app.btn_tema.configure(image=self._icon_photo(theme_icon, colors["text"]))
        except (KeyError, tk.TclError):
            pass

    def start_import(self):
        self.show_page("import")
        self.set_import_step(0)
        self.app.agregar_libros()

    def set_import_step(self, active):
        colors = getattr(self.app, "tema_actual", {})
        for index, (card, title, help_label, _title_key, _help_key) in enumerate(self.import_steps):
            completed = index < active
            selected = index == active
            if completed:
                accent = colors.get("success", "#16a34a")
            elif selected:
                accent = colors.get("accent", "#2563eb")
            else:
                accent = colors.get("border", "#d8dee8")
            card.configure(highlightbackground=accent, highlightcolor=accent)
            title.configure(fg=accent if completed or selected else colors.get("muted", "#5b6474"))
            help_label.configure(fg=colors.get("muted", "#5b6474"))

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for button in (getattr(self, "scan_button", None),):
            if button is not None:
                button.configure(state=state)
        detail_state = "normal" if not busy and self.selected_item else "disabled"
        self.open_button.configure(state=detail_state)
        self.metadata_button.configure(state=detail_state)
        self.lookup_metadata_button.configure(state=detail_state)
        self.copy_path_button.configure(state=detail_state)
        self.show_folder_button.configure(state=detail_state)
        self._refresh_detail_metadata_controls()
        if busy and self.current_page == "import":
            self.set_import_step(1)
        elif not busy and self.current_page == "import":
            self.set_import_step(3)

    def set_view(self, mode):
        if mode not in {"covers", "table"}:
            return
        if mode == self.view_mode:
            return
        if mode == "table" and self.view_mode == "covers":
            self.release_cover_images()
        self.view_mode = mode
        self._render_library_view()
        self._update_view_state()

    def _update_view_state(self):
        colors = getattr(self.app, "tema_actual", {})
        for mode, button in (("covers", self.cover_button), ("table", self.table_button)):
            active = mode == self.view_mode
            background = colors.get("primary_bg" if active else "quiet_bg", "#a9573e" if active else "#f0ece7")
            foreground = colors.get("primary_text" if active else "text", "#ffffff" if active else "#2d2a27")
            self._set_button_theme(
                button,
                background,
                foreground,
                background,
                colors.get("primary_active" if active else "quiet_active", "#8f4935" if active else "#e8ded6"),
                colors.get("button_disabled", "#f1ede8"),
                colors.get("disabled_text", "#aaa19a"),
            )

    def set_format_filter(self, value):
        self.active_format = value
        self.grid_page = 0
        self.refresh_library()
        self._update_filter_state()

    def _update_filter_state(self):
        colors = getattr(self.app, "tema_actual", {})
        for value, button in getattr(self, "filter_buttons", {}).items():
            active = value == self.active_format
            background = colors.get("primary_bg" if active else "quiet_bg", "#a9573e" if active else "#f0ece6")
            foreground = colors.get("primary_text" if active else "text", "#ffffff" if active else "#2d2a27")
            self._set_button_theme(
                button,
                background,
                foreground,
                background,
                colors.get("primary_active" if active else "quiet_active", "#914832" if active else "#e8e1d9"),
                colors.get("button_disabled", "#f1ede8"),
                colors.get("disabled_text", "#aaa19a"),
            )

    def _schedule_refresh(self):
        if self._refresh_after is not None:
            try:
                self.root.after_cancel(self._refresh_after)
            except Exception:
                pass
        self._refresh_after = self.root.after(100, self._refresh_from_search)

    def _refresh_from_search(self):
        self._refresh_after = None
        self.refresh_library(reset_page=True)

    def refresh_library(self, reset_page=False):
        if reset_page:
            self.grid_page = 0
        records = (self.app.indice or {}).get("archivos", [])
        if (
            getattr(self, "_view_index_records", None) is not records
            or getattr(self, "_view_index_count", -1) != len(records)
        ):
            self._view_index = LibraryViewIndex(records)
            self._view_index_records = records
            self._view_index_count = len(records)
        stats = self._view_index.stats
        stat_keys = {"books": "books", "authors": "authors", "formats": "formats", "missing": "missing_author"}
        for key, (value, label) in self.stat_values.items():
            value.configure(text=str(stats[stat_keys[key]]))
            label.configure(text=_text(key))
        self.library_summary.configure(text=f"{stats['books']} {_text('books').lower()}\n{stats['authors']} {_text('authors').lower()}")

        values = [_text("all_formats"), *self._view_index.formats]
        self.format_combo.configure(values=values)
        if self.format_var.get() not in values:
            self.format_var.set(values[0])
        selected_format = self.active_format if self.active_format not in {"other"} else "all"
        query = "" if self.search_placeholder_active else self.search_var.get()
        self.filtered_items = self._view_index.filter(query, selected_format)
        if self.active_format == "other":
            self.filtered_items = [item for item in self.filtered_items if item["formato"] not in {"EPUB", "PDF"}]
        if self.sort_var.get() == _text("sort_recent"):
            self.filtered_items.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
        self.filtered_items = self._apply_library_scope(self.filtered_items)
        max_page = max(0, (len(self.filtered_items) - 1) // self.PAGE_SIZE)
        self.grid_page = min(self.grid_page, max_page)
        self._update_filter_state()
        self._render_library_view()

    def _apply_library_scope(self, items):
        scope = self.library_scope
        if scope == "authors":
            shown = [item for item in items if item["autor_mostrar"] != "Autor desconocido"]
            return sorted(shown, key=lambda item: (item["autor_mostrar"].casefold(), item["titulo"].casefold()))
        if scope == "series":
            shown = [item for item in items if item.get("serie_mostrar")]
            return sorted(shown, key=lambda item: (item["serie_mostrar"].casefold(), item["titulo"].casefold()))
        if scope == "tags":
            shown = [item for item in items if item.get("tags_mostrar")]
            return sorted(
                shown,
                key=lambda item: (str(item["tags_mostrar"][0]).casefold(), item["titulo"].casefold()),
            )
        if scope == "favorites":
            return [item for item in items if item_is_favorite(item)]
        return list(items)

    def _render_library_view(self):
        if self.view_mode == "covers":
            self.table_view.pack_forget()
            self.cover_view.pack(fill="both", expand=True)
            self.pagination.pack(side="bottom", fill="x", pady=(8, 0))
            self._render_covers()
        else:
            self.cover_view.pack_forget()
            self.pagination.pack_forget()
            self.table_view.pack(fill="both", expand=True)
            self._render_table()

    def _render_covers(self):
        total = len(self.filtered_items)
        start = self.grid_page * self.PAGE_SIZE
        items = self.filtered_items[start:start + self.PAGE_SIZE]
        paths = tuple(item["ruta"] for item in items)
        changed = paths != self._cover_render_paths
        self._cover_render_paths = paths
        self.dynamic_cards.clear()
        self.dynamic_buttons.clear()
        self.dynamic_labels.clear()
        self.dynamic_muted_labels.clear()
        if self._empty_library_frame is not None:
            self._empty_library_frame.grid_remove()
        if not items:
            if self._empty_library_frame is None:
                empty = tk.Frame(self.cover_inner, bd=0, pady=80)
                self._empty_library_frame = empty
                self.frames.append(empty)
                title = self._label(empty, _text("empty_library"), bold=True)
                title.configure(wraplength=360, justify="center")
                title.pack()
                hint = self._muted(empty, _text("empty_hint"), wrap=360)
                hint.pack(pady=(6, 0))
                self._empty_library_labels = (title, hint)
                self._empty_library_action = self._button(
                    empty, _text("choose_library"), self.app.elegir_biblioteca,
                    primary=True, icon="folder",
                )
            empty = self._empty_library_frame
            title, hint = self._empty_library_labels
            first_use = not core.biblioteca_configurada()
            hint.configure(text=_text("first_library_hint" if first_use else "empty_hint"))
            self._empty_library_action.configure(text=_text("choose_library"))
            if first_use:
                self._empty_library_action.pack(pady=(18, 0))
            else:
                self._empty_library_action.pack_forget()
            colors = getattr(self.app, "tema_actual", {})
            empty.configure(bg=colors.get("bg", "#f8f6f1"))
            empty.grid(row=0, column=0, columnspan=max(2, self._cover_columns), sticky="ew")
            self.dynamic_labels.append(title)
            self.dynamic_muted_labels.append(hint)
        else:
            columns = max(2, min(6, self.cover_canvas.winfo_width() // 172))
            old_columns = self._cover_columns
            self._cover_columns = columns
            for index, item in enumerate(items):
                row, column = divmod(index, columns)
                if index >= len(self._cover_card_pool):
                    self._cover_card_pool.append(self._create_cover_card())
                card, cover, title, author = self._cover_card_pool[index]
                card.grid(row=row, column=column, sticky="n", padx=5, pady=(2, 14))
                self.dynamic_cards.append(card)
                self.dynamic_buttons.extend((cover, title))
                self.dynamic_muted_labels.append(author)
                cover_key = (item["ruta"], item.get("cover_url", ""))
                if getattr(cover, "_cover_key", None) != cover_key:
                    previous = getattr(cover, "_item_path", "")
                    self.cover_images.pop((str(cover), previous), None)
                    cover.configure(image="", text=item["formato"], width=18, height=11)
                    cover._cover_loaded = False
                    cover._cover_key = cover_key
                cover._item_path = item["ruta"]
                cover._item_format = item["formato"]
                cover.configure(command=lambda selected=item: self.select_item(selected))
                title.configure(text=item["titulo"], command=lambda selected=item: self.select_item(selected))
                author.configure(text=item["autor_mostrar"])
                if not getattr(cover, "_cover_loaded", False):
                    self._request_cover(cover, *cover_key)
            for column in range(max(old_columns, columns)):
                self.cover_inner.grid_columnconfigure(column, weight=1 if column < columns else 0)
        for card, cover, _title, _author in self._cover_card_pool[len(items):]:
            card.grid_remove()
            # Hidden cards do not retain covers for books no longer displayed.
            self.cover_images.pop((str(cover), getattr(cover, "_item_path", "")), None)
            cover.configure(image="")
            cover._cover_loaded = False
        shown = min(total, start + len(items))
        self.page_label.configure(text=_text("showing", shown=shown, total=total))
        self.page_previous.configure(state="normal" if self.grid_page > 0 else "disabled")
        self.page_next.configure(state="normal" if shown < total else "disabled")
        if changed:
            self.cover_canvas.yview_moveto(0)
        self._style_dynamic_library_items()

    def _create_cover_card(self):
        """Keep a bounded pool instead of recreating Tk widgets on every query."""
        card = tk.Frame(self.cover_inner, bd=0, highlightthickness=0, padx=5, pady=4)
        cover = tk.Button(card, width=18, height=11, relief="flat", bd=0,
                          font=("Georgia", 12, "bold"), cursor="hand2", highlightthickness=2)
        cover.pack()
        title = tk.Button(card, wraplength=144, justify="left", anchor="w", relief="flat", bd=0,
                          font=("Georgia", 10), cursor="hand2", highlightthickness=2)
        title.pack(fill="x", pady=(6, 0))
        author = self._muted(card, "", wrap=144)
        author.pack(fill="x", pady=(2, 0))
        self.cards.append(card)
        self.secondary_buttons.extend((cover, title))
        return card, cover, title, author

    def _style_dynamic_library_items(self):
        colors = getattr(self.app, "tema_actual", {})
        if not colors:
            return
        for card in self.dynamic_cards:
            card.configure(bg=colors["bg"], highlightbackground=colors["bg"])
        for button in self.dynamic_buttons:
            button.configure(
                bg=colors["bg"], fg=colors["text"], activebackground=colors["quiet_active"],
                activeforeground=colors["text"],
            )
        for label in self.dynamic_labels:
            label.configure(bg=label.master.cget("bg"), fg=colors["text"])
        for label in self.dynamic_muted_labels:
            label.configure(bg=label.master.cget("bg"), fg=colors["muted"])
        self._update_selected_card()

    def _on_cover_resize(self, event):
        self.cover_canvas.itemconfigure(self.cover_window, width=event.width)
        columns = max(2, min(6, event.width // 172))
        self._pending_cover_columns = columns
        if self.view_mode != "covers":
            return
        if columns == self._cover_columns:
            if self._cover_resize_after is not None:
                self.root.after_cancel(self._cover_resize_after)
                self._cover_resize_after = None
            return
        if self._cover_resize_after is None:
            self._cover_resize_after = self.root.after(16, self._rerender_covers_after_resize)

    def _rerender_covers_after_resize(self):
        self._cover_resize_after = None
        columns = self._pending_cover_columns
        self._pending_cover_columns = None
        if columns is None or self.view_mode != "covers":
            return
        self._relayout_cover_cards(columns)

    def _relayout_cover_cards(self, columns):
        columns = max(2, min(6, int(columns)))
        old_columns = self._cover_columns
        positions = cover_grid_positions(len(self.dynamic_cards), columns)
        for card, (row, column) in zip(self.dynamic_cards, positions):
            if not card.winfo_exists():
                continue
            card.grid_configure(row=row, column=column)
        for column in range(max(old_columns, columns)):
            self.cover_inner.grid_columnconfigure(column, weight=1 if column < columns else 0)
        self._cover_columns = columns
        self._schedule_cover_scrollregion()

    def _schedule_cover_scrollregion(self, _event=None):
        if self._cover_scroll_after is not None:
            try:
                self.root.after_cancel(self._cover_scroll_after)
            except tk.TclError:
                pass
        self._cover_scroll_after = self.root.after(40, self._update_cover_scrollregion)

    def _update_cover_scrollregion(self):
        self._cover_scroll_after = None
        try:
            self.cover_canvas.configure(scrollregion=self.cover_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _render_table(self):
        items = tuple(self.filtered_items)
        if items == self._table_items:
            return
        self._table_items = items
        self._table_generation += 1
        if self._table_after is not None:
            self.root.after_cancel(self._table_after)
            self._table_after = None
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.item_by_iid.clear()
        self._append_table_batch(items, 0, self._table_generation)

    def _append_table_batch(self, items, start, generation):
        self._table_after = None
        if generation != self._table_generation:
            return
        deadline = time.perf_counter() + 0.006
        index = start
        while index < len(items):
            item = items[index]
            iid=f"book-{index}"
            self.item_by_iid[iid] = item
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(item["titulo"], item["autor_mostrar"], item["formato"], item["tamano_mostrar"], item["ruta"]),
            )
            index += 1
            if index - start >= 120 or time.perf_counter() >= deadline:
                break
        if index < len(items):
            self._table_after = self.root.after(8, self._append_table_batch, items, index, generation)

    def _request_cover(self, widget, path, remote_url=""):
        key = str(path)
        generation = self.cover_generation
        # A pending job for an old view must not suppress this view's request.
        request_key = (key, str(remote_url or ""), generation)
        with self.cover_pending_lock:
            if request_key in self.cover_pending:
                return
            self.cover_pending.add(request_key)

        def load():
            try:
                if generation != self.cover_generation:
                    return
                visible = getattr(self, "_cover_render_paths", None)
                selected = getattr(self, "selected_item", None) or {}
                if visible is not None and key not in visible and selected.get("ruta") != key:
                    return
                thumbnail = self.cover_service.thumbnail_path(Path(key), remote_url=remote_url)
                self.app._encolar_ui(self._apply_cover, widget, key, thumbnail, generation)
            finally:
                with self.cover_pending_lock:
                    self.cover_pending.discard(request_key)

        self.cover_executor.submit(load)

    def _apply_cover(self, widget, item_path, thumbnail, generation):
        try:
            if generation != self.cover_generation or not thumbnail:
                return
            if not widget.winfo_exists() or getattr(widget, "_item_path", "") != item_path:
                widget = next(
                    (
                        candidate
                        for candidate in self.dynamic_buttons
                        if candidate.winfo_exists() and getattr(candidate, "_item_path", "") == item_path
                    ),
                    None,
                )
                if widget is None:
                    return
            with Image.open(thumbnail) as image:
                photo = ImageTk.PhotoImage(image.copy())
            self.cover_images[(str(widget), item_path)] = photo
            widget._cover_loaded = True
            widget.configure(image=photo, text="", width=144, height=206)
            if self.selected_item and self.selected_item.get("ruta") == item_path:
                with Image.open(thumbnail) as detail_source:
                    detail_photo = ImageTk.PhotoImage(detail_source.resize((174, 249), Image.Resampling.LANCZOS))
                self.cover_images[("details", item_path)] = detail_photo
                self.details_cover.configure(image=detail_photo, text="", width=174, height=249)
        except Exception:
            return

    def change_page(self, delta):
        max_page = max(0, (len(self.filtered_items) - 1) // self.PAGE_SIZE)
        self.grid_page = max(0, min(max_page, self.grid_page + delta))
        self._render_covers()

    def _on_tree_select(self, _event=None):
        selection = self.tree.selection()
        if selection:
            self.select_item(self.item_by_iid.get(selection[0]))

    def _filter_selected_metadata(self, scope, field):
        if not self.selected_item:
            return
        value = str(self.selected_item.get(field) or "").strip()
        if not value or value == "Autor desconocido":
            return
        self._clear_search_placeholder()
        self.search_var.set(value)
        self.show_page(scope)

    def _filter_selected_tag(self, position):
        if not self.selected_item:
            return
        tags = list(self.selected_item.get("tags_mostrar") or [])
        if position < 0 or position >= len(tags):
            return
        self._clear_search_placeholder()
        self.search_var.set(str(tags[position]))
        self.show_page("tags")

    def _refresh_detail_metadata_controls(self):
        item = self.selected_item or {}
        interactive = bool(item) and not self.app.trabajando
        author = str(item.get("autor_mostrar") or "").strip()
        author_known = bool(author and author != "Autor desconocido")
        author_enabled = interactive and author_known
        self.detail_author.configure(
            text=author or _text("author"),
            state="normal" if author_enabled else "disabled",
            cursor=interactive_cursor(author_enabled),
        )

        favorite = item_is_favorite(item)
        self.detail_favorite._detail_accent = favorite
        self.detail_favorite.configure(
            text=_text("favorite_active" if favorite else "favorite_add"),
            state="normal" if interactive else "disabled",
            cursor=interactive_cursor(interactive),
        )

        series = str(item.get("serie_mostrar") or "").strip()
        if series:
            self.detail_series.configure(
                text=series,
                state="normal" if interactive else "disabled",
                cursor=interactive_cursor(interactive),
            )
            if not self.detail_series.winfo_manager():
                self.detail_series.pack(fill="x", pady=(0, 5), before=self.detail_separator)
        else:
            self.detail_series.pack_forget()

        tags = [str(tag).strip() for tag in item.get("tags_mostrar", []) if str(tag).strip()]
        visible_tags = tags[:4]
        for index, button in enumerate(self.detail_tag_buttons):
            if index < len(visible_tags):
                text = visible_tags[index]
                if index == 3 and len(tags) > 4:
                    text = f"{text}  +{len(tags) - 4}"
                button.configure(
                    text=text,
                    state="normal" if interactive else "disabled",
                    cursor=interactive_cursor(interactive),
                )
                button.grid()
            else:
                button.grid_remove()
        if visible_tags:
            if not self.detail_tags.winfo_manager():
                self.detail_tags.pack(fill="x", pady=(0, 1), before=self.detail_separator)
        else:
            self.detail_tags.pack_forget()
        self._apply_detail_metadata_theme(getattr(self.app, "tema_actual", {}))

    def toggle_selected_favorite(self):
        if not self.selected_item or self.app.trabajando:
            return
        item = self.selected_item
        favorite = item_is_favorite(item)
        changes = {"favorite": not favorite}
        if favorite:
            tags = [
                tag for tag in item.get("tags_mostrar", [])
                if str(tag).strip().casefold() not in FAVORITE_TAGS
            ]
            if tags != list(item.get("tags_mostrar") or []):
                changes["tags"] = tags
        try:
            self.app.indice = core.aplicar_correccion_manual_indice(item["ruta"], changes, self.app.indice)
            updated = next(
                (
                    row for row in self.app.indice.get("archivos", [])
                    if core.clave_ruta_resuelta(row.get("ruta", "")) == core.clave_ruta_resuelta(item["ruta"])
                ),
                None,
            )
            self.refresh_library()
            if updated:
                self.select_item(display_item(updated))
            self.app.estado(_text("favorite_removed" if favorite else "favorite_added"))
        except Exception as exc:
            messagebox.showerror(core.tr("error_title"), str(exc))

    def select_item(self, item):
        if not item:
            return
        catalog = None
        try:
            catalog = core.registro_catalogo_para_ruta(item["ruta"])
        except Exception:
            catalog = None
        merged = dict(item)
        if catalog:
            field_map = {
                "title": "titulo", "author": "autor", "series": "serie",
                "language": "idioma", "publisher": "editorial",
                "publication_year": "anio", "edition_label": "edicion",
            }
            for source, target in field_map.items():
                if catalog.get(source) and not merged.get(target):
                    merged[target] = catalog[source]
            for key in ("isbn", "cover_url", "provenance", "confidence"):
                if catalog.get(key) not in (None, "", {}):
                    merged[key if key != "confidence" else "confianza_global"] = catalog[key]
        item = display_item(merged)
        self.selected_item = item
        self._update_selected_card()
        if not self.app.trabajando:
            self.open_button.configure(state="normal")
            self.metadata_button.configure(state="normal")
            self.lookup_metadata_button.configure(state="normal")
            self.copy_path_button.configure(state="normal")
            self.show_folder_button.configure(state="normal")
        self.detail_title.configure(text=item["titulo"])
        self._refresh_detail_metadata_controls()
        edition = []
        for label, key in [
            (_text("isbn"), "isbn"), (_text("language"), "idioma_mostrar"),
            (_text("publisher"), "editorial_mostrar"), (_text("year"), "anio_mostrar"),
        ]:
            if item.get(key):
                edition.append(f"{label}: {item[key]}")
        if item.get("edicion_mostrar"):
            edition.append(f"{_text('edition')}: {item['edicion_mostrar']}")
        self.detail_group_values["edition"].configure(text="\n".join(edition) or "—")
        self.detail_group_values["file_data"].configure(
            text=(
                f"{_text('format')}: {item['formato']}  ·  {_text('size')}: {item['tamano_mostrar']}\n"
                f"{_text('path')}:\n{full_display_path(item['ruta'])}"
            )
        )
        provenance = provenance_lines(item)
        confidence = item.get("confianza_mostrar")
        if confidence not in {None, ""}:
            provenance.insert(0, f"{_text('confidence')}: {confidence}%")
        self.detail_group_values["provenance"].configure(
            text="\n".join(provenance) if provenance else _text("no_provenance")
        )
        self.details_cover.configure(image="", text=item["formato"], width=16, height=7)
        self.details_cover._item_path = item["ruta"]
        self._request_cover(self.details_cover, item["ruta"], item.get("cover_url", ""))

    def shutdown(self):
        self._hide_tooltip()
        self._table_generation += 1
        for name in ("_table_after", "_refresh_after", "_cover_resize_after", "_cover_scroll_after"):
            pending = getattr(self, name, None)
            if pending is not None:
                self.root.after_cancel(pending)
                setattr(self, name, None)
        self.release_cover_images()
        self.cover_executor.shutdown(wait=False, cancel_futures=True)

    def release_cover_images(self):
        self.cover_generation += 1
        self.cover_images.clear()
        for button in self.dynamic_buttons:
            if not getattr(button, "_item_path", None):
                continue
            try:
                button.configure(
                    image="",
                    text=getattr(button, "_item_format", ""),
                    width=18,
                    height=11,
                )
                button._cover_loaded = False
            except tk.TclError:
                pass
        try:
            text = self.selected_item.get("formato", "") if self.selected_item else "▣"
            self.details_cover.configure(image="", text=text, width=16, height=7)
        except tk.TclError:
            pass

    def _update_selected_card(self):
        colors = getattr(self.app, "tema_actual", {})
        selected_path = self.selected_item.get("ruta") if self.selected_item else None
        for button in self.dynamic_buttons:
            path = getattr(button, "_item_path", None)
            if not path:
                continue
            selected = path == selected_path
            button.configure(
                bd=0,
                relief="flat",
                highlightthickness=3 if selected else 1,
                highlightbackground=colors.get("accent" if selected else "border", "#a9573e" if selected else "#ded8d0"),
                highlightcolor=colors.get("accent", "#a9573e"),
            )

    def open_selected(self):
        if not self.selected_item:
            return
        path = Path(self.selected_item["ruta"])
        if not path.exists():
            messagebox.showwarning(core.tr("error_title"), str(path))
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror(core.tr("error_title"), str(exc))

    def copy_selected_path(self):
        if not self.selected_item:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(full_display_path(self.selected_item["ruta"]))

    def show_selected_folder(self):
        if not self.selected_item:
            return
        path = Path(self.selected_item["ruta"])
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception as exc:
            messagebox.showerror(core.tr("error_title"), str(exc))

    def edit_selected_metadata(self):
        if not self.selected_item or self.app.trabajando:
            return
        item = display_item(dict(self.selected_item))
        colors = getattr(self.app, "tema_actual", {})
        window = tk.Toplevel(self.root)
        window.title(_text("edit_metadata"))
        window.geometry("560x590")
        window.minsize(500, 520)
        window.transient(self.root)
        window.configure(bg=colors.get("bg", "#faf8f4"))
        body = tk.Frame(window, bg=colors.get("bg", "#faf8f4"), padx=22, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(
            body, text=_text("edit_metadata"), font=("Georgia", 18), anchor="w",
            bg=colors.get("bg", "#faf8f4"), fg=colors.get("text", "#2d2a27"),
        ).pack(fill="x")
        tk.Label(
            body, text=_text("manual_edit_help"), font=("Segoe UI", 9), anchor="w",
            justify="left", wraplength=500, bg=colors.get("bg", "#faf8f4"),
            fg=colors.get("muted", "#706a64"),
        ).pack(fill="x", pady=(4, 14))

        form = tk.Frame(body, bg=colors.get("card", "#fffdf9"), padx=14, pady=12)
        form.pack(fill="both", expand=True)
        fields = [
            ("titulo", "title", item.get("titulo", "")),
            ("autor", "author", item.get("autor", "")),
            ("isbn", "isbn", item.get("isbn", "")),
            ("idioma", "language", item.get("idioma_mostrar", "")),
            ("editorial", "publisher", item.get("editorial_mostrar", "")),
            ("anio", "year", item.get("anio_mostrar", "")),
            ("serie", "series", item.get("serie_mostrar", "")),
            ("edicion", "edition", item.get("edicion_mostrar", "")),
            ("tags", "tags", ", ".join(str(tag) for tag in item.get("tags_mostrar", []))),
        ]
        variables = {}
        for row, (field, label_key, value) in enumerate(fields):
            label = tk.Label(
                form, text=_text(label_key), font=("Segoe UI", 9), anchor="w",
                bg=colors.get("card", "#fffdf9"), fg=colors.get("muted", "#706a64"),
            )
            label.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            variable = tk.StringVar(value=str(value or ""))
            entry = tk.Entry(
                form, textvariable=variable, font=("Segoe UI", 10), relief="flat", bd=1,
                bg=colors.get("entry_bg", "#fffdf9"), fg=colors.get("text", "#2d2a27"),
                insertbackground=colors.get("text", "#2d2a27"),
            )
            entry.grid(row=row, column=1, sticky="ew", pady=6, ipady=6)
            variables[field] = variable
        form.grid_columnconfigure(1, weight=1)

        actions = tk.Frame(body, bg=colors.get("bg", "#faf8f4"))
        actions.pack(fill="x", pady=(14, 0))

        def save():
            try:
                changes = {field: variable.get().strip() for field, variable in variables.items()}
                self.app.indice = core.aplicar_correccion_manual_indice(
                    item["ruta"], changes, self.app.indice,
                )
                self.refresh_library()
                updated = next(
                    (
                        row for row in self.app.indice.get("archivos", [])
                        if core.clave_ruta_resuelta(row.get("ruta", "")) == core.clave_ruta_resuelta(item["ruta"])
                    ),
                    None,
                )
                if updated:
                    self.select_item(display_item(updated))
                self.app.estado(_text("saved_metadata"))
                window.destroy()
            except Exception as exc:
                messagebox.showerror(core.tr("error_title"), str(exc), parent=window)

        save_button = RoundedButton(
            actions, text=_text("save_metadata"), command=save, width=170, height=40,
            radius=8, font=("Segoe UI", 9, "bold"),
        )
        save_button.set_theme(
            colors.get("primary_bg", "#a9573e"), colors.get("primary_text", "#ffffff"),
            colors.get("primary_bg", "#a9573e"), colors.get("primary_active", "#8f4935"),
            colors.get("button_disabled", "#f1ede8"), colors.get("disabled_text", "#aaa19a"),
        )
        save_button.pack(side="right")
        window.grab_set()

    def review_selected_metadata(self):
        if not self.selected_item or self.app.trabajando:
            return
        self.app.renombrar_por_metadatos_thread([Path(self.selected_item["ruta"])])

    def resume_pending_reviews(self):
        try:
            store = core.duplicate_review_store()
            session_id = store.latest_open_session()
            if not session_id:
                self._update_review_count()
                return
            rows = []
            offset = 0
            while True:
                page = store.page(session_id, offset=offset, limit=500, state="pending")
                rows.extend(page)
                if len(page) < 500:
                    break
                offset += len(page)
            if not rows:
                self._update_review_count()
                return
            self.app.abrir_asistente_dobles(
                [row["pair"] for row in rows],
                existing_review_session=session_id,
                review_ordinals=[row["ordinal"] for row in rows],
            )
        except Exception as exc:
            messagebox.showerror(core.tr("error_title"), str(exc))

    def scan_library_duplicates(self):
        if self.app.trabajando:
            return
        self.review_result_label.configure(text="")

        def task():
            try:
                self.app._encolar_ui(self.app.bloquear, True)
                duplicates = core.buscar_dobles_biblioteca(self.app.indice, cancellation=self.app.cancel_token)
                self.app._encolar_ui(self.review_result_label.configure, text=_text("review_count", count=len(duplicates)))
                self.app._encolar_ui(self.app.abrir_asistente_dobles, duplicates)
            except Exception as exc:
                self.app._encolar_ui(messagebox.showerror, core.tr("error_title"), str(exc))
            finally:
                self.app._encolar_ui(self.app.bloquear, False)
                self.app._encolar_ui(self._update_review_count)

        self.app._start_worker(task)

    def save_settings(self):
        theme_labels = {
            _text("theme_system"): "system",
            _text("theme_light"): "light",
            _text("theme_dark"): "dark",
        }
        saved = core.guardar_configuracion_operacion(
            {
                "ocr_max_pages": self.ocr_pages_var.get(),
                "offline_mode": self.offline_var.get(),
                "theme": theme_labels.get(self.theme_var.get(), "system"),
            }
        )
        self.app._aplicar_configuracion_operacion(saved)
        self.app.establecer_preferencia_tema(saved["theme"])
        self.refresh_provider_health()
        self.app.estado(_text("settings_saved"))

    def refresh_provider_health(self):
        state = core.estado_proveedores_web()
        if not state:
            self.provider_label.configure(text="—")
            return
        summary = "  •  ".join(f"{name}: {info.get('status', 'unknown')}" for name, info in sorted(state.items()))
        self.provider_label.configure(text=summary)

    def focus_search(self, _event=None):
        self.show_page("library")
        self._clear_search_placeholder()
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")
        return "break"

    def _show_search_placeholder(self):
        if self.search_var.get():
            return
        self.search_placeholder_active = True
        self.search_var.set(_text("search"))
        colors = getattr(self.app, "tema_actual", {})
        self.search_entry.configure(fg=colors.get("muted", "#5b6474"))

    def _clear_search_placeholder(self, _event=None):
        if not self.search_placeholder_active:
            return
        self.search_placeholder_active = False
        self.search_var.set("")
        colors = getattr(self.app, "tema_actual", {})
        self.search_entry.configure(fg=colors.get("text", "#172033"))

    def _restore_search_placeholder(self, _event=None):
        if not self.search_var.get().strip():
            self._show_search_placeholder()

    def translate(self):
        self.brand_label.configure(text=_text("brand"))
        self.brand_tagline.configure(text=_text("brand_tagline"))
        self._refresh_navigation_labels()
        if self.search_placeholder_active:
            self.search_var.set(_text("search"))
        self.cover_button.configure(text="")
        self.table_button.configure(text="")
        self.details_button.configure(text="")
        self.cover_button.configure(accessible_name=_text("covers"))
        self.table_button.configure(accessible_name=_text("table"))
        self.details_button.configure(accessible_name=_text("details"))
        self.filter_buttons["all"].configure(text=_text("all"))
        self.filter_buttons["other"].configure(text=_text("other_formats"))
        self.sort_label.configure(text=_text("sort_by"))
        self.sort_combo.configure(values=(_text("sort_recent"), _text("sort_title")))
        self.sort_var.set(_text("sort_recent"))
        self.open_button.configure(text=_text("open"))
        self.metadata_button.configure(text=_text("edit_metadata"))
        self.lookup_metadata_button.configure(text=_text("lookup_metadata"))
        self.copy_path_button.configure(text=_text("copy_path"))
        self.show_folder_button.configure(text=_text("show_folder"))
        self.details_heading.configure(text=_text("details"))
        self._refresh_detail_metadata_controls()
        for key, heading in self.detail_group_headings.items():
            heading.configure(text=_text(key))
        for column, title_key in [
            ("title", "title"), ("author", "author"), ("format", "format"),
            ("size", "size"), ("path", "path"),
        ]:
            self.tree.heading(column, text=_text(title_key))
        self.page_previous.configure(text=_text("previous"))
        self.page_next.configure(text=_text("next"))
        self.safe_import_label.configure(text=_text("safe_import"))
        self.resume_reviews_button.configure(text=_text("resume_reviews"))
        self.theme_label.configure(text=_text("theme"))
        theme_values = (_text("theme_system"), _text("theme_light"), _text("theme_dark"))
        self.theme_combo.configure(values=theme_values)
        theme_index = {"system": 0, "light": 1, "dark": 2}.get(getattr(self.app, "theme_preference", "system"), 0)
        self.theme_var.set(theme_values[theme_index])
        for _card, title, help_label, title_key, help_key in self.import_steps:
            title.configure(text=_text(title_key))
            help_label.configure(text=_text(help_key))
        self._update_heading()
        self.refresh_library()

    def apply_theme(self, colors):
        if not colors:
            return
        self._hide_tooltip()
        self.root.configure(bg=colors["bg"])
        self.shell.configure(bg=colors["border"])
        for frame in self.frames:
            try:
                frame.configure(bg=colors["bg"])
            except Exception:
                pass
        for card in self.cards:
            try:
                card.configure(
                    bg=colors["card"],
                    highlightbackground=colors["border"],
                    highlightcolor=colors["accent"],
                )
            except Exception:
                pass
        for label in self.labels:
            try:
                label.configure(bg=label.master.cget("bg"), fg=colors["text"])
            except Exception:
                pass
        for label in self.muted_labels:
            try:
                label.configure(bg=label.master.cget("bg"), fg=colors["muted"])
            except Exception:
                pass
        for entry in self.entries:
            try:
                entry.configure(bg=colors["entry_bg"], fg=colors["text"], insertbackground=colors["text"])
            except Exception:
                pass
        for button in self.secondary_buttons:
            try:
                self._set_button_theme(
                    button,
                    colors["button_bg"],
                    colors["text"],
                    colors["border"],
                    colors["button_active"],
                    colors["button_disabled"],
                    colors["disabled_text"],
                )
            except Exception:
                pass
        for card in self.dynamic_cards:
            try:
                card.configure(bg=colors["bg"], highlightbackground=colors["bg"])
            except Exception:
                pass
        for button in self.dynamic_buttons:
            try:
                button.configure(
                    bg=colors["bg"], fg=colors["text"], activebackground=colors["quiet_active"],
                    activeforeground=colors["text"],
                )
            except Exception:
                pass
        for button in self.primary_buttons:
            try:
                self._set_button_theme(
                    button,
                    colors["primary_bg"],
                    colors["primary_text"],
                    colors["primary_bg"],
                    colors["primary_active"],
                    colors["button_disabled"],
                    colors["disabled_text"],
                )
            except Exception:
                pass
        for rounded_card, role in self.rounded_cards:
            try:
                inner = colors["entry_bg"] if role == "entry" else colors["card"]
                rounded_card.set_theme(colors["bg"], inner, colors["border"])
            except Exception:
                pass
        try:
            self.cover_canvas.configure(bg=colors["bg"])
            self.library_panes.configure(bg=colors["border"])
            self.search_shell.set_theme(colors["bg"], colors["entry_bg"], colors["accent"])
            self._draw_search_icon(colors)
            for canvas in self.page_scroll_canvases.values():
                canvas.configure(bg=colors["bg"])
            self.sidebar.configure(highlightbackground=colors["border"], highlightcolor=colors["border"])
            self.brand_icon_label.configure(fg=colors["accent"])
            self.detail_separator.configure(bg=colors["border"])
            self.app.texto.configure(bg=colors["log_bg"], fg=colors["text"], insertbackground=colors["text"])
            self.offline_check.configure(
                bg=colors["card"], fg=colors["text"], activebackground=colors["card"],
                activeforeground=colors["text"], selectcolor=colors["entry_bg"],
            )
            self.ocr_spinbox.configure(bg=colors["entry_bg"], fg=colors["text"], buttonbackground=colors["button_bg"])
            self.app.style.configure(
                "Treeview",
                background=colors["card"], fieldbackground=colors["card"], foreground=colors["text"],
                rowheight=34, bordercolor=colors["border"],
            )
            self.app.style.configure("Treeview.Heading", background=colors["quiet_bg"], foreground=colors["text"], relief="flat")
            self.app.style.map("Treeview", background=[("selected", colors["primary_bg"])], foreground=[("selected", colors["primary_text"])])
            self._apply_combobox_theme(colors)
            self.app.style.configure("Visual.Horizontal.TProgressbar", troughcolor=colors["quiet_bg"], background=colors["progress"], thickness=8)
        except Exception:
            pass
        self._refresh_bound_icons(colors)
        self._apply_detail_metadata_theme(colors)
        self._update_navigation_state()
        self._update_filter_state()
        self._update_view_state()
        self._update_selected_card()
        self.set_import_step(1 if self.app.trabajando and self.current_page == "import" else 0)
        if self.search_placeholder_active:
            self.search_entry.configure(fg=colors["muted"])
        self._refresh_navigation_labels()

    def _apply_combobox_theme(self, colors):
        style_name = "Library.TCombobox"
        self.app.style.configure(
            style_name,
            fieldbackground=colors["entry_bg"],
            background=colors["button_bg"],
            foreground=colors["text"],
            arrowcolor=colors["text"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
            selectbackground=colors["primary_bg"],
            selectforeground=colors["primary_text"],
            padding=(7, 5),
        )
        self.app.style.map(
            style_name,
            fieldbackground=[
                ("readonly", colors["entry_bg"]),
                ("disabled", colors["button_disabled"]),
            ],
            foreground=[
                ("readonly", colors["text"]),
                ("disabled", colors["disabled_text"]),
            ],
            background=[
                ("readonly", colors["button_bg"]),
                ("active", colors["button_active"]),
            ],
            arrowcolor=[
                ("readonly", colors["text"]),
                ("disabled", colors["disabled_text"]),
            ],
        )
        self.root.option_add("*TCombobox*Listbox.background", colors["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", colors["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", colors["primary_bg"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", colors["primary_text"])
        combos = [self.format_combo, self.sort_combo]
        if hasattr(self, "theme_combo"):
            combos.append(self.theme_combo)
        for combo in combos:
            try:
                popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
                listbox = f"{popdown}.f.l"
                combo.tk.call(
                    listbox,
                    "configure",
                    "-background",
                    colors["card"],
                    "-foreground",
                    colors["text"],
                    "-selectbackground",
                    colors["primary_bg"],
                    "-selectforeground",
                    colors["primary_text"],
                    "-highlightbackground",
                    colors["border"],
                    "-highlightcolor",
                    colors["accent"],
                )
            except tk.TclError:
                pass
