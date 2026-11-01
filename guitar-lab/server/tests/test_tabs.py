import xml.etree.ElementTree as ET
import pytest
from fastapi.testclient import TestClient
from server import app as module
from server.tabs import parse_ascii_tab

STANDARD = [64, 59, 55, 50, 45, 40]
# An A minor arpeggio then a C chord: two bars, eighth notes in bar 1, one strum in bar 2.
TAB = """
Intro riff (my own)
e|---------------0-|-0---------------|
B|-------------1---|-1---------------|
G|---------2-------|-0---------------|
D|-----2-----------|-2---------------|
A|-0---------------|-3---------------|
E|-----------------|-----------------|
"""


def test_text_tab_timing_strings_and_chords():
    r = parse_ascii_tab(TAB, STANDARD, bpm=120)
    notes = r['notes']
    first_bar = [n for n in notes if n['time'] < 2]
    assert [n['midi'] for n in first_bar] == [45, 52, 57, 60, 64]        # A2 E3 A3 C4 E4
    assert [round(n['time'], 3) for n in first_bar] == [0.0, 0.5, 1.0, 1.5, 1.75]
    assert first_bar[0]['string'] == 5 and first_bar[0]['fret'] == 0     # tab convention: 1 = high e
    chord = [n for n in notes if abs(n['time']-2.0) < 1e-6]
    assert sorted(n['midi'] for n in chord) == [48, 52, 55, 60, 64]      # C major, one strum
    assert r['bars'] == [0.0, 2.0]


def test_text_tab_double_digit_frets_and_drop_d():
    drop_d = [64, 59, 55, 50, 45, 38]
    tab = "e|--12--15--|\nB|----------|\nG|----------|\nD|----------|\nA|----------|\nD|0---------|\n"
    notes = parse_ascii_tab(tab, drop_d, bpm=60)['notes']
    assert [(n['midi'], n['fret']) for n in notes] == [(38, 0), (76, 12), (79, 15)]


def test_text_tab_errors():
    with pytest.raises(ValueError, match='No 6-line tab'):
        parse_ascii_tab("just some lyrics\nno tab here", STANDARD)
    four = "G|--2--|\nD|--2--|\nA|--0--|\nE|-----|\n"
    with pytest.raises(ValueError):
        parse_ascii_tab(four, STANDARD)          # bass tab against a guitar
    assert parse_ascii_tab(four, [43, 38, 33, 28])['notes'][0]['midi'] == 45


def test_text_tab_endpoint_returns_notation():
    client = TestClient(module.app)
    r = client.post('/api/tabs/text', headers={'X-Fretwork-Client': 'studio'},
                    json={'text': TAB, 'bpm': 100, 'title': 'Riff'})
    assert r.status_code == 200, r.text
    body = r.json()
    root = ET.fromstring(body['musicxml'].split('\n', 2)[2])
    assert len(root.findall('.//measure')) == 2
    assert root.find('.//technical/fret') is not None
    assert body['key']['key'] in ('A minor', 'C major')
    assert client.post('/api/tabs/text', headers={'X-Fretwork-Client': 'studio'},
                       json={'text': TAB, 'instrument': 'piano', 'tuning': 'none'}).status_code == 422
