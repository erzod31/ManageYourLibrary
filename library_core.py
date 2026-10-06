import hashlib
import html
import json
import locale
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import zipfile
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET

import ai_model_catalog as _ai_model_catalog
import ai_paths as _ai_paths
import ai_runtime_manager as _ai_runtime_manager
import book_identity_scorer as _deep_identity_scorer
import metadata_decision as _metadata_decision
from ai_local_judge import request_ai_judgement
from core import config_store as _config_store
from core import catalog_store as _catalog_store
from core import duplicate_engine as _duplicate_engine
from core import document_context as _document_context
from core import document_readers as _document_readers
from core import duplicate_review_store as _duplicate_review_store
from core import file_identity as _file_identity
from core import file_transactions as _file_transactions
from core import index_store as _index_store
from core import index_service as _index_service
from core import naming as _naming
from core import normalizer as _normalizer
from core import operation_plans as _operation_plans
from core import performance_pipeline as _performance_pipeline
from core import undo_history as _undo_history
from core.cancellation import OperationCancelled
from metadata import external_providers as _external_providers
from metadata import orchestration as _orchestration
from metadata import scoring as _scoring
from review_explainer import explain_review_reasons

APP_NAME = _config_store.APP_NAME


def _default_start_dir() -> Path:
    return _config_store.default_start_dir()


def _app_data_dir() -> Path:
    return _config_store.app_data_dir()


DEFAULT_START_DIR = _default_start_dir()
APP_DATA = _app_data_dir()
CONFIG_JSON = APP_DATA / "config.json"
CONFIG_VERSION = _config_store.CONFIG_VERSION
INDICE_JSON = APP_DATA / "library_index.json"
HISTORIAL_CSV = APP_DATA / "library_history.csv"
UNDO_JSONL = APP_DATA / "undo_log.jsonl"
FILE_TRANSACTION_JOURNAL = APP_DATA / "file_transactions.jsonl"
TRASH_MANIFEST_JSONL = APP_DATA / "trash_manifest.jsonl"
OPERATION_PLANS_DB = APP_DATA / "operation_plans.sqlite3"
DUPLICATE_REVIEW_DB = APP_DATA / "duplicate_reviews.sqlite3"
CATALOG_DB = APP_DATA / "library_catalog.sqlite3"
TRASH_DIR_NAME = ".trash_manageyourlibrary"
MAX_WEB_CACHE_ENTRIES = 2500
ANALYSIS_CACHE_VERSION = "identity_v11_provenance"
AI_CONFIG_KEY = "ai_local"

FAST_OK = _performance_pipeline.FAST_OK
NEEDS_OCR = _performance_pipeline.NEEDS_OCR
NEEDS_REVIEW = _performance_pipeline.NEEDS_REVIEW
OCR_OK = _performance_pipeline.OCR_OK
ERROR = _performance_pipeline.ERROR
FAST_MODE = _performance_pipeline.FAST_MODE
DEEP_MODE = _performance_pipeline.DEEP_MODE
UiEventQueue = _performance_pipeline.UiEventQueue
OperationPlanStore = _operation_plans.OperationPlanStore


LANGUAGE_NAMES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "zh": "中文",
}
LANGUAGE_CODES_BY_NAME = {v: k for k, v in LANGUAGE_NAMES.items()}

TEXTS = {
    "es": {
        "window_title": "Gestiona tu biblioteca",
        "title": "Gestiona tu biblioteca",
        "subtitle": "Organiza, agrega, verifica duplicados y busca metadatos para tus libros.",
        "language": "Idioma:",
        "dark_mode": "Modo oscuro",
        "light_mode": "Modo claro",
        "library_active": "Biblioteca activa",
        "library_help": "Puedes escribir la ruta directamente y presionar Enter, o usar el botón de tres puntos.",
        "route": "Ruta:",
        "index_choose": "Índice: escribe o elige una biblioteca",
        "index_none": "Índice: todavía no creado",
        "index_status": "Índice: {count} libros | actualizado: {date}",
        "actions": "Acciones principales",
        "add_books": "Agregar libros",
        "metadata": "Buscar metadatos",
        "check_folder_duplicates": "Comprobar dobles entre carpetas",
        "open_library": "Abrir biblioteca",
        "status_title": "Estado",
        "initializing": "Iniciando...",
        "log_title": "Registro de actividad",
        "first_state": "Escribe o elige la ruta de la biblioteca.",
        "valid_library": "Escribe o elige una biblioteca válida.",
        "empty_route_title": "Ruta vacía",
        "empty_route_msg": "Escribe o elige una ruta de biblioteca.",
        "choose_library_title": "Selecciona la carpeta de tu biblioteca",
        "create_folder_title": "Crear carpeta",
        "create_folder_msg": "La ruta no existe:\n\n{path}\n\n¿Quieres crearla como biblioteca?",
        "invalid_route_title": "Ruta inválida",
        "invalid_route_msg": "La ruta indicada no es una carpeta.",
        "library_selected": "Biblioteca seleccionada:\n{path}\n",
        "updating_index": "Actualizando índice de la biblioteca...",
        "updating_index_path": "Actualizando índice de la biblioteca:\n{path}",
        "index_first_time": "Esto puede tardar la primera vez.\n",
        "index_ready": "\nÍndice listo. Libros indexados: {count}",
        "ready": "Listo.",
        "missing_library_title": "Falta biblioteca",
        "missing_library_msg": "Primero escribe o elige la ruta de la biblioteca.",
        "add_dialog_title": "Selecciona uno o varios libros para agregar",
        "filetype_books": "Libros",
        "filetype_all": "Todos los archivos",
        "selected_books": "Libros seleccionados: {count}",
        "verifying": "Verificando duplicados {i}/{total}: {name}",
        "new_book": "LIBRO NUEVO: {name}",
        "searching_web_name": "Analizando metadatos internos, texto e ISBN...",
        "metadata_searching": "Confirmando con bases de metadatos...",
        "metadata_confirm_isbn": "Confirmando por ISBN...",
        "metadata_confirm_doi": "Confirmando por DOI...",
        "metadata_confirm_search": "Buscando confirmación adicional...",
        "metadata_recovery": "Revisando variantes alternativas con la evidencia ya recopilada...",
        "pipeline_level0": "Nivel 0: metadatos internos y nombre de archivo",
        "pipeline_cache": "Análisis reutilizado desde caché local",
        "pipeline_fast_path": "Resolución rápida con metadatos estructurados suficientes",
        "pipeline_fast_complete": "Análisis rápido completado",
        "pipeline_ocr_required": "OCR diferido requerido",
        "pipeline_ocr_skipped": "OCR omitido: confianza suficiente",
        "pipeline_review": "Archivo enviado a revisión",
        "pipeline_fast_batch_status": "Análisis rápido {done}/{total}: {name}",
        "pipeline_ocr_batch_status": "Cola OCR {done}/{total}: {name}",
        "pipeline_level1": "Nivel 1: texto digital útil encontrado",
        "pipeline_ocr_hint": "OCR aportó evidencias; se usará solo como pista",
        "pipeline_deep_identity": "Deep Identity Scan: cruzando evidencias locales",
        "pipeline_external": "Verificación externa selectiva",
        "suggested_name": "Nombre sugerido: {name}",
        "source_conf": "Fuente: {source} | Confianza: {confidence}",
        "no_reliable": "No hubo correspondencia fiable.",
        "move_original": "Se deja sin cambios en su ubicación original.",
        "moved_final": "MOVIDO A BIBLIOTECA: {name}",
        "destination": "Destino: {path}",
        "not_added": "NO AGREGADO: {name}",
        "reason_exists": "Motivo: ya tienes este libro.",
        "exists_in": "Existe en: {path}",
        "reason_possible": "Motivo: posible duplicado. Por seguridad no se agregó.",
        "possible_match": "Posible coincidencia: {path}",
        "error_file": "ERROR: {name}",
        "updating_final_index": "Actualizando índice de biblioteca...",
        "add_summary": "Proceso terminado.\n\nMovidos a biblioteca total: {total}\nMovidos renombrados por metadatos: {renamed}\nSin coincidencia fiable, sin mover: {original}\nNo agregados porque ya existían: {duplicates}\nNo agregados por posible duplicado: {possible}\nErrores: {errors}",
        "metadata_window_title": "Buscar metadatos de libros",
        "metadata_question": "¿Qué quieres analizar para buscar metadatos y renombrar?",
        "files": "Ficheros",
        "folder": "Carpeta",
        "cancel": "Cancelar",
        "metadata_files_title": "Selecciona los libros que quieres renombrar por metadatos",
        "metadata_folder_title": "Selecciona la carpeta con libros para renombrar",
        "no_books_title": "Sin libros",
        "no_books_msg": "No se encontraron libros compatibles.",
        "metadata_header": "Buscar metadatos de libros",
        "metadata_selected": "Libros seleccionados: {count}",
        "metadata_only_rename": "Esta función solo renombra. No mueve archivos.",
        "does_not_exist": "NO EXISTE: {path}",
        "not_a_book": "No se trata de un libro: {name}",
        "metadata_status": "Buscando metadatos {i}/{total}: {name}",
        "analyzing": "Analizando: {name}",
        "unreliable_leave": "Sin correspondencia fiable. Se deja tal cual.",
        "best_confidence": "Sin cambios. Confianza: {confidence}\n",
        "suggested_equal": "El nombre sugerido es igual al actual. Se deja tal cual.\n",
        "renamed": "RENOMBRADO:",
        "before": "  Antes: {name}",
        "now": "  Ahora: {name}",
        "metadata_source_conf": "  Fuente: {source} | Confianza: {confidence}\n",
        "metadata_summary": "Proceso de metadatos terminado.\n\nRenombrados: {renamed}\nSin cambio: {unchanged}\nErrores: {errors}",
        "folder_duplicates_dialog_title": "Selecciona la carpeta base",
        "folder_duplicates_dialog_title_secondary": "Selecciona la carpeta a comparar",
        "folder_duplicates_invalid_pair_title": "Carpetas no válidas",
        "folder_duplicates_invalid_pair_msg": "Elige dos carpetas distintas. Una carpeta no puede estar dentro de la otra para esta comparación.",
        "folder_duplicates_header": "Comprobador de libros dobles entre carpetas",
        "folder_duplicates_selected": "Carpeta base: {path_a}\nCarpeta a comparar: {path_b}",
        "folder_duplicates_indexing": "Buscando libros en ambas carpetas...",
        "folder_duplicates_no_books_title": "Sin libros",
        "folder_duplicates_no_books_msg": "No se encontraron libros compatibles en una o ambas carpetas.",
        "folder_duplicates_analyzing": "Analizando posibles dobles {i}/{total}: {name}",
        "folder_duplicates_fast_scan": "Escaneo rápido {i}/{total}: {name}",
        "folder_duplicates_hashing": "Comprobando dobles exactos entre carpetas por tamaño y hash...",
        "folder_duplicates_fast_summary": "Escaneo rápido terminado: {books} libros, {candidates} candidatos para análisis profundo.",
        "folder_duplicates_deep_analyzing": "Análisis profundo de candidato {i}/{total}: {name}",
        "folder_duplicates_summary": "Comparación de carpetas terminada.\n\nCarpeta base: {path_a}\nCarpeta comparada: {path_b}\nLibros en base: {books_a}\nLibros en comparación: {books_b}\nLibros analizados: {books}\nPosibles dobles entre carpetas: {duplicates}\nErrores: {errors}",
        "folder_duplicates_no_doubles": "No se encontraron dobles entre las dos carpetas.",
        "eta_remaining": "Tiempo restante: {eta}",
        "eta_calculating": "calculando...",
        "eta_under_5s": "menos de 5 s",
        "eta_s": "{s} s",
        "eta_ms": "{m} min {s} s",
        "eta_hms": "{h} h {m} min {s} s",
    },
    "en": {
        "window_title": "Manage Your Library",
        "title": "Manage Your Library",
        "subtitle": "Organize, add, check duplicates, and search metadata for your books.",
        "language": "Language:",
        "dark_mode": "Dark mode",
        "light_mode": "Light mode",
        "library_active": "Active library",
        "library_help": "You can type the path directly and press Enter, or use the three-dot button.",
        "route": "Path:",
        "index_choose": "Index: type or choose a library",
        "index_none": "Index: not created yet",
        "index_status": "Index: {count} books | updated: {date}",
        "actions": "Main actions",
        "add_books": "Add books",
        "metadata": "Search metadata",
        "check_folder_duplicates": "Check duplicates between folders",
        "open_library": "Open library",
        "status_title": "Status",
        "initializing": "Starting...",
        "log_title": "Activity log",
        "first_state": "Type or choose the library path.",
        "valid_library": "Type or choose a valid library.",
        "empty_route_title": "Empty path",
        "empty_route_msg": "Type or choose a library path.",
        "choose_library_title": "Select your library folder",
        "create_folder_title": "Create folder",
        "create_folder_msg": "The path does not exist:\n\n{path}\n\nCreate it as the library?",
        "invalid_route_title": "Invalid path",
        "invalid_route_msg": "The selected path is not a folder.",
        "library_selected": "Library selected:\n{path}\n",
        "updating_index": "Updating library index...",
        "updating_index_path": "Updating library index:\n{path}",
        "index_first_time": "This may take a while the first time.\n",
        "index_ready": "\nIndex ready. Books indexed: {count}",
        "ready": "Ready.",
        "missing_library_title": "Missing library",
        "missing_library_msg": "First type or choose the library path.",
        "add_dialog_title": "Select one or more books to add",
        "filetype_books": "Books",
        "filetype_all": "All files",
        "selected_books": "Books selected: {count}",
        "verifying": "Checking duplicates {i}/{total}: {name}",
        "new_book": "NEW BOOK: {name}",
        "searching_web_name": "Analyzing internal metadata, text, and ISBN...",
        "metadata_searching": "Confirming with metadata databases...",
        "metadata_confirm_isbn": "Confirming by ISBN...",
        "metadata_confirm_doi": "Confirming by DOI...",
        "metadata_confirm_search": "Searching for additional confirmation...",
        "metadata_recovery": "Checking alternative variants with already collected evidence...",
        "pipeline_level0": "Level 0: internal metadata and filename",
        "pipeline_cache": "Analysis reused from local cache",
        "pipeline_fast_path": "Fast resolution with sufficient structured metadata",
        "pipeline_fast_complete": "Fast analysis completed",
        "pipeline_ocr_required": "Deferred OCR required",
        "pipeline_ocr_skipped": "OCR skipped: sufficient confidence",
        "pipeline_review": "File sent to review",
        "pipeline_fast_batch_status": "Fast analysis {done}/{total}: {name}",
        "pipeline_ocr_batch_status": "OCR queue {done}/{total}: {name}",
        "pipeline_level1": "Level 1: useful digital text found",
        "pipeline_ocr_hint": "OCR provided evidence; it will only be used as a hint",
        "pipeline_deep_identity": "Deep Identity Scan: cross-checking local evidence",
        "pipeline_external": "Selective external verification",
        "suggested_name": "Suggested name: {name}",
        "source_conf": "Source: {source} | Confidence: {confidence}",
        "no_reliable": "No reliable match found.",
        "move_original": "It will be left unchanged in its original location.",
        "moved_final": "MOVED TO LIBRARY: {name}",
        "destination": "Destination: {path}",
        "not_added": "NOT ADDED: {name}",
        "reason_exists": "Reason: you already have this book.",
        "exists_in": "Exists in: {path}",
        "reason_possible": "Reason: possible duplicate. It was not added for safety.",
        "possible_match": "Possible match: {path}",
        "error_file": "ERROR: {name}",
        "updating_final_index": "Updating library index...",
        "add_summary": "Process finished.\n\nMoved to library total: {total}\nMoved renamed by metadata: {renamed}\nNo reliable match, left unmoved: {original}\nNot added because already existing: {duplicates}\nNot added because possible duplicate: {possible}\nErrors: {errors}",
        "metadata_window_title": "Search book metadata",
        "metadata_question": "What do you want to analyze to search metadata and rename?",
        "files": "Files",
        "folder": "Folder",
        "cancel": "Cancel",
        "metadata_files_title": "Select the books you want to rename by metadata",
        "metadata_folder_title": "Select the folder with books to rename",
        "no_books_title": "No books",
        "no_books_msg": "No compatible books were found.",
        "metadata_header": "Search book metadata",
        "metadata_selected": "Books selected: {count}",
        "metadata_only_rename": "This function only renames. It does not move files.",
        "does_not_exist": "DOES NOT EXIST: {path}",
        "not_a_book": "This does not appear to be a book: {name}",
        "metadata_status": "Searching metadata {i}/{total}: {name}",
        "analyzing": "Analyzing: {name}",
        "unreliable_leave": "No reliable match found. Leaving it unchanged.",
        "best_confidence": "No changes. Confidence: {confidence}\n",
        "suggested_equal": "The suggested name is the same as the current one. Leaving it unchanged.\n",
        "renamed": "RENAMED:",
        "before": "  Before: {name}",
        "now": "  Now: {name}",
        "metadata_source_conf": "  Source: {source} | Confidence: {confidence}\n",
        "metadata_summary": "Metadata process finished.\n\nRenamed: {renamed}\nUnchanged: {unchanged}\nErrors: {errors}",
        "folder_duplicates_dialog_title": "Select the base folder",
        "folder_duplicates_dialog_title_secondary": "Select the folder to compare",
        "folder_duplicates_invalid_pair_title": "Invalid folders",
        "folder_duplicates_invalid_pair_msg": "Choose two different folders. One folder cannot be inside the other for this comparison.",
        "folder_duplicates_header": "Duplicate book checker between folders",
        "folder_duplicates_selected": "Base folder: {path_a}\nFolder to compare: {path_b}",
        "folder_duplicates_indexing": "Searching books in both folders...",
        "folder_duplicates_no_books_title": "No books",
        "folder_duplicates_no_books_msg": "No compatible books were found in one or both folders.",
        "folder_duplicates_analyzing": "Analyzing possible duplicates {i}/{total}: {name}",
        "folder_duplicates_fast_scan": "Fast scan {i}/{total}: {name}",
        "folder_duplicates_hashing": "Checking exact duplicates between folders by size and hash...",
        "folder_duplicates_fast_summary": "Fast scan finished: {books} books, {candidates} candidates for deep analysis.",
        "folder_duplicates_deep_analyzing": "Deep analysis of candidate {i}/{total}: {name}",
        "folder_duplicates_summary": "Folder comparison finished.\n\nBase folder: {path_a}\nCompared folder: {path_b}\nBooks in base: {books_a}\nBooks in compared folder: {books_b}\nBooks analyzed: {books}\nPossible duplicates between folders: {duplicates}\nErrors: {errors}",
        "folder_duplicates_no_doubles": "No duplicates were found between the two folders.",
        "eta_remaining": "Time remaining: {eta}",
        "eta_calculating": "calculating...",
        "eta_under_5s": "less than 5 s",
        "eta_s": "{s} s",
        "eta_ms": "{m} min {s} s",
        "eta_hms": "{h} h {m} min {s} s",
    },
    "fr": {
        "window_title": "Gère ta bibliothèque",
        "title": "Gère ta bibliothèque",
        "subtitle": "Organise, ajoute, vérifie les doublons et recherche les métadonnées de tes livres.",
        "language": "Langue :",
        "dark_mode": "Mode sombre",
        "light_mode": "Mode clair",
        "library_active": "Bibliothèque active",
        "library_help": "Tu peux écrire le chemin directement et appuyer sur Entrée, ou utiliser le bouton à trois points.",
        "route": "Chemin :",
        "index_choose": "Index : écris ou choisis une bibliothèque",
        "index_none": "Index : pas encore créé",
        "index_status": "Index : {count} livres | mis à jour : {date}",
        "actions": "Actions principales",
        "add_books": "Ajouter des livres",
        "metadata": "Rechercher métadonnées",
        "check_folder_duplicates": "Comparer deux dossiers",
        "open_library": "Ouvrir bibliothèque",
        "status_title": "État",
        "initializing": "Démarrage...",
        "log_title": "Journal d’activité",
        "first_state": "Écris ou choisis le chemin de la bibliothèque.",
        "valid_library": "Écris ou choisis une bibliothèque valide.",
        "empty_route_title": "Chemin vide",
        "empty_route_msg": "Écris ou choisis un chemin de bibliothèque.",
        "choose_library_title": "Sélectionne le dossier de ta bibliothèque",
        "create_folder_title": "Créer le dossier",
        "create_folder_msg": "Le chemin n’existe pas :\n\n{path}\n\nVeux-tu le créer comme bibliothèque ?",
        "invalid_route_title": "Chemin invalide",
        "invalid_route_msg": "Le chemin indiqué n’est pas un dossier.",
        "library_selected": "Bibliothèque sélectionnée :\n{path}\n",
        "updating_index": "Mise à jour de l’index de la bibliothèque...",
        "updating_index_path": "Mise à jour de l’index de la bibliothèque :\n{path}",
        "index_first_time": "Cela peut prendre du temps la première fois.\n",
        "index_ready": "\nIndex prêt. Livres indexés : {count}",
        "ready": "Prêt.",
        "missing_library_title": "Bibliothèque manquante",
        "missing_library_msg": "Écris ou choisis d’abord le chemin de la bibliothèque.",
        "add_dialog_title": "Sélectionne un ou plusieurs livres à ajouter",
        "filetype_books": "Livres",
        "filetype_all": "Tous les fichiers",
        "selected_books": "Livres sélectionnés : {count}",
        "verifying": "Vérification des doublons {i}/{total} : {name}",
        "new_book": "NOUVEAU LIVRE : {name}",
        "searching_web_name": "Analyse des métadonnées internes, du texte et de l’ISBN...",
        "metadata_searching": "Confirmation avec les bases de métadonnées...",
        "metadata_confirm_isbn": "Confirmation par ISBN...",
        "metadata_confirm_doi": "Confirmation par DOI...",
        "metadata_confirm_search": "Recherche d’une confirmation supplémentaire...",
        "metadata_recovery": "Vérification de variantes avec les éléments déjà collectés...",
        "pipeline_level0": "Niveau 0 : métadonnées internes et nom du fichier",
        "pipeline_cache": "Analyse réutilisée depuis le cache local",
        "pipeline_fast_path": "Résolution rapide avec métadonnées structurées suffisantes",
        "pipeline_fast_complete": "Analyse rapide terminée",
        "pipeline_ocr_required": "OCR différé requis",
        "pipeline_ocr_skipped": "OCR ignoré : confiance suffisante",
        "pipeline_review": "Fichier envoyé en révision",
        "pipeline_fast_batch_status": "Analyse rapide {done}/{total} : {name}",
        "pipeline_ocr_batch_status": "File OCR {done}/{total} : {name}",
        "pipeline_level1": "Niveau 1 : texte numérique utile trouvé",
        "pipeline_ocr_hint": "L’OCR a fourni des indices ; il ne sera utilisé que comme piste",
        "pipeline_deep_identity": "Deep Identity Scan : recoupement des preuves locales",
        "pipeline_external": "Vérification externe sélective",
        "suggested_name": "Nom suggéré : {name}",
        "source_conf": "Source : {source} | Fiabilité : {confidence}",
        "no_reliable": "Aucune correspondance fiable trouvée.",
        "move_original": "Il reste inchangé à son emplacement d’origine.",
        "moved_final": "DÉPLACÉ VERS LA BIBLIOTHÈQUE : {name}",
        "destination": "Destination : {path}",
        "not_added": "NON AJOUTÉ : {name}",
        "reason_exists": "Raison : tu as déjà ce livre.",
        "exists_in": "Existe dans : {path}",
        "reason_possible": "Raison : doublon possible. Il n’a pas été ajouté par sécurité.",
        "possible_match": "Correspondance possible : {path}",
        "error_file": "ERREUR : {name}",
        "updating_final_index": "Mise à jour de l’index de la bibliothèque...",
        "add_summary": "Processus terminé.\n\nDéplacés vers la bibliothèque : {total}\nDéplacés renommés par métadonnées : {renamed}\nSans correspondance fiable, non déplacés : {original}\nNon ajoutés car déjà existants : {duplicates}\nNon ajoutés pour doublon possible : {possible}\nErreurs : {errors}",
        "metadata_window_title": "Rechercher les métadonnées des livres",
        "metadata_question": "Que veux-tu analyser pour rechercher les métadonnées et renommer ?",
        "files": "Fichiers",
        "folder": "Dossier",
        "cancel": "Annuler",
        "metadata_files_title": "Sélectionne les livres à renommer par métadonnées",
        "metadata_folder_title": "Sélectionne le dossier contenant les livres à renommer",
        "no_books_title": "Aucun livre",
        "no_books_msg": "Aucun livre compatible trouvé.",
        "metadata_header": "Rechercher les métadonnées des livres",
        "metadata_selected": "Livres sélectionnés : {count}",
        "metadata_only_rename": "Cette fonction renomme seulement. Elle ne déplace aucun fichier.",
        "does_not_exist": "N’EXISTE PAS : {path}",
        "not_a_book": "Ce fichier ne semble pas être un livre : {name}",
        "metadata_status": "Recherche de métadonnées {i}/{total} : {name}",
        "analyzing": "Analyse : {name}",
        "unreliable_leave": "Aucune correspondance fiable. Le fichier reste inchangé.",
        "best_confidence": "Aucun changement. Fiabilité : {confidence}\n",
        "suggested_equal": "Le nom suggéré est identique au nom actuel. Aucun changement.\n",
        "renamed": "RENOMMÉ :",
        "before": "  Avant : {name}",
        "now": "  Maintenant : {name}",
        "metadata_source_conf": "  Source : {source} | Fiabilité : {confidence}\n",
        "metadata_summary": "Processus de métadonnées terminé.\n\nRenommés : {renamed}\nSans changement : {unchanged}\nErreurs : {errors}",
        "folder_duplicates_dialog_title": "Sélectionne le dossier de base",
        "folder_duplicates_dialog_title_secondary": "Sélectionne le dossier à comparer",
        "folder_duplicates_invalid_pair_title": "Dossiers non valides",
        "folder_duplicates_invalid_pair_msg": "Choisis deux dossiers différents. Un dossier ne peut pas être à l’intérieur de l’autre pour cette comparaison.",
        "folder_duplicates_header": "Vérificateur de livres en double entre dossiers",
        "folder_duplicates_selected": "Dossier de base : {path_a}\nDossier à comparer : {path_b}",
        "folder_duplicates_indexing": "Recherche de livres dans les deux dossiers...",
        "folder_duplicates_no_books_title": "Aucun livre",
        "folder_duplicates_no_books_msg": "Aucun livre compatible n’a été trouvé dans l’un des deux dossiers.",
        "folder_duplicates_analyzing": "Analyse des doublons possibles {i}/{total} : {name}",
        "folder_duplicates_fast_scan": "Analyse rapide {i}/{total} : {name}",
        "folder_duplicates_hashing": "Vérification des doublons exacts entre dossiers par taille et hash...",
        "folder_duplicates_fast_summary": "Analyse rapide terminée : {books} livres, {candidates} candidats pour l’analyse approfondie.",
        "folder_duplicates_deep_analyzing": "Analyse approfondie du candidat {i}/{total} : {name}",
        "folder_duplicates_summary": "Comparaison de dossiers terminée.\n\nDossier de base : {path_a}\nDossier comparé : {path_b}\nLivres dans la base : {books_a}\nLivres dans le dossier comparé : {books_b}\nLivres analysés : {books}\nDoublons possibles entre dossiers : {duplicates}\nErreurs : {errors}",
        "folder_duplicates_no_doubles": "Aucun doublon n’a été trouvé entre les deux dossiers.",
        "eta_remaining": "Temps restant : {eta}",
        "eta_calculating": "calcul...",
        "eta_under_5s": "moins de 5 s",
        "eta_s": "{s} s",
        "eta_ms": "{m} min {s} s",
        "eta_hms": "{h} h {m} min {s} s",
    },
    "zh": {
        "window_title": "管理你的图书馆",
        "title": "管理你的图书馆",
        "subtitle": "整理、添加、检查重复项，并为你的书籍搜索元数据。",
        "language": "语言：",
        "dark_mode": "深色模式",
        "light_mode": "浅色模式",
        "library_active": "当前图书馆",
        "library_help": "你可以直接输入路径并按 Enter，或使用三点按钮选择。",
        "route": "路径：",
        "index_choose": "索引：请输入或选择图书馆",
        "index_none": "索引：尚未创建",
        "index_status": "索引：{count} 本书 | 更新于：{date}",
        "actions": "主要操作",
        "add_books": "添加书籍",
        "metadata": "搜索元数据",
        "check_folder_duplicates": "比较两个文件夹",
        "open_library": "打开图书馆",
        "status_title": "状态",
        "initializing": "正在启动...",
        "log_title": "活动记录",
        "first_state": "请输入或选择图书馆路径。",
        "valid_library": "请输入或选择有效的图书馆。",
        "empty_route_title": "路径为空",
        "empty_route_msg": "请输入或选择图书馆路径。",
        "choose_library_title": "选择你的图书馆文件夹",
        "create_folder_title": "创建文件夹",
        "create_folder_msg": "路径不存在：\n\n{path}\n\n要创建为图书馆吗？",
        "invalid_route_title": "无效路径",
        "invalid_route_msg": "所选路径不是文件夹。",
        "library_selected": "已选择图书馆：\n{path}\n",
        "updating_index": "正在更新图书馆索引...",
        "updating_index_path": "正在更新图书馆索引：\n{path}",
        "index_first_time": "第一次可能需要一些时间。\n",
        "index_ready": "\n索引完成。已索引书籍：{count}",
        "ready": "就绪。",
        "missing_library_title": "缺少图书馆",
        "missing_library_msg": "请先输入或选择图书馆路径。",
        "add_dialog_title": "选择一个或多个要添加的书籍",
        "filetype_books": "书籍",
        "filetype_all": "所有文件",
        "selected_books": "已选择书籍：{count}",
        "verifying": "正在检查重复项 {i}/{total}：{name}",
        "new_book": "新书：{name}",
        "searching_web_name": "正在分析内部元数据、文本和 ISBN...",
        "metadata_searching": "正在通过元数据数据库确认...",
        "metadata_confirm_isbn": "正在通过 ISBN 确认...",
        "metadata_confirm_doi": "正在通过 DOI 确认...",
        "metadata_confirm_search": "正在查找额外确认...",
        "metadata_recovery": "正在使用已收集的信息检查其他变体...",
        "pipeline_level0": "第 0 层：内部元数据和文件名",
        "pipeline_cache": "已从本地缓存复用分析",
        "pipeline_fast_path": "结构化元数据充足，使用快速解析",
        "pipeline_fast_complete": "快速分析已完成",
        "pipeline_ocr_required": "需要延迟 OCR",
        "pipeline_ocr_skipped": "置信度充足，已跳过 OCR",
        "pipeline_review": "文件已发送以供复核",
        "pipeline_fast_batch_status": "快速分析 {done}/{total}：{name}",
        "pipeline_ocr_batch_status": "OCR 队列 {done}/{total}：{name}",
        "pipeline_level1": "第 1 层：找到有用的数字文本",
        "pipeline_ocr_hint": "OCR 提供了证据；仅作为线索使用",
        "pipeline_deep_identity": "Deep Identity Scan：交叉检查本地证据",
        "pipeline_external": "选择性外部验证",
        "suggested_name": "建议名称：{name}",
        "source_conf": "来源：{source} | 可信度：{confidence}",
        "no_reliable": "没有找到可靠匹配。",
        "move_original": "将保持原位置不变。",
        "moved_final": "已移动到图书馆：{name}",
        "destination": "目标：{path}",
        "not_added": "未添加：{name}",
        "reason_exists": "原因：你已经有这本书。",
        "exists_in": "已存在于：{path}",
        "reason_possible": "原因：可能重复。为安全起见未添加。",
        "possible_match": "可能匹配：{path}",
        "error_file": "错误：{name}",
        "updating_final_index": "正在更新图书馆索引...",
        "add_summary": "处理完成。\n\n移动到图书馆总数：{total}\n通过元数据重命名后移动：{renamed}\n无可靠匹配且未移动：{original}\n因已存在而未添加：{duplicates}\n因可能重复而未添加：{possible}\n错误：{errors}",
        "metadata_window_title": "搜索书籍元数据",
        "metadata_question": "你想分析什么来搜索元数据并重命名？",
        "files": "文件",
        "folder": "文件夹",
        "cancel": "取消",
        "metadata_files_title": "选择要按元数据重命名的书籍",
        "metadata_folder_title": "选择包含要重命名书籍的文件夹",
        "no_books_title": "没有书籍",
        "no_books_msg": "未找到兼容的书籍。",
        "metadata_header": "搜索书籍元数据",
        "metadata_selected": "已选择书籍：{count}",
        "metadata_only_rename": "此功能只会重命名，不会移动文件。",
        "does_not_exist": "不存在：{path}",
        "not_a_book": "这似乎不是一本书：{name}",
        "metadata_status": "正在搜索元数据 {i}/{total}：{name}",
        "analyzing": "正在分析：{name}",
        "unreliable_leave": "没有可靠匹配。保持原样。",
        "best_confidence": "未更改。可信度：{confidence}\n",
        "suggested_equal": "建议名称与当前名称相同。保持不变。\n",
        "renamed": "已重命名：",
        "before": "  之前：{name}",
        "now": "  现在：{name}",
        "metadata_source_conf": "  来源：{source} | 可信度：{confidence}\n",
        "metadata_summary": "元数据处理完成。\n\n已重命名：{renamed}\n未更改：{unchanged}\n错误：{errors}",
        "folder_duplicates_dialog_title": "选择基础文件夹",
        "folder_duplicates_dialog_title_secondary": "选择要比较的文件夹",
        "folder_duplicates_invalid_pair_title": "文件夹无效",
        "folder_duplicates_invalid_pair_msg": "请选择两个不同的文件夹。一个文件夹不能位于另一个文件夹内部。",
        "folder_duplicates_header": "两个文件夹之间的重复书籍检查器",
        "folder_duplicates_selected": "基础文件夹：{path_a}\n比较文件夹：{path_b}",
        "folder_duplicates_indexing": "正在两个文件夹中查找书籍...",
        "folder_duplicates_no_books_title": "没有书籍",
        "folder_duplicates_no_books_msg": "一个或两个文件夹中未找到兼容的书籍。",
        "folder_duplicates_analyzing": "正在分析可能的重复项 {i}/{total}：{name}",
        "folder_duplicates_fast_scan": "快速扫描 {i}/{total}：{name}",
        "folder_duplicates_hashing": "正在按大小和哈希检查两个文件夹之间的完全重复项...",
        "folder_duplicates_fast_summary": "快速扫描完成：{books} 本书，{candidates} 个候选项需要深度分析。",
        "folder_duplicates_deep_analyzing": "正在深度分析候选项 {i}/{total}：{name}",
        "folder_duplicates_summary": "文件夹比较完成。\n\n基础文件夹：{path_a}\n比较文件夹：{path_b}\n基础文件夹书籍数：{books_a}\n比较文件夹书籍数：{books_b}\n已分析书籍：{books}\n两个文件夹之间发现可能重复：{duplicates}\n错误：{errors}",
        "folder_duplicates_no_doubles": "两个文件夹之间未发现重复项。",
        "eta_remaining": "剩余时间：{eta}",
        "eta_calculating": "正在计算...",
        "eta_under_5s": "少于 5 秒",
        "eta_s": "{s} 秒",
        "eta_ms": "{m} 分 {s} 秒",
        "eta_hms": "{h} 小时 {m} 分 {s} 秒",
    },
}


def _normalizar_idioma_sistema(valor):
    valor = str(valor or "").strip().lower()
    if not valor:
        return ""

    # Common formats: en_US, es-ES, fr_FR.UTF-8, zh_CN, fr:en.
    valor = valor.split(":", 1)[0].split(".", 1)[0].replace("-", "_")
    codigo = valor.split("_", 1)[0]

    nombres_windows = {
        "english": "en",
        "spanish": "es",
        "french": "fr",
        "chinese": "zh",
    }
    codigo = nombres_windows.get(codigo, codigo)

    if codigo in LANGUAGE_NAMES:
        return codigo

    return ""


def _idioma_sistema():
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(variable, "")
        idioma = _normalizar_idioma_sistema(valor)
        if idioma:
            return idioma
        if valor:
            return "en"

    try:
        idioma = _normalizar_idioma_sistema(locale.getlocale()[0])
        if idioma:
            return idioma
    except Exception:
        pass

    return "en"


def _idioma_inicial():
    try:
        if CONFIG_JSON.exists():
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            idioma = str(data.get("language") or data.get("idioma") or "").strip().lower()
            if idioma in LANGUAGE_NAMES:
                return idioma
    except Exception:
        pass
    return _idioma_sistema()


IDIOMA_ACTUAL = _idioma_inicial()


def tr(clave, **kwargs):
    texto = TEXTS.get(IDIOMA_ACTUAL, TEXTS["en"]).get(clave, TEXTS["en"].get(clave, clave))
    try:
        return texto.format(**kwargs)
    except Exception:
        return texto


EXTRA_TEXTS_UNDO = {
    "es": {
        "undo_last_action": "Deshacer última acción",
        "undo_none_title": "Sin acción para deshacer",
        "undo_none_msg": "No hay operaciones recientes para deshacer.",
        "undo_confirm_title": "Deshacer última acción",
        "undo_confirm_msg": "Se intentará deshacer la última acción:\n\n{batch}\n\nOperaciones: {count}\n\n¿Continuar?",
        "undo_done_title": "Deshacer terminado",
        "undo_done_msg": "Operaciones revertidas: {done}\nErrores: {errors}",
        "undo_log_line": "Deshacer última acción terminado. Revertidas: {done} | Errores: {errors}",
    },
    "en": {
        "undo_last_action": "Undo last action",
        "undo_none_title": "No action to undo",
        "undo_none_msg": "There are no recent operations to undo.",
        "undo_confirm_title": "Undo last action",
        "undo_confirm_msg": "The last action will be undone:\n\n{batch}\n\nOperations: {count}\n\nContinue?",
        "undo_done_title": "Undo finished",
        "undo_done_msg": "Operations reverted: {done}\nErrors: {errors}",
        "undo_log_line": "Undo last action finished. Reverted: {done} | Errors: {errors}",
    },
    "fr": {
        "undo_last_action": "Annuler la dernière action",
        "undo_none_title": "Aucune action à annuler",
        "undo_none_msg": "Aucune opération récente à annuler.",
        "undo_confirm_title": "Annuler la dernière action",
        "undo_confirm_msg": "La dernière action sera annulée :\n\n{batch}\n\nOpérations : {count}\n\nContinuer ?",
        "undo_done_title": "Annulation terminée",
        "undo_done_msg": "Opérations annulées : {done}\nErreurs : {errors}",
        "undo_log_line": "Annulation terminée. Opérations annulées : {done} | Erreurs : {errors}",
    },
    "zh": {
        "undo_last_action": "撤销上一个操作",
        "undo_none_title": "没有可撤销的操作",
        "undo_none_msg": "没有最近的操作可撤销。",
        "undo_confirm_title": "撤销上一个操作",
        "undo_confirm_msg": "将撤销上一个操作：\n\n{batch}\n\n操作数：{count}\n\n继续吗？",
        "undo_done_title": "撤销完成",
        "undo_done_msg": "已撤销操作：{done}\n错误：{errors}",
        "undo_log_line": "撤销上一个操作完成。已撤销：{done} | 错误：{errors}",
    },
}


