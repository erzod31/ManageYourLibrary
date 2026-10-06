import unittest
from pathlib import Path

import library_core


class MetadataEvidenceDecisionTests(unittest.TestCase):
    def test_multilingual_secondary_roles_are_detected(self):
        cases = {
            ("Jean Dupont", "traduit par Jean Dupont"): "translator",
            ("Maria Rossi", "illustrato da Maria Rossi"): "illustrator",
            ("Anne Martin", "preface de Anne Martin"): "foreword_author",
            ("Luigi Bianchi", "a cura di Luigi Bianchi"): "editor",
            ("Claire Durand", "anthologie de Claire Durand"): "compiler",
        }

        for (name, context), expected in cases.items():
            with self.subTest(context=context):
                self.assertEqual(library_core.detectar_rol_bibliografico(name, context), expected)

    def test_consensus_blocks_web_author_conflicting_with_strong_local_metadata(self):
        datos = {
            "titulo_local": "Taxi",
            "autor_local": "Khaled Al Khamissi",
            "isbns": [],
        }
        resultado = {
            "encontrado": True,
            "confianza": 95,
            "nombre_sugerido": "Laura Garcia - Taxi.epub",
            "fuente": "Wikidata",
            "titulo": "Taxi",
            "autor": "Laura Garcia",
            "anio": "",
            "isbn": "",
            "motivo": "fixture",
        }

        final = library_core.aplicar_consenso_bibliografico(Path("Taxi.epub"), datos, resultado, [resultado])

        self.assertFalse(final["encontrado"])
        self.assertEqual(final["metodo"], "consenso_conflictivo")
        self.assertIn("Autor contradice evidencia local", " ".join(final["conflictos"]))

    def test_authority_label_only_candidate_stays_as_weak_evidence(self):
        datos = {
            "titulo_local": "El proceso",
            "autor_local": "Franz Kafka",
            "isbns": [],
        }
        resultado = {
            "encontrado": True,
            "confianza": 91,
            "nombre_sugerido": "Franz Kafka - El proceso.epub",
            "fuente": "Wikidata",
            "titulo": "El proceso",
            "autor": "Franz Kafka",
            "anio": "",
            "isbn": "",
            "motivo": "fixture",
        }
        candidatos = [
            {
                "fuente": "Wikidata",
                "titulo": "El proceso",
                "autor": "",
                "score": 91,
                "source_scope": "authority_label",
            }
        ]

        final = library_core.aplicar_consenso_bibliografico(Path("El proceso.epub"), datos, resultado, candidatos)

        self.assertTrue(final["encontrado"])
        self.assertIn("candidato externo incompleto", " ".join(final["advertencias"]))
        self.assertGreaterEqual(final["confianza_global"], 85)


if __name__ == "__main__":
    unittest.main()
