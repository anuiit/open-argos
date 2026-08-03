from pathlib import Path
from zipfile import ZipFile

from .path_utils import staging_path


def import_archive(archive_path: Path, data_root: Path, upload_name: str) -> list[Path]:
    destination = staging_path(data_root, upload_name)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = destination / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                output.write(source.read())
            written.append(target)
    return written