EXTRA_TEXTS_UNDO["es"].update({
    "result_title": "Resultado",
    "error_title": "Error",
    "updating_after_rename": "Actualizando índice después del renombrado...",
    "file_transactions_recovered_log": "Se detectaron {count} operación(es) de archivo incompletas en el journal. No se borró nada; revisa el historial si falta algo.",
})
EXTRA_TEXTS_UNDO["en"].update({
    "result_title": "Result",
    "error_title": "Error",
    "updating_after_rename": "Updating index after renaming...",
    "file_transactions_recovered_log": "{count} incomplete file operation(s) were found in the journal. Nothing was deleted; review the history if something is missing.",
})
EXTRA_TEXTS_UNDO["fr"].update({
    "result_title": "Résultat",
    "error_title": "Erreur",
    "updating_after_rename": "Mise à jour de l’index après renommage...",
    "file_transactions_recovered_log": "{count} opération(s) de fichier incomplète(s) ont été détectées dans le journal. Rien n’a été supprimé ; vérifiez l’historique si un fichier manque.",
})
EXTRA_TEXTS_UNDO["zh"].update({
    "result_title": "结果",
    "error_title": "错误",
    "updating_after_rename": "重命名后正在更新索引...",
    "file_transactions_recovered_log": "在日志中发现 {count} 个未完成的文件操作。未删除任何内容；如果缺少文件，请检查历史记录。",
})

EXTRA_TEXTS_REVIEW = {
    "es": {
        "possible_name_match_deferred": "Posible coincidencia por nombre. Se revisará después de encontrar el título real.",
        "stays_in_review": "Permanece en PARA REVISAR NUEVAMENTE: {name}",
        "moved_to_review": "Movido a PARA REVISAR NUEVAMENTE: {name}",
        "same_title_exists": "Mismo título detectado: ya existe en la biblioteca.",
        "deleted_from_review_existing": "Movido a cuarentena desde PARA REVISAR NUEVAMENTE: {name}",
        "same_title_previous_to_review": "Mismo título detectado: se movió la versión anterior a revisión: {name}",
        "same_title_keep_library": "Mismo título detectado: se conserva la versión de biblioteca.",
        "same_title_previous_deleted": "Mismo título detectado: se movió a cuarentena la versión anterior de la biblioteca: {name}",
        "same_title_input_deleted": "Mismo título detectado: se movió a cuarentena el archivo entrante porque la biblioteca ya conserva la versión preferida: {name}",
        "same_title_move_error": "No se pudo mover la versión anterior a revisión: {error}",
        "same_title_previous_detail": "Reemplazado por versión más reciente/formato preferido: {path}",
        "same_title_library_preferred_detail": "La biblioteca ya tiene una versión más reciente o formato preferido: {path}",
        "duplicate_exact_replaced_detail": "Se conservó la versión más reciente. Anterior: {path}",
        "duplicate_exact_deleted_detail": "Ya existe una versión igual o más reciente: {path}",
        "duplicate_exact_replaced_log": "Duplicado exacto: se conservó la versión más reciente y se reemplazó la anterior.",
        "duplicate_exact_deleted_log": "Duplicado exacto: la biblioteca ya tenía la versión más reciente; el archivo de entrada se movió a cuarentena.",
        "exact_duplicates_deleted": "Duplicados exactos movidos a cuarentena desde la carpeta de entrada: {count}",
        "exact_duplicates_replaced": "Duplicados exactos reemplazados por versión más reciente: {count}",
        "same_title_duplicates_deleted": "Duplicados por título movidos a cuarentena: {count}",
        "review_deleted_existing_count": "Movidos a cuarentena desde PARA REVISAR NUEVAMENTE porque ya estaban en biblioteca: {count}",
        "review_doubles_error": "No se pudo revisar dobles: {error}",
        "review_window_title": "Revisión rápida de biblioteca",
        "review_clean_title": "Biblioteca limpia",
        "review_clean_message": "Tu biblioteca esta al dia y limpia",
        "review_clean_detail": "No quedan comparaciones pendientes en esta revisión.",
        "field_format": "Formato",
        "field_size": "Tamaño",
        "field_modified": "Modificado",
        "field_hash": "Hash",
        "field_path": "Ruta",
        "newer_tag": "más reciente",
        "date_unavailable": "Fecha no disponible",
        "not_available": "No disponible",
        "keep_card_hint": "Haz clic en este recuadro para conservarlo",
        "auto_keep_newest": "Conservar más recientes automáticamente",
        "auto_keep_newest_title": "Conservar automáticamente",
        "auto_keep_newest_question": "Se conservará automáticamente la versión recomendada en {count} comparaciones pendientes.\n\n¿Qué quieres hacer con los archivos NO seleccionados?\n\nSí = mover a cuarentena\nNo = mover a PARA REVISAR NUEVAMENTE\nCancelar = no hacer nada",
        "auto_keep_newest_done": "Selección automática terminada. Conservados: {kept} | En cuarentena: {discarded} | Movidos a revisión: {moved} | Saltados: {skipped} | Errores: {errors}",
        "close": "Cerrar",
        "next": "Siguiente",
        "file_not_found_title": "Archivo no encontrado",
        "discard_missing_msg": "El archivo no seleccionado ya no existe:\n{path}",
        "duplicate_file_title": "Archivo duplicado",
        "duplicate_file_question": "Se conservará este archivo:\n\n{kept}\n\nEl archivo NO seleccionado parece ser el mismo libro.\n¿Quieres mover a cuarentena el archivo NO seleccionado?\n\nSí = mover a cuarentena\nNo = mover a PARA REVISAR NUEVAMENTE",
        "kept_log": "Conservado: {path}",
        "discard_deleted_log": "Archivo no seleccionado movido a cuarentena: {path}",
        "discard_moved_review_log": "Movido a PARA REVISAR NUEVAMENTE: {path}",
        "recommend_keep_a": "Recomendado: conservar Archivo A. Criterio: fecha más reciente; si empata, preferir EPUB y luego MOBI.",
        "recommend_keep_b": "Recomendado: conservar Archivo B. Criterio: fecha más reciente; si empata, preferir EPUB y luego MOBI.",
        "file_a_newer": "Archivo A parece ser la versión más reciente",
        "file_b_newer": "Archivo B parece ser la versión más reciente",
        "same_date_unknown": "Ambos archivos tienen la misma fecha o no se pudo determinar",
        "file_label_a": "Archivo A",
        "file_label_b": "Archivo B",
        "skip_now": "Saltar por ahora",
        "operation_summary_title": "Resumen de operación",
        "review_summary_subtitle": "La revisión rápida compara títulos reales ya resueltos. Si hay varios formatos del mismo título, se recomienda conservar la versión más reciente; si empata, EPUB y luego MOBI.",
        "operation_finished": "Operación terminada.",
        "review_pair_detail": "Tipo: {type}  |  Confianza: {confidence}  |  {reason}",
        "comparison_title": "Comparación {index} de {total}",
        "review_compare_subtitle": "Haz clic en el recuadro del archivo que quieres conservar. Después decides si el otro se mueve a revisión o a cuarentena.",
        "review_found_count": "Posibles dobles encontrados: {count}",
        "review_start_detail": "Pulsa Siguiente para revisar cada comparación una por una.",
        "review_no_doubles": "No se encontraron dobles en esta revisión.",
        "updating_index_item": "Actualizando índice {i}/{total}: {name}",
        "index_read_error": "Error leyendo {path}: {error}",
        "file_missing_msg": "No existe el archivo:\n{path}",
        "incompatible_book_msg": "No parece ser un libro compatible:\n{path}",
        "duplicate_exact_msg": "Ya tienes este libro. No se puede agregar:\n{name}",
        "possible_duplicate_msg": "Posible duplicado. Por seguridad no se agregará:\n{name}",
        "unique_book_msg": "Libro nuevo. Se puede agregar:\n{name}",
        "no_library_selected": "No hay biblioteca seleccionada.",
    },
    "en": {
        "possible_name_match_deferred": "Possible filename match. It will be checked after finding the real title.",
        "stays_in_review": "Remains in PARA REVISAR NUEVAMENTE: {name}",
        "moved_to_review": "Moved to PARA REVISAR NUEVAMENTE: {name}",
        "same_title_exists": "Same title detected: it already exists in the library.",
        "deleted_from_review_existing": "Moved to quarantine from PARA REVISAR NUEVAMENTE: {name}",
        "same_title_previous_to_review": "Same title detected: the previous version was moved to review: {name}",
        "same_title_keep_library": "Same title detected: keeping the library version.",
        "same_title_previous_deleted": "Same title detected: the previous library version was moved to quarantine: {name}",
        "same_title_input_deleted": "Same title detected: the incoming file was moved to quarantine because the library already keeps the preferred version: {name}",
        "same_title_move_error": "Could not move the previous version to review: {error}",
        "same_title_previous_detail": "Replaced by newer/preferred-format version: {path}",
        "same_title_library_preferred_detail": "The library already has a newer or preferred-format version: {path}",
        "duplicate_exact_replaced_detail": "The newest version was kept. Previous: {path}",
        "duplicate_exact_deleted_detail": "An equal or newer version already exists: {path}",
        "duplicate_exact_replaced_log": "Exact duplicate: the newest version was kept and the previous one was replaced.",
        "duplicate_exact_deleted_log": "Exact duplicate: the library already had the newest version; the input file was moved to quarantine.",
        "exact_duplicates_deleted": "Exact duplicates moved to quarantine from the input folder: {count}",
        "exact_duplicates_replaced": "Exact duplicates replaced by a newer version: {count}",
        "same_title_duplicates_deleted": "Title duplicates moved to quarantine: {count}",
        "review_deleted_existing_count": "Moved to quarantine from PARA REVISAR NUEVAMENTE because they already existed in the library: {count}",
        "review_doubles_error": "Could not review duplicates: {error}",
        "review_window_title": "Quick library review",
        "review_clean_title": "Library clean",
        "review_clean_message": "Your library is up to date and clean",
        "review_clean_detail": "There are no pending comparisons in this review.",
        "field_format": "Format",
        "field_size": "Size",
        "field_modified": "Modified",
        "field_hash": "Hash",
        "field_path": "Path",
        "newer_tag": "newest",
        "date_unavailable": "Date unavailable",
        "not_available": "Not available",
        "keep_card_hint": "Click this card to keep it",
        "auto_keep_newest": "Keep newest automatically",
        "auto_keep_newest_title": "Keep automatically",
        "auto_keep_newest_question": "The recommended version will be kept automatically in {count} pending comparisons.\n\nWhat do you want to do with the UNSELECTED files?\n\nYes = move to quarantine\nNo = move to PARA REVISAR NUEVAMENTE\nCancel = do nothing",
        "auto_keep_newest_done": "Automatic selection finished. Kept: {kept} | Quarantined: {discarded} | Moved to review: {moved} | Skipped: {skipped} | Errors: {errors}",
        "close": "Close",
        "next": "Next",
        "file_not_found_title": "File not found",
        "discard_missing_msg": "The unselected file no longer exists:\n{path}",
        "duplicate_file_title": "Duplicate file",
        "duplicate_file_question": "This file will be kept:\n\n{kept}\n\nThe unselected file appears to be the same book.\nDo you want to move the unselected file to quarantine?\n\nYes = move to quarantine\nNo = move to PARA REVISAR NUEVAMENTE",
        "kept_log": "Kept: {path}",
        "discard_deleted_log": "Unselected file moved to quarantine: {path}",
        "discard_moved_review_log": "Moved to PARA REVISAR NUEVAMENTE: {path}",
        "recommend_keep_a": "Recommended: keep File A. Criterion: newest modified date; if tied, prefer EPUB then MOBI.",
        "recommend_keep_b": "Recommended: keep File B. Criterion: newest modified date; if tied, prefer EPUB then MOBI.",
        "file_a_newer": "File A appears to be the newer version",
        "file_b_newer": "File B appears to be the newer version",
        "same_date_unknown": "Both files have the same date, or the date could not be determined",
        "file_label_a": "File A",
        "file_label_b": "File B",
        "skip_now": "Skip for now",
        "operation_summary_title": "Operation summary",
        "review_summary_subtitle": "The quick review compares already resolved real titles. If there are several formats of the same title, it recommends keeping the newest version; if tied, EPUB then MOBI.",
        "operation_finished": "Operation finished.",
        "review_pair_detail": "Type: {type}  |  Confidence: {confidence}  |  {reason}",
        "comparison_title": "Comparison {index} of {total}",
        "review_compare_subtitle": "Click the card for the file you want to keep. Then decide whether the other one is moved to review or quarantine.",
        "review_found_count": "Possible duplicates found: {count}",
        "review_start_detail": "Press Next to review each comparison one by one.",
        "review_no_doubles": "No duplicates were found in this review.",
        "updating_index_item": "Updating index {i}/{total}: {name}",
        "index_read_error": "Error reading {path}: {error}",
        "file_missing_msg": "The file does not exist:\n{path}",
        "incompatible_book_msg": "This does not appear to be a compatible book:\n{path}",
        "duplicate_exact_msg": "You already have this book. It cannot be added:\n{name}",
        "possible_duplicate_msg": "Possible duplicate. It was not added for safety:\n{name}",
        "unique_book_msg": "New book. It can be added:\n{name}",
        "no_library_selected": "No library selected.",
    },
    "fr": {
        "possible_name_match_deferred": "Correspondance possible par nom. Elle sera vérifiée après identification du titre réel.",
        "stays_in_review": "Reste dans PARA REVISAR NUEVAMENTE : {name}",
        "moved_to_review": "Déplacé vers PARA REVISAR NUEVAMENTE : {name}",
        "same_title_exists": "Même titre détecté : il existe déjà dans la bibliothèque.",
        "deleted_from_review_existing": "Déplacé en quarantaine depuis PARA REVISAR NUEVAMENTE : {name}",
        "same_title_previous_to_review": "Même titre détecté : l’ancienne version a été déplacée en révision : {name}",
        "same_title_keep_library": "Même titre détecté : la version de la bibliothèque est conservée.",
        "same_title_previous_deleted": "Même titre détecté : l’ancienne version de la bibliothèque a été déplacée en quarantaine : {name}",
        "same_title_input_deleted": "Même titre détecté : le fichier entrant a été déplacé en quarantaine car la bibliothèque conserve déjà la version préférée : {name}",
        "same_title_move_error": "Impossible de déplacer l’ancienne version en révision : {error}",
        "same_title_previous_detail": "Remplacé par une version plus récente ou au format préféré : {path}",
        "same_title_library_preferred_detail": "La bibliothèque possède déjà une version plus récente ou au format préféré : {path}",
        "duplicate_exact_replaced_detail": "La version la plus récente a été conservée. Ancienne version : {path}",
        "duplicate_exact_deleted_detail": "Une version identique ou plus récente existe déjà : {path}",
        "duplicate_exact_replaced_log": "Doublon exact : la version la plus récente a été conservée et l’ancienne remplacée.",
        "duplicate_exact_deleted_log": "Doublon exact : la bibliothèque possédait déjà la version la plus récente ; le fichier d’entrée a été déplacé en quarantaine.",
        "exact_duplicates_deleted": "Doublons exacts déplacés en quarantaine depuis le dossier d’entrée : {count}",
        "exact_duplicates_replaced": "Doublons exacts remplacés par une version plus récente : {count}",
        "same_title_duplicates_deleted": "Doublons par titre déplacés en quarantaine : {count}",
        "review_deleted_existing_count": "Déplacés en quarantaine depuis PARA REVISAR NUEVAMENTE car déjà présents dans la bibliothèque : {count}",
        "review_doubles_error": "Impossible de vérifier les doublons : {error}",
        "review_window_title": "Révision rapide de la bibliothèque",
        "review_clean_title": "Bibliothèque propre",
        "review_clean_message": "Ta bibliothèque est à jour et propre",
        "review_clean_detail": "Il ne reste aucune comparaison en attente dans cette révision.",
        "field_format": "Format",
        "field_size": "Taille",
        "field_modified": "Modifié",
        "field_hash": "Hash",
        "field_path": "Chemin",
        "newer_tag": "plus récent",
        "date_unavailable": "Date non disponible",
        "not_available": "Non disponible",
        "keep_card_hint": "Clique sur cette carte pour la conserver",
        "auto_keep_newest": "Conserver automatiquement les plus récents",
        "auto_keep_newest_title": "Conserver automatiquement",
        "auto_keep_newest_question": "La version recommandée sera conservée automatiquement dans {count} comparaisons restantes.\n\nQue veux-tu faire des fichiers NON sélectionnés ?\n\nOui = déplacer en quarantaine\nNon = déplacer vers PARA REVISAR NUEVAMENTE\nAnnuler = ne rien faire",
        "auto_keep_newest_done": "Sélection automatique terminée. Conservés : {kept} | En quarantaine : {discarded} | Déplacés en révision : {moved} | Ignorés : {skipped} | Erreurs : {errors}",
        "close": "Fermer",
        "next": "Suivant",
        "file_not_found_title": "Fichier introuvable",
        "discard_missing_msg": "Le fichier non sélectionné n’existe plus :\n{path}",
        "duplicate_file_title": "Fichier en double",
        "duplicate_file_question": "Ce fichier sera conservé :\n\n{kept}\n\nLe fichier NON sélectionné semble être le même livre.\nVeux-tu déplacer le fichier non sélectionné en quarantaine ?\n\nOui = déplacer en quarantaine\nNon = déplacer vers PARA REVISAR NUEVAMENTE",
        "kept_log": "Conservé : {path}",
        "discard_deleted_log": "Fichier non sélectionné déplacé en quarantaine : {path}",
        "discard_moved_review_log": "Déplacé vers PARA REVISAR NUEVAMENTE : {path}",
        "recommend_keep_a": "Recommandé : conserver le fichier A. Critère : date de modification la plus récente ; en cas d’égalité, préférer EPUB puis MOBI.",
        "recommend_keep_b": "Recommandé : conserver le fichier B. Critère : date de modification la plus récente ; en cas d’égalité, préférer EPUB puis MOBI.",
        "file_a_newer": "Le fichier A semble être la version la plus récente",
        "file_b_newer": "Le fichier B semble être la version la plus récente",
        "same_date_unknown": "Les deux fichiers ont la même date, ou la date n’a pas pu être déterminée",
        "file_label_a": "Fichier A",
        "file_label_b": "Fichier B",
        "skip_now": "Passer pour l’instant",
        "operation_summary_title": "Résumé de l’opération",
        "review_summary_subtitle": "La révision rapide compare les titres réels déjà résolus. S’il existe plusieurs formats du même titre, elle recommande de conserver la version la plus récente ; en cas d’égalité, EPUB puis MOBI.",
        "operation_finished": "Opération terminée.",
        "review_pair_detail": "Type : {type}  |  Fiabilité : {confidence}  |  {reason}",
        "comparison_title": "Comparaison {index} sur {total}",
        "review_compare_subtitle": "Clique sur la carte du fichier à conserver. Ensuite, décide si l’autre est déplacé en révision ou en quarantaine.",
        "review_found_count": "Doublons possibles trouvés : {count}",
        "review_start_detail": "Appuie sur Suivant pour vérifier chaque comparaison une par une.",
        "review_no_doubles": "Aucun doublon trouvé dans cette révision.",
        "updating_index_item": "Mise à jour de l’index {i}/{total} : {name}",
        "index_read_error": "Erreur lors de la lecture de {path} : {error}",
        "file_missing_msg": "Le fichier n’existe pas :\n{path}",
        "incompatible_book_msg": "Ce fichier ne semble pas être un livre compatible :\n{path}",
        "duplicate_exact_msg": "Tu as déjà ce livre. Il ne peut pas être ajouté :\n{name}",
        "possible_duplicate_msg": "Doublon possible. Il n’a pas été ajouté par sécurité :\n{name}",
        "unique_book_msg": "Nouveau livre. Il peut être ajouté :\n{name}",
        "no_library_selected": "Aucune bibliothèque sélectionnée.",
    },
    "zh": {
        "possible_name_match_deferred": "文件名可能匹配。找到真实标题后会再次检查。",
        "stays_in_review": "保留在 PARA REVISAR NUEVAMENTE：{name}",
        "moved_to_review": "已移动到 PARA REVISAR NUEVAMENTE：{name}",
        "same_title_exists": "检测到相同标题：图书馆中已存在。",
        "deleted_from_review_existing": "已从 PARA REVISAR NUEVAMENTE 移至隔离区：{name}",
        "same_title_previous_to_review": "检测到相同标题：旧版本已移至复查：{name}",
        "same_title_keep_library": "检测到相同标题：保留图书馆中的版本。",
        "same_title_previous_deleted": "检测到相同标题：已将图书馆中的旧版本移至隔离区：{name}",
        "same_title_input_deleted": "检测到相同标题：图书馆已保留首选版本，已将新输入文件移至隔离区：{name}",
        "same_title_move_error": "无法将旧版本移至复查：{error}",
        "same_title_previous_detail": "已由较新或首选格式版本替换：{path}",
        "same_title_library_preferred_detail": "图书馆中已有较新或首选格式版本：{path}",
        "duplicate_exact_replaced_detail": "已保留较新版本。旧版本：{path}",
        "duplicate_exact_deleted_detail": "已存在相同或较新的版本：{path}",
        "duplicate_exact_replaced_log": "完全重复：已保留较新版本并替换旧版本。",
        "duplicate_exact_deleted_log": "完全重复：图书馆中已有较新版本，输入文件已移至隔离区。",
        "exact_duplicates_deleted": "已从输入文件夹将完全重复项移至隔离区：{count}",
        "exact_duplicates_replaced": "完全重复项已替换为较新版本：{count}",
        "same_title_duplicates_deleted": "已将同标题重复项移至隔离区：{count}",
        "review_deleted_existing_count": "已从 PARA REVISAR NUEVAMENTE 移至隔离区，因为图书馆中已存在：{count}",
        "review_doubles_error": "无法检查重复项：{error}",
        "review_window_title": "图书馆快速检查",
        "review_clean_title": "图书馆已清理",
        "review_clean_message": "你的图书馆已更新并清理完成",
        "review_clean_detail": "本次检查没有待处理的比较。",
        "field_format": "格式",
        "field_size": "大小",
        "field_modified": "修改时间",
        "field_hash": "哈希",
        "field_path": "路径",
        "newer_tag": "最新",
        "date_unavailable": "日期不可用",
        "not_available": "不可用",
        "keep_card_hint": "点击此卡片以保留",
        "auto_keep_newest": "自动保留最新版本",
        "auto_keep_newest_title": "自动保留",
        "auto_keep_newest_question": "将自动保留 {count} 个待比较项中的推荐版本。\n\n未选中的文件要如何处理？\n\n是 = 移至隔离区\n否 = 移动到 PARA REVISAR NUEVAMENTE\n取消 = 不执行",
        "auto_keep_newest_done": "自动选择完成。已保留：{kept} | 已隔离：{discarded} | 已移至复查：{moved} | 已跳过：{skipped} | 错误：{errors}",
        "close": "关闭",
        "next": "下一步",
        "file_not_found_title": "找不到文件",
        "discard_missing_msg": "未选择的文件已不存在：\n{path}",
        "duplicate_file_title": "重复文件",
        "duplicate_file_question": "将保留此文件：\n\n{kept}\n\n未选择的文件似乎是同一本书。\n要将未选择的文件移至隔离区吗？\n\n是 = 移至隔离区\n否 = 移动到 PARA REVISAR NUEVAMENTE",
        "kept_log": "已保留：{path}",
        "discard_deleted_log": "未选择的文件已移至隔离区：{path}",
        "discard_moved_review_log": "已移动到 PARA REVISAR NUEVAMENTE：{path}",
        "recommend_keep_a": "建议：保留文件 A。标准：修改日期较新；若相同，优先 EPUB，然后 MOBI。",
        "recommend_keep_b": "建议：保留文件 B。标准：修改日期较新；若相同，优先 EPUB，然后 MOBI。",
        "file_a_newer": "文件 A 似乎是较新版本",
        "file_b_newer": "文件 B 似乎是较新版本",
        "same_date_unknown": "两个文件日期相同，或无法确定日期",
        "file_label_a": "文件 A",
        "file_label_b": "文件 B",
        "skip_now": "暂时跳过",
        "operation_summary_title": "操作摘要",
        "review_summary_subtitle": "快速检查会比较已经解析出的真实标题。如果同一标题有多种格式，建议保留修改日期最新的版本；若相同，则优先 EPUB，然后 MOBI。",
        "operation_finished": "操作完成。",
        "review_pair_detail": "类型：{type}  |  可信度：{confidence}  |  {reason}",
        "comparison_title": "比较 {index}/{total}",
        "review_compare_subtitle": "点击要保留文件的卡片。然后决定另一个文件移至复查还是隔离区。",
        "review_found_count": "发现可能重复项：{count}",
        "review_start_detail": "点击下一步逐一检查每组比较。",
        "review_no_doubles": "本次检查未发现重复项。",
        "updating_index_item": "正在更新索引 {i}/{total}：{name}",
        "index_read_error": "读取 {path} 时出错：{error}",
        "file_missing_msg": "文件不存在：\n{path}",
        "incompatible_book_msg": "这似乎不是兼容的书籍：\n{path}",
        "duplicate_exact_msg": "你已经有这本书，无法添加：\n{name}",
        "possible_duplicate_msg": "可能重复。为安全起见未添加：\n{name}",
        "unique_book_msg": "新书，可以添加：\n{name}",
        "no_library_selected": "未选择图书馆。",
    },
}

EXTRA_TEXTS_AI = {
    "es": {
        "ai_reinforce": "Reforzar con IA",
        "ai_window_title": "Reforzar con IA local",
        "ai_intro": "La IA local ayuda a resolver casos dudosos al identificar títulos, autores, duplicados y ediciones problemáticas. Funciona en tu ordenador, no necesita cuenta ni API key, y no envía tus libros a internet.",
        "ai_enable": "Activar IA local",
        "ai_model": "Modelo:",
        "ai_test": "Probar IA local",
        "ai_status": "Ver estado",
        "ai_open_folder": "Abrir carpeta de IA",
        "ai_save": "Guardar",
        "ai_saved": "Configuración de IA guardada.",
        "ai_state": "Estado IA: {state}",
        "ai_folder_missing": "La carpeta de IA todavía no existe.",
        "ai_runtime_missing": "Runtime de IA no encontrado",
        "ai_model_missing": "Modelo no instalado",
    },
    "en": {
        "ai_reinforce": "Reinforce with AI",
        "ai_window_title": "Reinforce with local AI",
        "ai_intro": "Local AI helps resolve uncertain cases by identifying titles, authors, duplicates, and problematic editions. It runs on your computer, needs no account or API key, and does not send your books to the internet.",
        "ai_enable": "Enable local AI",
        "ai_model": "Model:",
        "ai_test": "Test local AI",
        "ai_status": "View status",
        "ai_open_folder": "Open AI folder",
        "ai_save": "Save",
        "ai_saved": "AI configuration saved.",
        "ai_state": "AI status: {state}",
        "ai_folder_missing": "The AI folder does not exist yet.",
        "ai_runtime_missing": "AI runtime not found",
        "ai_model_missing": "Model not installed",
    },
    "fr": {
        "ai_reinforce": "Renforcer par IA",
        "ai_window_title": "Renforcer avec IA locale",
        "ai_intro": "L’IA locale aide à résoudre les cas incertains en identifiant titres, auteurs, doublons et éditions problématiques. Elle fonctionne sur ton ordinateur, sans compte ni clé API, et n’envoie pas tes livres sur internet.",
        "ai_enable": "Activer l’IA locale",
        "ai_model": "Modèle :",
        "ai_test": "Tester l’IA locale",
        "ai_status": "Voir l’état",
        "ai_open_folder": "Ouvrir le dossier IA",
        "ai_save": "Enregistrer",
        "ai_saved": "Configuration IA enregistrée.",
        "ai_state": "État IA : {state}",
        "ai_folder_missing": "Le dossier IA n’existe pas encore.",
        "ai_runtime_missing": "Runtime IA introuvable",
        "ai_model_missing": "Modèle non installé",
    },
    "zh": {
        "ai_reinforce": "用本地 AI 增强",
        "ai_window_title": "用本地 AI 增强",
        "ai_intro": "本地 AI 可帮助处理不确定的标题、作者、重复项和问题版本。它在你的电脑上运行，不需要账号或 API key，也不会把书籍发送到互联网。",
        "ai_enable": "启用本地 AI",
        "ai_model": "模型：",
        "ai_test": "测试本地 AI",
        "ai_status": "查看状态",
        "ai_open_folder": "打开 AI 文件夹",
        "ai_save": "保存",
        "ai_saved": "AI 配置已保存。",
        "ai_state": "AI 状态：{state}",
        "ai_folder_missing": "AI 文件夹尚不存在。",
        "ai_runtime_missing": "找不到 AI runtime",
        "ai_model_missing": "模型未安装",
    },
}

EXTRA_TEXTS_SETTINGS = {
    "es": {"settings": "Configuración", "ocr_pages": "Páginas máximas de OCR", "offline_mode": "Modo sin conexión", "save": "Guardar", "auto_process_exact": "Procesar exactos verificados", "auto_process_exact_title": "Duplicados exactos", "auto_process_exact_question": "Se procesarán {count} pares con contenido SHA-256 idéntico. ¿Enviar la copia no preferida a cuarentena?"},
    "en": {"settings": "Settings", "ocr_pages": "Maximum OCR pages", "offline_mode": "Offline mode", "save": "Save", "auto_process_exact": "Process verified exact copies", "auto_process_exact_title": "Exact duplicates", "auto_process_exact_question": "{count} pairs with identical SHA-256 content will be processed. Send the non-preferred copy to quarantine?"},
    "fr": {"settings": "Paramètres", "ocr_pages": "Pages OCR maximales", "offline_mode": "Mode hors connexion", "save": "Enregistrer", "auto_process_exact": "Traiter les copies exactes", "auto_process_exact_title": "Doublons exacts", "auto_process_exact_question": "{count} paires au contenu SHA-256 identique seront traitées. Envoyer la copie non préférée en quarantaine ?"},
    "zh": {"settings": "设置", "ocr_pages": "最大 OCR 页数", "offline_mode": "离线模式", "save": "保存", "auto_process_exact": "处理已验证的完全副本", "auto_process_exact_title": "完全重复项", "auto_process_exact_question": "将处理 {count} 对 SHA-256 内容相同的文件。是否将非首选副本移入隔离区？"},
}

for _lang, _data in EXTRA_TEXTS_UNDO.items():
    TEXTS.setdefault(_lang, {}).update(_data)

for _lang, _data in EXTRA_TEXTS_REVIEW.items():
    TEXTS.setdefault(_lang, {}).update(_data)

for _lang, _data in EXTRA_TEXTS_AI.items():
    TEXTS.setdefault(_lang, {}).update(_data)

for _lang, _data in EXTRA_TEXTS_SETTINGS.items():
    TEXTS.setdefault(_lang, {}).update(_data)


def nuevo_batch_id(prefijo):
    return _undo_history.nuevo_batch_id(prefijo)


def _timestamp():
    return _file_transactions.timestamp()


def escritura_atomica_texto(ruta, texto, encoding="utf-8"):
    return _file_transactions.escritura_atomica_texto(ruta, texto, encoding=encoding)


def _append_texto_atomico(ruta, texto, encoding="utf-8"):
    return _file_transactions.append_texto_durable(ruta, texto, encoding=encoding)


def _append_jsonl_atomico(ruta, registro):
    return _file_transactions.append_jsonl_durable(ruta, registro)


def nuevo_transaction_id(tipo):
    return _file_transactions.nuevo_transaction_id(tipo)


def registrar_evento_transaccion(op_id, tipo, estado, origen="", destino="", cuarentena="", motivo="", hash_archivo="", error=""):
    return _file_transactions.registrar_evento_transaccion(
        FILE_TRANSACTION_JOURNAL, APP_DATA, op_id, tipo, estado,
        origen, destino, cuarentena, motivo, hash_archivo, error
    )


def iniciar_transaccion_archivo(tipo, origen="", destino="", cuarentena="", motivo="", hash_archivo=""):
    return _file_transactions.iniciar_transaccion_archivo(
        FILE_TRANSACTION_JOURNAL, APP_DATA, tipo, origen, destino,
        cuarentena, motivo, hash_archivo
    )


def actualizar_transaccion_archivo(op_id, estado, tipo="update", origen="", destino="", cuarentena="", motivo="", hash_archivo="", error=""):
    return _file_transactions.actualizar_transaccion_archivo(
        FILE_TRANSACTION_JOURNAL, APP_DATA, op_id, estado, tipo,
        origen, destino, cuarentena, motivo, hash_archivo, error
    )


def _leer_jsonl(ruta):
    return _file_transactions.leer_jsonl(ruta)


def transacciones_archivo_incompletas():
    return _file_transactions.transacciones_archivo_incompletas(FILE_TRANSACTION_JOURNAL)


def recuperar_transacciones_archivo_pendientes():
    return _file_transactions.recuperar_transacciones_archivo_pendientes(FILE_TRANSACTION_JOURNAL, APP_DATA)


def operation_plan_store():
    store = OperationPlanStore(OPERATION_PLANS_DB)
    store.reconcile_from_journal(_file_transactions.leer_jsonl(FILE_TRANSACTION_JOURNAL))
    return store


def duplicate_review_store():
    return _duplicate_review_store.DuplicateReviewStore(DUPLICATE_REVIEW_DB)


def registrar_manifest_cuarentena(destino, origen, motivo="", conservado="", op_id=""):
    return _file_transactions.registrar_manifest_cuarentena(
        TRASH_MANIFEST_JSONL, destino, origen, motivo, conservado, op_id
    )


def registrar_undo(batch_id, tipo, origen, destino, detalle=""):
    return _undo_history.registrar_undo(UNDO_JSONL, APP_DATA, batch_id, tipo, origen, destino, detalle)


def mark_action_undone(batch_id):
    return _undo_history.mark_action_undone(UNDO_JSONL, APP_DATA, batch_id)


def mark_undo_item_restored(batch_id, item):
    return _undo_history.mark_undo_item_restored(UNDO_JSONL, APP_DATA, batch_id, item)


def obtener_ultima_accion_undo():
    return _undo_history.obtener_ultima_accion_undo(UNDO_JSONL)



def _biblioteca_inicial():
    """
    Load the last selected library folder.
    First-time users start without a configured library; defaults are only used by folder dialogs.
    """
    try:
        if CONFIG_JSON.exists():
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)

            ruta = str(data.get("library") or data.get("biblioteca") or "").strip()

            if not ruta:
                return None

            return Path(ruta)

    except Exception:
        pass

    return None

FINAL = _biblioteca_inicial()


def biblioteca_configurada() -> bool:
    return isinstance(FINAL, Path) and str(FINAL).strip() != ""

EXTENSIONES_LIBROS = {
    ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".djvu",
    ".fb2", ".txt", ".rtf", ".doc", ".docx", ".odt", ".cbr", ".cbz"
}
KINDLE_EXTENSIONS = {".mobi", ".azw", ".azw3"}

CARPETAS_IGNORADAS = {
    TRASH_DIR_NAME,
    "_reportes_duplicados",
    "duplicados_exactos",
    "_app_agregar_libros",
    "_renombrado_web",
    "para revisar nuevamente",
    "__pycache__",
}

UMBRAL_DUP_NOMBRE_ALTO = 0.93
UMBRAL_DUP_NOMBRE_MEDIO = 0.86
UMBRAL_DUP_TAMANO = 0.18
UMBRAL_RENOMBRAR = 90
PAUSA_WEB = 0.20
MAX_PAGINAS_TEXTO = 7
MAX_PAGINAS_OCR = 7


def es_libro(ruta: Path) -> bool:
    return ruta.is_file() and ruta.suffix.lower() in EXTENSIONES_LIBROS


def dentro_de(ruta: Path, carpeta: Path) -> bool:
    try:
        ruta.resolve().relative_to(carpeta.resolve())
        return True
    except Exception:
        return False


def clave_ruta_resuelta(ruta) -> str:
    return _normalizer.clave_ruta_resuelta(ruta)


def ignorar_por_carpeta(ruta: Path) -> bool:
    partes = [p.lower() for p in ruta.parts]
    return any(nombre in partes for nombre in CARPETAS_IGNORADAS)


def en_carpeta_revisar_nuevamente(ruta: Path) -> bool:
    if not biblioteca_configurada():
        return False
    return dentro_de(Path(ruta), FINAL / "PARA REVISAR NUEVAMENTE")


def en_raiz_biblioteca(ruta: Path) -> bool:
    if not biblioteca_configurada():
        return False
    try:
        return Path(ruta).resolve().parent == FINAL.resolve()
    except Exception:
        return False


def buscar_libros_final():
    if not biblioteca_configurada() or not FINAL.exists():
        return []
    return sorted(
        [p for p in FINAL.rglob("*") if es_libro(p) and not ignorar_por_carpeta(p)],
        key=lambda p: str(p).lower()
    )


def calcular_hash(ruta: Path, bloque=1024 * 1024) -> str:
    return _file_identity.sha256_file(ruta, block_size=bloque)


def calcular_hash_parcial(ruta: Path, bloque=256 * 1024) -> str:
    return _file_identity.partial_file_signature(ruta, block_size=bloque)


def archivos_identicos_vivos(a: Path, b: Path) -> bool:
    """Revalidate two live files immediately before a duplicate action."""
    return _file_identity.live_files_identical(a, b)


