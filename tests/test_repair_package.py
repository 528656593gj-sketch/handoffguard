import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "repair_package.py"
SPEC = importlib.util.spec_from_file_location("repair_package", MODULE_PATH)
repair = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules["repair_package"] = repair
SPEC.loader.exec_module(repair)


class RepairPackageTests(unittest.TestCase):
    def test_creates_clean_copy_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "delivery.zip"
            output = root / "repaired.zip"
            office_buffer = io.BytesIO()
            with zipfile.ZipFile(office_buffer, "w") as office:
                office.writestr("word/document.xml", "<document />")
            with zipfile.ZipFile(source, "w") as bundle:
                bundle.writestr("delivery/movie_final.mp4.mp4", b"video")
                bundle.writestr("delivery/movie_final_v2.mp4", b"video")
                bundle.writestr("delivery/notes.txt", office_buffer.getvalue())
                bundle.writestr("delivery/.DS_Store", b"junk")
                bundle.writestr("__MACOSX/delivery/._notes.txt", b"metadata")

            actions = repair.repair_zip(source, output)

            self.assertTrue(source.exists())
            with zipfile.ZipFile(output) as bundle:
                self.assertEqual(bundle.namelist(), ["delivery/movie_final.mp4", "delivery/notes.docx"])
            self.assertTrue(any("Removed duplicate" in action for action in actions))
            self.assertTrue(any("renamed extension to .docx" in action for action in actions))

    def test_converts_word_saved_srt_and_repairs_image_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "delivery.zip"
            output = root / "repaired.zip"
            office_buffer = io.BytesIO()
            document_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
            <w:p><w:r><w:t>1</w:t></w:r></w:p>
            <w:p><w:r><w:t>00:00:00,000 --&gt; 00:00:03,000</w:t></w:r></w:p>
            <w:p><w:r><w:t>Hello</w:t></w:r></w:p>
            </w:body></w:document>'''
            with zipfile.ZipFile(office_buffer, "w") as office:
                office.writestr("word/document.xml", document_xml)
            with zipfile.ZipFile(source, "w") as bundle:
                bundle.writestr("delivery/captions.srt.docx", office_buffer.getvalue())
                bundle.writestr("delivery/cover_03.jpg", b"\x89PNG\r\n\x1a\nimage")

            repair.repair_zip(source, output)

            with zipfile.ZipFile(output) as bundle:
                self.assertEqual(bundle.namelist(), ["delivery/captions.srt", "delivery/cover_03.png"])
                self.assertIn(b"00:00:00,000 --> 00:00:03,000", bundle.read("delivery/captions.srt"))


if __name__ == "__main__":
    unittest.main()
