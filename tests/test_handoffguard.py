import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "handoffguard.py"
SPEC = importlib.util.spec_from_file_location("handoffguard", MODULE_PATH)
hg = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules["handoffguard"] = hg
SPEC.loader.exec_module(hg)


class HandoffGuardTests(unittest.TestCase):
    def test_detects_missing_empty_duplicate_and_multiple_finals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "movie_final.mp4").write_bytes(b"same")
            (root / "movie_final_v2.mp4").write_bytes(b"same")
            (root / "notes.txt").write_bytes(b"")
            entries = hg.load_entries(root)
            rules = {
                "required": [
                    {"label": "Video", "extensions": [".mp4"], "min_count": 1, "max_count": 1},
                    {"label": "Subtitle", "extensions": [".srt"], "min_count": 1},
                ]
            }
            codes = {item.code for item in hg.audit(entries, rules)}
            self.assertTrue({"EMPTY_FILE", "DUPLICATE_CONTENT", "MULTIPLE_FINALS", "MISSING_REQUIRED", "TOO_MANY_MATCHES"}.issubset(codes))

    def test_clean_package_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "movie_final.mp4").write_bytes(b"\x00\x00\x00\x18ftypisomvideo")
            (root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi", encoding="utf-8")
            rules = {"required": [{"label": "Video", "extensions": ["mp4"]}, {"label": "Subtitle", "extensions": ["srt"]}]}
            self.assertEqual(hg.audit(hg.load_entries(root), rules), [])

    def test_scans_zip_without_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "delivery.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("video/movie_final.mp4", b"video")
                bundle.writestr("captions.srt", "caption")
                bundle.writestr("__MACOSX/video/._movie_final.mp4", b"metadata")
            entries = hg.load_entries(archive)
            self.assertEqual([entry.path for entry in entries], ["captions.srt", "video/movie_final.mp4"])

    def test_repairs_legacy_zip_filename_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "delivery.zip"
            garbled = "成片_final.mp4".encode("utf-8").decode("cp437")
            with zipfile.ZipFile(archive, "w") as bundle:
                info = zipfile.ZipInfo(garbled)
                info.flag_bits &= ~0x800
                bundle.writestr(info, b"video")
            self.assertEqual(hg.load_entries(archive)[0].path, "成片_final.mp4")

    def test_detects_double_extension(self):
        entry = hg.FileEntry("movie_final.mp4.mp4", 5, "abc")
        self.assertIn("DOUBLE_EXTENSION", {item.code for item in hg.audit([entry])})

    def test_detects_extension_mismatch(self):
        entry = hg.FileEntry("project-notes.txt", 100, "abc", "zip-container")
        self.assertIn("EXTENSION_MISMATCH", {item.code for item in hg.audit([entry])})

    def test_cover_names_are_not_versions(self):
        entries = [
            hg.FileEntry("cover_01.png", 10, "one", "png"),
            hg.FileEntry("cover_02.png", 11, "two", "png"),
            hg.FileEntry("cover_03.png", 12, "three", "png"),
        ]
        self.assertNotIn("MULTIPLE_FINALS", {item.code for item in hg.audit(entries)})


if __name__ == "__main__":
    unittest.main()