def quitar_acentos(texto: str) -> str:
    return _normalizer.quitar_acentos(texto)


def _texto_busqueda_unicode(texto: str) -> str:
    return _normalizer.texto_busqueda_unicode(texto)


def normalizar_texto(texto: str) -> str:
    return _normalizer.normalizar_texto(texto)


def normalizar_titulo_para_dobles_texto(texto: str) -> str:
    return _normalizer.normalizar_titulo_para_dobles_texto(texto)


def similitud(a: str, b: str) -> float:
    a = normalizar_texto(a)
    b = normalizar_texto(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def diferencia_tamano(a: int, b: int) -> float:
    return _duplicate_engine.diferencia_tamano(a, b)


def numeros_significativos_nombre(nombre: str):
    return _duplicate_engine.numeros_significativos_nombre(nombre)


def numeros_de_titulo_en_conflicto(nombre_a: str, nombre_b: str) -> bool:
    return _duplicate_engine.numeros_de_titulo_en_conflicto(nombre_a, nombre_b)


FORMATO_PREFERENCIA = _duplicate_engine.FORMATO_PREFERENCIA


def _stem_limpio_para_dobles(nombre: str) -> str:
    return _duplicate_engine._stem_limpio_para_dobles(
        nombre,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def titulo_normalizado_para_dobles(nombre: str) -> str:
    return _duplicate_engine.titulo_normalizado_para_dobles(
        nombre,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def _variante_titulo_doble_valida(valor: str) -> bool:
    return _duplicate_engine._variante_titulo_doble_valida(valor)


def variantes_titulo_normalizado_para_dobles(nombre: str):
    return _duplicate_engine.variantes_titulo_normalizado_para_dobles(
        nombre,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def similitud_titulo_doble(titulo_a: str, titulo_b: str) -> float:
    return _duplicate_engine.similitud_titulo_doble(titulo_a, titulo_b)


PALABRAS_NO_DISTINTIVAS_TITULO = _duplicate_engine.PALABRAS_NO_DISTINTIVAS_TITULO


def tokens_distintivos_titulo(titulo: str):
    return _duplicate_engine.tokens_distintivos_titulo(titulo)


def titulo_doble_requiere_autor(titulo: str) -> bool:
    return _duplicate_engine.titulo_doble_requiere_autor(titulo)


def autor_probable_desde_nombre_archivo(nombre: str) -> str:
    return _duplicate_engine.autor_probable_desde_nombre_archivo(
        nombre,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
    )


def autor_doble_es_informativo(autor: str) -> bool:
    return _duplicate_engine.autor_doble_es_informativo(autor, AUTORES_MONONIMOS_CONFIABLES)


def autores_dobles_compatibles(autor_a: str, autor_b: str) -> bool:
    return _duplicate_engine.autores_dobles_compatibles(
        autor_a,
        autor_b,
        autores_mononimos=AUTORES_MONONIMOS_CONFIABLES,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
    )


def autores_dobles_en_conflicto(autor_a: str, autor_b: str) -> bool:
    return _duplicate_engine.autores_dobles_en_conflicto(
        autor_a,
        autor_b,
        autores_mononimos=AUTORES_MONONIMOS_CONFIABLES,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
    )


def autor_item_para_dobles(item) -> str:
    return _duplicate_engine.autor_item_para_dobles(
        item,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
    )


def titulos_dobles_compatibles(titulo_a: str, titulo_b: str, umbral=0.96):
    return _duplicate_engine.titulos_dobles_compatibles(titulo_a, titulo_b, umbral=umbral)


def mtime_item(item) -> float:
    return _duplicate_engine.mtime_item(item)


def formato_rank(extension: str) -> int:
    return _duplicate_engine.formato_rank(extension)


def elegir_item_preferido_por_fecha_y_formato(a, b):
    return _duplicate_engine.elegir_item_preferido_por_fecha_y_formato(a, b)


def coincidencias_por_titulo_real(titulo: str, indice, umbral=0.96, autor: str = "", excluir_rutas=None):
    return _duplicate_engine.coincidencias_por_titulo_real(
        titulo,
        indice,
        umbral=umbral,
        autor=autor,
        excluir_rutas=excluir_rutas,
        ignorar_por_carpeta_func=ignorar_por_carpeta,
        path_key_func=clave_ruta_resuelta,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        autores_mononimos=AUTORES_MONONIMOS_CONFIABLES,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def item_indice_ligero_desde_ruta(ruta: Path, titulo_real: str = ""):
    return _duplicate_engine.item_indice_ligero_desde_ruta(
        ruta,
        titulo_real,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def coincidencias_por_titulo_real_en_biblioteca(titulo: str, indice=None, umbral=0.96, autor: str = "", excluir_rutas=None):
    coincidencias = coincidencias_por_titulo_real(
        titulo,
        indice or {"archivos": []},
        umbral=umbral,
        autor=autor,
        excluir_rutas=excluir_rutas,
    )
    if coincidencias:
        return coincidencias
    rutas_excluidas = {clave_ruta_resuelta(ruta) for ruta in (excluir_rutas or [])}
    indice_vivo = {"archivos": []}
    for ruta in buscar_libros_final():
        if clave_ruta_resuelta(ruta) in rutas_excluidas:
            continue
        try:
            indice_vivo["archivos"].append(item_indice_ligero_desde_ruta(ruta, ruta.name))
        except Exception:
            continue
    return coincidencias_por_titulo_real(titulo, indice_vivo, umbral=umbral, autor=autor, excluir_rutas=excluir_rutas)


def item_indice_desde_ruta(ruta: Path, titulo_real: str = ""):
    return _duplicate_engine.item_indice_desde_ruta(
        ruta,
        titulo_real,
        calcular_hash_func=calcular_hash,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def limpiar_nombre_archivo(texto: str, max_len=170) -> str:
    return _naming.sanitize_filename(texto, max_length=max_len)


def reparar_mojibake(texto: str) -> str:
    return _naming.repair_mojibake(texto)


def _variantes_autor_para_limpieza_titulo(autor: str) -> list[list[str]]:
    return _naming.author_cleanup_variants(autor)


def _quitar_fragmento_inicial_autor(titulo: str, autor: str) -> str:
    return _naming._remove_initial_author_fragment(titulo, autor)


def quitar_autor_pegado_al_titulo(titulo: str, autor: str = "") -> str:
    return _naming.remove_attached_author(titulo, autor)


def limpiar_ruido_ocr_en_titulo(titulo: str) -> str:
    return _naming.remove_ocr_title_noise(titulo)


def limpiar_titulo_legible(titulo: str, autor: str = "") -> str:
    return _naming.clean_readable_title(
        titulo,
        autor,
        extract_filename_metadata=extraer_metadatos_desde_nombre,
        similarity=similitud,
        clean_distribution_noise=limpiar_ruido_distribucion,
        correct_compact_title=corregir_compactos_titulo,
    )


def preferir_alias_latino_autor(autor: str) -> str:
    return _naming.prefer_latin_author_alias(autor)


def crear_nombre_sugerido(autor, titulo, anio, isbn, extension):
    return _naming.suggested_filename(
        autor,
        titulo,
        anio,
        isbn,
        extension,
        clean_title=limpiar_titulo_legible,
    )


def destino_sin_colision(destino: Path) -> Path:
    return _file_transactions.destino_sin_colision(destino)


def cargar_json(ruta, defecto):
    return _index_store.cargar_json(ruta, defecto)


def guardar_json(ruta, data):
    return _index_store.guardar_json(ruta, data)


def guardar_config_biblioteca():
    _config_store.save_library_config(
        CONFIG_JSON,
        library=str(FINAL) if biblioteca_configurada() else "",
        language=IDIOMA_ACTUAL,
    )


def configuracion_operacion_por_defecto():
    return dict(_config_store.DEFAULT_OPERATION_CONFIG)


def cargar_configuracion_operacion():
    return _config_store.load_operation_config(CONFIG_JSON)


def guardar_configuracion_operacion(operation_config):
    return _config_store.save_operation_config(
        CONFIG_JSON,
        operation_config,
        library=str(FINAL) if biblioteca_configurada() else None,
        language=IDIOMA_ACTUAL,
    )


def configuracion_ia_por_defecto():
    return {
        "enabled": False,
        "model_id": _ai_model_catalog.default_model_id(),
        "models_dir": "",
        "port": _ai_runtime_manager.DEFAULT_AI_PORT,
    }


def cargar_configuracion_ia():
    config = cargar_json(CONFIG_JSON, {})
    ai_config = dict(config.get(AI_CONFIG_KEY, {}) or {})
    defaults = configuracion_ia_por_defecto()
    defaults.update({
        "enabled": bool(ai_config.get("enabled", defaults["enabled"])),
        "model_id": ai_config.get("model_id") if _ai_model_catalog.is_allowed_model(ai_config.get("model_id")) else defaults["model_id"],
        "models_dir": str(ai_config.get("models_dir", "") or ""),
        "port": int(ai_config.get("port") or defaults["port"]),
    })
    return defaults


def guardar_configuracion_ia(ai_config):
    actual = cargar_json(CONFIG_JSON, {})
    cleaned = configuracion_ia_por_defecto()
    ai_config = ai_config or {}
    cleaned["enabled"] = bool(ai_config.get("enabled", False))
    model_id = ai_config.get("model_id") or cleaned["model_id"]
    cleaned["model_id"] = model_id if _ai_model_catalog.is_allowed_model(model_id) else _ai_model_catalog.default_model_id()
    cleaned["models_dir"] = str(ai_config.get("models_dir", "") or "")
    cleaned["port"] = int(ai_config.get("port") or cleaned["port"])
    actual[AI_CONFIG_KEY] = cleaned
    actual["version"] = CONFIG_VERSION
    actual["library"] = str(FINAL) if biblioteca_configurada() else actual.get("library", "")
    actual["language"] = IDIOMA_ACTUAL
    actual["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guardar_json(CONFIG_JSON, actual)
    return cleaned


def modelos_ia_local():
    return list(_ai_model_catalog.get_model_options())


def estado_ia_local(ai_config=None):
    return _ai_runtime_manager.get_ai_status(ai_config or cargar_configuracion_ia())


def probar_ia_local(ai_config=None):
    ai_config = ai_config or cargar_configuracion_ia()
    usable, status = _ai_runtime_manager.can_use_ai(ai_config)
    if not ai_config.get("enabled"):
        return False, tr("ai_state", state="IA desactivada"), status
    if not usable:
        return False, tr("ai_state", state=status.get("state", "IA no configurada")), status
    runtime = _ai_runtime_manager.LlamaCppServer(ai_config)
    ok, state = runtime.start(timeout_seconds=5)
    return ok, tr("ai_state", state=state), status


def carpeta_ia_local():
    return _ai_paths.bundled_ai_dir()

def cargar_indice():
    return _index_store.cargar_indice(INDICE_JSON)


def guardar_indice(indice):
    # Keep the portable JSON index as the compatibility/export surface.  The
    # richer catalog is a non-destructive projection: a catalog problem must
    # never prevent the already-proven atomic JSON write from completing.
    result = _index_store.guardar_indice(INDICE_JSON, indice)
    try:
        catalog_store().sync_index(indice)
    except Exception:
        pass
    return result


def catalog_store():
    return _catalog_store.CatalogStore(CATALOG_DB)


def sincronizar_catalogo(indice=None):
    """Populate the durable work/edition/file catalog from the current index."""
    return catalog_store().sync_index(indice if indice is not None else cargar_indice())


def registro_catalogo_para_ruta(ruta):
    # The inspector is a read path: never migrate/initialize a database or wait
    # behind the catalog-sync writer from the Tk main thread.
    return _catalog_store.CatalogStore(CATALOG_DB, initialize=False).record_for_path(ruta)


def aplicar_correccion_manual_indice(ruta, cambios, indice=None):
    """Persist human-confirmed catalog fields without renaming the source file."""
    ruta_clave = clave_ruta_resuelta(ruta)
    allowed = {
        "titulo", "autor", "isbn", "idioma", "editorial", "anio", "serie",
        "edicion", "tags", "favorite", "read_status",
    }
    identity_fields = {
        "titulo", "autor", "isbn", "idioma", "editorial", "anio", "serie", "edicion",
    }
    cleaned = {key: value for key, value in dict(cambios or {}).items() if key in allowed}
    current = dict(indice if indice is not None else cargar_indice())
    rows = [dict(row) for row in current.get("archivos", [])]
    found = False
    for row in rows:
        if clave_ruta_resuelta(row.get("ruta", "")) != ruta_clave:
            continue
        found = True
        provenance = dict(row.get("provenance") or {})
        for key, value in cleaned.items():
            if key == "tags" and isinstance(value, str):
                value = [part.strip() for part in value.split(",") if part.strip()]
            row[key] = value
            provenance[key] = {"source": "usuario", "confidence": 100}
        if "favorite" in cleaned:
            row.pop("favorito", None)
            row.pop("is_favorite", None)
        row["provenance"] = provenance
        if identity_fields.intersection(cleaned):
            row["manual_lock"] = True
            row["confirmed_correction"] = True
            row["confianza_global"] = 100
        break
    if not found:
        raise FileNotFoundError(str(ruta))
    current["archivos"] = rows
    guardar_indice(current)
    return current


def campos_indice_desde_metadatos(meta):
    """Project a recognition result into durable, provenance-aware index data."""
    meta = dict(meta or {})
    source = str(meta.get("fuente") or meta.get("metodo") or "").strip()
    confidence = meta.get("confianza_global", meta.get("confianza", 0)) or 0
    projected = {
        "titulo": meta.get("titulo", ""),
        "titulo_real": meta.get("titulo", ""),
        "autor": meta.get("autor", ""),
        "isbn": meta.get("isbn", ""),
        "cover_url": meta.get("cover_url", ""),
        "anio": meta.get("anio", meta.get("year", "")),
        "editorial": meta.get("editorial", meta.get("publisher", "")),
        "idioma": meta.get("idioma", meta.get("idioma_sugerido_ia", meta.get("language", ""))),
        "serie": meta.get("serie", meta.get("serie_sugerida_ia", meta.get("series", ""))),
        "edicion": meta.get("edicion", meta.get("edition", "")),
        "fuente": source,
        "confianza": meta.get("confianza", confidence),
        "confianza_global": confidence,
    }
    evidence = meta.get("evidencias") or meta.get("provenance")
    if evidence:
        projected["evidencias" if isinstance(evidence, list) else "provenance"] = evidence
    elif source:
        projected["provenance"] = {
            field: {"source": source, "confidence": confidence}
            for field in ("titulo", "autor", "isbn")
            if projected.get(field)
        }
    return {key: value for key, value in projected.items() if value not in (None, "", [], {})}


def actualizar_indice_rutas(rutas, indice=None, metadata_por_ruta=None):
    """Persist an incremental index update for paths changed by one operation."""
    if not biblioteca_configurada():
        return crear_o_actualizar_indice()
    metadata_normalizada = {
        os.path.normcase(os.path.abspath(str(path))): campos_indice_desde_metadatos(meta)
        for path, meta in (metadata_por_ruta or {}).items()
        if path
    }
    actualizado = _index_service.update_paths(
        indice if indice is not None else cargar_indice(),
        rutas,
        library_root=FINAL,
        build_item=item_indice_desde_ruta,
        ignore_path=ignorar_por_carpeta,
        metadata_by_path=metadata_normalizada,
    )
    guardar_indice(actualizado)
    return actualizado


def escribir_historial(accion, origen, destino="", resultado="", detalle="", nombre_sugerido="", fuente="", confianza=""):
    return _undo_history.escribir_historial(
        HISTORIAL_CSV, APP_DATA, accion, origen, destino, resultado,
        detalle, nombre_sugerido, fuente, confianza
    )


def crear_o_actualizar_indice(callback=None):
    APP_DATA.mkdir(parents=True, exist_ok=True)

    if not biblioteca_configurada():
        indice = {
            "creado": None,
            "library": "",
            "archivos": [],
        }
        guardar_indice(indice)
        return indice

    FINAL.mkdir(parents=True, exist_ok=True)

    viejo = cargar_indice()
    mapa_viejo = {clave_ruta_resuelta(item["ruta"]): item for item in viejo.get("archivos", []) if item.get("ruta")}
    libros = buscar_libros_final()
    items = []
    total = len(libros)

    for i, ruta in enumerate(libros, start=1):
        try:
            stat = ruta.stat()
            ruta_str = str(ruta)
            anterior = mapa_viejo.get(clave_ruta_resuelta(ruta))
            signature = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev]
            has_metadata = bool(anterior and any(
                key in anterior for key in _index_service.PERSISTENT_METADATA_FIELDS - {"autor"}
            ))
            # On Windows ctime is creation time; a same-size replacement with
            # preserved mtime can fool a stat cache. Rehash annotated records.
            if anterior and not has_metadata and anterior.get("file_signature") == signature and anterior.get("sha256"):
                sha = anterior["sha256"]
            else:
                if callback:
                    callback(tr("updating_index_item", i=i, total=total, name=ruta.name))
                _, sha = _file_identity.validated_sha256_file(ruta)

            meta_nombre = extraer_metadatos_desde_nombre(limpiar_nombre_como_pista(ruta.name))
            fresh = {
                "ruta": ruta_str,
                "nombre": ruta.name,
                "extension": ruta.suffix.lower(),
                "tamano_bytes": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": sha,
                "file_signature": signature,
                "nombre_normalizado": normalizar_texto(ruta.name),
                "autor": meta_nombre.get("autor", ""),
                "autor_normalizado": normalizar_texto(meta_nombre.get("autor", "")),
                "titulo_normalizado": titulo_normalizado_para_dobles(ruta.name),
                "titulos_normalizados": variantes_titulo_normalizado_para_dobles(ruta.name),
            }
            same_content = bool(anterior and anterior.get("sha256") == sha)
            items.append(_index_service.merge_persistent_metadata(fresh, anterior if same_content else None))
        except Exception as e:
            if callback:
                callback(tr("index_read_error", path=ruta, error=e))

    indice = {
        "creado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "library": str(FINAL),
        "archivos": items,
    }
    guardar_indice(indice)
    return indice


def verificar_libro(libro: Path, indice):
    return _duplicate_engine.verificar_libro(
        libro,
        indice,
        tr_func=tr,
        es_libro_func=es_libro,
        biblioteca_configurada_func=biblioteca_configurada,
        en_raiz_biblioteca_func=en_raiz_biblioteca,
        en_carpeta_revisar_nuevamente_func=en_carpeta_revisar_nuevamente,
        calcular_hash_func=calcular_hash,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        ignorar_por_carpeta_func=ignorar_por_carpeta,
        autores_mononimos=AUTORES_MONONIMOS_CONFIABLES,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
        umbral_nombre_alto=UMBRAL_DUP_NOMBRE_ALTO,
        umbral_nombre_medio=UMBRAL_DUP_NOMBRE_MEDIO,
        umbral_tamano=UMBRAL_DUP_TAMANO,
    )


def carpeta_cuarentena(base: Path | None = None) -> Path:
    return _file_transactions.carpeta_cuarentena(
        base,
        FINAL if biblioteca_configurada() else None,
        APP_DATA,
        TRASH_DIR_NAME,
    )


def descartar_archivo_seguro(
    ruta: Path,
    base_cuarentena: Path | None = None,
    motivo: str = "",
    conservado: Path | str | None = None,
    op_id: str | None = None,
) -> Path | None:
    return _file_transactions.descartar_archivo_seguro(
        ruta,
        base_cuarentena,
        motivo,
        conservado,
        op_id,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
        manifest_path=TRASH_MANIFEST_JSONL,
        library_root=FINAL if biblioteca_configurada() else None,
        trash_dir_name=TRASH_DIR_NAME,
    )


def restaurar_descartado(cuarentena: Path | None, destino_original: Path) -> bool:
    return _file_transactions.restaurar_descartado(cuarentena, destino_original)


def mover_a_revisar_nuevamente(ruta: Path, carpeta_destino: Path | None = None, motivo: str = "", op_id: str | None = None) -> Path:
    if carpeta_destino is None and not biblioteca_configurada():
        raise RuntimeError(tr("no_library_selected"))
    carpeta = Path(carpeta_destino) if carpeta_destino is not None else FINAL / "PARA REVISAR NUEVAMENTE"
    return _file_transactions.mover_a_revisar_nuevamente(
        ruta,
        carpeta,
        motivo,
        op_id,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
    )


def _clave_rapida_duplicado(nombre_normalizado: str):
    return _duplicate_engine._clave_rapida_duplicado(nombre_normalizado)


def variantes_item_para_dobles(item):
    return _duplicate_engine.variantes_item_para_dobles(
        item,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def claves_item_para_dobles(item):
    return _duplicate_engine.claves_item_para_dobles(
        item,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def buscar_dobles_biblioteca(indice, limite=None, ignorar_carpetas=True, cancellation=None):
    return _duplicate_engine.buscar_dobles_biblioteca(
        indice,
        limite=limite,
        ignorar_carpetas=ignorar_carpetas,
        calcular_hash_func=calcular_hash,
        cancellation=cancellation,
        ignorar_por_carpeta_func=ignorar_por_carpeta,
        extraer_metadatos_desde_nombre_func=extraer_metadatos_desde_nombre,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        autores_mononimos=AUTORES_MONONIMOS_CONFIABLES,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
        parece_autor_func=_linea_parece_nombre_autor,
        corregir_compactos_titulo_func=corregir_compactos_titulo,
    )


def doble_entre_carpetas(doble, carpeta_a, carpeta_b):
    return _duplicate_engine.doble_entre_carpetas(doble, carpeta_a, carpeta_b)


def filtrar_dobles_entre_carpetas(dobles, carpeta_a, carpeta_b):
    return _duplicate_engine.filtrar_dobles_entre_carpetas(dobles, carpeta_a, carpeta_b)


def validar_isbn10(isbn: str) -> bool:
    isbn = re.sub(r"[^0-9Xx]", "", isbn)
    if len(isbn) != 10:
        return False
    if len(set(isbn.upper())) == 1:
        return False
    total = 0
    for i, ch in enumerate(isbn):
        if i == 9 and ch.upper() == "X":
            val = 10
        elif ch.isdigit():
            val = int(ch)
        else:
            return False
        total += val * (10 - i)
    return total % 11 == 0


def validar_isbn13(isbn: str) -> bool:
    isbn = re.sub(r"[^0-9]", "", isbn)
    if len(isbn) != 13:
        return False
    if len(set(isbn)) == 1:
        return False
    if not isbn.startswith(("978", "979")):
        return False
    total = 0
    for i, ch in enumerate(isbn[:12]):
        total += int(ch) * (1 if i % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return check == int(isbn[-1])


def limpiar_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def extraer_isbns(texto: str):
    if not texto:
        return []
    candidatos = set()
    patron_prefijo = re.compile(r"ISBN(?:-1[03])?\s*[: ]?\s*([0-9Xx][0-9Xx\-\s]{8,25}[0-9Xx])", re.I)
    for m in patron_prefijo.finditer(texto):
        limpio = limpiar_isbn(m.group(1))
        if validar_isbn13(limpio) or validar_isbn10(limpio):
            candidatos.add(limpio)
    for m in re.finditer(r"(97[89][0-9\-\s]{10,20}[0-9])", texto):
        limpio = limpiar_isbn(m.group(1))
        if validar_isbn13(limpio):
            candidatos.add(limpio)
    for m in re.finditer(r"\b(97[89]\d{10})\b", texto):
        limpio = limpiar_isbn(m.group(1))
        if validar_isbn13(limpio):
            candidatos.add(limpio)
    for m in re.finditer(r"\b([0-9Xx][0-9Xx\-\s]{8,18}[0-9Xx])\b", texto):
        limpio = limpiar_isbn(m.group(1))
        if len(limpio) == 10 and validar_isbn10(limpio):
            candidatos.add(limpio)
    return sorted(candidatos)


def extraer_dois(texto: str):
    if not texto:
        return []
    patron = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
    return sorted({m.group(0).rstrip(".,);]").lower() for m in patron.finditer(texto)})


def _decodificar_campo_mobi(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16-be", "utf-16-le", "cp1252", "latin-1"):
        try:
            texto = data.decode(encoding, errors="ignore")
        except Exception:
            continue
        texto = limpiar_texto_extraido(texto.replace("\x00", " "))
        if texto:
            return texto
    return ""


def _texto_identificacion_valido(texto: str, max_len=140) -> str:
    texto = limpiar_nombre_archivo(texto, max_len)
    if not texto or texto == "SIN_TITULO":
        return ""
    texto_norm = normalizar_texto(texto)
    if not texto_norm:
        return ""
    tokens = set(texto_norm.split())
    ruido = {
        "bookmobi", "exth", "mobi", "azw", "azw3", "kindle", "calibre",
        "nn", "autor", "desconocido", "unknown", "sin", "titulo",
        "capitulo", "chapter", "contents", "indice",
    }
    if tokens <= ruido or len(tokens & ruido) >= max(2, len(tokens) - 1):
        return ""
    letras = re.findall(r"[A-Za-zÀ-ÿ]", texto)
    if len(letras) < 3:
        return ""
    raros = re.findall(r"[^A-Za-zÀ-ÿ0-9\s.,:;!?¡¿'’\"()&/\-]", texto)
    if raros and len(raros) / max(1, len(texto)) > 0.08:
        return ""
    return texto


def limpiar_nombre_como_pista(nombre: str) -> str:
    stem = reparar_mojibake(Path(str(nombre)).stem)
    stem = stem.replace("_", " ")
    if "-" in stem:
        partes = [p.strip() for p in stem.split("-") if p.strip()]
        prefijo = partes[0] if partes else ""
        prefijo_norm = normalizar_texto(prefijo)
        raros_prefijo = re.findall(r"[^A-Za-zÀ-ÿ0-9\s.,:;!?¡¿'’\"()&/\-]", prefijo)
        prefijo_ruidoso = (
            "autor desconocido" in prefijo_norm
            or re.search(r"(?i)\b(bookmobi|exth|nn|cap\s*[íi]?\s*t)", prefijo)
            or (raros_prefijo and len(raros_prefijo) / max(1, len(prefijo)) > 0.08)
        )
        if prefijo_ruidoso and len(partes) >= 2:
            stem = partes[-1]
    stem = re.sub(r"\[[^\]]*\]", " ", stem)
    stem = re.sub(r"\b(?:19|20)\d{2}\b", " ", stem)
    stem = re.sub(r"\(\s*\)", " ", stem)
    stem = re.sub(r"(?i)\b(?:nn\s+)?bookmobi\b.*$", " ", stem)
    stem = re.sub(r"(?i)\bautor\s+desconocido\b", " ", stem)
    stem = re.sub(r"(?i)\b(?:unknown\s+author|sin\s+autor|titulo\s+desconocido)\b", " ", stem)
    stem = re.sub(r"(?i)\b(?:bookmobi|exth|nn|calibre|ebook)\b", " ", stem)
    stem = re.sub(r"(?i)^\s*cap\s*[^\-]{0,14}\s*-\s*", " ", stem)
    stem = re.sub(r"(?i)\bcap\s*[íi]?\s*tulo\b", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -_.,;")
    return _texto_identificacion_valido(stem, 180)


def extraer_metadatos_mobi(ruta: Path):
    resultado = {"titulo": "", "autor": "", "editorial": "", "anio": "", "isbn": ""}
    try:
        with open(ruta, "rb") as f:
            data = f.read(8_000_000)
    except Exception:
        return resultado

    for exth in [m.start() for m in re.finditer(b"EXTH", data)]:
        if exth + 12 > len(data):
            continue
        try:
            length = struct.unpack(">I", data[exth + 4:exth + 8])[0]
            count = struct.unpack(">I", data[exth + 8:exth + 12])[0]
        except Exception:
            continue
        if length < 12 or length > len(data) - exth or count > 1000:
            continue
        pos = exth + 12
        end = exth + length
        for _ in range(count):
            if pos + 8 > end:
                break
            try:
                record_type, record_len = struct.unpack(">II", data[pos:pos + 8])
            except Exception:
                break
            if record_len < 8 or pos + record_len > end:
                break
            value = _decodificar_campo_mobi(data[pos + 8:pos + record_len])
            if value:
                if record_type == 100 and not resultado["autor"]:
                    resultado["autor"] = _texto_identificacion_valido(value, 90)
                elif record_type == 101 and not resultado["editorial"]:
                    resultado["editorial"] = _texto_identificacion_valido(value, 90)
                elif record_type == 104 and not resultado["isbn"]:
                    isbns = extraer_isbns(value)
                    if isbns:
                        resultado["isbn"] = isbns[0]
                elif record_type == 106 and not resultado["anio"]:
                    resultado["anio"] = extraer_anio(value)
                elif record_type == 503 and not resultado["titulo"]:
                    resultado["titulo"] = _texto_identificacion_valido(value, 120)
            pos += record_len
        if any(resultado.values()):
            break

    if not resultado["titulo"]:
        palm_name = _texto_identificacion_valido(_decodificar_campo_mobi(data[:32]), 120)
        if palm_name:
            resultado["titulo"] = palm_name

    if resultado["titulo"] and resultado["autor"] and similitud(resultado["titulo"], resultado["autor"]) >= 0.92:
        resultado["titulo"] = ""
    if resultado["titulo"]:
        resultado["titulo"] = limpiar_titulo_legible(resultado["titulo"], resultado.get("autor", ""))
    if resultado["autor"] and not autor_es_usable(resultado["autor"], resultado["editorial"]):
        resultado["autor"] = ""
    if resultado["isbn"]:
        resultado["isbn"] = limpiar_isbn(resultado["isbn"])
    return resultado


def texto_desde_epub(ruta: Path, max_bytes_total=2_500_000):
    textos = []
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            total = 0
            nombres = z.namelist()
            preferidos = [n for n in nombres if n.lower().endswith((".opf", ".html", ".xhtml", ".xml", ".txt"))]
            for nombre in preferidos[:80]:
                try:
                    info = z.getinfo(nombre)
                    if total + info.file_size > max_bytes_total:
                        break
                    data = z.read(nombre)
                    total += len(data)
                    textos.append(data.decode("utf-8", errors="ignore"))
                except Exception:
                    pass
    except Exception:
        pass
    return "\n".join(textos)


def _resolver_ruta_epub(base_opf: str, href: str) -> str:
    href = urllib.parse.unquote(str(href or "")).split("#", 1)[0].replace("\\", "/")
    base = str(Path(base_opf).parent).replace("\\", "/")
    if base in {"", "."}:
        return href
    return str(Path(base) / href).replace("\\", "/")


def imagenes_portada_epub(ruta: Path, max_imagenes=2):
    imagenes = []
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            nombres = z.namelist()
            lower_to_name = {n.lower(): n for n in nombres}
            candidatos = []

            opfs = [n for n in nombres if n.lower().endswith(".opf")]
            for opf in opfs[:3]:
                try:
                    data = z.read(opf)
                    root = ET.fromstring(data)
                    manifest = {}
                    for item in root.findall(".//{*}manifest/{*}item"):
                        item_id = item.attrib.get("id", "")
                        href = item.attrib.get("href", "")
                        media = item.attrib.get("media-type", "")
                        props = item.attrib.get("properties", "")
                        if item_id and href:
                            manifest[item_id] = (href, media, props)
                        if "cover-image" in props and href:
                            candidatos.append(_resolver_ruta_epub(opf, href))

                    for meta in root.findall(".//{*}meta"):
                        if meta.attrib.get("name", "").lower() == "cover":
                            cover_id = meta.attrib.get("content", "")
                            if cover_id in manifest:
                                candidatos.append(_resolver_ruta_epub(opf, manifest[cover_id][0]))
                except Exception:
                    continue

            for nombre in nombres:
                low = nombre.lower()
                if low.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")):
                    if "cover" in low or "portada" in low or "title" in low:
                        candidatos.append(nombre)

            vistos = set()
            for candidato in candidatos:
                key = candidato.lower()
                nombre = lower_to_name.get(key)
                if not nombre or nombre in vistos:
                    continue
                vistos.add(nombre)
                try:
                    data = z.read(nombre)
                    if len(data) >= 8_000:
                        imagenes.append(data)
                    if len(imagenes) >= max_imagenes:
                        break
                except Exception:
                    pass
    except Exception:
        pass
    return imagenes


def _imagen_dimensiones_desde_bytes(data: bytes):
    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(data)) as img:
            return img.size
    except Exception:
        return (0, 0)


def _es_imagen_archivo_comic(nombre: str) -> bool:
    return (
        bool(nombre)
        and not str(nombre).endswith("/")
        and str(nombre).lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"))
    )


def _prioridad_imagen_comic(nombre: str):
    low = str(nombre or "").lower()
    base = Path(low).name
    score = 50
    if any(token in base for token in ("cover", "portada", "front", "title")):
        score -= 40
    if re.search(r"(^|[^0-9])0*0([^0-9]|$)", base):
        score -= 18
    if re.search(r"(^|[^0-9])0*1([^0-9]|$)", base):
        score -= 12
    if "__macosx" in low or "/thumb" in low or "thumbnail" in low:
        score += 40
    return (score, len(low), low)


def _imagen_comic_util(data: bytes) -> bool:
    if len(data) < 6_000 or len(data) > 18_000_000:
        return False
    ancho, alto = _imagen_dimensiones_desde_bytes(data)
    return ancho >= 220 and alto >= 220


def _agregar_imagen_comic_si_util(imagenes, data: bytes, max_imagenes: int) -> bool:
    if not data or not _imagen_comic_util(data):
        return False
    if data not in imagenes:
        imagenes.append(data)
    return len(imagenes) >= max_imagenes


def _tar_executable() -> str:
    found = shutil.which("tar")
    if found:
        return found
    system_tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    return str(system_tar) if system_tar.exists() else ""


def _tar_archivo_lista(ruta: Path):
    tar = _tar_executable()
    if not tar:
        return []
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        run = subprocess.run(
            [tar, "-tf", str(ruta)],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=flags,
        )
        if run.returncode != 0:
            return []
        return [line.strip() for line in run.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def _tar_extraer_miembro_bytes(ruta: Path, miembro: str):
    tar = _tar_executable()
    if not tar or not miembro:
        return b""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        run = subprocess.run(
            [tar, "-xOf", str(ruta), miembro],
            capture_output=True,
            timeout=60,
            creationflags=flags,
        )
        if run.returncode != 0:
            return b""
        return run.stdout or b""
    except Exception:
        return b""


def _nombres_archivo_comic(ruta: Path):
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            return z.namelist()
    except Exception:
        return _tar_archivo_lista(ruta)


def _limpiar_nombre_comic_para_metadatos(texto: str):
    texto = str(texto or "").replace("\\", "/").strip()
    if "/" in texto:
        partes = [p for p in texto.split("/") if p]
        texto = partes[0] if partes else texto
    texto = Path(texto).stem
    anio = extraer_anio(texto)
    texto = re.sub(r"\((?!\s*(?:1[5-9]\d{2}|20\d{2})\s*\))[^)]*\)", " ", texto)
    texto = re.sub(r"\[[^\]]*\]", " ", texto)
    texto = re.sub(r"(?i)\b(?:digital|scan|scans|empire|blurpixel|dcp|minutemen|goldenagato|spanish|english)\b", " ", texto)
    texto = re.sub(r"(?i)\b(?:cbr|cbz|comic|manga|ebook)\b", " ", texto)
    texto = re.sub(r"[_\.]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" -_.,;")
    titulo = limpiar_titulo_legible(texto)
    if anio:
        titulo = re.sub(rf"\(?\b{re.escape(anio)}\b\)?", " ", titulo)
        titulo = re.sub(r"\s+", " ", titulo).strip(" -_.,;")
    return titulo, anio


def extraer_metadatos_comic_archivo(ruta: Path):
    candidatos = [ruta.stem]
    for nombre in _nombres_archivo_comic(ruta)[:60]:
        nombre = str(nombre or "").replace("\\", "/").strip("/")
        if not nombre:
            continue
        partes = [p for p in nombre.split("/") if p]
        if len(partes) > 1:
            candidatos.append(partes[0])
        if _es_imagen_archivo_comic(nombre):
            stem = Path(partes[-1]).stem if partes else Path(nombre).stem
            if not re.fullmatch(r"0*\d+", stem):
                candidatos.append(stem)

    mejores = []
    vistos = set()
    for candidato in candidatos:
        titulo, anio = _limpiar_nombre_comic_para_metadatos(candidato)
        key = normalizar_texto(f"{titulo} {anio}")
        if not titulo or key in vistos:
            continue
        vistos.add(key)
        if not _titulo_candidato_valido(titulo, permitir_nombre_persona=True):
            continue
        score = 50 + (15 if anio else 0)
        if len(titulo.split()) <= 8:
            score += 8
        if any(ch.isdigit() for ch in candidato) and anio:
            score += 5
        mejores.append((score, titulo, anio))
    if not mejores:
        return {"titulo": "", "autor": "", "editorial": "", "anio": "", "isbn": ""}
    _, titulo, anio = max(mejores, key=lambda item: item[0])
    return {"titulo": titulo, "autor": "", "editorial": "", "anio": anio, "isbn": ""}


def imagenes_portada_cbz(ruta: Path, max_imagenes=2):
    """Extrae portadas de CBZ/CBR, incluso si un .cbz es realmente RAR."""
    imagenes = []
    candidatos = []
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            nombres = [
                nombre for nombre in z.namelist()
                if _es_imagen_archivo_comic(nombre)
            ]
            if not nombres:
                return imagenes
            candidatos = sorted(nombres, key=_prioridad_imagen_comic)[: max(6, max_imagenes * 4)]
            for nombre in candidatos:
                try:
                    info = z.getinfo(nombre)
                    if info.file_size < 6_000 or info.file_size > 18_000_000:
                        continue
                    data = z.read(nombre)
                    if _agregar_imagen_comic_si_util(imagenes, data, max_imagenes):
                        break
                except Exception:
                    continue
    except Exception:
        pass
    if imagenes:
        return imagenes

    # Fallback: algunos archivos .cbz son RAR mal etiquetados. tar.exe/libarchive
    # puede listar y extraer miembros concretos a stdout sin crear temporales.
    try:
        nombres = [nombre for nombre in _tar_archivo_lista(ruta) if _es_imagen_archivo_comic(nombre)]
        candidatos = sorted(nombres, key=_prioridad_imagen_comic)[: max(6, max_imagenes * 4)]
        for nombre in candidatos:
            data = _tar_extraer_miembro_bytes(ruta, nombre)
            if _agregar_imagen_comic_si_util(imagenes, data, max_imagenes):
                break
    except Exception:
        pass
    return imagenes


def _uint32be(data: bytes, offset: int, default=None):
    try:
        if offset < 0 or offset + 4 > len(data):
            return default
        return struct.unpack(">I", data[offset:offset + 4])[0]
    except Exception:
        return default


def _pdb_record_ranges(data: bytes):
    try:
        if len(data) < 86:
            return []
        count = struct.unpack(">H", data[76:78])[0]
        if count <= 0 or count > 10000 or 78 + count * 8 > len(data):
            return []
        offsets = []
        for idx in range(count):
            off = _uint32be(data, 78 + idx * 8)
            if off is not None and 0 <= off < len(data):
                offsets.append(off)
        offsets = sorted(dict.fromkeys(offsets))
        ranges = []
        for idx, start in enumerate(offsets):
            end = offsets[idx + 1] if idx + 1 < len(offsets) else len(data)
            if end > start:
                ranges.append((start, end))
        return ranges
    except Exception:
        return []


def _exth_record_valores(data: bytes, exth_offset: int):
    if exth_offset < 0 or exth_offset + 12 > len(data) or data[exth_offset:exth_offset + 4] != b"EXTH":
        return {}
    length = _uint32be(data, exth_offset + 4, 0)
    count = _uint32be(data, exth_offset + 8, 0)
    if length < 12 or exth_offset + length > len(data) or count > 1000:
        return {}
    pos = exth_offset + 12
    end = exth_offset + length
    valores = {}
    for _ in range(count):
        if pos + 8 > end:
            break
        record_type = _uint32be(data, pos)
        record_len = _uint32be(data, pos + 4)
        if record_type is None or record_len is None or record_len < 8 or pos + record_len > end:
            break
        valores.setdefault(record_type, []).append(data[pos + 8:pos + record_len])
        pos += record_len
    return valores


def _imagenes_portada_mobi_por_exth(data: bytes):
    ranges = _pdb_record_ranges(data)
    if not ranges:
        return []
    first_record = ranges[0][0]
    mobi_header_offset = first_record + 16
    if mobi_header_offset + 132 > len(data) or data[mobi_header_offset:mobi_header_offset + 4] != b"MOBI":
        return []
    mobi_header_len = _uint32be(data, mobi_header_offset + 4, 0)
    first_image_candidates = [
        _uint32be(data, mobi_header_offset + 108),
        _uint32be(data, first_record + 108),
    ]
    exth_flag_candidates = [
        _uint32be(data, mobi_header_offset + 112, 0),
        _uint32be(data, first_record + 128, 0),
    ]
    first_image_candidates = [
        int(value) for value in first_image_candidates
        if value is not None and 0 <= int(value) < len(ranges)
    ]
    has_exth = any(value and (int(value) & 0x40) for value in exth_flag_candidates)
    if not mobi_header_len or not first_image_candidates or not has_exth:
        return []
    exth_offset = mobi_header_offset + mobi_header_len
    valores = _exth_record_valores(data, exth_offset)
    cover_values = valores.get(201, []) + valores.get(202, [])
    imagenes = []
    vistos = set()
    for raw in cover_values[:2]:
        if len(raw) not in {1, 2, 4}:
            continue
        cover_offset = int.from_bytes(raw, "big")
        for first_image_index in first_image_candidates:
            record_index = first_image_index + cover_offset
            if record_index < 0 or record_index >= len(ranges):
                continue
            start, end = ranges[record_index]
            blob = data[start:end]
            clave = hashlib.sha1(blob[:8192]).hexdigest()
            if clave in vistos:
                continue
            ancho, alto = _imagen_dimensiones_desde_bytes(blob)
            if ancho >= 220 and alto >= 220:
                vistos.add(clave)
                imagenes.append(blob)
    return imagenes


def imagenes_portada_mobi(ruta: Path, max_imagenes=3):
    """Extrae imágenes embebidas de MOBI/AZW en memoria para OCR de portada."""
    imagenes = []
    try:
        max_bytes = min(max(ruta.stat().st_size, 0), 24_000_000)
        with open(ruta, "rb") as f:
            data = f.read(max_bytes)
    except Exception:
        return imagenes

    for blob in _imagenes_portada_mobi_por_exth(data):
        if blob not in imagenes:
            imagenes.append(blob)
        if len(imagenes) >= max_imagenes:
            return imagenes

    candidatos = []

    def agregar(inicio, fin, tipo):
        if inicio < 0 or fin <= inicio:
            return
        blob = data[inicio:fin]
        if not (8_000 <= len(blob) <= 8_000_000):
            return
        ancho, alto = _imagen_dimensiones_desde_bytes(blob)
        area = ancho * alto
        if area and (ancho < 220 or alto < 220):
            return
        candidatos.append((area or len(blob), inicio, tipo, blob))

    for m in re.finditer(b"\xff\xd8\xff", data):
        inicio = m.start()
        fin = data.find(b"\xff\xd9", inicio + 3)
        if fin != -1:
            agregar(inicio, fin + 2, "jpeg")

    png_sig = b"\x89PNG\r\n\x1a\n"
    for m in re.finditer(re.escape(png_sig), data):
        inicio = m.start()
        fin = data.find(b"IEND", inicio + 8)
        if fin != -1:
            agregar(inicio, fin + 8, "png")

    for m in re.finditer(b"RIFF", data):
        inicio = m.start()
        if data[inicio + 8:inicio + 12] != b"WEBP" or inicio + 12 > len(data):
            continue
        try:
            size = struct.unpack("<I", data[inicio + 4:inicio + 8])[0] + 8
        except Exception:
            continue
        agregar(inicio, min(len(data), inicio + size), "webp")

    vistos = set()
    ordenados = []
    for item in sorted(candidatos, key=lambda item: item[1])[:max_imagenes]:
        ordenados.append(item)
    for item in sorted(candidatos, key=lambda item: (-item[0], item[1])):
        ordenados.append(item)
    for _peso, inicio, _tipo, blob in ordenados:
        clave = hashlib.sha1(blob[:8192]).hexdigest()
        if clave in vistos:
            continue
        vistos.add(clave)
        if blob not in imagenes:
            imagenes.append(blob)
        if len(imagenes) >= max_imagenes:
            break
    return imagenes


def limpiar_texto_extraido(texto: str) -> str:
    texto = reparar_mojibake(html.unescape(str(texto or " ")))
    texto = re.sub(r"(?i)<\s*(br|p|div|section|article|h[1-6]|li|tr|table|body|title)\b[^>]*>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _linea_parece_nombre_autor(linea: str) -> bool:
    linea = re.sub(r"\s+", " ", str(linea or "")).strip(" \t-–—|")
    if not 5 <= len(linea) <= 90:
        return False
    low = normalizar_texto(linea)
    bloqueadas = {
        "isbn", "copyright", "editorial", "publisher", "edicion", "edition",
        "traduccion", "traducido", "translator", "indice", "contents",
        "capitulo", "chapter", "prologo", "preface", "biblioteca",
        "public", "domain", "dominio", "licencia", "license", "creative",
        "commons", "rights", "derechos", "novela", "novel", "serie", "saga",
        "clasico", "classics", "filosofia", "philosophy", "genero", "genre",
        "adaptado", "ilustrado", "ilustraciones", "fiction", "description",
        "ciencia", "ficcion", "grammata",
        "certificado",
    }
    if set(low.split()) & bloqueadas:
        return False
    if re.search(r"\d|@|www\.|https?://", linea, re.I):
        return False
    palabras = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'.-]*", linea)
    if not 2 <= len(palabras) <= 6:
        return False
    conectores = {"de", "da", "di", "do", "du", "del", "van", "von", "der", "den", "la", "le", "el", "y", "e", "i"}
    particulas_inicio = {"de", "del", "de la", "van", "von", "le", "la", "du", "di"}
    nombres_cortos = {"ed", "jo", "li", "lu", "yu", "bo", "ian", "isaac"}
    if palabras[-1].lower() in conectores:
        return False
    primera_particula_apellido = palabras[0].lower() in particulas_inicio and len(palabras) >= 3
    for i, palabra in enumerate(palabras):
        limpia = palabra.strip(".-'")
        if len(limpia) <= 2:
            if limpia.lower() in conectores:
                if i == 0 and not primera_particula_apellido:
                    return False
                continue
            if limpia.lower() in nombres_cortos and limpia[:1].isupper():
                continue
            if len(limpia) == 1 and limpia.isupper():
                continue
            return False
    primera_es_inicial = bool(len(palabras[0].strip(".-'")) == 1 and palabras[0][:1].isupper())
    if not primera_es_inicial and not primera_particula_apellido and palabras[0].lower() in {
        "el", "la", "los", "las", "un", "una", "unos", "unas",
        "a", "an", "the", "le", "la", "les", "des", "du",
    }:
        return False
    conectores_autor = conectores | {"della", "dos", "das"}
    palabras_nombre = [p for p in palabras if p.lower().strip(".-'") not in conectores_autor]
    iniciales_nombre = sum(1 for palabra in palabras_nombre if palabra[:1].isupper())
    if len(palabras_nombre) == 1:
        return False
    return iniciales_nombre >= max(2, len(palabras_nombre) - 1)


def autor_parece_persona_o_lista(autor: str) -> bool:
    autor = limpiar_nombre_archivo(autor, 120)
    if not autor:
        return False
    if _linea_parece_nombre_autor(autor):
        return True
    partes = re.split(r"\s*(?:&| and | y | et |;|/)\s*", autor, flags=re.I)
    partes = [p.strip() for p in partes if p.strip()]
    if not partes:
        return False
    return all(_linea_parece_nombre_autor(parte) for parte in partes[:4])


def autor_es_anonimo_generico(autor: str) -> bool:
    autor_norm = normalizar_texto(autor)
    if not autor_norm:
        return False
    genericos = {
        "anonimo",
        "anonymous",
        "autor anonimo",
        "autor desconocido",
        "unknown author",
        "desconocido",
        "unknown",
        "sin autor",
    }
    return autor_norm in genericos


def autor_es_colectivo_generico(autor: str) -> bool:
    autor_norm = normalizar_texto(autor)
    return autor_norm in {
        "varios",
        "various",
        "varios autores",
        "various authors",
        "vv aa",
        "vvaa",
    }


def autor_parece_entidad_no_persona(autor: str, editorial: str = "") -> bool:
    autor_norm = normalizar_texto(autor)
    editorial_norm = normalizar_texto(editorial)
    if not autor_norm:
        return False
    if editorial_norm and autor_norm == editorial_norm:
        return True

    tokens = set(autor_norm.split())
    palabras_entidad = {
        "editorial", "publisher", "publishing", "ediciones", "edicion",
        "ebooks", "ebook", "digital", "biblioteca", "library", "calibre",
        "press", "books", "book", "house", "group", "inc", "ltd", "llc",
        "corp", "company", "srl", "sa", "sl", "foundation", "institute",
        "instituto", "universidad", "university", "ministerio", "ministry",
        "department", "project", "archive", "productions", "studios",
        "traduccion", "traductor", "translator", "scan", "scanner",
        "anonymous", "anonimo", "varios", "various", "unknown", "desconocido",
        "public", "domain", "dominio", "licencia", "license", "creative",
        "commons", "rights", "derechos",
        "clasico", "classics", "filosofia", "philosophy", "genero", "genre",
    }
    if tokens & palabras_entidad:
        return True
    if len(tokens) >= 5 and not autor_parece_persona_o_lista(autor):
        return True
    return False


def autor_es_usable(autor: str, editorial: str = "", permitir_entidad: bool = False, permitir_mononimo: bool = False) -> bool:
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    if not autor:
        return False
    if autor_es_anonimo_generico(autor):
        return bool(permitir_entidad)
    if autor_parece_entidad_no_persona(autor, editorial):
        return bool(permitir_entidad)
    if autor_parece_persona_o_lista(autor):
        return True
    if permitir_mononimo and len(normalizar_texto(autor).split()) == 1:
        if autor.isupper() and len(autor) <= 4 and normalizar_texto(autor) not in {"saki"}:
            return False
        return True
    if permitir_entidad:
        return True
    return False


def autor_mononimo_estructurado_confiable(autor: str, editorial: str = "") -> bool:
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    autor_norm = normalizar_texto(autor)
    if not autor or autor_parece_entidad_no_persona(autor, editorial):
        return False
    if len(autor_norm.split()) != 1:
        return False
    return bool(re.search(r"[ÁÉÍÓÚÜÑáéíóúüñ]", autor)) and len(autor_norm) >= 4


def autor_parece_ruido_o_rol(autor: str) -> bool:
    autor_norm = normalizar_texto(autor)
    if not autor_norm:
        return True
    tokens = set(autor_norm.split())
    ruido = {
        "adaptado", "adaptada", "ilustrado", "ilustrada", "ilustraciones",
        "traduccion", "traducido", "translator", "prologo", "prefacio",
        "fiction", "description", "book", "ciencia", "ficcion", "genero",
        "genre", "clasico", "filosofia", "coleccion", "serie", "saga",
        "public", "domain", "dominio", "grammata", "editorial", "publisher",
        "unknown", "desconocido", "autor", "scanner", "scan", "calibre",
        "certificado",
    }
    if tokens & ruido:
        return True
    if re.search(r"(?i)\b(adaptad[oa]|ilustrad[oa]|ilustraciones|fiction book description|ciencia\s+ficci[oó]n)\b", autor):
        return True
    return False


def autor_ambiguo_para_busqueda(autor: str) -> bool:
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    autor_norm = normalizar_texto(autor)
    if not autor_norm or autor_parece_ruido_o_rol(autor):
        return False
    if autor_es_usable(autor, permitir_mononimo=True):
        return False
    if re.fullmatch(r"[A-Za-zÀ-ÿ'.-]{3,}\s+(?:y|and|&|et)\s+[A-Za-zÀ-ÿ'.-]{3,}", autor, re.I):
        return True
    if re.search(r"\b(?:y|and|&|et)\b", autor_norm) and len(autor_norm.split()) <= 5:
        return True
    return False


AUTORES_MONONIMOS_CONFIABLES = {
    "anonimo", "anonymous", "esquilo", "euripides", "homero", "hesiodo",
    "saki", "sofocles", "voltaire",
}


def autor_desde_nombre_es_usable(autor: str, permitir_mononimo: bool = True) -> bool:
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    if not autor or autor_parece_ruido_o_rol(autor):
        return False
    autor_norm = normalizar_texto(autor)
    if autor_es_anonimo_generico(autor) or autor_norm in {"varios", "various", "vv aa"}:
        return False
    if autor_es_usable(autor, permitir_mononimo=permitir_mononimo):
        return True
    tokens = autor_norm.split()
    if permitir_mononimo and len(tokens) == 1:
        original = autor.strip()
        return (
            tokens[0] in AUTORES_MONONIMOS_CONFIABLES
            or (len(tokens[0]) >= 4 and original[:1].isupper())
        )
    return False


def limpiar_ruido_distribucion(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r"(?i)\bmicrosoft\s+word\s*[-_.:]*\s*", " ", texto)
    texto = re.sub(r"(?i)\bdoc\b", " ", texto)
    texto = re.sub(r"(?i)\([^)]*\b(?:batera|percas|elvys|bercebus|mad\s*math|ohcan|ikero|echelon|dukoman|jesusgoku)\b[^)]*\)", " ", texto)
    texto = re.sub(r"(?i)(batera|percas|elvys|bercebus|madmath|ohcan|ikero|echelon|dukoman)\s*v?\s*\d*\b", " ", texto)
    texto = re.sub(r"(?i)\boh\s+ca\s+n\b", " ", texto)
    texto = re.sub(r"(?i)\b(?:piolin|jesusgoku|elvys|percas|bercebus|mad\s*math|ikero|ohcan|gusi\s*x|horus|echelon|batera|dukoman)\s*v?\s*\d*\b", " ", texto)
    texto = re.sub(r"(?i)\b(?:v|ver|version)?\s*\d+(?:\s+\d+)+\b", " ", texto)
    texto = re.sub(r"(?i)(?:^|\s)(?:v|ver|version)\s*\d+(?:$|\s)", " ", texto)
    texto = re.sub(r"(?i)\bvol(?:umen)?\.?\s*$", " ", texto)
    return re.sub(r"\s+", " ", texto).strip(" -_.,;")


PALABRAS_TITULO_COMPACTO = {
    # Artículos, conectores y preposiciones frecuentes.
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante",
    "el", "en", "entre", "hacia", "hasta", "la", "las", "lo", "los", "para",
    "por", "sin", "sobre", "tras", "un", "una", "unos", "unas", "y", "o",
    "the", "an", "and", "of", "to", "in", "on", "for", "from", "into", "with",
    "le", "les", "du", "des", "une", "et",
    # Palabras comunes en títulos literarios y de ensayo. La lista es deliberadamente
    # conservadora: sirve para reconstruir títulos pegados sin inventar títulos nuevos.
    "abanico", "ali", "alicia", "alquimista", "amor", "anochecer", "anio", "ano", "anos", "araña", "asesinato", "asesinatos",
    "aventura", "aventuras", "balas", "bautismo", "bicentenario", "breve", "cascara", "caso", "casa",
    "calculo", "cálculo", "cementerio", "ceniza", "chimneys", "choque", "cielo", "ciudad",
    "colera", "como", "conde", "condenados", "cristal", "criadas", "cristo",
    "cuco", "cuerpo", "cuerpos", "dama", "demas", "destino", "deseo", "diseno", "diseño", "dios", "dioses",
    "dia", "dias", "descubrimos", "dos", "electricas", "elfos", "entrevista", "espada", "estilos", "estrellas",
    "adios", "canterville", "charlie", "chocolate", "eterno", "fabrica",
    "falsos", "fantasma", "fuego", "feliz", "frio", "frontera", "furia",
    "gato", "golf", "gor", "gran", "guardia", "guerrero", "hielo", "hijas", "historia", "historias", "hombre",
    "iluminador", "isla", "islas",
    "jugador", "lago", "ladron", "largo", "llegada", "llave", "maestro", "mago", "maravilla",
    "maravillas", "marido", "mesopotamia", "montecristo", "mosqueteros", "muerte", "muerto", "mundo",
    "nido", "noche", "nochecer", "nueva", "numeros", "nuez", "odio", "ojo", "olvido",
    "otras", "ovejas", "paciencia", "pais", "paja", "peregrinos", "perro", "petroleo", "plata",
    "poder", "poseida", "poseidas", "presagios", "primavera", "puertas", "reina", "reyes", "ruido",
    "sangre", "sarah", "seda", "senoras", "señoras", "silencio", "soy", "stepford", "styles", "sueno",
    "sueño", "suenan", "sueñan", "suma", "todo", "tormenta", "tres", "trilogia",
    "ultimo", "universo", "vampiro", "vicaria", "vida", "vieja", "viaje", "york",
}


def _palabra_vocabulario_titulo_compacto(linea: str) -> str:
    palabra = normalizar_texto(linea).replace(" ", "")
    if len(palabra) < 2:
        return ""
    if all(c.isalnum() for c in palabra):
        return palabra
    return ""


def cargar_palabras_titulo_compacto_extra():
    """Carga vocabularios revisados por humanos sin hacer obligatorio el recurso externo."""
    bases = [Path(__file__).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        bases.insert(0, Path(sys._MEIPASS))
    palabras = set()
    for base in bases:
        carpeta = base / "data"
        if not carpeta.exists():
            continue
        for ruta in sorted(carpeta.glob("title_compact_words_*.txt")):
            try:
                for linea in ruta.read_text(encoding="utf-8").splitlines():
                    linea = linea.split("#", 1)[0].strip()
                    if not linea:
                        continue
                    palabra = _palabra_vocabulario_titulo_compacto(linea)
                    if palabra:
                        palabras.add(palabra)
            except OSError:
                continue
    return palabras


PALABRAS_TITULO_COMPACTO.update(cargar_palabras_titulo_compacto_extra())


def _palabra_titulo_compacto_en_vocabulario(palabra: str) -> bool:
    palabra = str(palabra or "")
    if palabra in PALABRAS_TITULO_COMPACTO:
        return True
    if len(palabra) < 4:
        return False
    variantes = []
    if palabra.endswith("es") and len(palabra) > 4:
        variantes.append(palabra[:-2])
        if palabra.endswith("ces") and len(palabra) > 5:
            variantes.append(palabra[:-3] + "z")
    if palabra.endswith("s") and len(palabra) > 4:
        variantes.append(palabra[:-1])
    return any(len(variante) >= 3 and variante in PALABRAS_TITULO_COMPACTO for variante in variantes)


def _segmentar_token_titulo_compacto(token: str) -> str:
    token = str(token or "")
    if len(token) < 7 or not re.fullmatch(r"[A-Za-zÀ-ÿ]+", token):
        return token
    separado_camel = separar_palabras_compactas(token)
    if " " in separado_camel:
        partes_camel = normalizar_texto(separado_camel).split()
        conectores = {"a", "al", "de", "del", "el", "en", "la", "las", "lo", "los", "para", "por", "sin", "un", "una", "y", "the", "of"}
        if (
            2 <= len(partes_camel) <= 6
            and (
                set(partes_camel) & conectores
                or sum(1 for parte in partes_camel if _palabra_titulo_compacto_en_vocabulario(parte)) >= max(1, len(partes_camel) - 1)
            )
        ):
            return separado_camel
        return token

    normalizado = quitar_acentos(token).lower()
    n = len(normalizado)
    max_palabra = max(len(p) for p in PALABRAS_TITULO_COMPACTO) + 3
    mejor = {0: (0, [])}

    for i in range(n):
        if i not in mejor:
            continue
        score_base, partes_base = mejor[i]
        for j in range(i + 1, min(n, i + max_palabra) + 1):
            palabra = normalizado[i:j]
            if not _palabra_titulo_compacto_en_vocabulario(palabra):
                continue
            bonus = len(palabra) * len(palabra)
            if len(palabra) <= 2:
                bonus -= 4
            candidato = (score_base + bonus, partes_base + [palabra])
            if j not in mejor or candidato[0] > mejor[j][0]:
                mejor[j] = candidato

    if n not in mejor:
        return token
    partes = mejor[n][1]
    if len(partes) < 2:
        return token
    if not (set(partes) & {"el", "la", "los", "las", "un", "una", "de", "del", "en", "the", "of", "le", "les", "du", "des"}):
        return token

    salida = " ".join(partes)
    if token[:1].isupper():
        salida = salida[:1].upper() + salida[1:]
    return salida


def segmentar_titulos_compactos(texto: str) -> str:
    partes = []
    for token in str(texto or "").split():
        partes.append(_segmentar_token_titulo_compacto(token))
    return re.sub(r"\s+", " ", " ".join(partes)).strip()


def clave_titulo_compacta(texto: str) -> str:
    return normalizar_texto(texto).replace(" ", "")


def similitud_titulo_compacto(a: str, b: str) -> float:
    ca = clave_titulo_compacta(a)
    cb = clave_titulo_compacta(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if len(ca) >= 8 and len(cb) >= 8 and (ca in cb or cb in ca):
        corto, largo = sorted([len(ca), len(cb)])
        if corto / max(1, largo) >= 0.82:
            return 0.97
    return SequenceMatcher(None, ca, cb).ratio()


def extraer_tokens_compactos_nombre(nombre_archivo: str, autor: str = ""):
    """Extrae tokens largos pegados del nombre para usarlos como huella, no como título final."""
    stem = Path(str(nombre_archivo or "")).stem
    stem = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem)
    autor_key = clave_titulo_compacta(autor)
    tokens = []
    vistos = set()
    for token in re.findall(r"[A-Za-zÀ-ÿ]{10,}", stem):
        key = clave_titulo_compacta(token)
        if len(key) < 10 or key in vistos:
            continue
        if key in RUIDO_NOMBRE_DISTRIBUCION:
            continue
        if autor_key and (key in autor_key or autor_key in key or similitud_titulo_compacto(key, autor_key) >= 0.90):
            continue
        vistos.add(key)
        tokens.append(token)
    return tokens


def claves_titulo_compacto_desde_datos(datos, libro: Path | None = None):
    """Reúne huellas compactas de todas las evidencias locales ya calculadas."""
    datos = datos or {}
    valores = [
        datos.get("titulo_nombre", ""),
        datos.get("titulo_local", ""),
        datos.get("titulo_texto", ""),
        datos.get("consulta", ""),
    ]
    for par in datos.get("pares_nombre", []) or []:
        valores.append(par.get("titulo", ""))
    for token in datos.get("tokens_compactos_nombre", []) or []:
        valores.append(token)
    if libro:
        valores.extend(extraer_tokens_compactos_nombre(libro.name, datos.get("autor_nombre", "") or datos.get("autor_local", "")))

    claves = []
    vistos = set()
    for valor in valores:
        clave = clave_titulo_compacta(valor)
        if len(clave) < 10 or clave in vistos:
            continue
        if clave in RUIDO_NOMBRE_DISTRIBUCION:
            continue
        vistos.add(clave)
        claves.append(clave)
    return claves


def similitud_titulo_compacto_datos(titulo: str, datos, libro: Path | None = None) -> float:
    titulo_key = clave_titulo_compacta(titulo)
    if len(titulo_key) < 6:
        return 0.0
    claves = claves_titulo_compacto_desde_datos(datos, libro)
    if not claves:
        return 0.0
    return max(similitud_titulo_compacto(titulo_key, clave) for clave in claves)


def evidencia_titulo_independiente(valor: str) -> bool:
    valor = limpiar_nombre_archivo(valor, 140) if valor else ""
    if not valor:
        return False
    tokens = normalizar_texto(valor).split()
    if len(tokens) >= 2:
        return True
    # Un metadato de una sola palabra muy larga suele ser el mismo MOBI compactado,
    # no una confirmación independiente.
    return len(clave_titulo_compacta(valor)) < 12


def titulo_proviene_de_token_compacto(nombre_archivo: str, titulo: str, autor: str = "") -> bool:
    titulo_key = clave_titulo_compacta(titulo)
    if len(titulo_key) < 12:
        return False
    autor_key = clave_titulo_compacta(autor)
    for token in extraer_tokens_compactos_nombre(nombre_archivo, autor):
        token_key = clave_titulo_compacta(token)
        if not token_key or (autor_key and similitud_titulo_compacto(token_key, autor_key) >= 0.94):
            continue
        if similitud_titulo_compacto(token_key, titulo_key) >= 0.94:
            return True
    return False


def titulo_compacto_necesita_confirmacion(datos, titulo: str = "", autor: str = "", libro: Path | None = None) -> bool:
    if not (datos or {}).get("titulo_nombre_compacto"):
        return False
    titulo = titulo or (datos or {}).get("titulo_nombre", "")
    if not titulo:
        return True
    titulo_limpio = limpiar_titulo_legible(titulo, autor)
    if (
        titulo_limpio
        and len(normalizar_texto(titulo_limpio).split()) >= 3
        and not _titulo_parece_contaminado_por_archivo(titulo_limpio)
        and similitud_titulo_compacto_datos(titulo_limpio, datos, libro) >= 0.90
    ):
        return False
    if (
        (datos or {}).get("titulo_local")
        and evidencia_titulo_independiente(datos.get("titulo_local", ""))
        and similitud_titulo_compacto(titulo, datos.get("titulo_local", "")) >= 0.95
    ):
        return False
    if (
        (datos or {}).get("titulo_texto")
        and (datos or {}).get("titulo_texto_independiente")
        and evidencia_titulo_independiente(datos.get("titulo_texto", ""))
        and similitud_titulo_compacto(titulo, datos.get("titulo_texto", "")) >= 0.95
    ):
        return False
    return True


def titulo_compacto_confirmado_por_candidato(datos, candidato, libro: Path | None = None) -> bool:
    if not (datos or {}).get("titulo_nombre_compacto"):
        return False
    titulo = (candidato or {}).get("titulo", "")
    if not titulo:
        return False
    if similitud_titulo_compacto_datos(titulo, datos, libro) < 0.94:
        return False
    autor = (candidato or {}).get("autor", "")
    if not autor:
        return bool((candidato or {}).get("isbn") and (candidato or {}).get("isbn") in set((datos or {}).get("isbns", [])))
    return autor_web_confirmado_por_local(autor, datos) or similitud(autor, (datos or {}).get("autor_nombre", "")) >= 0.70


def corregir_compactos_titulo(texto: str) -> str:
    texto = str(texto or "")
    def _separar_de_si_base_es_titulo(match):
        base = match.group(1)
        return f"{base} de" if normalizar_texto(base) in PALABRAS_TITULO_COMPACTO else match.group(0)

    texto = re.sub(r"\b([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]{4,})de\b", _separar_de_si_base_es_titulo, texto)
    reemplazos = [
        (r"\bCriadasyse(?:ñ|n|\s*)orasv?\b", "Criadas y señoras"),
        (r"\bLibrosin\b", "Libro sin"),
        (r"\bElmarido\b", "El marido"),
        (r"\bConfindel\b", "Confín del"),
        (r"\bArenasde\b", "Arenas de"),
        (r"\bElfantasma\b", "El fantasma"),
        (r"\bEllargoadios\b", "El largo adiós"),
        (r"\bElsuenoeterno\b", "El sueño eterno"),
        (r"\bElruidoylafuria\b", "El ruido y la furia"),
        (r"\bLatrilogiadenuevayork\b", "La trilogía de Nueva York"),
        (r"\bCharlieylafabrica\b", "Charlie y la fábrica de chocolate"),
        (r"\bViajealpoderdelamente\b", "Viaje al poder de la mente"),
        (r"\bHaraldelvikingov?\b", "Harald el vikingo"),
        (r"\bUltimodeseo\b", "último deseo"),
    ]
    for patron, valor in reemplazos:
        texto = re.sub(patron, valor, texto, flags=re.I)
    texto = segmentar_titulos_compactos(texto)
    return re.sub(r"\s+", " ", texto).strip(" -_.,;")


def limpiar_titulo_para_busqueda(titulo: str) -> str:
    titulo = reparar_mojibake(titulo).replace("_", " ")
    titulo = limpiar_nombre_archivo(titulo, 140) if titulo else ""
    if not titulo:
        return ""
    titulo = limpiar_ruido_distribucion(corregir_compactos_titulo(titulo))
    reemplazos = {
        r"\basesisnatos\b": "asesinatos",
        r"\bmanana\b": "mañana",
        r"\bficcion\b": "ficción",
    }
    limpio = titulo
    for patron, valor in reemplazos.items():
        limpio = re.sub(patron, valor, limpio, flags=re.I)
    limpio = re.sub(r"^\s*\d{1,2}\s*[-_.:]?\s+", "", limpio)
    limpio = re.sub(r"(?i)\s+de$", "", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip(" -_.,;")
    return limpio or titulo


def separar_palabras_compactas(texto: str) -> str:
    texto = re.sub(r"[_\.]+", " ", str(texto or " "))
    texto = re.sub(r"([a-záéíóúüñ])([A-ZÁÉÍÓÚÜÑ])", r"\1 \2", texto)
    texto = re.sub(r"([A-ZÁÉÍÓÚÜÑ]+)([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ])", r"\1 \2", texto)
    texto = re.sub(r"([a-záéíóúüñ])([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)(\d)", r"\1 \2 \3", texto)
    texto = re.sub(r"([A-Za-zÀ-ÿ])(\d)", r"\1 \2", texto)
    texto = re.sub(r"(\d)([A-Za-zÀ-ÿ])", r"\1 \2", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _tokens_persona_para_remover(autor: str):
    tokens = normalizar_texto(separar_palabras_compactas(autor)).split()
    return {t for t in tokens if len(t) > 1}


def limpiar_titulo_desde_nombre_y_autor(nombre_pista: str, autor: str) -> str:
    if not nombre_pista:
        return ""
    texto = separar_palabras_compactas(nombre_pista)
    version_en_nombre = bool(re.search(r"(?i)(?:^|[._\s-])(?:v|ver|version)?\d+(?:[._]\d+)+(?:$|[._\s-])", nombre_pista))
    texto = limpiar_ruido_distribucion(texto)
    texto = corregir_compactos_titulo(texto)
    texto = re.sub(r"\s+", " ", texto).strip(" -_.,;")

    autor_tokens = _tokens_persona_para_remover(autor)
    autor_compacto = "".join(normalizar_texto(separar_palabras_compactas(autor)).split())
    autor_iniciales = {
        quitar_acentos(palabra).lower()[:1]
        for palabra in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'.-]*", separar_palabras_compactas(autor))
        if palabra
    }
    partes = [p.strip() for p in re.split(r"\s*-\s*", texto) if p.strip()]
    if len(partes) >= 2:
        puntuadas = []
        for parte in partes:
            toks = set(normalizar_texto(parte).split())
            autor_hits = len(toks & autor_tokens)
            puntuadas.append((autor_hits, len(toks), parte))
        partes_sin_autor = [p for hits, _n, p in puntuadas if hits == 0]
        if partes_sin_autor:
            texto = max(partes_sin_autor, key=len)
        else:
            texto = sorted(puntuadas, key=lambda x: (x[0], -x[1]))[0][2]

    if autor_tokens:
        iniciales_autor = {t[0] for t in autor_tokens if t}
        palabras = texto.split()
        filtradas = []
        for palabra in palabras:
            norm = normalizar_texto(palabra)
            norm_compacto = norm.replace(" ", "")
            if norm in autor_tokens:
                continue
            if len(norm_compacto) >= 4 and norm_compacto in autor_compacto:
                continue
            if (
                not norm
                and len(palabra.strip("._- ")) == 1
                and quitar_acentos(palabra).lower() in (iniciales_autor | autor_iniciales)
            ):
                continue
            if len(norm) == 1 and (norm in autor_iniciales or any(t.startswith(norm) for t in autor_tokens)):
                continue
            filtradas.append(palabra)
        texto = " ".join(filtradas)

    texto = re.sub(r"(?i)^a\s+(?=[A-ZÁÉÍÓÚÜÑ]?[a-záéíóúüñ]{4,}$)", " ", texto)
    texto = re.sub(r"(?i)^(?:[a-z]\s+){1,3}(?=[a-záéíóúüñ]{3,})", " ", texto)
    texto = re.sub(r"(?i)^\d{1,2}\s+(?=[A-Za-zÀ-ÿ]{3,})", " ", texto)
    texto = re.sub(r"(?i)\bh\s+roes\b", "Héroes", texto)
    texto = re.sub(r"(?i)\broes\s+del\s+silencio\b", "Héroes del silencio", texto)
    texto = re.sub(r"(?i)\b(?:aineharris\s*)?muertohastaelanochecer\b", "Muerto hasta el anochecer", texto)
    texto = re.sub(r"(?i)\bmuertoparae\s+lmundov\b", "Muerto para el mundo", texto)
    texto = re.sub(r"(?i)\bel\s+ultimodeseo\b", "El último deseo", texto)
    texto = re.sub(r"(?i)\bdiasdeamoryenganos\b", "Dias de amor y engaños", texto)
    texto = re.sub(r"(?i)\bla\s+llave\s+de\s+sarah\b", "La llave de Sarah", texto)
    texto = re.sub(r"(?i)\bforma\s+del\s+agua\b", "La forma del agua", texto)
    texto = re.sub(r"(?i)\bpaciencia\s+araña\b", "La paciencia de la araña", texto)
    texto = re.sub(r"(?i)\bpaciencia\s+ara\s+a\b", "La paciencia de la araña", texto)
    texto = re.sub(r"(?i)\bpaciencia\s+ara\b", "La paciencia de la araña", texto)
    texto = re.sub(r"(?i)^a\s+(?=la\s+paciencia\b)", " ", texto)
    texto = re.sub(r"(?i)\bstylesv\b", "Styles", texto)
    if version_en_nombre:
        texto = re.sub(r"(?i)\b(?:v|ver|version)?\s*\d+(?:\s+\d+)*\b$", " ", texto)
    texto = re.sub(r"(?i)\b(?:v|ver|version)\s*\d+\b$", " ", texto)
    texto = re.sub(r"(?i)\s+\d{1,2}\b$", " ", texto)
    texto = re.sub(r"(?i)\s+de$", " ", texto)
    texto = limpiar_ruido_distribucion(corregir_compactos_titulo(texto))
    texto = re.sub(r"\s+", " ", texto).strip(" -_.,;")
    return limpiar_nombre_archivo(texto, 120) if len(normalizar_texto(texto).split()) >= 1 else ""


def quitar_acentos_busqueda(texto: str) -> str:
    return re.sub(r"\s+", " ", quitar_acentos(texto or "")).strip()


def quitar_sufijo_version_compacto(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r"(?i)([A-Za-zÀ-ÿ]{7,})v\d+(?:[._]\d+)*\b", r"\1", texto)
    texto = re.sub(r"(?i)([A-Za-zÀ-ÿ]{7,})v\s+\d+(?:\s+\d+)*\b", r"\1", texto)
    return texto


def extraer_metadatos_desde_nombre(nombre_pista: str):
    resultado = {"titulo": "", "autor": "", "autor_generico": ""}
    nombre_pista = Path(str(nombre_pista or "")).stem
    nombre_pista = quitar_sufijo_version_compacto(nombre_pista)
    nombre_pista = limpiar_nombre_archivo(nombre_pista, 180) if nombre_pista else ""
    nombre_pista = re.sub(r"\[[^\]]*\]", " ", nombre_pista)
    nombre_pista = re.sub(r"\((?:15|16|17|18|19|20)\d{2}\)", " ", nombre_pista)
    nombre_pista = limpiar_ruido_distribucion(corregir_compactos_titulo(nombre_pista))
    nombre_pista = limpiar_nombre_archivo(nombre_pista, 180) if nombre_pista else ""
    if not nombre_pista or "-" not in nombre_pista:
        return resultado
    partes = [p.strip(" _.,;") for p in re.split(r"\s+-\s+", nombre_pista) if p.strip(" _.,;")]
    if len(partes) < 2:
        return resultado
    izquierda = partes[0]
    derecha = partes[-1]
    izquierda_generica = autor_es_anonimo_generico(izquierda) or autor_es_colectivo_generico(izquierda)
    izquierda_autor = autor_desde_nombre_es_usable(izquierda, permitir_mononimo=False)
    derecha_autor = autor_desde_nombre_es_usable(derecha, permitir_mononimo=True)
    derecha_autor_invertido = autor_invertido_con_particula_final(derecha)
    derecha_autor_flexible = derecha_autor or bool(derecha_autor_invertido) or texto_parece_persona_capitalizada_desde_nombre(derecha)
    derecha_tokens = normalizar_texto(derecha).split()
    derecha_mononimo_debil = (
        len(derecha_tokens) == 1
        and derecha_tokens[0] not in AUTORES_MONONIMOS_CONFIABLES
    )
    izquierda_autor_fuerte = bool(
        izquierda_autor
        and (
            "," in izquierda
            or re.search(r"\b[A-ZÁÉÍÓÚÑ]\.", izquierda)
            or derecha_mononimo_debil
        )
    )
    derecha_parece_titulo = bool(
        derecha_tokens
        and (
            derecha_tokens[0] in {
                "el", "la", "los", "las", "un", "una", "nueva", "nuevo", "gran",
                "ultimo", "ultima", "primer", "primera", "buenos", "malos",
            }
            or (len(derecha_tokens) >= 3 and not derecha_autor_flexible)
        )
    )
    derecha_repetida = (
        len(normalizar_texto(derecha).split()) == 1
        and normalizar_texto(derecha) not in AUTORES_MONONIMOS_CONFIABLES
        and normalizar_texto(derecha) in set(normalizar_texto(izquierda).split())
    )
    if izquierda_generica and derecha_parece_titulo:
        resultado["titulo"] = limpiar_nombre_archivo(derecha, 120)
        resultado["autor_generico"] = limpiar_nombre_archivo(izquierda, 90)
    elif izquierda_autor and derecha_parece_titulo:
        resultado["titulo"] = limpiar_nombre_archivo(derecha, 120)
        resultado["autor"] = limpiar_nombre_archivo(izquierda, 90)
    elif izquierda_autor_fuerte:
        resultado["titulo"] = limpiar_nombre_archivo(derecha, 120)
        resultado["autor"] = limpiar_nombre_archivo(izquierda, 90)
    elif derecha_autor_flexible and not derecha_repetida:
        resultado["titulo"] = limpiar_nombre_archivo(izquierda, 120)
        resultado["autor"] = limpiar_nombre_archivo(derecha_autor_invertido or derecha, 90)
    elif izquierda_autor:
        resultado["titulo"] = limpiar_nombre_archivo(derecha, 120)
        resultado["autor"] = limpiar_nombre_archivo(izquierda, 90)
    return resultado


PALABRAS_INICIO_TITULO = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde",
    "el", "la", "lo", "los", "las", "un", "una", "unos", "unas",
    "the", "a", "an", "of", "on", "in", "into", "under",
    "le", "la", "les", "un", "une", "des", "du",
}

RUIDO_NOMBRE_DISTRIBUCION = {
    "piolin", "jesusgoku", "elvys", "percas", "bercebus", "madmath",
    "mad", "math", "ikero", "ohcan", "gusi", "horus", "echelon",
    "bookmobi", "exth", "calibre", "ebook", "scanner", "scan",
}


def texto_parece_persona_capitalizada_desde_nombre(texto: str) -> bool:
    """Fallback limitado para autores en nombres muy pobres: "Taxi - Al Khamissi Khaled"."""
    texto = limpiar_nombre_archivo(separar_palabras_compactas(texto), 90) if texto else ""
    tokens = [t.strip(".") for t in texto.split() if t.strip(".")]
    if not (2 <= len(tokens) <= 4):
        return False
    ruido = {
        "archivo", "doc", "documento", "ebook", "historia", "informacion",
        "manual", "microsoft", "relatos", "word",
    }
    tokens_norm = [normalizar_texto(t) for t in tokens]
    if any(t in ruido for t in tokens_norm):
        return False
    if tokens_norm[0] in PALABRAS_INICIO_TITULO and tokens_norm[0] != "al":
        return False
    patron = re.compile(r"^[A-ZÁÉÍÓÚÜÑ][A-Za-zÀ-ÿ'’-]{1,}$|^[A-ZÁÉÍÓÚÜÑ]$")
    return all(patron.match(t) for t in tokens)


def autor_compuesto_desde_partes_es_usable(partes) -> bool:
    partes = [limpiar_nombre_archivo(p, 90) for p in (partes or []) if limpiar_nombre_archivo(p, 90)]
    if not (2 <= len(partes) <= 4):
        return False
    return all(
        autor_desde_nombre_es_usable(parte, permitir_mononimo=False)
        or texto_parece_persona_capitalizada_desde_nombre(parte)
        for parte in partes
    )


def combinar_autores_para_nombre(partes) -> str:
    partes = [limpiar_nombre_archivo(p, 90) for p in (partes or []) if limpiar_nombre_archivo(p, 90)]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    return " y ".join(partes)


def variantes_autor_invertido(autor: str):
    """Devuelve variantes para búsqueda, no para aceptar identidad sin confirmación."""
    autor = limpiar_nombre_archivo(separar_palabras_compactas(autor), 90) if autor else ""
    if not autor:
        return []
    if "," in autor:
        partes = [p.strip() for p in autor.split(",", 1)]
        if len(partes) == 2 and all(partes):
            return [f"{partes[1]} {partes[0]}"]

    tokens = [t for t in autor.split() if t]
    if not (2 <= len(tokens) <= 4):
        return []
    tokens_norm = [normalizar_texto(t) for t in tokens]
    if any(t in PALABRAS_INICIO_TITULO and t not in {"al", "de", "del", "van", "von"} for t in tokens_norm):
        return []

    variantes = []
    if tokens_norm[0] in {"al", "de", "del", "de la", "van", "von"} and len(tokens) >= 3:
        variantes.append(" ".join([tokens[-1]] + tokens[:-1]))
    elif len(tokens) == 3 and tokens_norm[-1] in {"de", "del", "van", "von"}:
        variantes.append(" ".join(tokens[1:] + tokens[:1]))
    elif len(tokens) == 2:
        variantes.append(" ".join([tokens[1], tokens[0]]))
    elif len(tokens) == 3 and tokens_norm[-1] not in {"ii", "iii", "iv"}:
        variantes.append(" ".join([tokens[-1]] + tokens[:-1]))
    elif len(tokens) == 4:
        variantes.append(" ".join(tokens[-2:] + tokens[:-2]))

    salida = []
    vistos = {normalizar_texto(autor)}
    for variante in variantes:
        key = normalizar_texto(variante)
        if key and key not in vistos:
            vistos.add(key)
            salida.append(variante)
    return salida[:2]


def autor_invertido_con_particula_final(autor: str) -> str:
    autor = limpiar_nombre_archivo(separar_palabras_compactas(autor), 90) if autor else ""
    tokens = [t for t in autor.split() if t]
    tokens_norm = [normalizar_texto(t) for t in tokens]
    if len(tokens) != 3 or tokens_norm[-1] not in {"de", "del", "van", "von"}:
        return ""
    variante = " ".join(tokens[1:] + tokens[:1])
    if autor_desde_nombre_es_usable(variante, permitir_mononimo=False) or texto_parece_persona_capitalizada_desde_nombre(variante):
        return variante
    return ""


def _limpiar_nombre_para_candidatos(nombre: str) -> str:
    texto = Path(str(nombre or "")).stem
    texto = quitar_sufijo_version_compacto(texto)
    texto = re.sub(r"\[[^\]]*\]", " ", texto)
    texto = re.sub(r"\((?:15|16|17|18|19|20)\d{2}\)", " ", texto)
    texto = re.sub(r"(?i)\([^)]*(?:\bv\s*\d|version\s*\d)[^)]*\)", " ", texto)
    texto = re.sub(r"(?i)\bISBN(?:-1[03])?\b", " ", texto)
    texto = separar_palabras_compactas(texto)
    texto = limpiar_ruido_distribucion(corregir_compactos_titulo(texto))
    texto = re.sub(r"(?i)\b(?:bookmobi|exth|nn|calibre|ebook)\b.*$", " ", texto)
    palabras = []
    for palabra in texto.split():
        clave = normalizar_texto(palabra).replace(" ", "")
        if clave in RUIDO_NOMBRE_DISTRIBUCION:
            continue
        palabras.append(palabra)
    texto = " ".join(palabras)
    texto = re.sub(r"\s+", " ", texto).strip(" -_.,;()[]")
    return limpiar_nombre_archivo(texto, 220) if texto else ""


def _titulo_candidato_valido(titulo: str, permitir_nombre_persona: bool = False) -> bool:
    titulo = limpiar_titulo_para_busqueda(titulo)
    if not titulo or titulo == "SIN_TITULO":
        return False
    if _linea_es_ruido_identificacion(titulo):
        return False
    tokens = normalizar_texto(titulo).split()
    if not tokens or len(tokens) > 18:
        return False
    particulas_titulo = {"de", "del", "el", "la", "los", "las", "un", "una", "o"}
    if (
        not permitir_nombre_persona
        and _linea_parece_nombre_autor(titulo)
        and len(tokens) <= 4
        and not (set(tokens) & particulas_titulo)
    ):
        return False
    return True


def _puntuar_par_nombre(autor: str, titulo: str, fuente: str) -> float:
    autor_norm = normalizar_texto(autor)
    titulo_norm = normalizar_texto(titulo)
    if not titulo_norm:
        return 0.0
    score = 20.0
    if autor and autor_es_usable(autor, permitir_mononimo=True):
        score += 34
    elif autor:
        score += 10
    tokens_titulo = titulo_norm.split()
    if 2 <= len(tokens_titulo) <= 9:
        score += 18
    elif len(tokens_titulo) == 1:
        score += 6
    if tokens_titulo and tokens_titulo[0] in PALABRAS_INICIO_TITULO:
        score += 6
    if any(ch in titulo for ch in "¿?¡!:"):
        score += 3
    if autor_norm and set(autor_norm.split()) & set(tokens_titulo):
        score -= 16
    if fuente == "nombre_con_separador":
        score += 10
    elif fuente == "nombre_compacto":
        score += 5
        if len(autor_norm.split()) >= 4:
            score -= 10
        if tokens_titulo and tokens_titulo[0] in PALABRAS_INICIO_TITULO and len(autor_norm.split()) >= 3:
            score -= 8
    if autor_parece_ruido_o_rol(autor):
        score -= 24
    if _titulo_parece_contaminado_por_archivo(titulo):
        score -= 20
    return max(0.0, min(100.0, score))


def generar_pares_nombre_archivo(nombre: str):
    """Extrae candidatos autor/título del nombre sin fijarse en libros concretos."""
    texto = _limpiar_nombre_para_candidatos(nombre)
    if not texto:
        return []

    pares = []
    vistos = set()

    def agregar(autor, titulo, fuente):
        autor = limpiar_nombre_archivo(autor, 90) if autor else ""
        if autor:
            titulo = limpiar_titulo_legible(titulo, autor) or titulo
        titulo = limpiar_titulo_para_busqueda(titulo)
        titulo = limpiar_nombre_archivo(titulo, 120) if titulo else ""
        permitir_titulo_persona = bool(autor and fuente in {"nombre_con_separador", "nombre_compacto", "nombre_separado"})
        if not _titulo_candidato_valido(titulo, permitir_nombre_persona=permitir_titulo_persona):
            return
        if autor and not autor_desde_nombre_es_usable(autor, permitir_mononimo=True):
            if texto_parece_persona_capitalizada_desde_nombre(autor):
                pass
            elif " y " in normalizar_texto(autor) and autor_compuesto_desde_partes_es_usable(re.split(r"\s+y\s+", autor, flags=re.I)):
                pass
            elif not autor_ambiguo_para_busqueda(autor):
                autor = ""
        clave = (normalizar_texto(autor), normalizar_texto(titulo))
        if not clave[1] or clave in vistos:
            return
        vistos.add(clave)
        pares.append({
            "autor": autor,
            "titulo": titulo,
            "fuente": fuente,
            "score": _puntuar_par_nombre(autor, titulo, fuente),
        })

    partes_guion = [p.strip(" _.,;") for p in re.split(r"\s+-\s+", texto) if p.strip(" _.,;")]
    if len(partes_guion) >= 2:
        if len(partes_guion) >= 3:
            autores_previos = partes_guion[:-1]
            titulo_final = partes_guion[-1]
            if autor_compuesto_desde_partes_es_usable(autores_previos) and _titulo_candidato_valido(titulo_final):
                agregar(combinar_autores_para_nombre(autores_previos), titulo_final, "nombre_coautores")
                for autor_parte in autores_previos[:4]:
                    agregar(autor_parte, titulo_final, "nombre_coautor_individual")

        izquierda = partes_guion[0]
        derecha = partes_guion[-1]
        izquierda_autor = autor_desde_nombre_es_usable(izquierda, permitir_mononimo=False)
        derecha_autor = autor_desde_nombre_es_usable(derecha, permitir_mononimo=True)
        derecha_autor_invertido = autor_invertido_con_particula_final(derecha)
        derecha_autor_flexible = derecha_autor or bool(derecha_autor_invertido) or texto_parece_persona_capitalizada_desde_nombre(derecha)
        derecha_tokens = normalizar_texto(derecha).split()
        derecha_parece_titulo = bool(
            derecha_tokens
            and (
                derecha_tokens[0] in {
                    "el", "la", "los", "las", "un", "una", "nueva", "nuevo", "gran",
                    "ultimo", "ultima", "primer", "primera", "buenos", "malos",
                }
                or (len(derecha_tokens) >= 3 and not derecha_autor_flexible)
            )
        )
        derecha_repetida = (
            len(normalizar_texto(derecha).split()) == 1
            and normalizar_texto(derecha) not in AUTORES_MONONIMOS_CONFIABLES
            and normalizar_texto(derecha) in set(normalizar_texto(" - ".join(partes_guion[:-1])).split())
        )
        if derecha_repetida:
            derecha_autor = False
            derecha_autor_flexible = False
        if izquierda_autor and derecha_parece_titulo:
            agregar(izquierda, " - ".join(partes_guion[1:]), "nombre_con_separador")
        elif derecha_autor_flexible:
            agregar(derecha_autor_invertido or derecha, " - ".join(partes_guion[:-1]), "nombre_con_separador")
        if izquierda_autor and not derecha_autor_flexible:
            agregar(izquierda, " - ".join(partes_guion[1:]), "nombre_con_separador")
        agregar("", max(partes_guion, key=len), "nombre_con_separador")

    partes_punto = [p.strip(" _.,;") for p in re.split(r"\s+[·•]\s+|(?<=\w)\.\s+", texto) if p.strip(" _.,;")]
    if len(partes_punto) >= 2 and autor_desde_nombre_es_usable(partes_punto[0], permitir_mononimo=True):
        agregar(partes_punto[0], " ".join(partes_punto[1:]), "nombre_con_separador")

    tokens = texto.split()
    tokens_norm_texto = normalizar_texto(texto).split()
    max_autor_tokens = min(4, max(1, len(tokens) - 1))
    for corte in range(1, max_autor_tokens + 1):
        autor = " ".join(tokens[:corte])
        titulo = " ".join(tokens[corte:])
        if not titulo:
            continue
        titulo_raw_tokens = titulo.split()
        if (
            len(titulo_raw_tokens) >= 2
            and titulo_raw_tokens[0].lower() in {"de", "del", "da", "di", "do", "du", "van", "von", "der", "den"}
            and titulo_raw_tokens[1][:1].isupper()
        ):
            continue
        titulo_tokens = normalizar_texto(titulo).split()
        autor_tokens = normalizar_texto(autor).split()
        if autor_tokens and autor_tokens[-1] in {
            "el", "la", "los", "las", "un", "una", "nueva", "nuevo", "gran",
            "ultimo", "ultima", "primer", "primera", "buenos", "malos",
        }:
            continue
        if (
            autor_tokens
            and autor_tokens[0] not in AUTORES_MONONIMOS_CONFIABLES
            and (autor_tokens[0] in titulo_tokens or tokens_norm_texto.count(autor_tokens[0]) > 1)
        ):
            continue
        titulo_empieza_bien = bool(titulo_tokens and titulo_tokens[0] in PALABRAS_INICIO_TITULO)
        titulo_unico_fuerte = bool(len(titulo_tokens) == 1 and len(titulo_tokens[0]) >= 5)
        autor_ok_compacto = autor_desde_nombre_es_usable(autor, permitir_mononimo=False)
        if not autor_ok_compacto and corte == 1 and normalizar_texto(autor) in AUTORES_MONONIMOS_CONFIABLES:
            autor_ok_compacto = True
        if autor_ok_compacto and (titulo_empieza_bien or len(titulo_tokens) >= 2 or titulo_unico_fuerte):
            agregar(autor, titulo, "nombre_compacto")

    agregar("", texto, "nombre_limpio")
    return sorted(pares, key=lambda x: x.get("score", 0), reverse=True)


def autores_desde_ambiguo(autor_ambiguo: str):
    autor_norm = normalizar_texto(autor_ambiguo)
    if not autor_norm:
        return []
    aliases = []
    if "preston" in autor_norm and "child" in autor_norm:
        aliases.extend(["Lincoln Child", "Douglas Preston"])
    return aliases


def autores_para_busqueda_compacta(datos):
    autores = []

    def agregar(valor):
        valor = limpiar_nombre_archivo(valor, 90) if valor else ""
        if not valor:
            return
        if autor_parece_ruido_o_rol(valor):
            return
        if not (
            autor_desde_nombre_es_usable(valor, permitir_mononimo=True)
            or autor_es_usable(valor, datos.get("editorial_local", "") or datos.get("editorial_texto", ""), permitir_mononimo=True)
        ):
            return
        key = normalizar_texto(valor)
        if key and key not in {normalizar_texto(a) for a in autores}:
            autores.append(valor)

    for campo in ("autor_local", "autor_nombre", "autor_texto", "autor_ambiguo"):
        agregar(datos.get(campo, ""))
    for par in datos.get("pares_nombre", []) or []:
        agregar(par.get("autor", ""))
    for alias in autores_desde_ambiguo(datos.get("autor_ambiguo", "")):
        agregar(alias)
    return autores[:4]


def autor_equivale_titulo(candidato_autor, candidato_titulo) -> bool:
    if not candidato_autor or not candidato_titulo:
        return False
    if similitud(candidato_autor, candidato_titulo) >= 0.86:
        return True
    tokens_autor = sorted(normalizar_texto(candidato_autor).split())
    tokens_titulo = sorted(normalizar_texto(candidato_titulo).split())
    return len(tokens_autor) >= 2 and tokens_autor == tokens_titulo


def generar_consultas_web(datos, libro: Path):
    mejor_par_nombre = (datos.get("pares_nombre") or [{}])[0]
    titulo = limpiar_titulo_para_busqueda(
        datos.get("titulo_local", "")
        or datos.get("titulo_texto", "")
        or datos.get("titulo_nombre", "")
        or mejor_par_nombre.get("titulo", "")
        or limpiar_nombre_como_pista(libro.name)
        or libro.stem
    )
    titulo_sin_acentos = quitar_acentos_busqueda(titulo)
    autor = datos.get("autor_local", "") or datos.get("autor_nombre", "") or mejor_par_nombre.get("autor", "")
    autor_ambiguo = datos.get("autor_ambiguo", "")
    if autor_equivale_titulo(autor, titulo):
        autor = ""
    if autor_equivale_titulo(autor_ambiguo, titulo):
        autor_ambiguo = ""
    consulta_base = datos.get("consulta") or " ".join([autor or autor_ambiguo, titulo]).strip()

    candidatos = [
        consulta_base,
        " ".join([autor, titulo]).strip(),
        " ".join([autor_ambiguo, titulo]).strip(),
        titulo,
        titulo_sin_acentos,
    ]
    if datos.get("tipo_documento") == "comic_manga" and titulo:
        anio = datos.get("anio_local", "") or datos.get("anio_texto", "")
        candidatos.extend([
            " ".join([titulo, anio]).strip(),
            f"{titulo} manga",
            f"{titulo} comic",
        ])

    autores_para_variantes = [autor_ambiguo]
    autores_para_variantes.extend(
        par.get("autor", "")
        for par in datos.get("pares_nombre", [])[:4]
        if par.get("autor")
        and float(par.get("score", 0) or 0) < 70
        and not autor_equivale_titulo(par.get("autor", ""), par.get("titulo", ""))
        and not str(par.get("titulo", "")).strip().startswith(("(", "["))
        and not autor_equivale_titulo(par.get("autor", ""), titulo)
    )
    for autor_base in autores_para_variantes:
        for variante in variantes_autor_invertido(autor_base):
            if titulo:
                candidatos.append(" ".join([variante, titulo]).strip())
            for par in datos.get("pares_nombre", [])[:3]:
                par_titulo = limpiar_titulo_para_busqueda(par.get("titulo", ""))
                if par_titulo:
                    candidatos.append(" ".join([variante, par_titulo]).strip())

    for par in datos.get("pares_nombre", [])[:6]:
        par_titulo = limpiar_titulo_para_busqueda(par.get("titulo", ""))
        par_autor = par.get("autor", "")
        if str(par.get("titulo", "")).strip().startswith(("(", "[")):
            par_titulo = ""
        if autor_equivale_titulo(par_autor, par_titulo):
            par_autor = ""
        if autor_equivale_titulo(par_autor, titulo):
            par_autor = ""
        if par_autor and par_titulo:
            candidatos.append(" ".join([par_autor, par_titulo]).strip())
        if par_titulo:
            candidatos.append(par_titulo)

    for alias in autores_desde_ambiguo(autor_ambiguo):
        candidatos.append(" ".join([alias, titulo]).strip())
        if titulo_sin_acentos and titulo_sin_acentos != titulo:
            candidatos.append(" ".join([alias, titulo_sin_acentos]).strip())

    if datos.get("titulo_nombre_compacto"):
        for autor_compacto in autores_para_busqueda_compacta(datos):
            candidatos.insert(0, " ".join([autor_compacto, titulo]).strip())
            for token in datos.get("tokens_compactos_nombre", [])[:2]:
                token_limpio = limpiar_titulo_para_busqueda(token)
                if token_limpio:
                    candidatos.append(" ".join([autor_compacto, token_limpio]).strip())

    out = []
    vistos = set()
    for query in candidatos:
        query = re.sub(r"\s+", " ", str(query or "")).strip()
        key = normalizar_texto(query)
        if not query or len(key) < 4 or key in vistos:
            continue
        vistos.add(key)
        out.append(query)
        if len(out) >= 8:
            break
    return out


def autor_texto_es_confiable(autor: str, datos, libro: Path | None = None) -> bool:
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    if not autor:
        return False
    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    if autor_parece_ruido_o_rol(autor):
        return False
    if not autor_es_usable(autor, editorial):
        return False

    autor_local = datos.get("autor_local", "")
    if autor_local and autor_es_usable(autor_local, editorial, permitir_mononimo=True):
        return similitud(autor, autor_local) >= 0.72

    for titulo in [datos.get("titulo_local", ""), datos.get("titulo_texto", "")]:
        if titulo and similitud(autor, titulo) >= 0.82:
            return False

    if libro:
        nombre_pista = limpiar_nombre_como_pista(libro.name)
        if nombre_pista and autor and normalizar_texto(autor) in normalizar_texto(nombre_pista):
            return False

    return True


def autor_generico_local_confirmado(datos) -> str:
    autor = limpiar_nombre_archivo(datos.get("autor_generico_local", ""), 90) if datos.get("autor_generico_local") else ""
    if not autor:
        return ""
    titulo = datos.get("titulo_local", "") or datos.get("titulo_texto", "") or datos.get("titulo_nombre", "")
    if not titulo:
        return ""
    tiene_metadatos_estructurados = bool(
        (datos.get("titulo_local") or datos.get("titulo_nombre"))
        and (datos.get("isbns") or datos.get("editorial_local") or datos.get("anio_local"))
    )
    if not tiene_metadatos_estructurados:
        return ""
    if autor_es_anonimo_generico(autor):
        if (
            datos.get("isbns")
            or datos.get("autor_generico_anonimo_contexto")
            or (datos.get("titulo_nombre") and datos.get("anio_local"))
        ):
            return limpiar_nombre_archivo(autor, 90)
    if autor_es_colectivo_generico(autor):
        if datos.get("autor_generico_colectivo_contexto") or not datos.get("isbns"):
            return "Varios"
    return ""


def elegir_autor_final(datos, autor_web: str = "", libro: Path | None = None, permitir_mononimo_web: bool = False) -> str:
    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")

    autor_local = limpiar_nombre_archivo(datos.get("autor_local", ""), 90) if datos.get("autor_local") else ""
    titulos_para_autor_nombre = [
        datos.get("titulo_local", ""),
        datos.get("titulo_texto", ""),
        datos.get("titulo_nombre", ""),
    ]
    autor_local_es_titulo = bool(
        autor_local
        and any(titulo and similitud(autor_local, titulo) >= 0.86 for titulo in titulos_para_autor_nombre)
    )
    if autor_local and (
        autor_es_usable(autor_local, editorial, permitir_mononimo=True)
        or autor_mononimo_estructurado_confiable(autor_local, editorial)
    ) and not autor_local_es_titulo:
        return autor_local

    autor_web = limpiar_nombre_archivo(preferir_alias_latino_autor(autor_web), 90) if autor_web else ""
    if autor_web and (
        autor_es_usable(autor_web, editorial, permitir_mononimo=permitir_mononimo_web)
        or permitir_mononimo_web
    ):
        return autor_web

    autor_nombre = datos.get("autor_nombre", "")
    autor_nombre_es_titulo = bool(
        autor_nombre
        and any(titulo and similitud(autor_nombre, titulo) >= 0.86 for titulo in titulos_para_autor_nombre)
    )
    if autor_nombre and (
        autor_es_usable(autor_nombre, editorial, permitir_mononimo=True)
        or autor_desde_nombre_es_usable(autor_nombre, permitir_mononimo=True)
    ) and not autor_nombre_es_titulo:
        titulo_ref = datos.get("titulo_local", "") or datos.get("titulo_texto", "") or datos.get("titulo_nombre", "")
        nombre_norm = normalizar_texto(libro.stem).replace(" ", "") if libro else ""
        autor_nombre_variantes = [autor_nombre] + variantes_autor_invertido(autor_nombre)
        nombre_ok = not libro or any(
            normalizar_texto(variante).replace(" ", "") in nombre_norm
            for variante in autor_nombre_variantes
            if variante
        )
        titulo_ok = not titulo_ref or similitud(titulo_ref, datos.get("titulo_nombre", "") or titulo_ref) >= 0.70
        if nombre_ok and titulo_ok and not autor_parece_ruido_o_rol(autor_nombre):
            return limpiar_nombre_archivo(autor_nombre, 90)

    autor_texto = datos.get("autor_texto", "")
    if autor_texto_es_confiable(autor_texto, datos, libro):
        return limpiar_nombre_archivo(autor_texto, 90)
    if (
        autor_texto
        and (autor_nombre_es_titulo or autor_local_es_titulo)
        and autor_es_usable(autor_texto, editorial)
        and not any(titulo and similitud(autor_texto, titulo) >= 0.82 for titulo in titulos_para_autor_nombre)
    ):
        return limpiar_nombre_archivo(autor_texto, 90)

    autor_generico = autor_generico_local_confirmado(datos)
    if autor_generico:
        return autor_generico

    return ""


def autor_web_confirmado_por_local(autor_web: str, datos) -> bool:
    return _orchestration.autor_web_confirmado_por_local(
        autor_web,
        datos,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        similitud_func=similitud,
    )


def autor_anonimo_confirmado_por_web(autor_web: str, datos, confianza: float = 0) -> bool:
    return _orchestration.autor_anonimo_confirmado_por_web(
        autor_web,
        datos,
        confianza,
        autor_es_anonimo_generico_func=autor_es_anonimo_generico,
        umbral_renombrar=UMBRAL_RENOMBRAR,
    )


def autor_aparece_en_texto(autor: str, texto: str) -> bool:
    autor_norm = normalizar_texto(autor)
    texto_norm = normalizar_texto(texto)
    if not autor_norm or not texto_norm:
        return False
    if autor_norm in texto_norm:
        return True
    partes = [normalizar_texto(p) for p in re.split(r"\s*(?:&| and | y | et |,|;|/)\s*", autor or "", flags=re.I)]
    partes = [p for p in partes if p]
    return bool(partes) and all(p in texto_norm for p in partes[:4])


def inferir_titulo_desde_portada(texto: str) -> str:
    texto = limpiar_texto_extraido(texto)
    lineas = []
    for linea in texto.splitlines()[:40]:
        linea = re.sub(r"\s+", " ", linea).strip(" \t-–—|")
        if 4 <= len(linea) <= 100 and not re.fullmatch(r"\d+", linea):
            lineas.append(linea)

    for i, linea in enumerate(lineas[:12]):
        low = normalizar_texto(linea)
        if _linea_parece_nombre_autor(linea):
            continue
        if set(low.split()) & {"isbn", "copyright", "editorial", "publisher", "traduccion", "translator"}:
            continue
        partes = [linea]
        if len(linea) >= 8 and re.search(r"[?¿!¡:]", linea):
            titulo = limpiar_nombre_archivo(linea, 120)
            if titulo and not _titulo_parece_contaminado_por_archivo(titulo):
                return titulo
        for siguiente in lineas[i + 1:i + 4]:
            if _linea_parece_nombre_autor(siguiente):
                break
            siguiente_norm = normalizar_texto(siguiente)
            if set(siguiente_norm.split()) & {"isbn", "copyright", "editorial", "publisher", "traduccion", "translator", "novela", "novel", "serie", "saga"}:
                break
            partes.append(siguiente)
            unido = " ".join(partes)
            if len(unido) >= 12 and re.search(r"[?¿!:]", unido):
                break
        titulo = limpiar_nombre_archivo(" ".join(partes), 120)
        if titulo and not _titulo_parece_contaminado_por_archivo(titulo):
            return titulo
    return ""


def inferir_autor_desde_portada(texto: str, titulo_ref: str = "") -> str:
    texto = limpiar_texto_extraido(texto)
    lineas = []
    for linea in texto.splitlines()[:80]:
        linea = re.sub(r"\s+", " ", linea).strip(" \t-–—|")
        if 4 <= len(linea) <= 140 and not re.fullmatch(r"\d+", linea):
            lineas.append(linea)

    if not lineas:
        return ""

    titulo_norm = normalizar_texto(titulo_ref)
    indice_titulo = -1
    if titulo_norm:
        for i, linea in enumerate(lineas):
            linea_norm = normalizar_texto(linea)
            if titulo_norm in linea_norm or linea_norm in titulo_norm or similitud(linea, titulo_ref) >= 0.72:
                indice_titulo = i
                break

    def _autor_candidato(linea: str) -> bool:
        linea_norm = normalizar_texto(linea)
        return (
            _linea_parece_nombre_autor(linea)
            and linea_norm != titulo_norm
            and linea_norm not in titulo_norm
            and titulo_norm not in linea_norm
        )

    if indice_titulo < 0:
        limite = min(10, len(lineas))
        candidatos = [linea for linea in lineas[:limite] if _linea_parece_nombre_autor(linea)]
    else:
        inicio = max(0, indice_titulo - 6)
        anteriores = [linea for linea in lineas[inicio:indice_titulo] if _autor_candidato(linea)]
        posteriores = []
        for linea in lineas[indice_titulo + 1:indice_titulo + 6]:
            low = normalizar_texto(linea)
            if set(low.split()) & {"isbn", "editorial", "publisher", "traduccion", "translator", "copyright"}:
                break
            if _autor_candidato(linea):
                posteriores.append(linea)
                continue
            if posteriores:
                break
        candidatos = posteriores or anteriores

    if not candidatos:
        return ""

    return limpiar_nombre_archivo(" & ".join(candidatos[-3:]), 90)


def _mejor_candidato_ocr(candidatos, min_score=0):
    validos = []
    for candidato in candidatos or []:
        texto = limpiar_nombre_archivo(candidato.get("text", ""), 140)
        try:
            score = float(candidato.get("score", 0) or 0)
        except Exception:
            score = 0
        if texto and score >= min_score:
            item = dict(candidato)
            item["text"] = texto
            item["score"] = score
            validos.append(item)
    return sorted(validos, key=lambda item: item["score"], reverse=True)[0] if validos else None


def aplicar_candidatos_ocr_portada(ocr_result, inferido, meta, ruta: Path, titulo_actual="", autor_actual=""):
    """Use short OCR layout candidates without trusting full OCR text blindly."""
    if not ocr_result:
        return False
    cambio = False
    editorial = meta.get("editorial", "") if isinstance(meta, dict) else ""
    titulo_actual = titulo_actual or inferido.get("titulo", "") or (meta or {}).get("titulo", "")
    autor_actual = autor_actual or inferido.get("autor", "") or (meta or {}).get("autor", "")

    titulo_candidato = _mejor_candidato_ocr(ocr_result.get("ocr_title_candidates"), min_score=68)
    if titulo_candidato:
        titulo_ocr = limpiar_titulo_legible(titulo_candidato["text"], autor_actual)
        titulo_actual_limpio = limpiar_titulo_legible(titulo_actual, autor_actual)
        compatible = (
            not titulo_actual_limpio
            or similitud(titulo_ocr, titulo_actual_limpio) >= 0.62
            or similitud_titulo_compacto(titulo_ocr, titulo_actual_limpio) >= 0.82
            or float(titulo_candidato.get("score", 0) or 0) >= 82
        )
        puede_reemplazar = (
            not inferido.get("titulo")
            or _titulo_parece_contaminado_por_archivo(inferido.get("titulo", ""))
            or titulo_compacto_necesita_confirmacion(
                {
                    "titulo_nombre_compacto": True,
                    "titulo_local": (meta or {}).get("titulo", ""),
                    "titulo_texto": inferido.get("titulo", ""),
                },
                inferido.get("titulo", ""),
                autor_actual,
                ruta,
            )
            or len(titulo_ocr) > len(inferido.get("titulo", "")) + 3
        )
        if (
            titulo_ocr
            and compatible
            and puede_reemplazar
            and _titulo_candidato_valido(titulo_ocr)
            and _ruido_titulo_investigacion(titulo_ocr, autor_actual) < 35
        ):
            inferido["titulo"] = titulo_ocr
            cambio = True

    autor_candidato = _mejor_candidato_ocr(ocr_result.get("ocr_author_candidates"), min_score=62)
    if autor_candidato:
        autor_ocr = limpiar_nombre_archivo(autor_candidato["text"], 90)
        titulo_ref = inferido.get("titulo", "") or titulo_actual
        autor_actual_util = autor_es_usable(autor_actual, editorial, permitir_mononimo=True) and not autor_parece_ruido_o_rol(autor_actual)
        autor_ocr_util = (
            autor_ocr
            and autor_es_usable(autor_ocr, editorial, permitir_mononimo=True)
            and not autor_parece_ruido_o_rol(autor_ocr)
            and similitud(autor_ocr, titulo_ref) < 0.82
        )
        if autor_ocr_util and (
            not autor_actual_util
            or not autor_aparece_en_texto(autor_actual, ocr_result.get("texto", ""))
            or float(autor_candidato.get("score", 0) or 0) >= 78
        ):
            inferido["autor"] = autor_ocr
            cambio = True

    if not inferido.get("anio") and ocr_result.get("ocr_year_candidates"):
        inferido["anio"] = str(ocr_result["ocr_year_candidates"][0])
        cambio = True
    return cambio


def extraer_metadatos_pdf(ruta: Path):
    resultado = {"titulo": "", "autor": "", "editorial": "", "anio": "", "isbn": ""}
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(ruta))
        metadata = getattr(reader, "metadata", None) or {}
        get = metadata.get if hasattr(metadata, "get") else lambda _k, _d="": ""
        resultado["titulo"] = str(get("/Title", "") or get("title", "") or "").strip()
        resultado["autor"] = str(get("/Author", "") or get("author", "") or "").strip()
        resultado["editorial"] = str(get("/Publisher", "") or get("publisher", "") or "").strip()
        resultado["anio"] = extraer_anio(" ".join(str(v) for v in metadata.values()))
        isbns = extraer_isbns(" ".join(str(v) for v in metadata.values()))
        if isbns:
            resultado["isbn"] = isbns[0]
    except Exception:
        pass
    return resultado


def texto_desde_pdf_primeras_paginas(ruta: Path, max_paginas=MAX_PAGINAS_TEXTO):
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(ruta))
        textos = []
        for page in list(reader.pages)[:max_paginas]:
            try:
                textos.append(page.extract_text() or "")
            except Exception:
                pass
        texto = limpiar_texto_extraido("\n".join(textos))
        if texto:
            return texto
    except Exception:
        pass
    return ""


def extraer_metadatos_epub(ruta: Path):
    resultado = {"titulo": "", "autor": "", "autor_ambiguo": "", "autor_generico": "", "editorial": "", "anio": "", "isbn": ""}
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            opfs = [n for n in z.namelist() if n.lower().endswith(".opf")]
            for opf in opfs[:3]:
                try:
                    data = z.read(opf)
                    root = ET.fromstring(data)
                    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
                    tit = root.find(".//dc:title", ns)
                    aut = root.find(".//dc:creator", ns)
                    pub = root.find(".//dc:publisher", ns)
                    date = root.find(".//dc:date", ns)
                    if tit is not None and tit.text:
                        resultado["titulo"] = tit.text.strip()
                    autor_original = ""
                    if aut is not None and aut.text:
                        autor_original = aut.text.strip()
                        resultado["autor"] = autor_original
                        if autor_es_anonimo_generico(autor_original) or autor_es_colectivo_generico(autor_original):
                            resultado["autor_generico"] = limpiar_nombre_archivo(autor_original, 90)
                    if pub is not None and pub.text:
                        resultado["editorial"] = pub.text.strip()
                    if not (
                        autor_es_usable(resultado["autor"], resultado["editorial"])
                        or autor_mononimo_estructurado_confiable(resultado["autor"], resultado["editorial"])
                    ):
                        if autor_ambiguo_para_busqueda(autor_original):
                            resultado["autor_ambiguo"] = autor_original
                        resultado["autor"] = ""
                    if date is not None and date.text:
                        resultado["anio"] = extraer_anio(date.text)
                    isbns = extraer_isbns(data.decode("utf-8", errors="ignore"))
                    if isbns:
                        resultado["isbn"] = isbns[0]
                    break
                except Exception:
                    continue
    except Exception:
        pass
    return resultado


def _linea_es_ruido_identificacion(linea: str) -> bool:
    linea = re.sub(r"\s+", " ", str(linea or "")).strip()
    if not linea:
        return True
    if re.search(r"(?i)(@page|margin-|font-|urn[: ]+uuid|urn\s+uuid|<\?xml|stylesheet|\{|\})", linea):
        return True
    low = normalizar_texto(linea)
    if not low:
        return True
    tokens = set(low.split())
    ruido_duro = {
        "bookmobi", "exth", "nn", "calibre", "autor", "desconocido",
        "unknown", "titulo", "sin", "capitulo", "chapter", "contents",
        "indice", "copyright", "rights", "derechos", "public", "domain",
        "dominio", "licencia", "license", "creative", "commons",
    }
    if tokens <= ruido_duro or len(tokens & ruido_duro) >= max(2, len(tokens) - 1):
        return True
    if re.search(r"(?i)\b(bookmobi|exth|autor\s+desconocido|unknown\s+author)\b", linea):
        return True
    partes = low.split()
    if len(partes) >= 8:
        cortas = sum(1 for parte in partes if len(parte) <= 2)
        largas = sum(1 for parte in partes if len(parte) >= 4)
        if cortas / len(partes) >= 0.45 and largas <= 2:
            return True
    raros = re.findall(r"[^A-Za-zÀ-ÿ0-9\s.,:;!?¡¿'’\"()&/\-]", linea)
    return bool(raros and len(raros) / max(1, len(linea)) > 0.10)


def limpiar_linea_identificacion(linea: str) -> str:
    linea = re.sub(r"(?i)@page.*$", " ", str(linea or ""))
    linea = re.sub(r"(?i)\burn(?:[: ]+)uuid[: ]*[a-f0-9-]+\b", " ", linea)
    linea = re.sub(r"(?i)\b(?:margin|font|padding|line-height|text-align)[-_a-z]*\s*[:=][^;]+;?", " ", linea)
    linea = re.sub(r"\s+", " ", linea).strip(" \t-–—|")
    return linea


def inferir_metadatos_desde_texto(texto: str):
    texto = limpiar_texto_extraido(texto)
    lineas = []
    for linea in texto.splitlines()[:120]:
        linea = limpiar_linea_identificacion(linea)
        if 4 <= len(linea) <= 140 and not re.fullmatch(r"\d+", linea) and not _linea_es_ruido_identificacion(linea):
            lineas.append(linea)

    titulo = ""
    autor = ""
    editorial = ""
    anio = extraer_anio(texto)

    for linea in lineas[:40]:
        low = linea.lower()
        if not titulo and not re.search(r"\b(isbn|copyright|all rights|edition|publisher|editorial)\b", low):
            titulo = linea
            continue
        if not autor:
            m = re.search(r"\b(?:by|author|autor|autora|auteur)\s+(.{3,90})$", linea, re.I)
            if m:
                candidato_autor = m.group(1).strip()
                if _linea_parece_nombre_autor(candidato_autor):
                    autor = candidato_autor
            elif re.fullmatch(r"(?i)de\s+(.{3,90})", linea):
                candidato_autor = re.sub(r"(?i)^de\s+", "", linea).strip()
                if _linea_parece_nombre_autor(candidato_autor):
                    autor = candidato_autor
        if not editorial:
            m = re.search(r"\b(?:publisher|editorial|published by)\s*[:\-]?\s*(.{3,90})$", linea, re.I)
            if m:
                editorial = m.group(1).strip()

    return {
        "titulo": limpiar_nombre_archivo(titulo, 120) if titulo else "",
        "autor": limpiar_nombre_archivo(autor, 90) if autor else "",
        "editorial": limpiar_nombre_archivo(editorial, 90) if editorial else "",
        "anio": anio,
    }


def _titulo_parece_contaminado_por_archivo(titulo: str) -> bool:
    titulo_norm = normalizar_texto(titulo)
    if not titulo_norm:
        return False
    ruido = {"autor", "desconocido", "unknown", "sin", "titulo"}
    return bool(set(titulo_norm.split()) & ruido)


def _texto_tiene_datos_utiles(texto: str) -> bool:
    if extraer_isbns(texto):
        return True
    inferido = inferir_metadatos_desde_texto(texto)
    if inferido.get("titulo") and inferido.get("autor"):
        return True
    texto_norm = normalizar_texto(texto)
    pistas = {"isbn", "author", "autor", "auteur", "chapter", "capitulo", "contents", "indice", "publisher", "editorial"}
    if inferido.get("titulo") and (set(texto_norm.split()) & pistas):
        return True
    palabras = re.findall(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]{3,}", texto or "")
    return len(palabras) >= 35


def parece_libro_por_datos(ruta: Path, datos) -> bool:
    suffix = ruta.suffix.lower()
    if suffix in {".epub", ".mobi", ".azw", ".azw3", ".fb2", ".cbr", ".cbz"}:
        return True
    if datos.get("isbns") or datos.get("dois") or datos.get("ocr_isbn"):
        return True
    if datos.get("titulo_local") and (datos.get("autor_local") or datos.get("anio_local")):
        return True
    if datos.get("titulo_texto") and datos.get("autor_texto"):
        return True

    consulta = normalizar_texto(datos.get("consulta", ""))
    nombre = normalizar_texto(ruta.stem)
    pistas_nombre = {
        "book", "libro", "livre", "ebook", "manual", "novel", "novela",
        "author", "autor", "auteur", "isbn", "volume", "chapter", "capitulo",
        "edition", "edicion", "edition"
    }
    if set(nombre.split()) & pistas_nombre:
        return True

    texto_ocr = datos.get("ocr_texto", "")
    if texto_ocr and _texto_tiene_datos_utiles(texto_ocr):
        return True
    if consulta and set(consulta.split()) & pistas_nombre:
        return True

    return False


def detectar_tipo_documento_desde_texto(texto: str, ruta: Path | None = None) -> str:
    suffix = ruta.suffix.lower() if ruta else ""
    texto_norm = normalizar_texto(texto)
    tokens = set(texto_norm.split())

    if suffix in {".cbr", ".cbz"}:
        return "comic_manga"

    if suffix in {".epub", ".mobi", ".azw", ".azw3", ".fb2"} and not extraer_dois(texto):
        return "libro_comercial"

    senales_academicas = {
        "abstract", "references", "journal", "doi", "volume", "issue",
        "conference", "proceedings", "keywords", "appendix", "methodology",
        "bibliography", "revista", "resumen", "referencias",
    }
    if extraer_dois(texto) or len(tokens & senales_academicas) >= 2:
        return "paper_academico"

    senales_manual = {"manual", "guide", "guia", "tutorial", "instructions", "procedimiento"}
    if len(tokens & senales_manual) >= 2:
        return "manual_tecnico"

    if suffix in {".epub", ".mobi", ".azw", ".azw3", ".fb2", ".pdf"}:
        return "libro_comercial"

    return "documento_desconocido"


def elegir_metadatos_locales(libro: Path, datos):
    editorial = datos.get("editorial_local", "")
    anio = datos.get("anio_local", "")
    isbn = datos["isbns"][0] if datos.get("isbns") else ""
    autor = elegir_autor_final(datos, libro=libro)
    titulo = limpiar_titulo_legible(datos.get("titulo_local", ""), autor)

    if not titulo and datos.get("titulo_texto"):
        titulo = limpiar_titulo_legible(datos.get("titulo_texto", ""), autor)
    if not titulo and datos.get("titulo_nombre"):
        titulo = limpiar_titulo_legible(datos.get("titulo_nombre", ""), autor)
    titulo_nombre_limpio = limpiar_titulo_legible(datos.get("titulo_nombre", ""), autor)
    titulo_norm = normalizar_texto(titulo)
    titulo_nombre_norm = normalizar_texto(titulo_nombre_limpio)
    titulo_es_fragmento_de_nombre = bool(
        titulo_norm
        and titulo_nombre_norm
        and titulo_norm != titulo_nombre_norm
        and titulo_norm in titulo_nombre_norm
        and len(titulo_nombre_norm.split()) >= len(titulo_norm.split()) + 2
    )
    titulo_ruidoso_frente_a_nombre = bool(
        titulo_norm
        and titulo_nombre_norm
        and titulo_norm != titulo_nombre_norm
        and len(titulo_nombre_norm.split()) >= 3
        and (
            (len(titulo_norm.split()) <= 2 and not (set(titulo_norm.split()) & set(titulo_nombre_norm.split())))
            or (bool(re.search(r"\b\d{1,2}\b", titulo_norm)) and not re.search(r"\b\d{1,2}\b", titulo_nombre_norm))
        )
    )
    if (
        titulo
        and titulo_nombre_limpio
        and datos.get("autor_nombre")
        and autor
        and similitud(autor, datos.get("autor_nombre", "")) >= 0.72
        and (
            len(normalizar_texto(titulo).split()) > 12
            or len(titulo) > len(titulo_nombre_limpio) + 35
            or titulo.strip().startswith(("«", "\"", "“"))
            or titulo_es_fragmento_de_nombre
            or titulo_ruidoso_frente_a_nombre
        )
    ):
        titulo = titulo_nombre_limpio
    if not editorial and datos.get("editorial_texto"):
        editorial = datos.get("editorial_texto", "")
    if not anio and datos.get("anio_texto"):
        anio = datos.get("anio_texto", "")

    if not titulo:
        return {
            "encontrado": False,
            "confianza": 0,
            "nombre_sugerido": libro.name,
            "fuente": "Local analysis",
            "titulo": "",
            "autor": "",
            "editorial": editorial,
            "anio": anio,
            "isbn": isbn,
            "motivo": "No reliable local title found",
        }

    score = 58
    fuente = []
    if datos.get("titulo_local"):
        score += 14
        fuente.append("internal metadata")
    if datos.get("titulo_texto"):
        score += 10
        fuente.append("first pages")
    autor_texto_confirmado_por_final = bool(
        datos.get("autor_texto")
        and autor
        and similitud(autor, datos.get("autor_texto", "")) >= 0.72
    )
    if datos.get("titulo_texto") and (
        autor_texto_es_confiable(datos.get("autor_texto", ""), datos, libro)
        or autor_texto_confirmado_por_final
    ):
        score += 10
        fuente.append("title+author in content")
    if isbn:
        score += 12
        fuente.append("ISBN")
    if autor:
        score += 6
    if datos.get("titulo_nombre") and autor:
        score += 8
        fuente.append("filename pattern")
    if datos.get("titulo_nombre") and datos.get("autor_nombre") and autor and similitud(autor, datos.get("autor_nombre", "")) >= 0.78:
        score += 4
    if datos.get("titulo_local") and autor:
        score += 4
    if anio:
        score += 2
    nombre_pista = limpiar_nombre_como_pista(libro.name)
    if nombre_pista and similitud(titulo, nombre_pista) >= 0.72:
        score += 8
    elif nombre_pista and normalizar_texto(titulo) and normalizar_texto(titulo) in normalizar_texto(nombre_pista):
        score += 6
    if datos.get("titulo_local") and datos.get("titulo_texto"):
        score += round(similitud(datos["titulo_local"], datos["titulo_texto"]) * 8, 1)
    if not autor:
        score = min(score, 84)
        fuente.append("author not reliable")

    confianza = min(96, round(score, 1))
    nuevo_nombre = crear_nombre_sugerido(autor, titulo, anio, isbn, libro.suffix)
    return {
        "encontrado": confianza >= UMBRAL_RENOMBRAR,
        "confianza": confianza,
        "nombre_sugerido": nuevo_nombre,
        "fuente": "Local analysis",
        "titulo": titulo,
        "autor": autor,
        "editorial": editorial,
        "anio": anio,
        "isbn": isbn,
        "motivo": "Local evidence: " + ", ".join(fuente or ["filename/content"]),
    }


def extraer_datos_locales(ruta: Path, callback=None, permitir_ocr=True, max_paginas_ocr=12, cancellation=None):
    if cancellation:
        cancellation.raise_if_cancelled()
    isbns_nombre = extraer_isbns(ruta.name)
    nombre_pista = limpiar_nombre_como_pista(ruta.name)
    texto = (nombre_pista + "\n" if nombre_pista else "")
    if isbns_nombre:
        texto += " ".join(isbns_nombre) + "\n"
    texto_documento = ""
    meta = {"titulo": "", "autor": "", "autor_ambiguo": "", "autor_generico": "", "editorial": "", "anio": "", "isbn": ""}
    meta_nombre = extraer_metadatos_desde_nombre(nombre_pista)
    pares_nombre = generar_pares_nombre_archivo(ruta.name)
    mejor_par_nombre = pares_nombre[0] if pares_nombre else {}
    if meta_nombre.get("titulo") and meta_nombre.get("autor") and (
        not mejor_par_nombre
        or not mejor_par_nombre.get("autor")
        or float(mejor_par_nombre.get("score", 0)) < 70
    ):
        par_meta_nombre = {
            "titulo": meta_nombre["titulo"],
            "autor": meta_nombre["autor"],
            "fuente": "nombre_separado",
            "score": 82,
        }
        mejor_par_nombre = par_meta_nombre
        pares_nombre = [par_meta_nombre] + pares_nombre

    if ruta.suffix.lower() == ".epub":
        meta = extraer_metadatos_epub(ruta)
        texto += "\n".join([meta.get("titulo", ""), meta.get("autor", ""), meta.get("autor_ambiguo", ""), meta.get("editorial", ""), meta.get("anio", ""), meta.get("isbn", "")])
        texto_documento = texto_desde_epub(ruta)
        texto += "\n" + texto_documento
    elif ruta.suffix.lower() in KINDLE_EXTENSIONS:
        meta = extraer_metadatos_mobi(ruta)
        texto += "\n".join([meta.get("titulo", ""), meta.get("autor", ""), meta.get("autor_ambiguo", ""), meta.get("editorial", ""), meta.get("anio", ""), meta.get("isbn", "")])
    elif ruta.suffix.lower() == ".pdf":
        meta = extraer_metadatos_pdf(ruta)
        texto += "\n".join([meta.get("titulo", ""), meta.get("autor", ""), meta.get("autor_ambiguo", ""), meta.get("editorial", ""), meta.get("anio", ""), meta.get("isbn", "")])
        texto_documento = texto_desde_pdf_primeras_paginas(ruta)
        texto += "\n" + texto_documento
    elif ruta.suffix.lower() in {".cbz", ".cbr"}:
        # Los contenedores de cómic son binarios; leerlos como texto genera falsos títulos/autores.
        meta = extraer_metadatos_comic_archivo(ruta)
        texto += "\n".join([meta.get("titulo", ""), meta.get("autor", ""), meta.get("editorial", ""), meta.get("anio", ""), meta.get("isbn", "")])
        texto_documento = ""
    elif ruta.suffix.lower() in {".txt", ".rtf", ".doc", ".docx", ".odt", ".djvu", ".fb2"}:
        lectura = _document_readers.extract_document(ruta, cancellation=cancellation)
        texto_documento = lectura.get("text", "")
        texto += "\n" + texto_documento
        meta_lector = lectura.get("metadata", {})
        meta["titulo"] = meta_lector.get("title", "")
        meta["autor"] = meta_lector.get("creator", "")
        if lectura.get("error") and callback:
            callback(f"Lector {ruta.suffix}: {lectura['error']}")

    isbns = list(dict.fromkeys(isbns_nombre + extraer_isbns(texto)))
    dois = extraer_dois(texto)
    if meta.get("isbn"):
        mi = limpiar_isbn(meta["isbn"])
        if mi and mi not in isbns:
            isbns = [mi] + isbns

    inferido = inferir_metadatos_desde_texto(texto)
    inferido_documento = inferir_metadatos_desde_texto(texto_documento)
    titulo_portada = inferir_titulo_desde_portada(texto_documento)
    if meta_nombre.get("titulo") and not meta.get("titulo"):
        inferido["titulo"] = meta_nombre["titulo"]
    if meta_nombre.get("autor") and not meta.get("autor") and not inferido.get("autor"):
        inferido["autor"] = meta_nombre["autor"]
    if mejor_par_nombre.get("titulo") and not meta.get("titulo") and not inferido.get("titulo"):
        inferido["titulo"] = mejor_par_nombre["titulo"]
    if mejor_par_nombre.get("autor") and not meta.get("autor") and not inferido.get("autor"):
        inferido["autor"] = mejor_par_nombre["autor"]
    titulo_desde_nombre = limpiar_titulo_desde_nombre_y_autor(nombre_pista, meta.get("autor", ""))
    if titulo_desde_nombre and (
        not meta.get("titulo")
        and (
            not inferido.get("titulo")
            or similitud(inferido.get("titulo", ""), nombre_pista) >= 0.75
            or similitud(inferido.get("titulo", ""), titulo_desde_nombre) >= 0.78
            or len(inferido.get("titulo", "")) > len(titulo_desde_nombre) + 8
        )
    ):
        inferido["titulo"] = titulo_desde_nombre
    if inferido_documento.get("titulo") and (
        not inferido.get("titulo") or _titulo_parece_contaminado_por_archivo(inferido.get("titulo", ""))
    ):
        inferido["titulo"] = inferido_documento["titulo"]
    if meta.get("autor") and inferido.get("titulo") and similitud(meta["autor"], inferido["titulo"]) >= 0.92:
        inferido["titulo"] = nombre_pista
    if titulo_portada and not _linea_es_ruido_identificacion(titulo_portada) and (
        not inferido.get("titulo")
        or _titulo_parece_contaminado_por_archivo(inferido.get("titulo", ""))
        or len(titulo_portada) > len(inferido.get("titulo", "")) + 4
    ):
        inferido["titulo"] = titulo_portada
    for clave in ("autor", "editorial", "anio"):
        if inferido_documento.get(clave) and not inferido.get(clave):
            inferido[clave] = inferido_documento[clave]

    autor_portada = inferir_autor_desde_portada(
        texto_documento,
        meta.get("titulo") or inferido.get("titulo") or ruta.stem,
    )
    if autor_portada and (
        not inferido.get("autor")
        or not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", ""))
        or not autor_aparece_en_texto(inferido.get("autor", ""), texto_documento)
    ):
        inferido["autor"] = autor_portada
    ocr_result = {}
    epub_requiere_ocr_portada = ruta.suffix.lower() == ".epub" and (
        not inferido.get("autor")
        or not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", ""))
    )
    if epub_requiere_ocr_portada and permitir_ocr:
        try:
            from ocr_engine import extraer_texto_imagen_bytes_ocr

            for image_bytes in imagenes_portada_epub(ruta, max_imagenes=2):
                if cancellation:
                    cancellation.raise_if_cancelled()
                if callback:
                    callback("OCR: analizando portada EPUB")
                portada_ocr = extraer_texto_imagen_bytes_ocr(
                    image_bytes, callback=callback, cancellation=cancellation,
                )
                texto_portada = portada_ocr.get("texto", "")
                if not texto_portada:
                    continue
                texto += "\n" + texto_portada
                aplicar_candidatos_ocr_portada(
                    portada_ocr,
                    inferido,
                    meta,
                    ruta,
                    titulo_actual=meta.get("titulo", "") or inferido.get("titulo", "") or ruta.stem,
                    autor_actual=meta.get("autor", "") or inferido.get("autor", ""),
                )
                inferido_portada = inferir_metadatos_desde_texto(texto_portada)
                for clave in ("titulo", "editorial", "anio"):
                    if inferido_portada.get(clave) and not inferido.get(clave):
                        inferido[clave] = inferido_portada[clave]
                autor_portada = inferir_autor_desde_portada(
                    texto_portada,
                    meta.get("titulo") or inferido.get("titulo") or ruta.stem,
                )
                if autor_portada:
                    inferido["autor"] = autor_portada
                    ocr_result = portada_ocr
                    break
                if inferido_portada.get("autor") and autor_es_usable(inferido_portada["autor"], meta.get("editorial", "")):
                    inferido["autor"] = inferido_portada["autor"]
                    ocr_result = portada_ocr
                    break
        except OperationCancelled:
            raise
        except Exception as exc:
            if callback:
                callback(f"OCR: {exc}")
    titulo_mobi_actual = meta.get("titulo", "") or inferido.get("titulo", "") or mejor_par_nombre.get("titulo", "")
    autor_mobi_actual = meta.get("autor", "") or inferido.get("autor", "") or mejor_par_nombre.get("autor", "")
    mobi_requiere_ocr_portada = (
        ruta.suffix.lower() in KINDLE_EXTENSIONS
        and (
            not autor_es_usable(autor_mobi_actual, meta.get("editorial", ""), permitir_mononimo=True)
            or not titulo_mobi_actual
            or titulo_proviene_de_token_compacto(ruta.name, titulo_mobi_actual, autor_mobi_actual)
            or _titulo_parece_contaminado_por_archivo(titulo_mobi_actual)
            or "Ã" in titulo_mobi_actual
            or any(ch in titulo_mobi_actual for ch in ("\x82", "\xa4", "¤"))
        )
    )
    if mobi_requiere_ocr_portada and permitir_ocr:
        try:
            from ocr_engine import extraer_texto_imagen_bytes_ocr

            for image_bytes in imagenes_portada_mobi(ruta, max_imagenes=3):
                if cancellation:
                    cancellation.raise_if_cancelled()
                if callback:
                    callback("OCR: analizando portada MOBI")
                portada_ocr = extraer_texto_imagen_bytes_ocr(
                    image_bytes, callback=callback, cancellation=cancellation,
                )
                texto_portada = portada_ocr.get("texto", "")
                if not texto_portada:
                    continue
                texto += "\n" + texto_portada
                aplicar_candidatos_ocr_portada(
                    portada_ocr,
                    inferido,
                    meta,
                    ruta,
                    titulo_actual=titulo_mobi_actual,
                    autor_actual=autor_mobi_actual,
                )
                inferido_portada = inferir_metadatos_desde_texto(texto_portada)
                if inferido_portada.get("titulo"):
                    titulo_ocr = limpiar_titulo_legible(inferido_portada["titulo"], inferido_portada.get("autor", "") or autor_mobi_actual)
                    titulo_actual_limpio = limpiar_titulo_legible(inferido.get("titulo", "") or titulo_mobi_actual, autor_mobi_actual)
                    titulo_ocr_compatible = (
                        not titulo_actual_limpio
                        or similitud(titulo_ocr, titulo_actual_limpio) >= 0.68
                        or similitud_titulo_compacto(titulo_ocr, titulo_actual_limpio) >= 0.86
                    )
                    titulo_ocr_puede_reemplazar = (
                        not inferido.get("titulo")
                        or titulo_compacto_necesita_confirmacion(
                            {
                                "titulo_nombre_compacto": True,
                                "titulo_local": meta.get("titulo", ""),
                                "titulo_texto": inferido.get("titulo", ""),
                            },
                            inferido.get("titulo", ""),
                            autor_mobi_actual,
                        )
                        or len(titulo_ocr) > len(inferido.get("titulo", "")) + 2
                    )
                    if (
                        titulo_ocr
                        and _titulo_candidato_valido(titulo_ocr)
                        and _ruido_titulo_investigacion(titulo_ocr, autor_mobi_actual) < 35
                        and titulo_ocr_compatible
                        and titulo_ocr_puede_reemplazar
                    ):
                        inferido["titulo"] = titulo_ocr
                autor_portada = inferir_autor_desde_portada(
                    texto_portada,
                    meta.get("titulo") or inferido.get("titulo") or ruta.stem,
                )
                if autor_portada and (
                    not inferido.get("autor")
                    or not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", ""))
                    or not autor_aparece_en_texto(inferido.get("autor", ""), texto_portada)
                ):
                    inferido["autor"] = autor_portada
                for clave in ("editorial", "anio"):
                    if inferido_portada.get(clave) and not inferido.get(clave):
                        inferido[clave] = inferido_portada[clave]
                for isbn in extraer_isbns(texto_portada):
                    if isbn not in isbns:
                        isbns.append(isbn)
                ocr_result = portada_ocr
                if inferido.get("titulo") and inferido.get("autor"):
                    break
        except OperationCancelled:
            raise
        except Exception as exc:
            if callback:
                callback(f"OCR: {exc}")
    cbz_requiere_ocr_portada = ruta.suffix.lower() in {".cbz", ".cbr"}
    if cbz_requiere_ocr_portada and permitir_ocr:
        try:
            from ocr_engine import extraer_texto_imagen_bytes_ocr

            imagenes_cbz = imagenes_portada_cbz(ruta, max_imagenes=2)
            if callback and not imagenes_cbz:
                callback("OCR: no se encontró portada CBZ/CBR legible")
            for image_bytes in imagenes_cbz:
                if cancellation:
                    cancellation.raise_if_cancelled()
                if callback:
                    callback("OCR: analizando portada CBZ/CBR")
                portada_ocr = extraer_texto_imagen_bytes_ocr(
                    image_bytes, callback=callback, cancellation=cancellation,
                )
                texto_portada = portada_ocr.get("texto", "")
                if not texto_portada:
                    continue
                texto += "\n" + texto_portada
                aplicar_candidatos_ocr_portada(
                    portada_ocr,
                    inferido,
                    meta,
                    ruta,
                    titulo_actual=meta.get("titulo", "") or inferido.get("titulo", "") or ruta.stem,
                    autor_actual=meta.get("autor", "") or inferido.get("autor", ""),
                )
                inferido_portada = inferir_metadatos_desde_texto(texto_portada)
                for clave in ("titulo", "autor", "editorial", "anio"):
                    if inferido_portada.get(clave) and not inferido.get(clave):
                        inferido[clave] = inferido_portada[clave]
                autor_portada = inferir_autor_desde_portada(
                    texto_portada,
                    meta.get("titulo") or inferido.get("titulo") or ruta.stem,
                )
                if autor_portada and (
                    not inferido.get("autor")
                    or not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", ""))
                    or not autor_aparece_en_texto(inferido.get("autor", ""), texto_portada)
                ):
                    inferido["autor"] = autor_portada
                for isbn in extraer_isbns(texto_portada):
                    if isbn not in isbns:
                        isbns.append(isbn)
                ocr_result = portada_ocr
                if inferido.get("titulo") and inferido.get("autor"):
                    break
        except OperationCancelled:
            raise
        except Exception as exc:
            if callback:
                callback(f"OCR: {exc}")
    documento_requiere_ocr = (
        ruta.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
        and not (texto_documento.strip() and _texto_tiene_datos_utiles(texto_documento))
    )
    if documento_requiere_ocr and permitir_ocr:
        try:
            from ocr_engine import extraer_texto_documento_ocr

            ocr_result = extraer_texto_documento_ocr(
                ruta, max_paginas=max(1, min(int(max_paginas_ocr or 12), 200)),
                callback=callback, cancellation=cancellation,
            )
            texto_ocr = ocr_result.get("texto", "")
            if texto_ocr:
                texto += "\n" + texto_ocr
                aplicar_candidatos_ocr_portada(
                    ocr_result,
                    inferido,
                    meta,
                    ruta,
                    titulo_actual=meta.get("titulo", "") or inferido.get("titulo", "") or ruta.stem,
                    autor_actual=meta.get("autor", "") or inferido.get("autor", ""),
                )
                inferido_ocr = inferir_metadatos_desde_texto(texto_ocr)
                for clave in ("titulo", "autor", "editorial", "anio"):
                    if inferido_ocr.get(clave):
                        if clave in {"titulo", "autor"} and inferido.get(clave):
                            continue
                        inferido[clave] = inferido_ocr[clave]
                autor_portada = inferir_autor_desde_portada(
                    texto_ocr,
                    meta.get("titulo") or inferido.get("titulo") or ruta.stem,
                )
                if autor_portada and (
                    not inferido.get("autor")
                    or not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", ""))
                    or not autor_aparece_en_texto(inferido.get("autor", ""), texto_ocr)
                ):
                    inferido["autor"] = autor_portada
                isbns_ocr = extraer_isbns(texto_ocr)
                for isbn in isbns_ocr:
                    if isbn not in isbns:
                        isbns.append(isbn)
            elif callback and ocr_result.get("error"):
                callback(f"OCR: {ocr_result.get('error')}")
        except OperationCancelled:
            raise
        except Exception as exc:
            if callback:
                callback(f"OCR: {exc}")

    if inferido.get("autor") and not autor_es_usable(inferido.get("autor", ""), meta.get("editorial", "")):
        inferido["autor"] = ""
    if meta.get("titulo"):
        meta["titulo"] = limpiar_titulo_legible(meta["titulo"], meta.get("autor", ""))
    if inferido.get("titulo"):
        inferido["titulo"] = limpiar_titulo_legible(inferido["titulo"], inferido.get("autor", "") or meta.get("autor", ""))
    if mejor_par_nombre.get("titulo"):
        mejor_par_nombre["titulo"] = limpiar_titulo_legible(mejor_par_nombre["titulo"], mejor_par_nombre.get("autor", ""))

    texto_norm_contexto = normalizar_texto(texto[:120_000])
    anonimo_contexto = bool(
        "autor anonimo" in texto_norm_contexto
        or "firmado por anonimo" in texto_norm_contexto
        or "anonymous author" in texto_norm_contexto
    )
    colectivo_contexto = bool(
        re.search(r"\b(antologia|antologico|relatos|cuentos|seleccion|varios autores|various authors)\b", texto_norm_contexto)
    )

    consulta = nombre_pista or ruta.stem
    autor_consulta = (
        meta.get("autor", "")
        or meta.get("autor_ambiguo", "")
        or inferido.get("autor", "")
        or meta_nombre.get("autor", "")
        or mejor_par_nombre.get("autor", "")
    )
    titulo_consulta = limpiar_titulo_para_busqueda(
        meta.get("titulo", "")
        or inferido.get("titulo", "")
        or mejor_par_nombre.get("titulo", "")
        or nombre_pista
    )
    if autor_consulta and titulo_consulta and similitud(autor_consulta, titulo_consulta) >= 0.86:
        autor_consulta = ""
    if autor_consulta or titulo_consulta:
        consulta = " ".join([autor_consulta, titulo_consulta]).strip() or nombre_pista or ruta.stem
    titulo_nombre_compacto = bool(
        mejor_par_nombre.get("titulo")
        and titulo_proviene_de_token_compacto(ruta.name, mejor_par_nombre.get("titulo", ""), mejor_par_nombre.get("autor", ""))
    )
    tokens_compactos_nombre = extraer_tokens_compactos_nombre(
        ruta.name,
        mejor_par_nombre.get("autor", "") or meta.get("autor", "") or inferido.get("autor", ""),
    )
    if not mejor_par_nombre.get("titulo") and tokens_compactos_nombre:
        titulo_token = limpiar_titulo_legible(tokens_compactos_nombre[0], meta.get("autor", "") or inferido.get("autor", ""))
        if titulo_token and _titulo_candidato_valido(titulo_token):
            mejor_par_nombre = {
                "titulo": titulo_token,
                "autor": meta.get("autor", "") or inferido.get("autor", ""),
                "fuente": "nombre_compacto_token",
                "score": 72,
            }
            titulo_nombre_compacto = True
    titulo_inferido_final = inferido.get("titulo", "")
    texto_ocr_final = ocr_result.get("texto", "")
    titulo_texto_independiente = False
    if titulo_inferido_final:
        if texto_documento.strip() and _texto_tiene_datos_utiles(texto_documento):
            titulo_texto_independiente = True
        if texto_ocr_final and (
            similitud(titulo_inferido_final, texto_ocr_final) >= 0.55
            or similitud_titulo_compacto(titulo_inferido_final, texto_ocr_final) >= 0.78
            or normalizar_texto(titulo_inferido_final) in normalizar_texto(texto_ocr_final)
        ):
            titulo_texto_independiente = True

    if meta.get("autor") and any(
        titulo and similitud(meta.get("autor", ""), titulo) >= 0.86
        for titulo in (meta.get("titulo", ""), inferido.get("titulo", ""), mejor_par_nombre.get("titulo", ""))
    ):
        meta["autor"] = ""

    return {
        "isbns": isbns[:4],
        "dois": dois[:2],
        "titulo_local": meta.get("titulo", ""),
        "autor_local": meta.get("autor", ""),
        "autor_generico_local": meta.get("autor_generico", "") or meta_nombre.get("autor_generico", ""),
        "autor_generico_anonimo_contexto": anonimo_contexto,
        "autor_generico_colectivo_contexto": colectivo_contexto,
        "autor_ambiguo": meta.get("autor_ambiguo", ""),
        "editorial_local": meta.get("editorial", ""),
        "anio_local": meta.get("anio", ""),
        "titulo_texto": inferido.get("titulo", ""),
        "titulo_texto_independiente": titulo_texto_independiente,
        "autor_texto": inferido.get("autor", ""),
        "titulo_nombre": mejor_par_nombre.get("titulo", ""),
        "autor_nombre": mejor_par_nombre.get("autor", ""),
        "titulo_nombre_compacto": titulo_nombre_compacto,
        "tokens_compactos_nombre": tokens_compactos_nombre[:6],
        "pares_nombre": pares_nombre[:8],
        "editorial_texto": inferido.get("editorial", ""),
        "anio_texto": inferido.get("anio", ""),
        "ocr_texto": ocr_result.get("texto", ""),
        "ocr_metodo": ocr_result.get("metodo", ""),
        "ocr_idioma": ocr_result.get("idioma_detectado", ""),
        "ocr_paginas": ocr_result.get("paginas_analizadas", 0),
        "ocr_isbn": ocr_result.get("isbn_detectado", ""),
        "ocr_recomendado": bool(epub_requiere_ocr_portada or mobi_requiere_ocr_portada or cbz_requiere_ocr_portada or documento_requiere_ocr),
        "ocr_diferido_ejecutado": bool(ocr_result.get("metodo")),
        "tipo_documento": detectar_tipo_documento_desde_texto(texto, ruta),
        "consulta": consulta,
    }


def extraer_datos_rapidos(ruta: Path):
    isbns_nombre = extraer_isbns(ruta.name)
    nombre_pista = limpiar_nombre_como_pista(ruta.name)
    meta_nombre = extraer_metadatos_desde_nombre(nombre_pista)
    pares_nombre = generar_pares_nombre_archivo(ruta.name)
    mejor_par_nombre = pares_nombre[0] if pares_nombre else {}
    if meta_nombre.get("titulo") and meta_nombre.get("autor") and (
        not mejor_par_nombre
        or not mejor_par_nombre.get("autor")
        or float(mejor_par_nombre.get("score", 0)) < 70
    ):
        mejor_par_nombre = {
            "titulo": meta_nombre["titulo"],
            "autor": meta_nombre["autor"],
            "fuente": "nombre_separado",
            "score": 82,
        }
        pares_nombre = [mejor_par_nombre] + pares_nombre

    meta = {"titulo": "", "autor": "", "autor_ambiguo": "", "autor_generico": "", "editorial": "", "anio": "", "isbn": ""}
    suffix = ruta.suffix.lower()
    if suffix == ".epub":
        meta = extraer_metadatos_epub(ruta)
    elif suffix in KINDLE_EXTENSIONS:
        meta = extraer_metadatos_mobi(ruta)
    elif suffix == ".pdf":
        meta = extraer_metadatos_pdf(ruta)

    titulo_nombre = limpiar_titulo_desde_nombre_y_autor(nombre_pista, meta.get("autor", ""))
    if mejor_par_nombre.get("titulo"):
        titulo_nombre = limpiar_titulo_legible(mejor_par_nombre["titulo"], mejor_par_nombre.get("autor", ""))
    autor_nombre = mejor_par_nombre.get("autor", "") or meta_nombre.get("autor", "")
    if not titulo_nombre and meta_nombre.get("titulo"):
        titulo_nombre = limpiar_titulo_legible(meta_nombre["titulo"], autor_nombre)

    isbns = list(dict.fromkeys(isbns_nombre + extraer_isbns(" ".join(str(v) for v in meta.values()))))
    if meta.get("isbn"):
        mi = limpiar_isbn(meta["isbn"])
        if mi and mi not in isbns:
            isbns = [mi] + isbns

    consulta = " ".join([
        meta.get("autor", "") or autor_nombre or meta.get("autor_ambiguo", ""),
        limpiar_titulo_para_busqueda(meta.get("titulo", "") or titulo_nombre or nombre_pista),
    ]).strip() or nombre_pista or ruta.stem

    tokens_compactos_nombre = extraer_tokens_compactos_nombre(
        ruta.name,
        meta.get("autor", "") or autor_nombre,
    )
    texto_minimo = "\n".join([
        nombre_pista,
        meta.get("titulo", ""),
        meta.get("autor", ""),
        meta.get("editorial", ""),
        meta.get("isbn", ""),
    ])

    return {
        "isbns": isbns[:4],
        "dois": [],
        "titulo_local": limpiar_titulo_legible(meta.get("titulo", ""), meta.get("autor", "")) if meta.get("titulo") else "",
        "autor_local": meta.get("autor", ""),
        "autor_generico_local": meta.get("autor_generico", ""),
        "autor_generico_anonimo_contexto": False,
        "autor_generico_colectivo_contexto": False,
        "autor_ambiguo": meta.get("autor_ambiguo", ""),
        "editorial_local": meta.get("editorial", ""),
        "anio_local": meta.get("anio", ""),
        "titulo_texto": "",
        "titulo_texto_independiente": False,
        "autor_texto": "",
        "titulo_nombre": titulo_nombre,
        "autor_nombre": autor_nombre,
        "titulo_nombre_compacto": bool(
            titulo_nombre and titulo_proviene_de_token_compacto(ruta.name, titulo_nombre, meta.get("autor", "") or autor_nombre)
        ),
        "tokens_compactos_nombre": tokens_compactos_nombre[:6],
        "pares_nombre": pares_nombre[:8],
        "editorial_texto": "",
        "anio_texto": "",
        "ocr_texto": "",
        "ocr_metodo": "",
        "ocr_idioma": "",
        "ocr_paginas": 0,
        "ocr_isbn": "",
        "ocr_recomendado": False,
        "ocr_diferido_ejecutado": False,
        "tipo_documento": detectar_tipo_documento_desde_texto(texto_minimo, ruta),
        "consulta": consulta,
    }


def evidencia_rapida_suficiente(datos, local, libro: Path):
    if local.get("confianza", 0) < 94 or not local.get("encontrado"):
        return False
    if datos.get("tipo_documento") == "paper_academico" or datos.get("dois"):
        return False
    titulo = local.get("titulo", "")
    autor = local.get("autor", "")
    if not titulo or not autor:
        return False
    if not datos.get("titulo_local") or not datos.get("autor_local"):
        return False
    if datos.get("autor_ambiguo"):
        return False
    if titulo_compacto_necesita_confirmacion(datos, titulo, autor, libro):
        return False
    editorial = datos.get("editorial_local", "")
    if not autor_es_usable(autor, editorial, permitir_mononimo=True):
        return False
    if autor_parece_ruido_o_rol(autor) or _titulo_parece_contaminado_por_archivo(titulo):
        return False

    titulo_nombre = datos.get("titulo_nombre", "")
    autor_nombre = datos.get("autor_nombre", "")
    titulo_en_nombre = bool(titulo_nombre and similitud(titulo, titulo_nombre) >= 0.86)
    autor_en_nombre = bool(autor_nombre and similitud(autor, autor_nombre) >= 0.78)
    suffix = libro.suffix.lower()

    if suffix == ".pdf":
        return False
    if datos.get("isbns"):
        return True
    if titulo_en_nombre and autor_en_nombre:
        return True
    if suffix == ".epub" and datos.get("anio_local"):
        return True
    if suffix in KINDLE_EXTENSIONS and datos.get("anio_local") and titulo_en_nombre:
        return True
    return False


def resolver_rapido_si_seguro(libro: Path, callback=None, solo_analizar=False, datos=None, local=None):
    try:
        datos = datos if datos is not None else extraer_datos_rapidos(libro)
        local = local if local is not None else elegir_metadatos_locales(libro, datos)
        if not evidencia_rapida_suficiente(datos, local, libro):
            return None
        resultado = completar_resultado_estandar(
            local,
            datos,
            metodo="local_fast_structured",
            accion="solo_analizar" if solo_analizar else "renombrar",
        )
        resultado["motivo"] = f"{resultado.get('motivo', '')}; ruta rápida: metadatos estructurados suficientes"
        resultado = aplicar_consenso_bibliografico(libro, datos, resultado, [])
        if not resultado.get("encontrado"):
            return None
        if callback:
            callback(tr("pipeline_fast_path"))
        return resultado
    except Exception:
        return None


def analizar_archivo_rapido(libro: Path, callback=None, solo_analizar=False):
    libro = Path(libro)
    try:
        datos = extraer_datos_rapidos(libro)
        local = elegir_metadatos_locales(libro, datos)
        identidad = resolver_rapido_si_seguro(
            libro,
            callback=callback,
            solo_analizar=solo_analizar,
            datos=datos,
            local=local,
        )
        if identidad:
            identidad["estado_analisis"] = FAST_OK
            if callback:
                callback(tr("pipeline_fast_complete"))
            return _performance_pipeline.make_analysis_result(
                libro,
                FAST_OK,
                title=identidad.get("titulo", ""),
                author=identidad.get("autor", ""),
                year=identidad.get("anio", ""),
                isbn=identidad.get("isbn", ""),
                confidence=identidad.get("confianza_global", identidad.get("confianza", 0)),
                primary_method=identidad.get("metodo_identificacion", "local_fast_structured"),
                identity_result=identidad,
            )

        status = NEEDS_OCR if _performance_pipeline.supports_deferred_ocr(libro) else NEEDS_REVIEW
        return _performance_pipeline.make_analysis_result(
            libro,
            status,
            title=local.get("titulo", ""),
            author=local.get("autor", ""),
            year=local.get("anio", ""),
            isbn=local.get("isbn", ""),
            confidence=local.get("confianza", 0),
            primary_method="local_fast_incomplete",
        )
    except Exception as exc:
        return _performance_pipeline.make_analysis_result(
            libro,
            ERROR,
            primary_method="local_fast_error",
            error=str(exc),
        )


def recolectar_datos_con_ocr_diferido(libro: Path, callback=None, modo_analisis=DEEP_MODE, max_paginas_ocr=12, cancellation=None):
    datos = extraer_datos_locales(libro, callback=callback, permitir_ocr=False, cancellation=cancellation)
    if not datos.get("ocr_recomendado"):
        if callback:
            callback(tr("pipeline_ocr_skipped"))
        return datos

    if callback:
        callback(tr("pipeline_ocr_required"))
    if modo_analisis == FAST_MODE:
        return datos

    return extraer_datos_locales(
        libro,
        callback=callback,
        permitir_ocr=True,
        max_paginas_ocr=max_paginas_ocr,
        cancellation=cancellation,
    )


def aplicar_estado_analisis(resultado, datos):
    resultado = dict(resultado or {})
    resultado["estado_analisis"] = _performance_pipeline.final_status(
        resultado,
        used_ocr=bool((datos or {}).get("ocr_diferido_ejecutado") or (datos or {}).get("ocr_metodo")),
    )
    return resultado


def analizar_archivos_rapido_en_paralelo(
    libros,
    callback=None,
    event_callback=None,
    max_workers=None,
    solo_analizar=False,
    cancellation=None,
):
    return _performance_pipeline.process_fast_batch(
        libros,
        lambda libro: analizar_archivo_rapido(libro, callback=callback, solo_analizar=solo_analizar),
        max_workers=max_workers,
        event_callback=event_callback,
        cancellation=cancellation,
    )


def procesar_cola_ocr_diferido(
    analisis_rapidos,
    callback=None,
    event_callback=None,
    max_workers=None,
    solo_analizar=False,
    cancellation=None,
    max_paginas_ocr=None,
):
    if max_paginas_ocr is None:
        max_paginas_ocr = cargar_configuracion_operacion()["ocr_max_pages"]
    return _performance_pipeline.process_ocr_batch(
        analisis_rapidos,
        lambda libro: resolver_identidad_libro(
            libro,
            callback=callback,
            solo_analizar=solo_analizar,
            modo_analisis=DEEP_MODE,
            max_paginas_ocr=max_paginas_ocr,
            cancellation=cancellation,
        ),
        max_workers=max_workers,
        event_callback=event_callback,
        cancellation=cancellation,
    )


WEB_CACHE = _external_providers.WEB_CACHE


def _cache_key_web(url: str) -> str:
    return _external_providers.cache_key_web(url)


def _prune_web_cache():
    return _external_providers.prune_web_cache(MAX_WEB_CACHE_ENTRIES)


def estado_proveedores_web():
    return _external_providers.provider_health()


def http_get(url, accept="application/json"):
    return _external_providers.http_get(url, accept=accept, pause=PAUSA_WEB, max_cache_entries=MAX_WEB_CACHE_ENTRIES)


def extraer_anio(texto):
    return _external_providers.extraer_anio(texto)


def candidato(fuente, titulo="", autor="", anio="", isbn="", metodo="", identificador=""):
    return _external_providers.candidato(fuente, titulo, autor, anio, isbn, metodo, identificador, limpiar_isbn_func=limpiar_isbn)


def openlibrary_isbn(isbn):
    return _external_providers.openlibrary_isbn(isbn, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def openlibrary_busqueda(query, idioma=""):
    return _external_providers.openlibrary_busqueda(query, language=idioma, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def openlibrary_busqueda_autor(autor, limit=25):
    return _external_providers.openlibrary_busqueda_autor(
        autor,
        limit=limit,
        http_get_func=http_get,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
        autor_desde_nombre_es_usable_func=autor_desde_nombre_es_usable,
        limpiar_isbn_func=limpiar_isbn,
    )


def internetarchive_busqueda(query):
    return _external_providers.internetarchive_busqueda(query, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def gutendex_busqueda(query):
    return _external_providers.gutendex_busqueda(query, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def crossref_doi(doi):
    return _external_providers.crossref_doi(doi, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def crossref_busqueda(query):
    return _external_providers.crossref_busqueda(query, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def parse_crossref_item(item, metodo):
    return _external_providers.parse_crossref_item(item, metodo, limpiar_isbn_func=limpiar_isbn)


def openalex_doi(doi):
    return _external_providers.openalex_doi(doi, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def openalex_busqueda(query):
    return _external_providers.openalex_busqueda(query, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def parse_openalex_work(w, metodo):
    return _external_providers.parse_openalex_work(w, metodo, limpiar_isbn_func=limpiar_isbn)


def wikidata_busqueda(query, idiomas=None):
    return _external_providers.wikidata_busqueda(query, languages=idiomas, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def loc_busqueda(query):
    return _external_providers.loc_busqueda(query, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn)


def filtrar_consultas_web(consultas, usadas):
    return _orchestration.filtrar_consultas_web(
        consultas,
        usadas,
        normalizar_texto_func=normalizar_texto,
    )


def registrar_consulta_web_usada(datos, usadas, query, prefijo=""):
    return _orchestration.registrar_consulta_web_usada(
        datos,
        usadas,
        query,
        normalizar_texto_func=normalizar_texto,
        prefijo=prefijo,
    )


def invocar_proveedor_seguro(candidatos, proveedor_func, *args, **kwargs):
    return _orchestration.invocar_proveedor_seguro(candidatos, proveedor_func, *args, **kwargs)


def construir_proveedores_respaldo_busqueda(es_academico):
    return _orchestration.construir_proveedores_respaldo_busqueda(
        es_academico,
        loc_busqueda_func=loc_busqueda,
        wikidata_busqueda_func=wikidata_busqueda,
        crossref_busqueda_func=crossref_busqueda,
        openalex_busqueda_func=openalex_busqueda,
    )


def resultado_parada_temprana_web(libro, datos, candidatos, umbral):
    return _orchestration.resultado_parada_temprana_web(
        libro,
        datos,
        candidatos,
        umbral=umbral,
        hay_candidato_web_fuerte_func=_hay_candidato_web_fuerte,
        deduplicar_candidatos_func=deduplicar_candidatos,
    )


def invocar_proveedores_con_parada_temprana(libro, datos, candidatos, proveedores, argumento, umbral, **kwargs):
    return _orchestration.invocar_proveedores_con_parada_temprana(
        libro,
        datos,
        candidatos,
        proveedores,
        argumento,
        umbral=umbral,
        invocar_proveedor_seguro_func=invocar_proveedor_seguro,
        resultado_parada_temprana_web_func=resultado_parada_temprana_web,
        **kwargs,
    )


def consultar_web(libro: Path, callback=None, datos=None, busqueda_amplia=True, consultas_extra=None, incluir_identificadores=True):
    datos = datos or extraer_datos_locales(libro)
    candidatos = []
    isbns = datos.get("isbns", [])
    dois = datos.get("dois", [])
    consultas = generar_consultas_web(datos, libro)
    if consultas_extra:
        consultas.extend(consultas_extra)
    usadas = set(datos.setdefault("_consultas_web_usadas", []))
    consultas = filtrar_consultas_web(consultas, usadas)
    es_academico = datos.get("tipo_documento") == "paper_academico" or bool(dois)

    if incluir_identificadores and callback and isbns:
        callback(tr("metadata_confirm_isbn"))
    if incluir_identificadores:
        for isbn in isbns[:3]:
            resultado_temprano = invocar_proveedores_con_parada_temprana(
                libro,
                datos,
                candidatos,
                [
                    ("Open Library ISBN", openlibrary_isbn),
                ],
                isbn,
                umbral=95,
            )
            if resultado_temprano is not None:
                return resultado_temprano

    if incluir_identificadores and callback and dois:
        callback(tr("metadata_confirm_doi"))
    if incluir_identificadores:
        for doi in dois[:1]:
            resultado_temprano = invocar_proveedores_con_parada_temprana(
                libro,
                datos,
                candidatos,
                [
                    ("Crossref DOI", crossref_doi),
                    ("OpenAlex DOI", openalex_doi),
                ],
                doi,
                umbral=95,
            )
            if resultado_temprano is not None:
                return resultado_temprano

    if busqueda_amplia and consultas:
        if callback:
            callback(tr("metadata_confirm_search"))
        idioma_local = datos.get("idioma", "") or datos.get("idioma_probable", "")

        def openlibrary_busqueda_contextual(query):
            return openlibrary_busqueda(query, idioma=idioma_local)

        proveedores_principales = [("Open Library Search", openlibrary_busqueda_contextual)]
        proveedores_respaldo = construir_proveedores_respaldo_busqueda(es_academico)
        if datos.get("titulo_nombre_compacto"):
            for autor_compacto in autores_para_busqueda_compacta(datos):
                key_autor = "compact-author:" + normalizar_texto(autor_compacto)
                if key_autor in usadas:
                    continue
                registrar_consulta_web_usada(datos, usadas, autor_compacto, prefijo="compact-author:")
                resultado_temprano = invocar_proveedores_con_parada_temprana(
                    libro,
                    datos,
                    candidatos,
                    [("Open Library Author Search", openlibrary_busqueda_autor)],
                    autor_compacto,
                    umbral=96,
                    limit=25,
                )
                if resultado_temprano is not None:
                    return resultado_temprano
        for query_actual in consultas:
            registrar_consulta_web_usada(datos, usadas, query_actual)
            resultado_temprano = invocar_proveedores_con_parada_temprana(
                libro,
                datos,
                candidatos,
                proveedores_principales,
                query_actual,
                umbral=96,
            )
            if resultado_temprano is not None:
                return resultado_temprano

        consultas_respaldo = consultas[:2] if consultas else []
        for query_actual in consultas_respaldo:
            registrar_consulta_web_usada(datos, usadas, query_actual)
            resultado_temprano = invocar_proveedores_con_parada_temprana(
                libro,
                datos,
                candidatos,
                proveedores_respaldo,
                query_actual,
                umbral=96,
            )
            if resultado_temprano is not None:
                return resultado_temprano

    return datos, deduplicar_candidatos(candidatos)


def _hay_candidato_web_fuerte(libro: Path, datos, candidatos, umbral=96):
    candidatos = deduplicar_candidatos(candidatos)
    if not candidatos:
        return False
    try:
        mejor = elegir_mejor_metadato(libro, datos, candidatos)
    except Exception:
        return False
    return bool(mejor.get("encontrado") and mejor.get("confianza", 0) >= umbral)


def deduplicar_candidatos(candidatos):
    return _scoring.deduplicar_candidatos(candidatos)


def candidato_web_parece_ficha_de_autor(titulo: str, autor: str = "", datos=None) -> bool:
    datos = datos or {}
    titulo = limpiar_nombre_archivo(titulo, 140) if titulo else ""
    if not titulo:
        return False
    titulo_norm = normalizar_texto(titulo)
    if re.search(r"\b(author|autor|auteur|writer|escritor|novelista|poeta)\b", titulo_norm) and re.search(r"\b(?:18|19|20)\d{2}\b", titulo):
        return True

    titulo_limpio = re.sub(r"\([^)]*\)", " ", titulo)
    titulo_limpio = re.sub(r"(?i)\b(author|autor|auteur|writer|escritor|novelista|poeta)\b", " ", titulo_limpio)
    titulo_limpio = re.sub(r"\s+", " ", titulo_limpio).strip(" -_.,;")
    titulo_tokens = {t for t in normalizar_texto(titulo_limpio).split() if t}
    if len(titulo_tokens) < 2:
        return False

    titulos_ref = [
        titulo,
        datos.get("titulo_local", ""),
        datos.get("titulo_texto", ""),
        datos.get("titulo_nombre", ""),
    ]
    autores_ref = [
        autor,
        datos.get("autor_local", ""),
        datos.get("autor_nombre", ""),
        datos.get("autor_ambiguo", ""),
        datos.get("autor_texto", ""),
    ]
    for autor_ref in autores_ref:
        if autor_ref and any(t and similitud(autor_ref, t) >= 0.86 for t in titulos_ref):
            continue
        autor_tokens = {t for t in normalizar_texto(autor_ref).split() if t}
        if len(autor_tokens) >= 2 and titulo_tokens == autor_tokens:
            return True
        if autor_ref and similitud(titulo_limpio, autor_ref) >= 0.88:
            return True

    return bool(not autor and _linea_parece_nombre_autor(titulo_limpio))


def puntuar_candidato(libro: Path, c, datos):
    return _scoring.puntuar_candidato(
        libro,
        c,
        datos,
        candidato_web_parece_ficha_de_autor_func=candidato_web_parece_ficha_de_autor,
        linea_parece_nombre_autor_func=_linea_parece_nombre_autor,
        limpiar_nombre_como_pista_func=limpiar_nombre_como_pista,
        limpiar_titulo_para_busqueda_func=limpiar_titulo_para_busqueda,
        similitud_func=similitud,
        similitud_titulo_compacto_func=similitud_titulo_compacto,
        similitud_titulo_compacto_datos_func=similitud_titulo_compacto_datos,
        titulo_compacto_confirmado_por_candidato_func=titulo_compacto_confirmado_por_candidato,
        autor_es_usable_func=autor_es_usable,
        tokens_distintivos_titulo_func=tokens_distintivos_titulo,
        normalizar_texto_func=normalizar_texto,
    )


def diagnosticar_revision_metadatos(datos, candidatos=None, mejor=None, mejor_confianza=0):
    datos = datos or {}
    candidatos = candidatos or []
    motivos = []

    titulo_local = datos.get("titulo_local", "") or datos.get("titulo_texto", "") or datos.get("titulo_nombre", "")
    autor_local = datos.get("autor_local", "") or datos.get("autor_texto", "") or datos.get("autor_nombre", "") or datos.get("autor_ambiguo", "")
    pares_fuertes = [
        par for par in datos.get("pares_nombre", []) or []
        if par.get("titulo") and float(par.get("score", 0)) >= 70
    ]

    if not candidatos:
        motivos.append("sin_candidatos_externos")
    if not datos.get("isbns") and not datos.get("dois"):
        motivos.append("sin_identificador_fuerte")
    if not titulo_local and not pares_fuertes:
        motivos.append("nombre_sin_titulo_fiable")
    if not autor_local:
        motivos.append("autor_no_fiable")
    if datos.get("titulo_nombre_compacto") and mejor_confianza < UMBRAL_RENOMBRAR:
        motivos.append("titulo_compacto_no_confirmado")
    if candidatos and not any(c.get("titulo") and (c.get("autor") or c.get("isbn") or c.get("metodo") == "DOI") for c in candidatos):
        motivos.append("candidatos_externos_incompletos")
    if mejor and mejor.get("autor") and autor_local and similitud(mejor.get("autor", ""), autor_local) < 0.45:
        motivos.append("conflicto_autor_local_web")
    if mejor and mejor.get("titulo") and titulo_local and similitud(mejor.get("titulo", ""), titulo_local) < 0.55:
        motivos.append("conflicto_titulo_local_web")

    salida = []
    for motivo in motivos:
        if motivo not in salida:
            salida.append(motivo)
    return salida


def texto_diagnostico_revision(motivos):
    etiquetas = {
        "sin_candidatos_externos": "sin candidatos externos",
        "sin_identificador_fuerte": "sin ISBN/DOI local fuerte",
        "nombre_sin_titulo_fiable": "nombre sin título fiable",
        "autor_no_fiable": "autor no fiable",
        "titulo_compacto_no_confirmado": "título compacto no confirmado",
        "candidatos_externos_incompletos": "candidatos externos incompletos",
        "conflicto_autor_local_web": "conflicto entre autor local y web",
        "conflicto_titulo_local_web": "conflicto entre título local y web",
    }
    return ", ".join(etiquetas.get(m, m) for m in (motivos or []))


def adjuntar_diagnostico_revision(resultado, datos, candidatos=None, mejor=None, mejor_confianza=0, enriquecer_motivo=False):
    resultado = dict(resultado or {})
    motivos = diagnosticar_revision_metadatos(datos, candidatos, mejor, mejor_confianza)
    resultado["motivos_revision"] = motivos
    if enriquecer_motivo and motivos:
        texto = texto_diagnostico_revision(motivos)
        motivo_base = resultado.get("motivo", "") or "Sin coincidencia suficientemente fiable"
        if texto and texto not in motivo_base:
            resultado["motivo"] = f"{motivo_base}; diagnóstico: {texto}"
    return resultado


def clasificar_identidad_bibliografica(resultado, datos=None):
    resultado = resultado or {}
    datos = datos or {}
    confianza = float(resultado.get("confianza", 0) or 0)
    isbn = resultado.get("isbn", "")
    isbns_locales = set(datos.get("isbns", []) or [])
    titulo = resultado.get("titulo", "")
    autor = resultado.get("autor", "")

    obra = "indeterminada"
    edicion = "indeterminada"
    if isbn and isbn in isbns_locales:
        obra = "obra_confirmada"
        edicion = "edicion_confirmada_por_isbn"
    elif confianza >= UMBRAL_RENOMBRAR and titulo and autor:
        obra = "obra_probable"
        edicion = "edicion_no_confirmada"
    elif titulo and (autor or confianza >= 80):
        obra = "obra_posible"
        edicion = "edicion_desconocida"

    return {
        "obra": obra,
        "edicion": edicion,
        "confianza": confianza,
    }


def reforzar_candidato_dudoso_con_ia(libro: Path, datos, puntuados, mejor, mejor_confianza, mejor_motivo, judge=None):
    if not mejor or not _metadata_decision.should_call_ai_for_confidence(mejor_confianza):
        return None
    ai_config = cargar_configuracion_ia()
    usable, status = _ai_runtime_manager.can_use_ai(ai_config)
    if not usable and judge is None:
        return None

    candidatos_ia = [mejor]
    for candidato_item in sorted(puntuados or [], key=lambda x: x.get("score", 0), reverse=True):
        if candidato_item is mejor:
            continue
        clave = (
            normalizar_texto(candidato_item.get("titulo", "")),
            normalizar_texto(candidato_item.get("autor", "")),
            candidato_item.get("isbn", ""),
        )
        claves = {
            (
                normalizar_texto(c.get("titulo", "")),
                normalizar_texto(c.get("autor", "")),
                c.get("isbn", ""),
            )
            for c in candidatos_ia
        }
        if clave not in claves:
            candidatos_ia.append(candidato_item)
        if len(candidatos_ia) >= 6:
            break

    try:
        ai_result = request_ai_judgement(
            libro.name,
            datos,
            candidatos_ia,
            local_confidence=mejor_confianza,
            model_id=ai_config.get("model_id", ""),
            judge=judge,
        )
    except Exception as exc:
        return {
            "tipo": "review",
            "motivo": f"IA local no disponible: {exc}",
            "estado": status,
        }

    evaluation = _metadata_decision.evaluate_ai_decision(ai_result, datos)
    if evaluation.get("action") == "choose_candidate":
        ai_decision = evaluation.get("ai_decision", {})
        candidato_elegido = dict(evaluation["candidate"])
        if ai_decision.get("normalized_author"):
            candidato_elegido["autor"] = ai_decision["normalized_author"]
        if ai_decision.get("normalized_title"):
            candidato_elegido["titulo"] = ai_decision["normalized_title"]
        if ai_decision.get("detected_series"):
            candidato_elegido["serie_sugerida_ia"] = ai_decision["detected_series"]
        if ai_decision.get("detected_volume"):
            candidato_elegido["volumen_sugerido_ia"] = ai_decision["detected_volume"]
        if ai_decision.get("language"):
            candidato_elegido["idioma_sugerido_ia"] = ai_decision["language"]
        if ai_decision.get("problem_flags"):
            candidato_elegido["problem_flags_ia"] = list(ai_decision.get("problem_flags") or [])
        confianza = max(float(mejor_confianza or 0), min(94, float(evaluation.get("ai_confidence", 0) or 0)))
        motivo = f"{mejor_motivo}; reforzado por IA local ({round(confianza, 1)})"
        return {
            "tipo": "choose",
            "candidato": candidato_elegido,
            "confianza": confianza,
            "motivo": motivo,
            "decision": ai_decision,
        }
    return {
        "tipo": "review",
        "motivo": evaluation.get("reason", "La IA local pidió revisión humana"),
        "decision": evaluation.get("ai_decision", {}),
    }


def elegir_mejor_metadato(libro: Path, datos, candidatos):
    if not candidatos:
        resultado = _orchestration.resultado_sin_candidatos(libro.name)
        resultado = adjuntar_diagnostico_revision(resultado, datos, candidatos, enriquecer_motivo=False)
        resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
        return resultado

    puntuados = _orchestration.preparar_candidatos_puntuados(
        candidatos,
        datos,
        libro,
        limpiar_titulo_legible_func=limpiar_titulo_legible,
        candidato_web_parece_ficha_de_autor_func=candidato_web_parece_ficha_de_autor,
        puntuar_candidato_func=puntuar_candidato,
    )
    if not puntuados:
        resultado = _orchestration.resultado_candidatos_descartados(libro.name)
        resultado = adjuntar_diagnostico_revision(resultado, datos, candidatos, enriquecer_motivo=False)
        resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
        return resultado

    grupos = _orchestration.agrupar_candidatos_por_titulo(puntuados, similitud_func=similitud)
    isbns_locales = set(datos.get("isbns", []))
    mejor, mejor_confianza, mejor_motivo = _orchestration.seleccionar_mejor_candidato_por_grupos(grupos, isbns_locales)
    ai_refuerzo = reforzar_candidato_dudoso_con_ia(libro, datos, puntuados, mejor, mejor_confianza, mejor_motivo)
    if ai_refuerzo and ai_refuerzo.get("tipo") == "choose":
        mejor = ai_refuerzo["candidato"]
        mejor_confianza = ai_refuerzo["confianza"]
        mejor_motivo = ai_refuerzo["motivo"]
    elif ai_refuerzo and ai_refuerzo.get("tipo") == "review":
        resultado = _orchestration.resultado_baja_confianza(
            libro.name,
            mejor,
            min(mejor_confianza, 89),
            f"{mejor_motivo}; IA local: {ai_refuerzo.get('motivo', '')}",
            limpiar_titulo_legible_func=limpiar_titulo_legible,
        )
        resultado = _metadata_decision.merge_ai_review_reason(resultado, {"reason": ai_refuerzo.get("motivo", "")})
        resultado = adjuntar_diagnostico_revision(resultado, datos, candidatos, mejor, mejor_confianza, enriquecer_motivo=True)
        resultado["revision_explicada"] = explain_review_reasons(
            resultado.get("motivos_revision", []),
            (ai_refuerzo.get("decision") or {}).get("review_reasons", []),
        )
        resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
        return resultado

    if not mejor or mejor_confianza < UMBRAL_RENOMBRAR:
        resultado = _orchestration.resultado_baja_confianza(
            libro.name,
            mejor,
            mejor_confianza,
            mejor_motivo,
            limpiar_titulo_legible_func=limpiar_titulo_legible,
        )
        resultado = adjuntar_diagnostico_revision(resultado, datos, candidatos, mejor, mejor_confianza, enriquecer_motivo=True)
        resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
        return resultado

    editorial_final = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    autor_web = mejor.get("autor", "")
    autor_web_confirmado = autor_web_confirmado_por_local(autor_web, datos)
    autor_anonimo_confirmado = autor_anonimo_confirmado_por_web(autor_web, datos, mejor_confianza)
    if autor_web and not (
        autor_es_usable(autor_web, editorial_final)
        or autor_web_confirmado
        or autor_anonimo_confirmado
    ):
        autor_web = ""
    autor_final = elegir_autor_final(
        datos,
        autor_web=autor_web,
        libro=libro,
        permitir_mononimo_web=autor_web_confirmado,
    )
    if not autor_final and autor_anonimo_confirmado:
        autor_final = limpiar_nombre_archivo(autor_web, 90)
    titulo_final = elegir_titulo_final(datos, mejor.get("titulo", ""))
    titulo_final = limpiar_titulo_legible(titulo_final, autor_final)
    anio_final, isbn_final = _orchestration.resolver_anio_isbn_final(mejor, datos, isbns_locales)

    if not autor_final:
        resultado = {
            "encontrado": False,
            "confianza": min(mejor_confianza, 84),
            "nombre_sugerido": libro.name,
            "fuente": mejor.get("fuente", ""),
            "titulo": titulo_final,
            "autor": "",
            "anio": anio_final,
            "isbn": isbn_final,
            "cover_url": mejor.get("cover_url", ""),
            "motivo": f"{mejor_motivo}; autor no confirmado",
        }
        resultado = adjuntar_diagnostico_revision(resultado, datos, candidatos, mejor, mejor_confianza, enriquecer_motivo=True)
        resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
        return resultado

    nuevo_nombre = crear_nombre_sugerido(autor_final, titulo_final, anio_final, isbn_final, libro.suffix)

    resultado = {
        "encontrado": True,
        "confianza": mejor_confianza,
        "nombre_sugerido": nuevo_nombre,
        "fuente": mejor.get("fuente", ""),
        "titulo": titulo_final,
        "autor": autor_final,
        "anio": anio_final,
        "isbn": isbn_final,
        "cover_url": mejor.get("cover_url", ""),
        "motivo": mejor_motivo,
    }
    for clave in ("serie_sugerida_ia", "volumen_sugerido_ia", "idioma_sugerido_ia", "problem_flags_ia"):
        if mejor.get(clave):
            resultado[clave] = mejor[clave]
    if mejor.get("problem_flags_ia"):
        resultado.setdefault("advertencias", [])
        for flag in mejor["problem_flags_ia"]:
            if flag not in resultado["advertencias"]:
                resultado["advertencias"].append(flag)
    resultado["identidad_bibliografica"] = clasificar_identidad_bibliografica(resultado, datos)
    return resultado


def completar_resultado_estandar(resultado, datos, metodo="", accion=None):
    return _scoring.completar_resultado_estandar(resultado, datos, metodo=metodo, accion=accion)


def elegir_titulo_final(datos, titulo_web: str = "") -> str:
    return _orchestration.elegir_titulo_final(
        datos,
        titulo_web,
        limpiar_titulo_legible_func=limpiar_titulo_legible,
        normalizar_texto_func=normalizar_texto,
        tokens_distintivos_titulo_func=tokens_distintivos_titulo,
        similitud_titulo_compacto_func=similitud_titulo_compacto,
        similitud_titulo_compacto_datos_func=similitud_titulo_compacto_datos,
        similitud_func=similitud,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
    )


def _ruido_titulo_investigacion(titulo: str, autor: str = "") -> int:
    titulo = limpiar_nombre_archivo(titulo, 140) if titulo else ""
    if not titulo:
        return 100
    ruido = 0
    if _titulo_parece_contaminado_por_archivo(titulo):
        ruido += 25
    titulo_norm = normalizar_texto(titulo)
    titulo_tokens = titulo_norm.split()
    if len(titulo_tokens) > 14:
        ruido += 15
    if len(titulo_tokens) == 1 and len(titulo_norm) >= 12:
        ruido += 35
    if len(titulo_tokens) <= 1 and len(titulo_norm) < 5:
        ruido += 20
    raw_tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", titulo)
    if any(len(t) == 1 and t.isalpha() for t in raw_tokens):
        ruido += 8
    if re.search(r"(?i)\b(?:oh\s+ca\s+n|percas|elvys|bercebus|mad\s*math|ikero|bookmobi|exth)\b", titulo):
        ruido += 25
    autor_tokens = {t for t in normalizar_texto(autor).split() if len(t) >= 4}
    if autor_tokens:
        if set(titulo_tokens) & autor_tokens:
            ruido += 20
        titulo_compacto = titulo_norm.replace(" ", "")
        if any(token in titulo_compacto for token in autor_tokens):
            ruido += 12
    return ruido


def elegir_titulo_mas_limpio_para_investigacion(titulos, autor: str = "") -> str:
    candidatos = []
    for titulo in titulos:
        titulo = limpiar_titulo_para_busqueda(titulo)
        if not _titulo_candidato_valido(titulo):
            continue
        candidatos.append(titulo)
    if not candidatos:
        return ""
    vistos = {}
    for titulo in candidatos:
        vistos.setdefault(normalizar_texto(titulo), titulo)
    candidatos = list(vistos.values())

    def puntaje(titulo):
        ruido = _ruido_titulo_investigacion(titulo, autor)
        tokens = normalizar_texto(titulo).split()
        estructura = 0
        if tokens and tokens[0] in PALABRAS_INICIO_TITULO:
            estructura += 6
        if 2 <= len(tokens) <= 8:
            estructura += 8
        elif len(tokens) == 1:
            estructura += 2
        return (100 - ruido) + estructura - max(0, len(tokens) - 10)

    return max(candidatos, key=puntaje)


def _autor_investigacion_usable(autor: str, datos) -> bool:
    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    autor = limpiar_nombre_archivo(autor, 90) if autor else ""
    if not autor or autor_parece_ruido_o_rol(autor):
        return False
    if autor_es_anonimo_generico(autor) or normalizar_texto(autor) in {"varios", "various", "vv aa"}:
        return False
    return (
        autor_es_usable(autor, editorial, permitir_mononimo=True)
        or autor_desde_nombre_es_usable(autor, permitir_mononimo=True)
        or autor_mononimo_estructurado_confiable(autor, editorial)
    )


def _puntuar_hipotesis_local(hipotesis, datos, libro: Path):
    autor = hipotesis.get("autor", "")
    titulo = hipotesis.get("titulo", "")
    if not titulo or not autor:
        return 0, "hipótesis incompleta"
    if not _autor_investigacion_usable(autor, datos):
        return 0, "autor no fiable"
    if not _titulo_candidato_valido(titulo):
        return 0, "título no fiable"
    if _ruido_titulo_investigacion(titulo, autor) >= 35:
        return 0, "título contaminado"
    compactado_sin_confirmar = titulo_compacto_necesita_confirmacion(datos, titulo, autor, libro)

    score = 50
    motivos = []
    titulo_local = datos.get("titulo_local", "")
    titulo_texto = datos.get("titulo_texto", "")
    titulo_nombre = datos.get("titulo_nombre", "")
    autor_local = datos.get("autor_local", "")
    autor_texto = datos.get("autor_texto", "")
    autor_nombre = datos.get("autor_nombre", "")
    nombre_pista = limpiar_nombre_como_pista(libro.name)

    if titulo_local and similitud(titulo, titulo_local) >= 0.88:
        score += 16
        motivos.append("título en metadatos")
    if titulo_texto and similitud(titulo, titulo_texto) >= 0.80:
        score += 10
        motivos.append("título en texto")
    if titulo_nombre and similitud(titulo, titulo_nombre) >= 0.80:
        score += 12
        motivos.append("título en nombre")
    if nombre_pista and similitud(titulo, nombre_pista) >= 0.70:
        score += 8
        motivos.append("nombre de archivo compatible")

    if autor_local and similitud(autor, autor_local) >= 0.82:
        score += 16
        motivos.append("autor estructurado")
    if autor_texto and autor_texto_es_confiable(autor_texto, datos, libro) and similitud(autor, autor_texto) >= 0.72:
        score += 10
        motivos.append("autor en texto")
    if autor_nombre and similitud(autor, autor_nombre) >= 0.72:
        score += 12
        motivos.append("autor en nombre")
    if nombre_pista and normalizar_texto(autor).replace(" ", "") in normalizar_texto(nombre_pista).replace(" ", ""):
        score += 8
        motivos.append("autor aparece en archivo")

    if datos.get("isbns"):
        score += 7
        motivos.append("ISBN local")
    if datos.get("anio_local") or datos.get("anio_texto"):
        score += 2
    if hipotesis.get("fuente") == "pares_nombre":
        score += min(8, max(0, (float(hipotesis.get("score", 0)) - 60) / 4))
    if hipotesis.get("fuente") == "web_apoyo":
        score += 5
    if compactado_sin_confirmar and hipotesis.get("fuente") != "web_apoyo":
        score -= 35
        motivos.append("título compactado requiere confirmación bibliográfica")

    titulo_tokens = set(normalizar_texto(titulo).split())
    autor_tokens = {t for t in normalizar_texto(autor).split() if len(t) >= 4}
    if titulo_tokens & autor_tokens:
        score -= 25
        motivos.append("autor mezclado en título")
    if _titulo_parece_contaminado_por_archivo(titulo):
        score -= 25
    if datos.get("tipo_documento") == "paper_academico":
        score -= 20

    return max(0, min(96, round(score, 1))), ", ".join(motivos or ["evidencia local"])


def investigar_hipotesis_locales(libro: Path, datos, local, web=None):
    """Reproduce la revisión manual: probar hipótesis limpias y descartar contradicciones."""
    hipotesis = []
    vistos = set()

    def agregar(autor, titulos, fuente, score=0):
        autor = limpiar_nombre_archivo(autor, 90) if autor else ""
        titulo = elegir_titulo_mas_limpio_para_investigacion(titulos, autor)
        clave = (normalizar_texto(autor), normalizar_texto(titulo))
        if not clave[0] or not clave[1] or clave in vistos:
            return
        vistos.add(clave)
        hipotesis.append({
            "autor": autor,
            "titulo": titulo,
            "fuente": fuente,
            "score": score,
        })

    autor_base = elegir_autor_final(datos, libro=libro)
    titulos_base = [
        local.get("titulo", ""),
        datos.get("titulo_local", ""),
        datos.get("titulo_texto", ""),
        datos.get("titulo_nombre", ""),
    ]
    if autor_base:
        agregar(autor_base, titulos_base, "autor_base")
        titulo_desde_autor = limpiar_titulo_desde_nombre_y_autor(limpiar_nombre_como_pista(libro.name), autor_base)
        if titulo_desde_autor:
            agregar(autor_base, [titulo_desde_autor] + titulos_base, "autor_base")

    for par in datos.get("pares_nombre", [])[:8]:
        agregar(par.get("autor", ""), [par.get("titulo", "")] + titulos_base, "pares_nombre", par.get("score", 0))

    meta_nombre = extraer_metadatos_desde_nombre(limpiar_nombre_como_pista(libro.name))
    if meta_nombre.get("autor") and meta_nombre.get("titulo"):
        agregar(meta_nombre["autor"], [meta_nombre["titulo"]] + titulos_base, "nombre_separado", 80)

    if web and web.get("autor") and web.get("titulo") and web.get("confianza", 0) >= 84:
        agregar(web.get("autor", ""), [web.get("titulo", "")] + titulos_base, "web_apoyo")

    mejor = None
    mejor_score = 0
    mejor_motivo = ""
    for hipotesis_item in hipotesis:
        score, motivo = _puntuar_hipotesis_local(hipotesis_item, datos, libro)
        if score > mejor_score:
            mejor = hipotesis_item
            mejor_score = score
            mejor_motivo = motivo

    if not mejor or mejor_score < UMBRAL_RENOMBRAR:
        return completar_resultado_estandar({
            "encontrado": False,
            "confianza": mejor_score,
            "nombre_sugerido": libro.name,
            "fuente": "Local investigation",
            "titulo": mejor.get("titulo", "") if mejor else local.get("titulo", ""),
            "autor": mejor.get("autor", "") if mejor else local.get("autor", ""),
            "anio": local.get("anio", "") or datos.get("anio_local", "") or datos.get("anio_texto", ""),
            "isbn": local.get("isbn", "") or (datos.get("isbns", [""])[0] if datos.get("isbns") else ""),
            "motivo": mejor_motivo or "sin hipótesis local suficientemente fiable",
        }, datos, metodo="investigacion_local", accion="dejar_igual")

    anio = datos.get("anio_local", "") or datos.get("anio_texto", "") or local.get("anio", "")
    isbn = local.get("isbn", "") or (datos.get("isbns", [""])[0] if datos.get("isbns") else "")
    return completar_resultado_estandar({
        "encontrado": True,
        "confianza": mejor_score,
        "nombre_sugerido": crear_nombre_sugerido(mejor["autor"], mejor["titulo"], anio, isbn, libro.suffix),
        "fuente": "Local investigation",
        "titulo": mejor["titulo"],
        "autor": mejor["autor"],
        "anio": anio,
        "isbn": isbn,
        "motivo": f"Investigación interna: {mejor_motivo}",
    }, datos, metodo="investigacion_local", accion="renombrar")


def evidencia_local_suficiente(datos, local):
    if not local.get("encontrado") or local.get("confianza", 0) < 94:
        return False
    if not local.get("autor") or not local.get("titulo"):
        return False
    if titulo_compacto_necesita_confirmacion(datos, local.get("titulo", ""), local.get("autor", "")):
        return False
    if datos.get("tipo_documento") == "paper_academico":
        return False
    if datos.get("isbns") and datos.get("titulo_local") and datos.get("autor_local"):
        return True
    if datos.get("titulo_local") and datos.get("autor_local") and not datos.get("autor_ambiguo"):
        return True
    if datos.get("titulo_texto") and datos.get("autor_texto") and autor_texto_es_confiable(datos.get("autor_texto", ""), datos):
        return True
    return False


def evidencia_local_conservadora_suficiente(datos, local, libro: Path):
    if datos.get("tipo_documento") == "paper_academico":
        return False
    if local.get("confianza", 0) < 84:
        return False
    titulo = local.get("titulo", "")
    autor = local.get("autor", "")
    if not titulo or not autor:
        return False
    if titulo_compacto_necesita_confirmacion(datos, titulo, autor):
        return False
    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    if not autor_es_usable(autor, editorial, permitir_mononimo=True):
        return False
    if autor_parece_ruido_o_rol(autor):
        return False
    if _titulo_parece_contaminado_por_archivo(titulo):
        return False
    titulo_tokens = set(normalizar_texto(titulo).split())
    autor_tokens = {t for t in normalizar_texto(autor).split() if len(t) >= 4}
    if titulo_tokens & autor_tokens:
        return False
    titulo_compacto = normalizar_texto(titulo).replace(" ", "")
    if any(token in titulo_compacto for token in autor_tokens):
        return False

    nombre_pista = limpiar_nombre_como_pista(libro.name)
    titulo_en_nombre = nombre_pista and similitud(titulo, nombre_pista) >= 0.70
    autor_en_nombre = nombre_pista and normalizar_texto(autor).replace(" ", "") in normalizar_texto(nombre_pista).replace(" ", "")
    autor_estructurado = bool(datos.get("autor_local")) and similitud(autor, datos.get("autor_local", "")) >= 0.88
    titulo_desde_texto = bool(datos.get("titulo_texto")) and similitud(titulo, datos.get("titulo_texto", "")) >= 0.90
    titulo_desde_metadato = bool(datos.get("titulo_local")) and similitud(titulo, datos.get("titulo_local", "")) >= 0.90

    return bool((autor_estructurado or autor_en_nombre) and (titulo_desde_metadato or titulo_desde_texto or titulo_en_nombre))


def debe_consultar_web(datos, local):
    if datos.get("dois") or datos.get("tipo_documento") == "paper_academico":
        return True
    if evidencia_local_suficiente(datos, local):
        return False
    if titulo_compacto_necesita_confirmacion(datos, local.get("titulo", ""), local.get("autor", "")):
        return True
    return True


def _agregar_consulta_unica(salida, vistos, *partes):
    query = " ".join(str(p or "").strip() for p in partes if str(p or "").strip())
    query = re.sub(r"\s+", " ", query).strip()
    key = normalizar_texto(query)
    if not query or len(key) < 4 or key in vistos:
        return
    vistos.add(key)
    salida.append(query)


def generar_consultas_recuperacion(datos, libro: Path, local, web, candidatos):
    titulos = []
    autores = []

    def add_titulo(valor):
        valor = limpiar_titulo_para_busqueda(valor)
        if valor and _titulo_candidato_valido(valor):
            titulos.append(valor)

    def add_autor(valor):
        valor = limpiar_nombre_archivo(valor, 90) if valor else ""
        if valor and (
            autor_es_usable(valor, datos.get("editorial_local", "") or datos.get("editorial_texto", ""), permitir_mononimo=True)
            or autor_ambiguo_para_busqueda(valor)
        ) and not autor_parece_ruido_o_rol(valor):
            autores.append(valor)

    for fuente in (datos, local, web):
        add_titulo(fuente.get("titulo", "") or fuente.get("titulo_local", "") or fuente.get("titulo_texto", "") or fuente.get("titulo_nombre", ""))
        add_autor(fuente.get("autor", "") or fuente.get("autor_local", "") or fuente.get("autor_texto", "") or fuente.get("autor_nombre", ""))

    for par in datos.get("pares_nombre", [])[:8]:
        add_titulo(par.get("titulo", ""))
        add_autor(par.get("autor", ""))

    for c in sorted(candidatos or [], key=lambda item: puntuar_candidato(libro, item, datos)[0], reverse=True)[:6]:
        add_titulo(c.get("titulo", ""))
        add_autor(c.get("autor", ""))

    limpio_nombre = _limpiar_nombre_para_candidatos(libro.name)
    if limpio_nombre:
        add_titulo(limpio_nombre)

    titulos_unicos = []
    autores_unicos = []
    vistos_t = set()
    vistos_a = set()
    for titulo in titulos:
        key = normalizar_texto(titulo)
        if key and key not in vistos_t:
            vistos_t.add(key)
            titulos_unicos.append(titulo)
    for autor in autores:
        key = normalizar_texto(autor)
        if key and key not in vistos_a:
            vistos_a.add(key)
            autores_unicos.append(autor)

    consultas = []
    vistos = set()
    for par in datos.get("pares_nombre", [])[:6]:
        _agregar_consulta_unica(consultas, vistos, par.get("autor", ""), par.get("titulo", ""))
        _agregar_consulta_unica(consultas, vistos, par.get("titulo", ""))

    for autor in autores_unicos[:4]:
        for titulo in titulos_unicos[:5]:
            _agregar_consulta_unica(consultas, vistos, autor, titulo)
            if len(consultas) >= 10:
                return consultas

    for titulo in titulos_unicos[:8]:
        _agregar_consulta_unica(consultas, vistos, titulo)
        if len(consultas) >= 12:
            break
    return consultas


def consultar_proveedores_auxiliares_recuperacion(libro: Path, datos, consultas):
    """Fallback bibliográfico controlado: solo corre durante recuperación activa."""
    if not consultas:
        return []
    candidatos = []
    usadas = set(datos.setdefault("_consultas_auxiliares_usadas", []))
    proveedores = [
        ("Internet Archive Recovery", internetarchive_busqueda),
        ("Gutendex Recovery", gutendex_busqueda),
    ]
    for query in consultas[:5]:
        key = normalizar_texto(query)
        if not key or key in usadas:
            continue
        usadas.add(key)
        datos["_consultas_auxiliares_usadas"] = sorted(usadas)
        for _nombre, func in proveedores:
            try:
                candidatos.extend(func(query))
            except Exception:
                pass
        if _hay_candidato_web_fuerte(libro, datos, candidatos, umbral=94):
            break
    return deduplicar_candidatos(candidatos)


def resolver_caso_dificil(libro: Path, datos, local, web, candidatos, callback=None):
    consultas = generar_consultas_recuperacion(datos, libro, local, web, candidatos)
    if consultas and callback:
        callback(tr("metadata_recovery"))

    nuevos_candidatos = []
    if consultas:
        datos, nuevos_candidatos = consultar_web(
            libro,
            callback=callback,
            datos=datos,
            busqueda_amplia=True,
            consultas_extra=consultas,
            incluir_identificadores=False,
        )

    auxiliares = []
    if consultas:
        auxiliares = consultar_proveedores_auxiliares_recuperacion(libro, datos, consultas)

    todos = deduplicar_candidatos(list(candidatos or []) + list(nuevos_candidatos or []) + list(auxiliares or []))
    web_recuperado = elegir_mejor_metadato(libro, datos, todos) if todos else web
    resultado = elegir_resultado_final(libro, datos, local, web_recuperado)
    if resultado.get("encontrado"):
        resultado["motivo"] = f"{resultado.get('motivo', '')}; recuperación activa con evidencia reutilizada"
        resultado["metodo"] = "recuperacion_activa"
        return resultado

    mejor = web_recuperado if web_recuperado.get("confianza", 0) >= web.get("confianza", 0) else web
    if mejor.get("confianza", 0) > resultado.get("confianza", 0):
        resultado = completar_resultado_estandar({
            "encontrado": False,
            "confianza": mejor.get("confianza", 0),
            "nombre_sugerido": libro.name,
            "fuente": mejor.get("fuente", ""),
            "titulo": mejor.get("titulo", ""),
            "autor": mejor.get("autor", ""),
            "anio": mejor.get("anio", ""),
            "isbn": mejor.get("isbn", ""),
            "motivo": mejor.get("motivo", "No reliable metadata found"),
        }, datos, metodo="sin_confianza", accion="dejar_igual")
    return resultado


ROLES_AUTOR_VALIDOS = {"author", "coauthor", "corporate_author"}
ROLES_CREDITO_SECUNDARIO = {
    "translator",
    "illustrator",
    "foreword_author",
    "editor",
    "compiler",
    "coordinator",
    "publisher",
    "series",
}


def detectar_rol_bibliografico(nombre: str, contexto: str = "") -> str:
    texto = normalizar_texto(f"{contexto} {nombre}")
    if not texto:
        return "unknown_name"
    reglas = [
        ("translator", r"\b(translated by|translation by|traduccion de|traducido por|traductor|traductora|traduit par|traducteur|traductrice|traduction de|traduzione di|traduttore|traduttrice|traduzido por|tradutor|tradutora|ubersetzt von|uebersetzt von|translator)\b"),
        ("illustrator", r"\b(illustrated by|illustrations by|ilustrado por|ilustraciones de|illustrator|ilustrador|ilustradora|illustre par|illustrateur|illustratrice|illustrato da|illustratore|ilustrado por)\b"),
        ("foreword_author", r"\b(foreword by|preface by|introduction by|prologo de|prologuista|introduccion de|prefacio de|preface de|avant propos de|introduzione di|prefazione di)\b"),
        ("compiler", r"\b(compiled by|compilado por|compilador|compiladora|recopilado por|recopilador|antologia de|seleccion de|selected by|selection by|anthology by|anthologie de|antologie de|compile par|compilateur)\b"),
        ("coordinator", r"\b(coordinado por|coordinador|coordinadora|coordinator|coordination by|coordonne par|coordinateur|coordinatore)\b"),
        ("editor", r"\b(edited by|editor|editado por|edicion de|edition by|editeur|editrice|curated by|curador|curadora|cura di)\b"),
        ("publisher", r"\b(editorial|publisher|press|ediciones|publishing|publishing house|maison d edition|editeur commercial|editore|verlag)\b"),
        ("series", r"\b(serie|saga|coleccion|collection|series|collana|reeks)\b"),
    ]
    for role, pattern in reglas:
        if re.search(pattern, texto):
            return role
    if autor_parece_entidad_no_persona(nombre):
        return "corporate_author" if autor_es_usable(nombre, permitir_entidad=True) else "publisher"
    if autor_es_usable(nombre, permitir_mononimo=True):
        return "author"
    return "unknown_name"


def crear_evidencia(source, field, value, confidence=0, role="", page_type="", positive=None, negative=None, warnings=None):
    return _scoring.crear_evidencia(
        source,
        field,
        value,
        confidence,
        role=role,
        page_type=page_type,
        positive=positive,
        negative=negative,
        warnings=warnings,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
    )


def _agregar_evidencia(evidencias, source, field, value, confidence=0, role="", page_type="", positive=None, negative=None, warnings=None):
    return _scoring.agregar_evidencia(
        evidencias,
        source,
        field,
        value,
        confidence,
        role=role,
        page_type=page_type,
        positive=positive,
        negative=negative,
        warnings=warnings,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
    )


def evidencias_desde_datos_locales(datos, libro: Path):
    evidencias = []
    if datos.get("titulo_local"):
        _agregar_evidencia(evidencias, "metadata_structured", "title", datos["titulo_local"], 85, positive=["structured_metadata"])
    if datos.get("autor_local"):
        _agregar_evidencia(evidencias, "metadata_structured", "author", datos["autor_local"], 85, role=detectar_rol_bibliografico(datos["autor_local"]), positive=["structured_metadata"])
    if datos.get("autor_generico_local"):
        role = "author" if autor_es_anonimo_generico(datos["autor_generico_local"]) or autor_es_colectivo_generico(datos["autor_generico_local"]) else "unknown_name"
        _agregar_evidencia(evidencias, "metadata_structured", "author", datos["autor_generico_local"], 72, role=role, positive=["generic_structured_author"])
    if datos.get("titulo_texto"):
        _agregar_evidencia(evidencias, "digital_text", "title", datos["titulo_texto"], 74, page_type="first_pages", positive=["first_pages"])
    if datos.get("autor_texto"):
        _agregar_evidencia(evidencias, "digital_text", "author", datos["autor_texto"], 70, role=detectar_rol_bibliografico(datos["autor_texto"]), page_type="first_pages", positive=["first_pages"])
    if datos.get("titulo_nombre"):
        _agregar_evidencia(evidencias, "filename", "title", datos["titulo_nombre"], 58, positive=["filename_hint"])
    if datos.get("autor_nombre"):
        autor_nombre_es_titulo = any(
            titulo and similitud(datos["autor_nombre"], titulo) >= 0.86
            for titulo in (datos.get("titulo_local", ""), datos.get("titulo_texto", ""), datos.get("titulo_nombre", ""))
        )
        if not autor_nombre_es_titulo:
            _agregar_evidencia(evidencias, "filename", "author", datos["autor_nombre"], 58, role=detectar_rol_bibliografico(datos["autor_nombre"]), positive=["filename_hint"])
    for isbn in datos.get("isbns", [])[:3]:
        _agregar_evidencia(evidencias, "local_isbn", "isbn", isbn, 92, positive=["valid_isbn"])
    if datos.get("anio_local"):
        _agregar_evidencia(evidencias, "metadata_structured", "year", datos["anio_local"], 68, positive=["structured_metadata"])
    elif datos.get("anio_texto"):
        _agregar_evidencia(evidencias, "digital_text", "year", datos["anio_texto"], 55, positive=["first_pages"])
    if datos.get("editorial_local"):
        _agregar_evidencia(evidencias, "metadata_structured", "publisher", datos["editorial_local"], 60)
    if datos.get("ocr_isbn"):
        _agregar_evidencia(evidencias, "ocr", "isbn", datos["ocr_isbn"], 78, positive=["ocr_valid_isbn"])
    if datos.get("ocr_texto") and (datos.get("titulo_texto") or datos.get("autor_texto")):
        _agregar_evidencia(evidencias, "ocr", "ocr_signal", "OCR aportó pistas locales", 55, positive=["ocr_hint"])
    return evidencias


def evidencias_desde_resultado_y_candidatos(resultado, candidatos):
    return _scoring.evidencias_desde_resultado_y_candidatos(
        resultado,
        candidatos,
        detectar_rol_bibliografico_func=detectar_rol_bibliografico,
        limpiar_nombre_archivo_func=limpiar_nombre_archivo,
    )


def _score_campo_consenso(valor_final, evidencias, field):
    return _scoring.score_campo_consenso(valor_final, evidencias, field, similitud_func=similitud)


def calculate_confidence(resultado, evidencias, datos=None):
    return _scoring.calculate_confidence(
        resultado,
        evidencias,
        datos,
        similitud_func=similitud,
        roles_credito_secundario=ROLES_CREDITO_SECUNDARIO,
        umbral_renombrar=UMBRAL_RENOMBRAR,
    )


def normalize_book_identity(resultado, datos=None, evidencias=None):
    return _scoring.normalize_book_identity(resultado, datos, evidencias)


def decide_final_action(resultado, consensus):
    return _scoring.decide_final_action(resultado, consensus)


def aplicar_consenso_bibliografico(libro: Path, datos, resultado, candidatos=None):
    evidencias = evidencias_desde_datos_locales(datos, libro)
    evidencias.extend(evidencias_desde_resultado_y_candidatos(resultado, candidatos or []))
    consenso = calculate_confidence(resultado, evidencias, datos)
    identidad = normalize_book_identity(resultado, datos, evidencias)
    accion = decide_final_action(resultado, consenso)
    deep_scan = datos.get("deep_identity") or ejecutar_deep_identity_scan(libro, datos, candidatos=candidatos or [])
    conflictos_deep = list(deep_scan.get("conflicts", []) or [])
    if conflictos_deep:
        consenso["conflicts"] = list(dict.fromkeys(list(consenso["conflicts"]) + conflictos_deep))
        accion = "revisar_nuevamente"

    out = dict(resultado)
    out["evidencia"] = identidad["evidencia"]
    out["otros_creditos"] = identidad["otros_creditos"]
    out["autor_principal"] = identidad["autor_principal"]
    out["titulo_completo"] = identidad["titulo_completo"]
    out["confianza_titulo"] = consenso["confidence_title"]
    out["confianza_autor"] = consenso["confidence_author"]
    out["confianza_global"] = max(float(out.get("confianza", 0) or 0), consenso["confidence_total"])
    out["razones_consenso"] = consenso["reasons"]
    out["conflictos"] = consenso["conflicts"]
    out["advertencias"] = list(dict.fromkeys(list(out.get("advertencias", [])) + consenso["warnings"]))
    out["decision_bibliografica"] = accion
    out["politica_identidad"] = ANALYSIS_CACHE_VERSION
    out["procedencia_identidad"] = identidad["evidencia"]
    out["requiere_revision_manual"] = accion in {"revision_rapida", "revisar_nuevamente"} or bool(consenso["conflicts"])
    if out.get("encontrado") and consenso["conflicts"]:
        out["encontrado"] = False
        out["accion_recomendada"] = "dejar_igual"
        out["metodo"] = "consenso_conflictivo"
        out["motivo"] = f"{out.get('motivo', '')}; consenso bloqueó el renombrado: {', '.join(consenso['conflicts'])}"
    elif out.get("encontrado") and accion != "renombrar":
        out["encontrado"] = False
        out["accion_recomendada"] = "dejar_igual"
        out["metodo"] = "consenso_insuficiente"
        out["motivo"] = (
            f"{out.get('motivo', '')}; consenso bloqueó el renombrado: "
            f"acción recomendada {accion}, confianza global {round(consenso['confidence_total'], 1)}"
        )
    elif out.get("encontrado"):
        out["motivo"] = f"{out.get('motivo', '')}; consenso bibliográfico: {round(out['confianza_global'], 1)}"
    return out


def ejecutar_deep_identity_scan(libro: Path, datos, candidatos=None):
    """Run the shared Deep Identity Scan and keep only short audit signals."""
    try:
        scan = _deep_identity_scorer.scan_identity_from_data(libro, datos or {}, candidates=candidatos or [])
        scan_publico = dict(scan)
        scan_publico.pop("evidence", None)
        datos["deep_identity"] = scan_publico
        return scan_publico
    except Exception as exc:
        datos["deep_identity_error"] = str(exc)[:160]
        return {
            "title": "",
            "author": "",
            "year": "",
            "isbn": "",
            "confidence": 0.0,
            "confidence_percent": 0,
            "decision": _deep_identity_scorer.UNIDENTIFIED,
            "evidence_summary": [],
            "warnings": [f"Deep Identity Scan no disponible: {str(exc)[:120]}"],
            "conflicts": [],
        }


def resultado_deep_identity_si_seguro(libro: Path, datos, local=None, candidatos=None):
    scan = datos.get("deep_identity") or ejecutar_deep_identity_scan(libro, datos, candidatos=candidatos)
    if scan.get("conflicts"):
        return None
    if scan.get("decision") != _deep_identity_scorer.AUTO_RENAME:
        return None
    confianza = float(scan.get("confidence_percent", 0) or 0)
    if confianza < UMBRAL_RENOMBRAR:
        return None

    titulo = limpiar_titulo_legible(scan.get("title", ""), scan.get("author", ""))
    autor = limpiar_nombre_archivo(scan.get("author", ""), 90) if scan.get("author") else ""
    if not autor and local and local.get("autor"):
        autor = limpiar_nombre_archivo(local.get("autor", ""), 90)
    if not titulo or not autor:
        return None
    if titulo_compacto_necesita_confirmacion(datos, titulo, autor, libro):
        return None
    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    if not autor_es_usable(autor, editorial, permitir_mononimo=True) or autor_parece_ruido_o_rol(autor):
        return None

    anio = scan.get("year", "") or (local or {}).get("anio", "") or datos.get("anio_local", "") or datos.get("anio_texto", "")
    isbn = scan.get("isbn", "") or (local or {}).get("isbn", "") or (datos.get("isbns", [""])[0] if datos.get("isbns") else "")
    resultado = {
        "encontrado": True,
        "confianza": confianza,
        "nombre_sugerido": crear_nombre_sugerido(autor, titulo, anio, isbn, libro.suffix),
        "fuente": "Deep Identity Scan",
        "titulo": titulo,
        "autor": autor,
        "anio": anio,
        "isbn": isbn,
        "motivo": "; ".join(scan.get("evidence_summary", []) or ["Deep Identity Scan"]),
        "advertencias": list(scan.get("warnings", [])),
        "deep_identity": scan,
    }
    return completar_resultado_estandar(resultado, datos, metodo="deep_identity_scan", accion="renombrar")


def resultado_deep_identity_como_revision(libro: Path, datos):
    scan = datos.get("deep_identity") or ejecutar_deep_identity_scan(libro, datos)
    confianza = float(scan.get("confidence_percent", 0) or 0)
    if confianza <= 0:
        return None
    return completar_resultado_estandar({
        "encontrado": False,
        "confianza": confianza,
        "nombre_sugerido": libro.name,
        "fuente": "Deep Identity Scan",
        "titulo": limpiar_titulo_legible(scan.get("title", ""), scan.get("author", "")),
        "autor": limpiar_nombre_archivo(scan.get("author", ""), 90) if scan.get("author") else "",
        "anio": scan.get("year", ""),
        "isbn": scan.get("isbn", ""),
        "motivo": "; ".join(scan.get("evidence_summary", []) or ["Deep Identity Scan sin confianza suficiente"]),
        "advertencias": list(scan.get("warnings", [])),
        "deep_identity": scan,
    }, datos, metodo="deep_identity_review", accion="dejar_igual")


def detect_duplicates(titulo_real: str, indice=None, umbral=0.96, autor: str = ""):
    return coincidencias_por_titulo_real_en_biblioteca(titulo_real, indice, umbral=umbral, autor=autor)


def titulo_parece_antologia_colectiva(titulo: str, datos=None, libro: Path | None = None) -> bool:
    datos = datos or {}
    contexto = " ".join(
        str(x or "")
        for x in [
            titulo,
            datos.get("titulo_local", ""),
            datos.get("titulo_texto", ""),
            datos.get("titulo_nombre", ""),
            libro.stem if libro else "",
        ]
    )
    contexto_norm = normalizar_texto(contexto)
    if re.search(r"\b(antologia|antologias|antologico|anthology|anthologie|antologie)\b", contexto_norm):
        return True
    return bool(
        datos.get("autor_generico_colectivo_contexto")
        and re.search(r"\b(varios autores|various authors|seleccion|seleccion de textos)\b", contexto_norm)
    )


def resolver_antologia_colectiva_sin_autor(libro: Path, datos, local):
    if datos.get("tipo_documento") == "paper_academico":
        return None
    titulo = limpiar_titulo_legible(
        local.get("titulo", "")
        or datos.get("titulo_local", "")
        or datos.get("titulo_texto", "")
        or datos.get("titulo_nombre", "")
    )
    if not titulo or not titulo_parece_antologia_colectiva(titulo, datos, libro):
        return None
    if float(local.get("confianza", 0) or 0) < 84:
        return None
    if not (datos.get("titulo_local") or datos.get("titulo_texto")):
        return None

    editorial = datos.get("editorial_local", "") or datos.get("editorial_texto", "")
    for autor in [
        local.get("autor", ""),
        datos.get("autor_local", ""),
        datos.get("autor_texto", ""),
        datos.get("autor_nombre", ""),
    ]:
        if autor and autor_es_usable(autor, editorial, permitir_mononimo=True) and not autor_parece_ruido_o_rol(autor):
            return None

    autor = "Varios autores"
    anio = local.get("anio", "") or datos.get("anio_local", "") or datos.get("anio_texto", "")
    isbn = local.get("isbn", "") or (datos.get("isbns", [""])[0] if datos.get("isbns") else "")
    confianza = max(UMBRAL_RENOMBRAR, min(92, float(local.get("confianza", 0) or 0) + 6))
    return completar_resultado_estandar({
        "encontrado": True,
        "confianza": confianza,
        "nombre_sugerido": crear_nombre_sugerido(autor, titulo, anio, isbn, libro.suffix),
        "fuente": "Local analysis",
        "titulo": titulo,
        "autor": autor,
        "anio": anio,
        "isbn": isbn,
        "motivo": "Antología colectiva: título confirmado localmente; sin autor principal individual",
        "advertencias": ["Autor principal inferido como colectivo por tratarse de una antología"],
    }, datos, metodo="antologia_colectiva", accion="renombrar")


def elegir_resultado_final(libro: Path, datos, local, web):
    if web.get("encontrado") and web.get("confianza", 0) >= UMBRAL_RENOMBRAR:
        return completar_resultado_estandar(web, datos, metodo="web_confirmado", accion="renombrar")

    if evidencia_local_suficiente(datos, local):
        local = dict(local)
        local["motivo"] = f"{local.get('motivo', '')}; evidencia local estructurada suficiente"
        return completar_resultado_estandar(local, datos, metodo="local_structured", accion="renombrar")

    deep_seguro = resultado_deep_identity_si_seguro(libro, datos, local)
    if deep_seguro:
        return deep_seguro

    investigado = investigar_hipotesis_locales(libro, datos, local, web)
    if investigado.get("encontrado"):
        return investigado

    antologia = resolver_antologia_colectiva_sin_autor(libro, datos, local)
    if antologia:
        return antologia

    if evidencia_local_conservadora_suficiente(datos, local, libro):
        local = dict(local)
        local["encontrado"] = True
        local["confianza"] = max(local.get("confianza", 0), 90)
        local["motivo"] = f"{local.get('motivo', '')}; evidencia local conservadora suficiente"
        return completar_resultado_estandar(local, datos, metodo="local_conservative", accion="renombrar")

    if (
        local.get("encontrado")
        and local.get("confianza", 0) >= UMBRAL_RENOMBRAR
        and not titulo_compacto_necesita_confirmacion(datos, local.get("titulo", ""), local.get("autor", ""), libro)
    ):
        local = dict(local)
        local["motivo"] = f"{local.get('motivo', '')}; sin confirmación web fuerte"
        return completar_resultado_estandar(local, datos, metodo="local_unconfirmed", accion="renombrar")

    deep_revision = resultado_deep_identity_como_revision(libro, datos)
    opciones = [web, local]
    if deep_revision:
        opciones.append(deep_revision)
    mejor = max(opciones, key=lambda item: float(item.get("confianza", 0) or 0))
    confianza_final = mejor.get("confianza", 0)
    motivo_final = mejor.get("motivo", "No reliable metadata found")
    if mejor is local and titulo_compacto_necesita_confirmacion(datos, local.get("titulo", ""), local.get("autor", ""), libro):
        confianza_final = min(confianza_final, 84)
        motivo_final = f"{motivo_final}; título compactado pendiente de confirmación bibliográfica"
    return completar_resultado_estandar({
        "encontrado": False,
        "confianza": confianza_final,
        "nombre_sugerido": libro.name,
        "fuente": mejor.get("fuente", ""),
        "titulo": mejor.get("titulo", ""),
        "autor": mejor.get("autor", ""),
        "anio": mejor.get("anio", ""),
        "isbn": mejor.get("isbn", ""),
        "motivo": motivo_final,
    }, datos, metodo="sin_confianza", accion="dejar_igual")


def _file_key_para_cache(path: Path, context=None) -> str:
    try:
        return context.sha256 if context is not None else calcular_hash(path)
    except Exception:
        return hashlib.sha256(str(path).encode("utf-8", errors="ignore")).hexdigest()


def _cache_analisis_es_decisivo(cached) -> bool:
    if not isinstance(cached, dict):
        return False
    if cached.get("no_es_libro"):
        return True
    confianza = max(float(cached.get("confianza_global", 0) or 0), float(cached.get("confianza", 0) or 0))
    accion = str(cached.get("accion_recomendada", "") or "").lower()
    if not cached.get("encontrado"):
        return False
    if accion not in {"renombrar", "solo_analizar"}:
        return False
    if confianza < UMBRAL_RENOMBRAR:
        return False
    if not str(cached.get("titulo", "")).strip() or not str(cached.get("autor", "")).strip():
        return False
    return True


def _leer_resumen_analisis_cache(libro: Path, context=None):
    try:
        from cache_engine import get_cached_file_analysis

        stat = libro.stat()
        cached = get_cached_file_analysis(
            _file_key_para_cache(libro, context),
            size=stat.st_size,
            modified_time=stat.st_mtime,
            max_age_days=30,
        )
        if not cached or cached.get("cache_version") != ANALYSIS_CACHE_VERSION:
            return None
        if not _cache_analisis_es_decisivo(cached):
            return None
        out = completar_resultado_estandar(
            cached,
            {
                "editorial_local": cached.get("editorial", ""),
                "idioma": cached.get("idioma", ""),
                "tipo_documento": cached.get("tipo_documento", "documento_desconocido"),
            },
            metodo=cached.get("metodo", "cache_local"),
            accion=cached.get("accion_recomendada", None),
        )
        for key in (
            "confianza_titulo",
            "confianza_autor",
            "confianza_global",
            "decision_bibliografica",
            "requiere_revision_manual",
            "no_es_libro",
        ):
            if key in cached:
                out[key] = cached[key]
        out["desde_cache"] = True
        out["motivo"] = f"{out.get('motivo', '')}; análisis reutilizado desde caché local".strip("; ")
        return out
    except Exception:
        return None


def _guardar_resumen_analisis_cache(libro: Path, resultado, context=None):
    try:
        from cache_engine import cache_file_analysis

        stat = libro.stat()
        accion_cache = resultado.get("accion_recomendada", "")
        if accion_cache == "solo_analizar":
            accion_cache = "renombrar" if resultado.get("encontrado") else "dejar_igual"
        resumen = {
            "cache_version": ANALYSIS_CACHE_VERSION,
            "encontrado": bool(resultado.get("encontrado", False)),
            "no_es_libro": bool(resultado.get("no_es_libro", False)),
            "nombre_sugerido": resultado.get("nombre_sugerido", libro.name),
            "titulo": resultado.get("titulo", ""),
            "autor": resultado.get("autor", ""),
            "isbn": resultado.get("isbn", ""),
            "cover_url": resultado.get("cover_url", ""),
            "anio": resultado.get("anio", ""),
            "editorial": resultado.get("editorial", ""),
            "idioma": resultado.get("idioma", ""),
            "tipo_documento": resultado.get("tipo_documento", ""),
            "fuente": resultado.get("fuente", ""),
            "confianza": resultado.get("confianza", 0),
            "confianza_titulo": resultado.get("confianza_titulo", 0),
            "confianza_autor": resultado.get("confianza_autor", 0),
            "confianza_global": resultado.get("confianza_global", 0),
            "metodo": resultado.get("metodo", ""),
            "accion_recomendada": accion_cache,
            "decision_bibliografica": resultado.get("decision_bibliografica", ""),
            "requiere_revision_manual": bool(resultado.get("requiere_revision_manual", False)),
            "advertencias": list(resultado.get("advertencias", []))[:8],
            "motivo": resultado.get("motivo", "")[:500],
        }
        if context is not None:
            context.assert_unchanged()
        cache_file_analysis(_file_key_para_cache(libro, context), libro, stat.st_size, stat.st_mtime, libro.suffix.lower(), resumen, resultado.get("confianza_global", resultado.get("confianza", 0)))
    except Exception:
        pass


def orchestrate_identification(libro: Path, callback=None, solo_analizar=False, modo_analisis=DEEP_MODE, max_paginas_ocr=None, cancellation=None):
    if cancellation:
        cancellation.raise_if_cancelled()
    context = _document_context.DocumentContext(libro)
    cached = _leer_resumen_analisis_cache(libro, context)
    if cached:
        if callback:
            callback(tr("pipeline_cache"))
        if solo_analizar:
            cached["accion_recomendada"] = "solo_analizar"
        return cached

    if callback:
        callback(tr("pipeline_level0"))
    analisis_rapido = analizar_archivo_rapido(libro, callback=callback, solo_analizar=solo_analizar)
    if analisis_rapido.get("status") == FAST_OK:
        resultado_rapido = analisis_rapido["identity_result"]
        _guardar_resumen_analisis_cache(libro, resultado_rapido, context)
        return resultado_rapido

    if max_paginas_ocr is None:
        max_paginas_ocr = cargar_configuracion_operacion()["ocr_max_pages"]
    datos = recolectar_datos_con_ocr_diferido(
        libro, callback=callback, modo_analisis=modo_analisis,
        max_paginas_ocr=max_paginas_ocr, cancellation=cancellation,
    )
    if not parece_libro_por_datos(libro, datos):
        resultado = completar_resultado_estandar({
            "encontrado": False,
            "no_es_libro": True,
            "confianza": 0,
            "nombre_sugerido": libro.name,
            "fuente": "Local analysis",
            "titulo": "",
            "autor": "",
            "anio": "",
            "isbn": "",
            "motivo": "El archivo no parece contener datos de libro suficientes",
        }, datos, metodo="no_es_libro", accion="dejar_igual")
        resultado = aplicar_consenso_bibliografico(libro, datos, resultado, [])
        _guardar_resumen_analisis_cache(libro, resultado, context)
        return aplicar_estado_analisis(resultado, datos)

    if callback and (datos.get("titulo_texto") or datos.get("autor_texto")):
        callback(tr("pipeline_level1"))
    if callback and datos.get("ocr_metodo"):
        callback(tr("pipeline_ocr_hint"))

    local = elegir_metadatos_locales(libro, datos)
    if not debe_consultar_web(datos, local):
        resultado = completar_resultado_estandar(local, datos, metodo="local_structured", accion="solo_analizar" if solo_analizar else "renombrar")
        resultado["motivo"] = f"{resultado.get('motivo', '')}; no se consultó web porque la evidencia local es suficiente"
        resultado = aplicar_consenso_bibliografico(libro, datos, resultado, [])
        _guardar_resumen_analisis_cache(libro, resultado, context)
        return aplicar_estado_analisis(resultado, datos)

    if callback:
        callback(tr("pipeline_external"))

    datos, candidatos = consultar_web(
        libro,
        callback=callback,
        datos=datos,
        busqueda_amplia=True,
    )
    if callback:
        callback(tr("pipeline_deep_identity"))
    ejecutar_deep_identity_scan(libro, datos, candidatos=candidatos)
    web = elegir_mejor_metadato(libro, datos, candidatos)
    resultado = elegir_resultado_final(libro, datos, local, web)
    if not resultado.get("encontrado"):
        resultado = resolver_caso_dificil(libro, datos, local, web, candidatos, callback=callback)
    resultado = aplicar_consenso_bibliografico(libro, datos, resultado, candidatos)
    if solo_analizar:
        resultado["accion_recomendada"] = "solo_analizar"
    _guardar_resumen_analisis_cache(libro, resultado, context)
    return aplicar_estado_analisis(resultado, datos)


def resolver_identidad_libro(libro: Path, callback=None, solo_analizar=False, modo_analisis=DEEP_MODE, max_paginas_ocr=None, cancellation=None):
    return orchestrate_identification(
        libro, callback=callback, solo_analizar=solo_analizar,
        modo_analisis=modo_analisis, max_paginas_ocr=max_paginas_ocr,
        cancellation=cancellation,
    )


def obtener_nombre_web(libro: Path, callback=None, modo_analisis=DEEP_MODE, cancellation=None):
    return resolver_identidad_libro(
        libro, callback=callback, modo_analisis=modo_analisis,
        cancellation=cancellation,
    )


def mover_a_final(libro: Path, nombre_destino: str, motivo: str = "", op_id: str | None = None) -> Path:
    """
    Mueve el archivo original a la biblioteca elegida.
    Si el movimiento falla, el archivo original queda en su ubicación.
    """
    if not biblioteca_configurada():
        raise RuntimeError(tr("no_library_selected"))
    return _file_transactions.mover_a_final(
        libro,
        nombre_destino,
        FINAL,
        motivo,
        op_id,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
    )


def mover_a_final_reemplazando(libro: Path, nombre_destino: str, existente: Path, motivo: str = "") -> tuple[Path, Path | None]:
    """
    Move a new preferred copy to the library after quarantining the previous copy.
    If moving the new file fails, the previous copy is restored when possible.
    """
    if not biblioteca_configurada():
        raise RuntimeError(tr("no_library_selected"))
    return _file_transactions.mover_a_final_reemplazando(
        libro,
        nombre_destino,
        existente,
        FINAL,
        motivo,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
        manifest_path=TRASH_MANIFEST_JSONL,
        trash_dir_name=TRASH_DIR_NAME,
    )


def reemplazar_archivo_transaccional(nuevo: Path, destino_existente: Path, base_cuarentena: Path | None = None, motivo: str = "") -> tuple[Path, Path | None]:
    """
    Replace an existing file by quarantining it first, then moving the new file.
    The old file is restored if the new move fails before verification.
    """
    return _file_transactions.reemplazar_archivo_transaccional(
        nuevo,
        destino_existente,
        base_cuarentena,
        motivo,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
        manifest_path=TRASH_MANIFEST_JSONL,
        trash_dir_name=TRASH_DIR_NAME,
    )


def renombrar_en_sitio_seguro(origen: Path, nuevo_nombre: str, motivo: str = "") -> Path:
    return _file_transactions.renombrar_en_sitio_seguro(
        origen,
        nuevo_nombre,
        motivo,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
    )


def restaurar_accion_undo(item):
    return _file_transactions.restaurar_accion_undo(
        item,
        journal_path=FILE_TRANSACTION_JOURNAL,
        app_data=APP_DATA,
    )
