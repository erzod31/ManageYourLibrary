import unittest
from pathlib import Path

import library_core
import ocr_engine
from bibliographic_validator import candidate_to_evidence
from book_identity_evidence import (
    canonical_isbn,
    evidence_from_existing_data,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    make_evidence,
    normalize_author,
    normalize_title,
)
from book_identity_scorer import (
    AUTO_RENAME,
    QUICK_REVIEW,
    REVIEW_AGAIN,
    UNIDENTIFIED,
    decision_for_confidence,
    group_equivalent_evidence,
    score_identity,
)
from front_matter_analyzer import analyze_front_matter, is_false_positive_heading
from kindle_identity_reader import build_kindle_identity_evidence
from pdf_identity_reader import (
    PDF_CORRUPT,
    PDF_MIXED,
    PDF_PROTECTED,
    PDF_SCANNED,
    PDF_TEXTUAL,
    PDF_UNKNOWN,
    classify_pdf_from_signals,
)


class DeepIdentityScanTests(unittest.TestCase):
    def test_title_normalization_removes_distribution_noise(self):
        normalized = normalize_title("Microsoft Word - El poder del perro (2005).mobi")

        self.assertIn("poder", normalized)
        self.assertIn("perro", normalized)
        self.assertNotIn("microsoft", normalized)
        self.assertNotIn("mobi", normalized)

    def test_author_normalization_inverts_comma_name_when_safe(self):
        self.assertEqual(normalize_author("García Márquez, Gabriel"), "gabriel garcia marquez")

    def test_author_normalization_keeps_corporate_author(self):
        self.assertEqual(normalize_author("University Press, Oxford"), "university press oxford")

    def test_non_latin_title_does_not_normalize_to_empty(self):
        self.assertEqual(normalize_title("三体"), "三体")

    def test_isbn10_validation_and_conversion(self):
        self.assertTrue(is_valid_isbn10("0306406152"))
        self.assertFalse(is_valid_isbn10("0306406153"))
        self.assertEqual(isbn10_to_isbn13("0306406152"), "9780306406157")
        self.assertEqual(canonical_isbn("0-306-40615-2"), "9780306406157")

    def test_isbn13_validation(self):
        self.assertTrue(is_valid_isbn13("9780306406157"))
        self.assertFalse(is_valid_isbn13("9780306406158"))

    def test_front_matter_penalizes_false_positive_headings(self):
        for line in ["Índice", "Table of Contents", "Capítulo 1", "Prólogo", "Editorial Planeta"]:
            with self.subTest(line=line):
                self.assertTrue(is_false_positive_heading(line))

    def test_front_matter_extracts_title_author_isbn_and_year(self):
        text = """
        El nombre de la rosa
        Umberto Eco
        Copyright 1980
        ISBN 978-84-376-0494-7
        """

        evidence = analyze_front_matter(text, source="epub_front_matter")
        fields = {(ev.field, ev.normalized) for ev in evidence}

        self.assertIn(("title", "nombre rosa"), fields)
        self.assertIn(("author", "umberto eco"), fields)
        self.assertIn(("year", "1980"), fields)
        self.assertIn(("isbn", "9788437604947"), fields)

    def test_equivalent_candidate_grouping_handles_accents(self):
        evidence = [
            make_evidence("title", "El niño ñandú", "metadata", 80),
            make_evidence("title", "El nino nandu", "front_matter", 70),
        ]

        groups = group_equivalent_evidence([ev for ev in evidence if ev], "title")

        self.assertEqual(len(groups), 1)
        self.assertGreaterEqual(groups[0]["score"], 90)

    def test_high_confidence_score_auto_renames(self):
        evidence = [
            make_evidence("title", "Cien años de soledad", "metadata", 82),
            make_evidence("title", "Cien anos de soledad", "front_matter", 72),
            make_evidence("author", "Gabriel García Márquez", "metadata", 82),
            make_evidence("author", "Gabriel Garcia Marquez", "external_source", 76),
            make_evidence("isbn", "9780307474728", "local_isbn", 90),
            make_evidence("isbn", "9780307474728", "Open Library", 92),
        ]

        result = score_identity([ev for ev in evidence if ev])

        self.assertEqual(result["decision"], AUTO_RENAME)
        self.assertGreaterEqual(result["confidence_percent"], 90)

    def test_contradiction_lowers_confidence(self):
        evidence = [
            make_evidence("title", "Taxi", "metadata", 82),
            make_evidence("title", "El gran Gatsby", "external_source", 86),
            make_evidence("author", "Khaled Al Khamissi", "metadata", 82),
        ]

        result = score_identity([ev for ev in evidence if ev])

        self.assertLess(result["confidence_percent"], 90)
        self.assertTrue(result["conflicts"])

    def test_poor_ocr_stays_conservative(self):
        evidence = [
            make_evidence("title", "Texto dudoso", "ocr", 80, quality=0.35),
            make_evidence("author", "Autor Dudoso", "ocr", 70, quality=0.35),
        ]

        result = score_identity([ev for ev in evidence if ev])

        self.assertNotEqual(result["decision"], AUTO_RENAME)
        self.assertIn("OCR", " ".join(result["warnings"]))

    def test_filename_only_stays_below_quick_review(self):
        evidence = [
            make_evidence("title", "La sombra", "filename", 48),
            make_evidence("author", "Autor Desconocido", "filename", 48),
        ]

        result = score_identity([ev for ev in evidence if ev])

        self.assertLessEqual(result["confidence_percent"], 64)
        self.assertEqual(result["decision"], REVIEW_AGAIN)

    def test_pdf_classifier_variants(self):
        text = "Texto útil " * 20

        self.assertEqual(classify_pdf_from_signals([text]), PDF_TEXTUAL)
        self.assertEqual(classify_pdf_from_signals([""], ocr_texts=[text]), PDF_SCANNED)
        self.assertEqual(classify_pdf_from_signals([text], ocr_texts=[text]), PDF_MIXED)
        self.assertEqual(classify_pdf_from_signals(encrypted=True), PDF_PROTECTED)
        self.assertEqual(classify_pdf_from_signals(errors=["broken xref"]), PDF_CORRUPT)
        self.assertEqual(classify_pdf_from_signals([""]), PDF_UNKNOWN)

    def test_decision_thresholds(self):
        self.assertEqual(decision_for_confidence(90), AUTO_RENAME)
        self.assertEqual(decision_for_confidence(75), QUICK_REVIEW)
        self.assertEqual(decision_for_confidence(50), REVIEW_AGAIN)
        self.assertEqual(decision_for_confidence(49.9), UNIDENTIFIED)

    def test_external_candidate_to_evidence_uses_allowed_short_fields(self):
        evidence = candidate_to_evidence({
            "fuente": "Open Library",
            "titulo": "El proceso",
            "autor": "Franz Kafka",
            "anio": "1925",
            "isbn": "9780805209990",
        })

        fields = {ev.field for ev in evidence}

        self.assertEqual(fields, {"title", "author", "year", "isbn"})

    def test_kindle_evidence_uses_existing_metadata_without_pdf_assumptions(self):
        datos = {"titulo_local": "Soy un gato", "autor_local": "Natsume Soseki"}

        evidence = build_kindle_identity_evidence(Path("Natsume Soseki - Soy un gato.mobi"), datos)

        self.assertTrue(any(ev.source == "metadata" and ev.field == "title" for ev in evidence))
        self.assertTrue(any(ev.source == "metadata" and ev.field == "author" for ev in evidence))

    def test_existing_data_evidence_does_not_require_long_text(self):
        datos = {
            "titulo_local": "El invencible",
            "autor_local": "Stanislaw Lem",
            "isbns": ["9780156440421"],
        }

        evidence = evidence_from_existing_data(datos, filename="Stanislaw Lem - El invencible.epub")

        self.assertTrue(evidence)
        self.assertFalse(any(len(ev.value) > 200 for ev in evidence))

    def test_library_core_deep_identity_safe_integration(self):
        datos = {
            "titulo_local": "Cien anos de soledad",
            "autor_local": "Gabriel Garcia Marquez",
            "anio_local": "1967",
            "isbns": ["9780307474728"],
        }
        candidate = {
            "fuente": "Open Library",
            "titulo": "Cien anos de soledad",
            "autor": "Gabriel Garcia Marquez",
            "anio": "1967",
            "isbn": "9780307474728",
        }
        path = Path("Cien anos de soledad.epub")

        scan = library_core.ejecutar_deep_identity_scan(path, datos, candidatos=[candidate])
        result = library_core.resultado_deep_identity_si_seguro(
            path,
            datos,
            {"autor": "Gabriel Garcia Marquez", "anio": "1967", "isbn": "9780307474728"},
        )

        self.assertEqual(scan["decision"], AUTO_RENAME)
        self.assertTrue(result["encontrado"])
        self.assertEqual(result["metodo"], "deep_identity_scan")

    def test_ocr_layout_prefers_large_cover_title_and_near_author(self):
        layout = {
            "lines": [
                {"text": "Colección Austral", "height": 20, "confidence": 70, "relative_position": "top", "y": 90},
                {"text": "El nombre de la rosa", "height": 82, "confidence": 91, "relative_position": "center", "y": 520},
                {"text": "Umberto Eco", "height": 34, "confidence": 88, "relative_position": "center", "y": 710},
                {"text": "Editorial", "height": 25, "confidence": 80, "relative_position": "bottom", "y": 1600},
            ]
        }

        result = ocr_engine.detect_title_author_candidates("El nombre de la rosa\nUmberto Eco", layout=layout)

        self.assertEqual(result["ocr_title_candidates"][0]["text"], "El nombre de la rosa")
        self.assertTrue(any(c["text"] == "Umberto Eco" for c in result["ocr_author_candidates"]))

    def test_library_core_applies_ocr_cover_candidates_conservatively(self):
        inferido = {"titulo": "", "autor": "", "anio": ""}
        meta = {"titulo": "", "autor": "", "editorial": ""}
        ocr_result = {
            "texto": "El nombre de la rosa\nUmberto Eco\n1980",
            "ocr_title_candidates": [{"text": "El nombre de la rosa", "score": 86}],
            "ocr_author_candidates": [{"text": "Umberto Eco", "score": 78, "role": "author"}],
            "ocr_year_candidates": ["1980"],
        }

        changed = library_core.aplicar_candidatos_ocr_portada(
            ocr_result,
            inferido,
            meta,
            Path("cover.png"),
        )

        self.assertTrue(changed)
        self.assertEqual(inferido["titulo"], "El nombre de la rosa")
        self.assertEqual(inferido["autor"], "Umberto Eco")
        self.assertEqual(inferido["anio"], "1980")

    def test_filename_author_equal_to_title_is_not_existing_data_evidence(self):
        evidences = evidence_from_existing_data(
            {
                "titulo_texto": "Fortunata y Jacinta",
                "autor_local": "Fortunata y Jacinta",
                "autor_texto": "Benito Pérez Galdós",
                "autor_nombre": "Fortunata y Jacinta",
            },
            "Fortunata y Jacinta - Fortunata y Jacinta.epub",
        )

        filename_authors = [ev.value for ev in evidences if ev.field == "author" and ev.source == "filename"]
        self.assertEqual(filename_authors, [])


if __name__ == "__main__":
    unittest.main()
