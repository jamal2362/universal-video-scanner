"""
Deep test suite for the resource-efficient / crash-safe scanning changes.

Covers services/database.py (atomic + batched + reentrant save),
services/video_scanner.py (defer_save, bulk_scan_files: batching, parallelism,
failure isolation, bounded submission) and config env parsing.

External tools (hdrprobe / mediainfo / 7z) and network services are never
touched: run_hdrprobe / get_media_info are monkeypatched and poster callables
are stubs.
"""
import os
import sys
import json
import time
import threading
import importlib

import pytest

# Repo root is the parent of this tests/ directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import config
from services import database
from services import video_scanner as vs


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def clean_state():
    """Reset the shared in-memory DB before and after every test."""
    with database.scan_lock:
        database.scanned_files.clear()
        database.scanned_paths.clear()
    yield
    with database.scan_lock:
        database.scanned_files.clear()
        database.scanned_paths.clear()


def make_scan_deps(save_counter):
    """
    Build the dependency callables scan_video_file expects. Poster/TMDB stubs
    return empty so no network is used. ``save_counter`` is a list whose length
    counts save invocations.
    """
    def save_func():
        save_counter.append(1)

    fanart = lambda filename: (None, None)
    tmdb = lambda filename: (None, None, None, None, None, None)
    tmdb_by_id = lambda tmdb_id, mt: (None, None, None, None, None)
    credits = lambda tmdb_id, mt: ([], [])
    cached = lambda tmdb_id, url: None
    return save_func, fanart, tmdb, tmdb_by_id, credits, cached


def call_scan(monkeypatch, tmp_path, filename='movie.mkv', defer_save=False,
              report=None, tracks=None, save_counter=None):
    """Invoke scan_video_file with hdrprobe/mediainfo mocked and a real file."""
    if save_counter is None:
        save_counter = []
    f = tmp_path / filename
    f.write_bytes(b'\x00' * 2048)
    if report is None:
        report = {'video_tracks': [{'hdr': {'format': 'SDR'},
                                    'width': 1920, 'height': 1080}]}
    monkeypatch.setattr(vs, 'run_hdrprobe', lambda p: report)
    monkeypatch.setattr(vs, 'get_media_info', lambda p: tracks or [])
    save_func, fanart, tmdb, tmdb_by_id, credits, cached = make_scan_deps(save_counter)
    result = vs.scan_video_file(
        str(f), database.scanned_paths, database.scanned_files, database.scan_lock,
        save_func, fanart, tmdb, tmdb_by_id, credits, cached, defer_save=defer_save)
    return result, save_counter, str(f)


def fake_scan_factory(record=None, fail_paths=(), false_paths=(), none_paths=(),
                      sleep=0.0):
    """
    A stand-in for the scan wrapper used by bulk_scan_files. Records calls,
    mutates the shared DB under the lock (like the real one), and can be told to
    raise / return success=False / return None for specific paths.
    """
    if record is None:
        record = []

    def _scan(path, defer_save=False):
        if sleep:
            time.sleep(sleep)
        record.append((path, defer_save))
        if path in fail_paths:
            raise RuntimeError(f"boom:{path}")
        if path in none_paths:
            return None
        if path in false_paths:
            return {'success': False, 'message': 'not detected'}
        with database.scan_lock:
            database.scanned_files[path] = {'filename': os.path.basename(path)}
            database.scanned_paths.add(path)
        return {'success': True}

    _scan.record = record
    return _scan


# --------------------------------------------------------------------------- #
# database.save_database  (atomic / reentrant / concurrent)
# --------------------------------------------------------------------------- #

