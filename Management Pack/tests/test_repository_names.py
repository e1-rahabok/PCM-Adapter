#  Copyright 2026 VCF Operations vCommunity Management Pack
"""No tracked file names an old repository, or names the management pack other than VCF vCommunity Adapter.

T-ADP-005a and T-ADP-025a, of R-ADP-005 and R-ADP-025 in spec/requirements/adapter.md. The test reads every text
file that git tracks, except two folders that name the old names and phrases to forbid them: the dated engineering
reviews and spec/requirements. The copyright line at the top of a code file, and the author line under it, are
left as they are, so they are skipped.

Run from the "Management Pack" folder:  python -m pytest tests
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXCLUDED_FOLDERS = ("docs/development-guide/engineering-review/", "spec/requirements/")

# The brackets keep each pattern from matching its own source line, so this file is checked like any other.
OLD_REPOSITORY_NAMES = re.compile(r"VCF-vCommunity-Adapte[r]|private-cloud-managemen[t]", re.IGNORECASE)
OTHER_PACK_NAMES = re.compile(r"\b(?:vCommunity M[P]|vCommunity Management Pac[k]|the pac[k])\b", re.IGNORECASE)

COPYRIGHT_LINE = re.compile(r"^\s*#\s*Copyright\b")
AUTHOR_LINE = re.compile(r"^\s*#\s*Author:")


def tracked_text_files():
    """{path relative to the repository: its lines}, for every tracked file outside EXCLUDED_FOLDERS that is text."""
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO).decode("utf-8").split("\0")
    files = {}
    for name in names:
        if not name or name.startswith(EXCLUDED_FOLDERS):
            continue
        data = (REPO / name).read_bytes()
        if b"\0" in data:
            continue
        try:
            files[name] = data.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue
    return files


def checked_lines(lines):
    """(line number, text) of each line, without a code file's copyright line and the author line under it."""
    skip_author = False
    for number, line in enumerate(lines, start=1):
        if COPYRIGHT_LINE.match(line):
            skip_author = True
            continue
        if skip_author and AUTHOR_LINE.match(line):
            skip_author = False
            continue
        skip_author = False
        yield number, line


def matches(pattern):
    return [
        f"{name}:{number}: {pattern.search(line).group(0)!r} in {line.strip()[:160]}"
        for name, lines in sorted(tracked_text_files().items())
        for number, line in checked_lines(lines)
        if pattern.search(line)
    ]


def test_the_checked_files_include_the_code_docs_and_tools():
    files = tracked_text_files()
    assert "README.md" in files
    assert "Management Pack/app/definition.py" in files
    assert "tools/README.md" in files
    assert not any(name.startswith(EXCLUDED_FOLDERS) for name in files)


def test_the_copyright_and_author_lines_are_skipped_and_the_rest_is_checked():
    lines = [
        "#  Copyright 2026 an example holder",
        "#  Author: someone",
        "# a comment that is checked",
        "#  Author: an author line that is not under a copyright line is checked",
    ]
    assert [number for number, _ in checked_lines(lines)] == [3, 4]


def test_other_names_match_as_whole_words_in_any_case():
    # Each phrase is split in two parts, for the same reason as the brackets above.
    for text in ("The Pa" "ck collects", "the pa" "ck's settings", "a VCOMMUNITY " "MP install",
                 "the vCommunity Management " "Pack"):
        assert OTHER_PACK_NAMES.search(text), text
    for text in ("the package", "the packs", "the pak file", "the VCF vCommunity Adapter"):
        assert not OTHER_PACK_NAMES.search(text), text


def test_no_file_names_an_old_repository():
    # R-ADP-005: the two old repository names.
    assert matches(OLD_REPOSITORY_NAMES) == []


def test_no_file_names_the_management_pack_another_way():
    # R-ADP-025: the management pack is the VCF vCommunity Adapter in every file.
    assert matches(OTHER_PACK_NAMES) == []
