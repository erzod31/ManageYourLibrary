import unittest
from pathlib import Path

import library_core
from metadata import orchestration


class ReviewFolderMetadataResolutionTests(unittest.TestCase):
    def top_pair(self, filename):
        pairs = library_core.generar_pares_nombre_archivo(filename)
        self.assertTrue(pairs, filename)
        return pairs[0]

    def test_filename_parser_strips_extension_from_author(self):
        meta = library_core.extraer_metadatos_desde_nombre("Superviviente - Chuck Palahniuk.epub")

        self.assertEqual(meta["titulo"], "Superviviente")
        self.assertEqual(meta["autor"], "Chuck Palahniuk")
        self.assertNotIn(".epub", meta["autor"].lower())

    def test_title_author_pattern_keeps_author_as_search_hint(self):
        meta = library_core.extraer_metadatos_desde_nombre("Taxi - Al Khamissi Khaled.epub")
        pair = self.top_pair("Taxi - Al Khamissi Khaled.epub")

        self.assertEqual(meta["titulo"], "Taxi")
        self.assertEqual(meta["autor"], "Al Khamissi Khaled")
        self.assertEqual(pair["titulo"], "Taxi")
        self.assertEqual(pair["autor"], "Al Khamissi Khaled")

    def test_anonymous_author_from_filename_is_preserved_as_generic_author(self):
        meta = library_core.extraer_metadatos_desde_nombre(
            "Anonymous - Las Mil y Una Noches (1997) [9789508100696].mobi"
        )

        self.assertEqual(meta["titulo"], "Las Mil y Una Noches")
        self.assertEqual(meta["autor_generico"], "Anonymous")

    def test_anonymous_author_with_isbn_can_resolve_from_filename(self):
        datos = {
            "isbns": ["9789508100696"],
            "titulo_local": "",
            "autor_local": "",
            "autor_generico_local": "Anonymous",
            "autor_generico_anonimo_contexto": False,
            "editorial_local": "",
            "anio_local": "1997",
            "titulo_texto": "Las Mil y Una Noches",
            "autor_texto": "",
            "titulo_nombre": "Las Mil y Una Noches",
            "autor_nombre": "",
            "titulo_nombre_compacto": False,
            "tokens_compactos_nombre": [],
            "tipo_documento": "libro_comercial",
        }

        result = library_core.elegir_metadatos_locales(
            Path("Anonymous - Las Mil y Una Noches (1997) [9789508100696].mobi"),
            datos,
        )

        self.assertEqual(result["autor"], "Anonymous")
        self.assertEqual(result["titulo"], "Las Mil y Una Noches")
        self.assertTrue(result["encontrado"])

    def test_ocr_gibberish_line_is_not_used_as_title(self):
        result = library_core.inferir_metadatos_desde_texto(
            "yee i, oe = BA ee uel she F- Ne es Fee . BS oa ae\n"
            "9789508100696"
        )

        self.assertEqual(result["titulo"], "")

    def test_repeated_title_is_collapsed(self):
        self.assertEqual(
            library_core.limpiar_titulo_legible("Fortunata y Jacinta - Fortunata y Jacinta"),
            "Fortunata y Jacinta",
        )

    def test_anonymous_author_without_isbn_can_be_confirmed_by_filename_and_year(self):
        datos = {
            "autor_generico_local": "Anonimo",
            "autor_generico_anonimo_contexto": False,
            "titulo_nombre": "La division azul en la Batalla de Krazny Bor",
            "titulo_local": "",
            "titulo_texto": "",
            "anio_local": "2010",
            "isbns": [],
        }

        self.assertEqual(library_core.autor_generico_local_confirmado(datos), "Anonimo")

    def test_short_uppercase_acronym_is_not_accepted_as_author(self):
        self.assertFalse(library_core.autor_es_usable("VCC", permitir_mononimo=True))

    def test_author_filename_check_accepts_inverted_variant(self):
        datos = {
            "autor_nombre": "Honore de Balzac",
            "titulo_nombre": "Grandeza y decadencia de Cesar Birotteau",
            "titulo_local": "Grandeza y decadencia de Cesar Birotteau",
            "titulo_texto": "",
            "editorial_local": "",
            "editorial_texto": "",
        }

        self.assertEqual(
            library_core.elegir_autor_final(
                datos,
                libro=Path("Grandeza y decadencia de Cesar Birotteau - Balzac Honore de.epub"),
            ),
            "Honore de Balzac",
        )

    def test_repeated_filename_title_does_not_block_text_author(self):
        datos = {
            "titulo_texto": "Fortunata y Jacinta",
            "autor_texto": "Benito Pérez Galdós",
            "titulo_nombre": "",
            "autor_nombre": "Fortunata y Jacinta",
            "titulo_local": "",
            "autor_local": "Fortunata y Jacinta",
            "editorial_local": "",
            "editorial_texto": "",
        }

        self.assertEqual(
            library_core.elegir_autor_final(
                datos,
                libro=Path("Fortunata y Jacinta - Fortunata y Jacinta.epub"),
            ),
            "Benito Pérez Galdós",
        )

    def test_title_author_from_text_and_repeated_filename_reaches_local_threshold(self):
        datos = {
            "titulo_texto": "Fortunata y Jacinta",
            "autor_texto": "Benito Pérez Galdós",
            "titulo_nombre": "",
            "autor_nombre": "Fortunata y Jacinta",
            "titulo_local": "",
            "autor_local": "Fortunata y Jacinta",
            "editorial_local": "",
            "editorial_texto": "",
            "anio_local": "2012",
            "isbns": [],
        }

        result = library_core.elegir_metadatos_locales(
            Path("Fortunata y Jacinta - Fortunata y Jacinta.epub"),
            datos,
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["titulo"], "Fortunata y Jacinta")
        self.assertEqual(result["autor"], "Benito Pérez Galdós")

    def test_filename_author_equal_to_title_is_not_deep_identity_author_evidence(self):
        datos = {
            "titulo_texto": "Fortunata y Jacinta",
            "autor_texto": "Benito Pérez Galdós",
            "titulo_nombre": "",
            "autor_nombre": "Fortunata y Jacinta",
        }

        evidences = library_core.evidencias_desde_datos_locales(
            datos,
            Path("Fortunata y Jacinta - Fortunata y Jacinta.epub"),
        )

        filename_authors = [
            e.get("value")
            for e in evidences
            if e.get("field") == "author" and e.get("source") == "filename"
        ]
        self.assertEqual(filename_authors, [])

    def test_ocr_uppercase_artifacts_are_removed_from_title(self):
        self.assertEqual(
            library_core.limpiar_titulo_legible("Tarzán Y y los hombres ERA hormiga ER"),
            "Tarzán y los hombres hormiga",
        )

    def test_compact_camelcase_mobi_name_builds_searchable_pair(self):
        pair = self.top_pair("IsaacAsimov.Elhombrebicentenarioyotrashistorias2.1.mobi")

        self.assertEqual(pair["autor"], "Isaac Asimov")
        self.assertEqual(pair["titulo"], "El hombre bicentenario y otras historias")

    def test_compact_version_suffix_is_removed_before_query_generation(self):
        name = "JohnScalzi.Laviejaguardiav1.2.mobi"
        pairs = library_core.generar_pares_nombre_archivo(name)
        datos = {"titulo_nombre": "", "autor_nombre": "", "pares_nombre": pairs, "isbns": []}

        queries = library_core.generar_consultas_web(datos, Path(name))

        self.assertEqual(queries[0], "John Scalzi La vieja guardia")
        self.assertIn("La vieja guardia", queries)
        self.assertTrue(all(".mobi" not in query.lower() for query in queries[:3]))

    def test_review_folder_compact_titles_are_segmented_by_general_vocabulary(self):
        cases = {
            "Don Winslow - Elpoderdelperro (2005).mobi": "El poder del perro",
            "Brenda Rickman Vantrease - Elmaestroiluminador (2005).mobi": "El maestro iluminador",
            "Cassandra Clare - Ciudaddeceniza (2009).mobi": "Ciudad de ceniza",
            "Cassandra Clare - Ciudaddecristal (2010).mobi": "Ciudad de cristal",
            "Charles Dickens - Historiadedosciudades (1859).mobi": "Historia de dos ciudades",
            "Alberto Vázquez-Figueroa - zquez Alienelpaisdelasmaravillas (2005).mobi": "Ali en el pais de las maravillas",
            "glasAdams.Lavidaeluniversoytodolodemas.v1.1.mobi": "La vida el universo y todo lo demas",
            "IraLevin.Lasposeidasdestepford1.1.mobi": "Las poseidas de stepford",
            "JohnNorman.GuerreroGor1.0.mobi": "Guerrero Gor",
            "Natsume Soseki - Soyungatov 10 (2010).mobi": "Soy un gato",
            "IsaacAsimov.Comodescubrimoselpetroleo.v1.0.mobi": "Como descubrimos el petroleo",
            "IsaacAsimov.Comodescubrimoslosnumeros.v1.0.mobi": "Como descubrimos los numeros",
            "KathrynStockett.Criadasyseñoras.1.1.mobi": "Criadas y señoras",
            "LNiven_JPournelle.Lapajaenelojodedios1.0.mobi": "La paja en el ojo de dios",
        }

        for filename, expected_title in cases.items():
            with self.subTest(filename=filename):
                titles = [p["titulo"] for p in library_core.generar_pares_nombre_archivo(filename)]
                meta_title = library_core.extraer_metadatos_desde_nombre(filename).get("titulo", "")
                compact_titles = [
                    library_core.limpiar_titulo_legible(token)
                    for token in library_core.extraer_tokens_compactos_nombre(filename, "")
                ]
                self.assertIn(expected_title, titles + [meta_title] + compact_titles)

    def test_partial_internal_title_does_not_override_full_compact_filename_title(self):
        datos = {
            "isbns": [],
            "titulo_local": "",
            "autor_local": "Alberto Vázquez-Figueroa",
            "anio_local": "2005",
            "titulo_texto": "de las maravillas",
            "autor_texto": "",
            "titulo_nombre": "Ali en el pais de las maravillas",
            "autor_nombre": "Alberto Vázquez-Figueroa",
            "titulo_nombre_compacto": True,
            "tokens_compactos_nombre": ["Alienelpaisdelasmaravillas"],
            "tipo_documento": "libro_comercial",
        }

        result = library_core.elegir_metadatos_locales(
            Path("Alberto Vázquez-Figueroa - zquez Alienelpaisdelasmaravillas (2005).mobi"),
            datos,
        )

        self.assertEqual(result["titulo"], "Ali en el pais de las maravillas")
        self.assertEqual(
            result["nombre_sugerido"],
            "Alberto Vázquez-Figueroa - Ali en el pais de las maravillas (2005).mobi",
        )

    def test_allende_is_not_split_as_allen_de_when_compact_title_is_present(self):
        pairs = library_core.generar_pares_nombre_archivo("IsabelAllende.LaSumaDeLosDias1.0.mobi")

        self.assertIn(
            ("Isabel Allende", "La Suma De Los Dias"),
            {(p["autor"], p["titulo"]) for p in pairs},
        )

    def test_inverted_author_with_final_particle_is_restored(self):
        meta = library_core.extraer_metadatos_desde_nombre("Eugenia Grandet - Balzac Honore de.epub")
        pairs = library_core.generar_pares_nombre_archivo("Eugenia Grandet - Balzac Honore de.epub")

        self.assertEqual(meta["titulo"], "Eugenia Grandet")
        self.assertEqual(meta["autor"], "Honore de Balzac")
        self.assertIn(("Honore de Balzac", "Eugenia Grandet"), {(p["autor"], p["titulo"]) for p in pairs})

    def test_short_ocr_noise_does_not_override_full_compact_filename_title(self):
        datos = {
            "isbns": [],
            "titulo_local": "",
            "autor_local": "Douglas Adams",
            "anio_local": "1982",
            "titulo_texto": "LAO)",
            "autor_texto": "Douglas Adams",
            "titulo_nombre": "La vida el universo y todo lo demas",
            "autor_nombre": "Douglas Adams",
            "titulo_nombre_compacto": True,
            "tokens_compactos_nombre": ["Lavidaeluniversoytodolodemas"],
            "tipo_documento": "libro_comercial",
        }

        result = library_core.elegir_metadatos_locales(
            Path("glasAdams.Lavidaeluniversoytodolodemas.v1.1.mobi"),
            datos,
        )

        self.assertEqual(result["titulo"], "La vida el universo y todo lo demas")

    def test_unicode_title_is_not_destroyed_by_search_cleanup(self):
        self.assertEqual(library_core.limpiar_titulo_para_busqueda("三体 ñ"), "三体 ñ")

    def test_multi_hyphen_coauthors_generate_combined_author_pair(self):
        pairs = library_core.generar_pares_nombre_archivo(
            "Roderick Gordon - Brian Williams - Profundidades (2008).mobi"
        )

        self.assertIn(
            ("Roderick Gordon y Brian Williams", "Profundidades"),
            {(p["autor"], p["titulo"]) for p in pairs},
        )
        self.assertIn(("Roderick Gordon", "Profundidades"), {(p["autor"], p["titulo"]) for p in pairs})
        self.assertIn(("Brian Williams", "Profundidades"), {(p["autor"], p["titulo"]) for p in pairs})

    def test_inverted_author_variant_is_used_as_search_hint_only(self):
        datos = {
            "titulo_nombre": "Taxi",
            "autor_nombre": "Al Khamissi Khaled",
            "pares_nombre": [{"autor": "Al Khamissi Khaled", "titulo": "Taxi", "score": 46}],
            "isbns": [],
        }

        queries = library_core.generar_consultas_web(datos, Path("Taxi - Al Khamissi Khaled.epub"))

        self.assertIn("Khaled Al Khamissi Taxi", queries)

    def test_low_confidence_result_carries_structured_review_reasons(self):
        result = library_core.elegir_mejor_metadato(
            Path("Entrada rota.epub"),
            {"titulo_nombre_compacto": True, "pares_nombre": [], "isbns": []},
            [{"titulo": "", "autor": "", "fuente": "Open Library", "metodo": "Búsqueda"}],
        )

        self.assertFalse(result["encontrado"])
        self.assertIn("motivos_revision", result)
        self.assertIn("sin_identificador_fuerte", result["motivos_revision"])
        self.assertIn("candidatos_externos_incompletos", result["motivos_revision"])

    def test_identity_classification_distinguishes_work_from_edition(self):
        edition = library_core.clasificar_identidad_bibliografica(
            {"titulo": "Taxi", "autor": "Khaled Al Khamissi", "isbn": "9781234567890", "confianza": 95},
            {"isbns": ["9781234567890"]},
        )
        work = library_core.clasificar_identidad_bibliografica(
            {"titulo": "Taxi", "autor": "Khaled Al Khamissi", "isbn": "", "confianza": 95},
            {"isbns": []},
        )

        self.assertEqual(edition["obra"], "obra_confirmada")
        self.assertEqual(edition["edicion"], "edicion_confirmada_por_isbn")
        self.assertEqual(work["obra"], "obra_probable")
        self.assertEqual(work["edicion"], "edicion_no_confirmada")

    def test_textual_consensus_is_capped_when_authors_conflict(self):
        group = [
            {"titulo": "Taxi", "autor": "Khaled Al Khamissi", "fuente": "Open Library", "score": 95},
            {"titulo": "Taxi", "autor": "Laura Garcia", "fuente": "Wikidata", "score": 95},
        ]

        _best, confidence, reason = orchestration.seleccionar_mejor_candidato_por_grupos([group], set())

        self.assertLessEqual(confidence, 88)
        self.assertIn("autores contradictorios", reason)

    def test_external_compact_word_file_is_loaded(self):
        self.assertIn("profundidades", library_core.PALABRAS_TITULO_COMPACTO)
        self.assertIn("shadow", library_core.PALABRAS_TITULO_COMPACTO)
        self.assertIn("mystere", library_core.PALABRAS_TITULO_COMPACTO)


if __name__ == "__main__":
    unittest.main()