class TestSaveDatabase:

    def test_roundtrip(self, tmp_path):
        db = str(tmp_path / 'db.json')
        with database.scan_lock:
            database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv', 'x': 1}
            database.scanned_paths.add('/m/a.mkv')
        database.save_database(db)
        data = json.load(open(db))
        assert data['files']['/m/a.mkv']['filename'] == 'a.mkv'
        assert data['paths'] == ['/m/a.mkv']

    def test_load_roundtrip(self, tmp_path):
        db = str(tmp_path / 'db.json')
        database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv'}
        database.scanned_paths.add('/m/a.mkv')
        database.save_database(db)
        database.scanned_files.clear()
        database.scanned_paths.clear()
        database.load_database(db)
        assert database.scanned_files['/m/a.mkv']['filename'] == 'a.mkv'
        assert '/m/a.mkv' in database.scanned_paths

    def test_no_tempfiles_left_on_success(self, tmp_path):
        db = str(tmp_path / 'db.json')
        database.save_database(db)
        leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.scanned_files_')]
        assert leftovers == []

    def test_empty_db(self, tmp_path):
        db = str(tmp_path / 'db.json')
        database.save_database(db)
        data = json.load(open(db))
        assert data == {'files': {}, 'paths': []}

    def test_reentrant_save_while_holding_lock(self, tmp_path):
        """A plain Lock would deadlock here; RLock must not."""
        db = str(tmp_path / 'db.json')
        with database.scan_lock:
            database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv'}
            database.scanned_paths.add('/m/a.mkv')
            database.save_database(db)  # nested acquire
        assert json.load(open(db))['files']['/m/a.mkv']['filename'] == 'a.mkv'

    def test_previous_db_intact_on_replace_failure(self, tmp_path, monkeypatch):
        db = str(tmp_path / 'db.json')
        database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv'}
        database.save_database(db)
        good = open(db).read()

        # Second save: os.replace explodes mid-write.
        database.scanned_files['/m/b.mkv'] = {'filename': 'b.mkv'}
        monkeypatch.setattr(os, 'replace', lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        database.save_database(db)  # must be caught, not raised
        monkeypatch.undo()

        assert open(db).read() == good, "old DB was clobbered on failed write"
        leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.scanned_files_')]
        assert leftovers == [], "temp file not cleaned up after failure"

    def test_serialization_failure_no_temp_no_crash(self, tmp_path):
        db = str(tmp_path / 'db.json')
        database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv'}
        database.save_database(db)
        good = open(db).read()
        # Non-serializable object -> json.dumps raises inside the locked block.
        database.scanned_files['/m/bad'] = {'obj': {1, 2, 3}}  # a set
        database.save_database(db)  # must not raise
        assert open(db).read() == good
        leftovers = [n for n in os.listdir(tmp_path) if n.startswith('.scanned_files_')]
        assert leftovers == []

    def test_missing_directory_no_crash(self, tmp_path):
        db = str(tmp_path / 'does' / 'not' / 'exist' / 'db.json')
        database.save_database(db)  # mkstemp fails -> caught, no raise
        assert not os.path.exists(db)

    def test_no_dirname_uses_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        database.scanned_files['/m/a.mkv'] = {'filename': 'a.mkv'}
        database.save_database('db.json')  # no directory component
        assert json.load(open(tmp_path / 'db.json'))['files']['/m/a.mkv']

    def test_fsync_invoked(self, tmp_path, monkeypatch):
        db = str(tmp_path / 'db.json')
        calls = []
        real = os.fsync
        monkeypatch.setattr(os, 'fsync', lambda fd: calls.append(fd) or real(fd))
        database.save_database(db)
        assert calls, "fsync not called - durability path skipped"

    def test_valid_json_after_overwrite(self, tmp_path):
        db = str(tmp_path / 'db.json')
        for i in range(5):
            database.scanned_files[f'/m/{i}.mkv'] = {'filename': f'{i}.mkv'}
            database.scanned_paths.add(f'/m/{i}.mkv')
            database.save_database(db)
        data = json.load(open(db))
        assert len(data['files']) == 5

    def test_concurrent_saves_and_mutations(self, tmp_path):
        """
        Many threads mutate the DB (under the lock) and save concurrently.
        Must never raise 'dict changed size during iteration' and must always
        leave valid JSON. This is exactly the race the RLock snapshot guards.
        """
        db = str(tmp_path / 'db.json')
        errors = []

        def worker(n):
            try:
                for i in range(50):
                    key = f'/m/t{n}_{i}.mkv'
                    with database.scan_lock:
                        database.scanned_files[key] = {'filename': key}
                        database.scanned_paths.add(key)
                    database.save_database(db)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, errors
        data = json.load(open(db))  # must be parseable
        assert len(data['files']) == 8 * 50

    def test_snapshot_consistent_while_mutating(self, tmp_path):
        """
        A writer thread hammers the dict while the main thread saves repeatedly.
        Every produced file must be valid JSON (snapshot is taken under lock).
        """
        db = str(tmp_path / 'db.json')
        stop = threading.Event()
        errors = []

        def mutator():
            i = 0
            while not stop.is_set():
                # Bounded key space (256) so the snapshot stays small and fast;
                # the point is concurrent mutation during the save, not volume.
                key = f'/m/{i % 256}.mkv'
                with database.scan_lock:
                    database.scanned_files[key] = {'filename': f'{i}.mkv'}
                    database.scanned_paths.add(key)
                i += 1
                if i % 64 == 0:
                    time.sleep(0)  # yield to the saver

        t = threading.Thread(target=mutator)
        t.start()
        try:
            for _ in range(100):
                database.save_database(db)
                try:
                    json.load(open(db))
                except Exception as e:  # pragma: no cover
                    errors.append(e)
                    break
        finally:
            stop.set()
            t.join()
        assert not errors, errors


# --------------------------------------------------------------------------- #
# scan_video_file  defer_save
# --------------------------------------------------------------------------- #

class TestScanVideoFileDeferSave:

    def test_defer_true_does_not_save_but_records(self, monkeypatch, tmp_path):
        result, saves, path = call_scan(monkeypatch, tmp_path, defer_save=True)
        assert result['success'] is True
        assert saves == [], "defer_save=True must not persist"
        assert path in database.scanned_files
        assert path in database.scanned_paths

    def test_defer_false_saves_once(self, monkeypatch, tmp_path):
        result, saves, path = call_scan(monkeypatch, tmp_path, defer_save=False)
        assert result['success'] is True
        assert len(saves) == 1
        assert path in database.scanned_files

    def test_already_scanned_returns_early(self, monkeypatch, tmp_path):
        _, saves, path = call_scan(monkeypatch, tmp_path, defer_save=False)
        saves.clear()
        # Second scan of the same path
        result, saves2, _ = call_scan(monkeypatch, tmp_path, defer_save=False,
                                      save_counter=saves)
        assert result['success'] is False
        assert 'already scanned' in result['message'].lower()
        assert saves == [], "already-scanned path must not save again"

    def test_metadata_shape(self, monkeypatch, tmp_path):
        result, _, _ = call_scan(monkeypatch, tmp_path, defer_save=True)
        fi = result['file_info']
        for key in ('filename', 'path', 'hdr_format', 'resolution',
                    'audio_codec', 'duration', 'file_size'):
            assert key in fi
        assert fi['resolution'] == '1080p (Full HD)'
        assert fi['hdr_format'] == 'SDR'

    def test_hdrprobe_none_still_completes(self, monkeypatch, tmp_path):
        # hdrprobe fails entirely -> Unknown, but scan must not crash.
        result, _, _ = call_scan(monkeypatch, tmp_path, defer_save=True,
                                 report=None)
        assert result['success'] is True
        assert result['file_info']['hdr_format'] in ('Unknown', 'SDR')


# --------------------------------------------------------------------------- #
# bulk_scan_files
# --------------------------------------------------------------------------- #

class TestBulkScanFiles:

    @pytest.mark.parametrize('workers', [1, 2, 4, 8])
    def test_all_success(self, workers):
        files = [f'/m/f{i}.mkv' for i in range(30)]
        scan = fake_scan_factory()
        saves = []
        n = vs.bulk_scan_files(files, scan, lambda: saves.append(1),
                               max_workers=workers)
        assert n == 30
        assert len(database.scanned_files) == 30

    def test_empty_list(self):
        saves = []
        n = vs.bulk_scan_files([], fake_scan_factory(), lambda: saves.append(1),
                               max_workers=4)
        assert n == 0
        assert saves == []

    def test_single_file(self):
        n = vs.bulk_scan_files(['/m/a.mkv'], fake_scan_factory(), None,
                               max_workers=1)
        assert n == 1

    @pytest.mark.parametrize('workers', [1, 4])
    def test_failure_isolation(self, workers):
        files = [f'/m/f{i}.mkv' for i in range(10)]
        bad = {'/m/f3.mkv', '/m/f7.mkv'}
        scan = fake_scan_factory(fail_paths=bad)
        n = vs.bulk_scan_files(files, scan, None, max_workers=workers)
        assert n == 8
        assert len(database.scanned_files) == 8
        for b in bad:
            assert b not in database.scanned_files

    def test_success_false_not_counted(self):
        files = [f'/m/f{i}.mkv' for i in range(6)]
        scan = fake_scan_factory(false_paths={'/m/f1.mkv', '/m/f2.mkv'})
        n = vs.bulk_scan_files(files, scan, None, max_workers=1)
        assert n == 4

    def test_none_result_not_counted(self):
        files = [f'/m/f{i}.mkv' for i in range(6)]
        scan = fake_scan_factory(none_paths={'/m/f0.mkv'})
        n = vs.bulk_scan_files(files, scan, None, max_workers=1)
        assert n == 5

    def test_mixed(self):
        files = [f'/m/f{i}.mkv' for i in range(10)]
        scan = fake_scan_factory(fail_paths={'/m/f0.mkv'},
                                 false_paths={'/m/f1.mkv'},
                                 none_paths={'/m/f2.mkv'})
        n = vs.bulk_scan_files(files, scan, None, max_workers=3)
        assert n == 7

    def test_all_fail(self):
        files = [f'/m/f{i}.mkv' for i in range(5)]
        scan = fake_scan_factory(fail_paths=set(files))
        n = vs.bulk_scan_files(files, scan, None, max_workers=2)
        assert n == 0
        assert len(database.scanned_files) == 0

    def test_batch_save_counts(self, monkeypatch):
        """25 successes, batch 10 -> saves at 10, 20, + final flush of 5 = 3."""
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 10)
        files = [f'/m/f{i}.mkv' for i in range(25)]
        saves = []
        vs.bulk_scan_files(files, fake_scan_factory(), lambda: saves.append(1),
                           max_workers=1)
        assert len(saves) == 3

    def test_batch_boundary_no_double_final_save(self, monkeypatch):
        """20 successes, batch 10 -> saves at 10 and 20, no extra final flush."""
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 10)
        files = [f'/m/f{i}.mkv' for i in range(20)]
        saves = []
        vs.bulk_scan_files(files, fake_scan_factory(), lambda: saves.append(1),
                           max_workers=1)
        assert len(saves) == 2

    def test_batch_only_final_when_below_batch(self, monkeypatch):
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 100)
        files = [f'/m/f{i}.mkv' for i in range(7)]
        saves = []
        vs.bulk_scan_files(files, fake_scan_factory(), lambda: saves.append(1),
                           max_workers=1)
        assert len(saves) == 1  # single final flush

    def test_failures_do_not_trigger_saves(self, monkeypatch):
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 5)
        files = [f'/m/f{i}.mkv' for i in range(20)]
        # Only 4 succeed -> below batch -> exactly one final flush.
        ok = {f'/m/f{i}.mkv' for i in range(4)}
        scan = fake_scan_factory(fail_paths=set(files) - ok)
        saves = []
        n = vs.bulk_scan_files(files, scan, lambda: saves.append(1), max_workers=1)
        assert n == 4
        assert len(saves) == 1

    def test_no_save_func(self):
        files = [f'/m/f{i}.mkv' for i in range(5)]
        n = vs.bulk_scan_files(files, fake_scan_factory(), None, max_workers=2)
        assert n == 5  # must not crash without a save func

    def test_save_func_exception_isolated(self, monkeypatch):
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 2)
        files = [f'/m/f{i}.mkv' for i in range(6)]

        def bad_save():
            raise IOError("cannot write")

        n = vs.bulk_scan_files(files, fake_scan_factory(), bad_save, max_workers=1)
        assert n == 6  # scan completes despite save failures

    def test_progress_cb_none(self):
        n = vs.bulk_scan_files(['/m/a.mkv'], fake_scan_factory(), None,
                               max_workers=1, progress_cb=None)
        assert n == 1

    def test_progress_cb_called_per_file(self):
        files = [f'/m/f{i}.mkv' for i in range(12)]
        seen = []
        vs.bulk_scan_files(files, fake_scan_factory(), None, max_workers=4,
                           progress_cb=lambda c, t, p, r: seen.append((c, t, p)))
        assert len(seen) == 12
        # completed index is unique 1..12 and total is always 12
        assert sorted(c for c, _, _ in seen) == list(range(1, 13))
        assert all(t == 12 for _, t, _ in seen)

    def test_progress_cb_exception_isolated(self):
        files = [f'/m/f{i}.mkv' for i in range(5)]

        def bad_cb(c, t, p, r):
            raise ValueError("ui blew up")

        n = vs.bulk_scan_files(files, fake_scan_factory(), None, max_workers=2,
                               progress_cb=bad_cb)
        assert n == 5

    @pytest.mark.parametrize('workers', [0, -1, -5])
    def test_workers_coerced_to_one(self, workers):
        files = [f'/m/f{i}.mkv' for i in range(4)]
        n = vs.bulk_scan_files(files, fake_scan_factory(), None, max_workers=workers)
        assert n == 4

    def test_workers_greater_than_files(self):
        files = ['/m/a.mkv', '/m/b.mkv', '/m/c.mkv']
        n = vs.bulk_scan_files(files, fake_scan_factory(), None, max_workers=16)
        assert n == 3
        assert len(database.scanned_files) == 3

    def test_defer_save_always_passed_true(self):
        files = [f'/m/f{i}.mkv' for i in range(5)]
        scan = fake_scan_factory()
        vs.bulk_scan_files(files, scan, None, max_workers=3)
        assert all(defer is True for _, defer in scan.record)

    def test_large_library_all_scanned(self, monkeypatch):
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 25)
        files = [f'/m/f{i}.mkv' for i in range(500)]
        scan = fake_scan_factory(sleep=0.0005)
        saves = []
        n = vs.bulk_scan_files(files, scan, lambda: saves.append(1),
                               max_workers=8)
        assert n == 500
        assert len(database.scanned_files) == 500
        # 500 / 25 = 20 batched saves, exactly on boundary -> no extra flush.
        assert len(saves) == 20
        # every file probed exactly once (bounded submission, no dupes/drops)
        assert len({p for p, _ in scan.record}) == 500

    def test_parallel_deterministic_count(self, monkeypatch):
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 7)
        for _ in range(5):
            with database.scan_lock:
                database.scanned_files.clear()
                database.scanned_paths.clear()
            files = [f'/m/f{i}.mkv' for i in range(60)]
            scan = fake_scan_factory(fail_paths={'/m/f10.mkv', '/m/f55.mkv'},
                                     sleep=0.0002)
            n = vs.bulk_scan_files(files, scan, None, max_workers=8)
            assert n == 58
            assert len(database.scanned_files) == 58

    def test_parallel_no_lost_updates(self):
        """Real shared-dict mutation under contention: nothing is lost."""
        files = [f'/m/f{i}.mkv' for i in range(300)]
        scan = fake_scan_factory(sleep=0.0003)
        n = vs.bulk_scan_files(files, scan, None, max_workers=16)
        assert n == 300
        assert len(database.scanned_files) == 300
        assert set(database.scanned_paths) == set(files)


