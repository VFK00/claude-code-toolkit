from cctk_core import SkipReport


def test_report_vide_est_falsy():
    r = SkipReport()
    assert not r
    assert r.total == 0
    assert r.lines() == []


def test_skip_entry_compte_et_classe():
    r = SkipReport()
    r.skip_entry("timestamp illisible", "/a.jsonl:4")
    r.skip_entry("timestamp illisible", "/a.jsonl:9")
    r.skip_entry("JSON invalide", "/b.jsonl:1")
    assert r.entries == 3
    assert r.files == 0
    assert r.total == 3
    assert r.reasons["timestamp illisible"] == 2


def test_skip_file_compte_a_part():
    r = SkipReport()
    r.skip_file("lecture impossible", "/c.jsonl")
    assert r.files == 1
    assert r.entries == 0
    assert bool(r) is True


def test_lines_detaille_motifs_et_exemples():
    r = SkipReport()
    r.skip_entry("timestamp illisible", "/a.jsonl:4")
    r.skip_file("lecture impossible", "/c.jsonl")
    text = "\n".join(r.lines())
    assert "1 entry" in text
    assert "1 file" in text
    assert "timestamp illisible" in text
    assert "/a.jsonl:4" in text


def test_lines_plafonne_les_exemples():
    r = SkipReport(max_samples=2)
    for i in range(10):
        r.skip_entry("JSON invalide", f"/a.jsonl:{i}")
    text = "\n".join(r.lines())
    assert text.count("/a.jsonl") == 2
    assert "JSON invalide x10" in text


def test_lines_sans_localisation():
    r = SkipReport()
    r.skip_entry("motif seul")
    assert any("motif seul" in line for line in r.lines())
