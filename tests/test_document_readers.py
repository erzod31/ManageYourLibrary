import tempfile
import unittest
import zipfile
from pathlib import Path

from core import document_readers


class DocumentReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_docx_extracts_structured_text_and_metadata(self):
        path = self.root / "book.docx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="urn:w"><w:p><w:t>Visible title</w:t></w:p></w:document>')
            archive.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="urn:cp" xmlns:dc="urn:dc"><dc:title>Book title</dc:title><dc:creator>Ada Author</dc:creator></cp:coreProperties>')

        result = document_readers.extract_document(path)

        self.assertIn("Visible title", result["text"])
        self.assertEqual(result["metadata"]["title"], "Book title")
        self.assertEqual(result["metadata"]["creator"], "Ada Author")

    def test_odt_extracts_content(self):
        path = self.root / "book.odt"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("content.xml", '<office:document xmlns:office="urn:o" xmlns:text="urn:t"><text:p>ODT content</text:p></office:document>')

        result = document_readers.extract_document(path)

        self.assertIn("ODT content", result["text"])
        self.assertEqual(result["method"], "odt_xml")

    def test_rtf_is_not_decoded_as_raw_binary(self):
        path = self.root / "book.rtf"
        path.write_text(r"{\rtf1\ansi Book\par Author Name}", encoding="latin-1")

        result = document_readers.extract_document(path)

        self.assertIn("Book", result["text"])
        self.assertIn("Author Name", result["text"])
        self.assertNotIn("\\rtf", result["text"])


if __name__ == "__main__":
    unittest.main()