# --------------------------------------------------------------------------- #
# bulk_scan_files integrated with the REAL scan_video_file + real save_database
# --------------------------------------------------------------------------- #

class TestBulkIntegration:

    def _wrapper(self, monkeypatch, tmp_path, save_counter):
        report = {'video_tracks': [{'hdr': {'format': 'SDR'},
                                    'width': 3840, 'height': 2160}]}
        monkeypatch.setattr(vs, 'run_hdrprobe', lambda p: report)
        monkeypatch.setattr(vs, 'get_media_info', lambda p: [])
        save_func, fanart, tmdb, tmdb_by_id, credits, cached = make_scan_deps(save_counter)

        def wrapper(path, defer_save=False):
            return vs.scan_video_file(
                path, database.scanned_paths, database.scanned_files,
                database.scan_lock, lambda: database.save_database(str(tmp_path / 'db.json')),
                fanart, tmdb, tmdb_by_id, credits, cached, defer_save=defer_save)
        return wrapper

    def test_end_to_end_parallel_writes_valid_db(self, monkeypatch, tmp_path):
        db = str(tmp_path / 'db.json')
        # Create real files so os.path.getsize works.
        files = []
        for i in range(80):
            f = tmp_path / f'movie_{i}.mkv'
            f.write_bytes(b'\x00' * 1024)
            files.append(str(f))
        wrapper = self._wrapper(monkeypatch, tmp_path, [])
        monkeypatch.setattr(config, 'SCAN_SAVE_BATCH', 15)
        n = vs.bulk_scan_files(files, wrapper,
                               lambda: database.save_database(db), max_workers=8)
        assert n == 80
        data = json.load(open(db))  # valid JSON, no corruption under parallel writes
        assert len(data['files']) == 80
        assert data['files'][files[0]]['resolution'] == '4K (UHD)'
        leftovers = [x for x in os.listdir(tmp_path) if x.startswith('.scanned_files_')]
        assert leftovers == []

    def test_rescan_skips_already_scanned(self, monkeypatch, tmp_path):
        db = str(tmp_path / 'db.json')
        files = []
        for i in range(10):
            f = tmp_path / f'm_{i}.mkv'
            f.write_bytes(b'\x00' * 512)
            files.append(str(f))
        wrapper = self._wrapper(monkeypatch, tmp_path, [])
        first = vs.bulk_scan_files(files, wrapper,
                                   lambda: database.save_database(db), max_workers=4)
        assert first == 10
        # Second pass: all already scanned -> 0 new (scan returns success False)
        second = vs.bulk_scan_files(files, wrapper,
                                    lambda: database.save_database(db), max_workers=4)
        assert second == 0
        assert len(database.scanned_files) == 10


