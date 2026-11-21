# studio_archive.py

`write_studio_zip(name, project_type, main, files)` produces a normal ZIP with
the given `ArchiveFile(path, data)` members. The ZIP comment starts with the
ASCII line `Matplobbot-Studio-Project` and contains a UTF-8 JSON manifest with
`version`, `name`, `type`, `main` and `binary`. The `binary` bit string follows
the order of non-directory members and records whether each source field was
text or bytes. Ordinary extraction and existing relative paths work as before.

`read_studio_zip(data)` checks compressed, expanded, directory-index and file
count limits and uses the shared renderer allowlist for paths. It rejects
unsupported archive members and malformed metadata. It returns `StudioArchive`
with file data and the selected main path where known. For a legacy ZIP with
an ordinary comment or no comment, the parser proposes a conventional main or
a single unambiguous source path. An ambiguous archive can be inspected and
assigned a type and a text main file in Studio. An archive without a usable
text file cannot be imported.

The parser only uses the standard library and the renderer path policy. ZIP
members remain in memory and are never extracted to host paths. Keep compiler
file limits and import resource limits coordinated. Legacy export still works
for existing large projects even if the resulting ZIP exceeds the import limit.
Run `python -m unittest tests.test_studio_archive` before changing format or
validation rules.
