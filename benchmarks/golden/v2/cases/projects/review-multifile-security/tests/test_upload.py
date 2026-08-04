from pathlib import Path
from zipfile import ZipFile

from services.upload import import_archive


def test_import_archive_extracts_regular_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "upload.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("notes/readme.txt", "hello")

    written = import_archive(archive_path, tmp_path / "data", "customer-42")

    assert [path.read_text() for path in written] == ["hello"]
