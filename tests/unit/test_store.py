"""Run records are polled while a worker rewrites them: a reader must never see a half-written file."""
import threading

from gruntly.store import Store, atomic_write


def test_a_poller_never_reads_a_half_written_record(tmp_path):
    st = Store(tmp_path, "r_race")
    st.dir.mkdir(parents=True)
    st.write_json("status.json", {"state": "running", "pad": "x" * 20000})
    stop, errors = threading.Event(), []

    def writer():
        i = 0
        while not stop.is_set():
            st.write_json("status.json", {"state": "running", "n": i, "pad": "x" * 20000})
            i += 1

    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(400):
            try:
                assert st.read_json("status.json")["state"] == "running"
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
    finally:
        stop.set()
        t.join()
    assert not errors, errors[:3]


def test_atomic_write_leaves_no_temp_file_and_replaces_the_old_content(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("old", encoding="utf8")
    atomic_write(f, "new")
    assert f.read_text(encoding="utf8") == "new" and [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_missing_record_reads_as_the_default(tmp_path):
    st = Store(tmp_path, "r_none")
    st.dir.mkdir(parents=True)
    assert st.read_json("nothing.json", {"d": 1}) == {"d": 1}