# --------------------------------------------------------------------------- #
# config env parsing (hardened)
# --------------------------------------------------------------------------- #

class TestConfigEnv:

    def test_env_int_default_on_missing(self, monkeypatch):
        monkeypatch.delenv('NOPE_XYZ', raising=False)
        assert config._env_int('NOPE_XYZ', 42) == 42

    def test_env_int_valid(self, monkeypatch):
        monkeypatch.setenv('SOME_INT', '7')
        assert config._env_int('SOME_INT', 1) == 7

    def test_env_int_whitespace(self, monkeypatch):
        monkeypatch.setenv('SOME_INT', '  9  ')
        assert config._env_int('SOME_INT', 1) == 9

    def test_env_int_empty_falls_back(self, monkeypatch):
        monkeypatch.setenv('SOME_INT', '')
        assert config._env_int('SOME_INT', 3) == 3

    def test_env_int_garbage_falls_back(self, monkeypatch):
        monkeypatch.setenv('SOME_INT', 'abc')
        assert config._env_int('SOME_INT', 5) == 5

    def test_env_int_float_string_falls_back(self, monkeypatch):
        monkeypatch.setenv('SOME_INT', '2.5')
        assert config._env_int('SOME_INT', 5) == 5

    @pytest.mark.parametrize('val,expected', [('1', 1), ('4', 4), ('0', 1),
                                              ('-3', 1), ('abc', 1), ('', 1)])
    def test_scan_workers_clamped(self, monkeypatch, val, expected):
        monkeypatch.setenv('SCAN_WORKERS', val)
        importlib.reload(config)
        try:
            assert config.SCAN_WORKERS == expected
        finally:
            monkeypatch.delenv('SCAN_WORKERS', raising=False)
            importlib.reload(config)

    @pytest.mark.parametrize('val,expected', [('25', 25), ('1', 1), ('0', 1),
                                              ('bad', 25), ('', 25)])
    def test_scan_save_batch_clamped(self, monkeypatch, val, expected):
        monkeypatch.setenv('SCAN_SAVE_BATCH', val)
        importlib.reload(config)
        try:
            assert config.SCAN_SAVE_BATCH == expected
        finally:
            monkeypatch.delenv('SCAN_SAVE_BATCH', raising=False)
            importlib.reload(config)

    def test_bad_env_does_not_crash_import(self, monkeypatch):
        monkeypatch.setenv('SCAN_WORKERS', 'garbage')
        monkeypatch.setenv('ISO_SAMPLE_SIZE_MB', 'nan')
        monkeypatch.setenv('FILE_WRITE_DELAY', 'x')
        try:
            importlib.reload(config)  # must not raise
            assert config.SCAN_WORKERS == 1
            assert config.ISO_SAMPLE_SIZE_MB == 16
            assert config.FILE_WRITE_DELAY == 5
        finally:
            for k in ('SCAN_WORKERS', 'ISO_SAMPLE_SIZE_MB', 'FILE_WRITE_DELAY'):
                monkeypatch.delenv(k, raising=False)
            importlib.reload(config)
