import json

import sync_lotw_log


def _write_adif(path, call, qso_date, time_on, band='20M', mode='FT8'):
    path.write_text(
        f"<call:{len(call)}>{call}<qso_date:8>{qso_date}<time_on:6>{time_on}"
        f"<band:{len(band)}>{band}<mode:{len(mode)}>{mode}<eor>\n"
    )


def _write_station_log(path, contacts):
    path.write_text(json.dumps({
        'header': {'total_contacts': len(contacts)},
        'contacts': contacts,
    }))


def test_new_contact_gets_saved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_station_log(tmp_path / 'station_log.json', [])
    adif_file = tmp_path / 'session.adi'
    _write_adif(adif_file, 'W5MMW', '20250815', '123456')

    exit_code = sync_lotw_log.main([str(adif_file)])

    assert exit_code == 0
    saved = json.loads((tmp_path / 'station_log.json').read_text())
    assert len(saved['contacts']) == 1
    assert saved['contacts'][0]['call'] == 'W5MMW'


def test_rerun_with_unchanged_data_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_station_log(tmp_path / 'station_log.json', [])
    adif_file = tmp_path / 'session.adi'
    _write_adif(adif_file, 'W5MMW', '20250815', '123456')

    first = sync_lotw_log.main([str(adif_file)])
    before = (tmp_path / 'station_log.json').read_text()
    second = sync_lotw_log.main([str(adif_file)])
    after = (tmp_path / 'station_log.json').read_text()

    assert first == 0
    assert second == 10
    assert before == after


def test_missing_source_files_are_skipped_without_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_station_log(tmp_path / 'station_log.json', [])

    exit_code = sync_lotw_log.main([str(tmp_path / 'does_not_exist.adi')])

    assert exit_code == 10


def test_refuses_to_overwrite_a_corrupted_station_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / 'station_log.json'
    # Sizeable but invalid JSON, simulating a truncated/corrupted write.
    log_path.write_text('{"header": {}, "contacts": [' + 'x' * 200)
    adif_file = tmp_path / 'session.adi'
    _write_adif(adif_file, 'W5MMW', '20250815', '123456')

    original_content = log_path.read_text()
    exit_code = sync_lotw_log.main([str(adif_file)])

    assert exit_code == 2
    assert log_path.read_text() == original_content


def test_refuses_to_save_if_merge_would_shrink_contacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existing = [
        {'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56'},
        {'call': 'K1ABC', 'qso_date': '2025-08-15', 'time_on': '13:00:00'},
    ]
    _write_station_log(tmp_path / 'station_log.json', existing)
    adif_file = tmp_path / 'session.adi'
    _write_adif(adif_file, 'N0CALL', '20250815', '140000')

    # Force merge_contacts to simulate a buggy merge that drops contacts.
    monkeypatch.setattr(sync_lotw_log, 'merge_contacts', lambda existing, new: ([existing[0]], 0))

    original_content = (tmp_path / 'station_log.json').read_text()
    exit_code = sync_lotw_log.main([str(adif_file)])

    assert exit_code == 2
    assert (tmp_path / 'station_log.json').read_text() == original_content
