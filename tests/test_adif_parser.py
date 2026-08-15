from adif_parser import (
    clean_band,
    clean_callsign,
    clean_date,
    clean_mode,
    parse_adif_file,
)


def test_clean_callsign_strips_invalid_chars_and_uppercases():
    assert clean_callsign('km6kfx!') == 'KM6KFX'
    assert clean_callsign('w5mmw/p') == 'W5MMW/P'


def test_clean_date_handles_common_formats():
    assert clean_date('20250815') == '2025-08-15'
    assert clean_date('2025-08-15') == '2025-08-15'
    assert clean_date('08/15/2025') == '2025-08-15'


def test_clean_band_normalizes_bare_numbers():
    assert clean_band('20') == '20M'
    assert clean_band('40m') == '40M'
    assert clean_band('70CM') == '70CM'


def test_clean_mode_maps_known_modes():
    assert clean_mode('ft8') == 'FT8'
    assert clean_mode('ssb') == 'SSB'


def test_parse_adif_file_extracts_contacts(tmp_path):
    adif_content = (
        "<station_callsign:6>KM6KFX<eoh>\n"
        "<call:5>W5MMW<qso_date:8>20250815<time_on:6>123456"
        "<band:3>20M<mode:3>FT8<eor>\n"
    )
    adif_file = tmp_path / "test.adi"
    adif_file.write_text(adif_content)

    result = parse_adif_file(str(adif_file))

    assert result['header']['station_callsign'] == 'KM6KFX'
    assert len(result['contacts']) == 1
    contact = result['contacts'][0]
    assert contact['call'] == 'W5MMW'
    assert contact['qso_date'] == '2025-08-15'
    assert contact['time_on'] == '12:34:56'
    assert contact['band'] == '20M'
    assert contact['mode'] == 'FT8'


def test_parse_adif_file_skips_empty_records(tmp_path):
    adif_file = tmp_path / "empty.adi"
    adif_file.write_text("<eoh>\n<eor>\n")

    result = parse_adif_file(str(adif_file))

    assert result['contacts'] == []
