from evolution_lab_v2 import artifacts


def test_archived_sha_used_for_downloaded_zip(tmp_path, monkeypatch):
    (tmp_path / '.git_archival.txt').write_text('node: 0123456789abcdef\n', encoding='utf-8')
    monkeypatch.setattr(artifacts, 'ROOT', tmp_path)
    record = artifacts.provenance()
    assert record['git_sha'] == '0123456789abcdef'
    assert record['source_origin'] == 'archive'
    assert record['git_status'] is None


def test_unsubstituted_placeholder_is_ignored(tmp_path, monkeypatch):
    (tmp_path / '.git_archival.txt').write_text('node: $Format:%H$\n', encoding='utf-8')
    monkeypatch.setattr(artifacts, 'ROOT', tmp_path)
    assert artifacts.archived_git_sha() is None
