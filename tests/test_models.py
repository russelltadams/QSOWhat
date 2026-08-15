from models import merge_contacts


def test_merge_contacts_adds_new_contact():
    existing = []
    new = [{'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56', 'band': '20M'}]

    merged, updated = merge_contacts(existing, new)

    assert len(merged) == 1
    assert updated == 0
    assert merged[0]['call'] == 'W5MMW'


def test_merge_contacts_fills_missing_fields_without_overwriting_existing():
    existing = [{
        'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56',
        'band': '20M', 'rst_sent': '599',
    }]
    new = [{
        'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56',
        'band': '40M',  # different value for an already-populated field
        'gridsquare': 'CM87',  # new field not previously present
    }]

    merged, updated = merge_contacts(existing, new)

    assert len(merged) == 1
    assert updated == 1
    # existing non-empty field is preserved, not clobbered by the new record
    assert merged[0]['band'] == '20M'
    # previously-missing field gets filled in
    assert merged[0]['gridsquare'] == 'CM87'


def test_merge_contacts_matches_on_call_date_and_time():
    existing = [{'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56'}]
    # same callsign, different time -> distinct QSO, should be added not merged
    new = [{'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '13:00:00'}]

    merged, updated = merge_contacts(existing, new)

    assert len(merged) == 2
    assert updated == 0


def test_merge_contacts_is_idempotent_on_rerun():
    existing = [{'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56', 'band': '20M'}]
    same_again = [{'call': 'W5MMW', 'qso_date': '2025-08-15', 'time_on': '12:34:56', 'band': '20M'}]

    merged, updated = merge_contacts(existing, same_again)

    assert merged == existing
    assert updated == 1  # matched, but no field content actually changed
