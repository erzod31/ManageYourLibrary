"""Analyze immutable input signatures before any user-authorized file mutation."""
from pathlib import Path

REVIEW_FIELDS = ('titulo', 'autor', 'isbn', 'anio', 'idioma', 'editorial', 'serie', 'edicion')


def field_comparison(previous, proposed):
    """Explain each proposed field without replacing a human-confirmed value."""
    previous, proposed = previous or {}, proposed or {}
    locked = set(previous.get('locked_fields') or [])
    if not locked and (previous.get('manual_lock') or previous.get('confirmed_correction')):
        locked = set(REVIEW_FIELDS)
    provenance = proposed.get('provenance') or {}
    rows = []
    for field in REVIEW_FIELDS:
        old, new = str(previous.get(field) or ''), str(proposed.get(field) or '')
        evidence = provenance.get(field, {}) if isinstance(provenance, dict) else {}
        source = evidence.get('source', evidence.get('fuente', '')) if isinstance(evidence, dict) else str(evidence)
        rows.append({'field': field, 'before': old, 'proposed': new,
                     'effective': old if field in locked else new or old,
                     'locked': field in locked, 'changed': old != new and bool(new),
                     'source': source or str(proposed.get('fuente') or '—'),
                     'reason': 'Corrección humana protegida' if field in locked else str(proposed.get('motivo') or 'Sin evidencia detallada')})
    return rows


def needs_review(metadata):
    return bool(not metadata or not metadata.get('encontrado') or metadata.get('requiere_revision_manual')
                or metadata.get('no_es_libro'))


def prepare_import(paths, store, analyzer, library, cancellation, progress=None, previous_plan=None, previous_catalog=None):
    paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
    cancellation.raise_if_cancelled()
    plan = previous_plan or store.create_plan('import_books', [{'action': 'analyze_and_import', 'source': path,
                                                               'destination': str(library)} for path in paths],
                                               metadata={'library': str(library)}, cancellation=cancellation)
    pending = [item for item in plan['items'] if item['state'] not in {'completed', 'skipped'}]
    metadata = dict(plan.get('metadata', {}).get('prepared_metadata', {}))
    previous_rows = {str(Path(row['ruta']).resolve()): row for row in (previous_catalog or {}).get('archivos', []) if row.get('ruta')}
    try:
        store.set_plan_state(plan['id'], 'applying')
        for position, item in enumerate(pending):
            cancellation.raise_if_cancelled()
            path = item['source']
            store.validate_item(plan['id'], item['ordinal'], cancellation=cancellation)
            prepared = item.get('result', {}).get('prepared_metadata')
            if prepared is not None:
                metadata[path] = dict(prepared)
                # Corrections may have been made while this preview was paused.
                comparisons = field_comparison(previous_rows.get(path), prepared)
                if any(row['locked'] and row['changed'] for row in comparisons):
                    metadata[path]['requiere_revision_manual'] = True
                    metadata[path]['motivo'] = 'La propuesta contradice correcciones humanas protegidas; revisar antes de mover o copiar.'
                store.set_item_state(plan['id'], item['ordinal'], 'pending',
                                     result={**item.get('result', {}), 'prepared_metadata': metadata[path]})
                if progress:
                    progress(position + 1, len(pending))
                continue
            from .reader_worker import ReaderFailure
            try:
                result = dict(analyzer(Path(path)) or {})
            except ReaderFailure as exc:
                result = {'encontrado': False, 'requiere_revision_manual': True,
                          'fuente': 'local_reader', 'motivo': str(exc)}
            store.validate_item(plan['id'], item['ordinal'], cancellation=cancellation)
            # Persist concise decision data, never OCR pages or document contents.
            allowed = {'titulo', 'autor', 'isbn', 'anio', 'idioma', 'editorial', 'serie', 'edicion',
                       'cover_url', 'encontrado', 'no_es_libro', 'confianza', 'confianza_global',
                       'nombre_sugerido', 'fuente', 'motivo', 'requiere_revision_manual', 'accion',
                       'provenance', 'confianza_titulo', 'confianza_autor', 'advertencias'}
            metadata[path] = {key: value for key, value in result.items() if key in allowed}
            comparisons = field_comparison(previous_rows.get(path), result)
            if any(row['locked'] and row['changed'] for row in comparisons):
                metadata[path]['requiere_revision_manual'] = True
                metadata[path]['motivo'] = 'La propuesta contradice correcciones humanas protegidas; revisar antes de mover o copiar.'
            store.set_item_state(plan['id'], item['ordinal'], 'pending',
                                 result={**item.get('result', {}), 'prepared_metadata': metadata[path]})
            if progress:
                progress(position + 1, len(pending))
        store.update_metadata(plan['id'], {**plan.get('metadata', {}), 'library': str(library), 'analyzed_preview': True,
                                          'prepared_metadata': metadata})
        store.set_plan_state(plan['id'], 'preview')
    except Exception:
        store.set_plan_state(plan['id'], 'paused')
        raise
    return store.get_plan(plan['id'])
