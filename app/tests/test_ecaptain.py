import io

import openpyxl
import pytest

from accesscontrol import db, devices, ecaptain, members
from accesscontrol.engine import Engine


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.init(str(tmp_path / "t.db"))
    devices.create({"name": "Water", "serial_port": "socket://127.0.0.1:1",
                    "tasmota_topic": "water", "on_seconds": 1200}, True, "test")
    devices.create({"name": "Poort", "enabled": False, "tasmota_topic": "poort",
                    "on_seconds": 1}, True, "test")
    yield


def W():
    return devices.by_name()["water"]["id"]


def G():
    return devices.by_name()["poort"]["id"]


def sync(text, filename="ecaptain.csv", dry_run=False):
    return ecaptain.sync_file(filename, text.encode("utf-8"), "BE", "admin@x", dry_run)


def by_no():
    return {m["member_no"]: m for m in members.list_members()}


# ---------- rapport lezen ----------

def test_parse_csv_with_title_row_and_active_status():
    rows, warnings = ecaptain.parse_report(
        "leden.csv",
        b"Rapport actieve leden\n"
        b"Lidnummer;Naam;Mobiel;Status\n"
        b"1;An Peeters;0470 12 34 56;Actief\n"
        b"2;Bert;+32 495 00 00 02;Opgezegd\n",
        "BE")
    assert not warnings
    assert rows[0] == {"external_id": None, "member_no": "1", "name": "An Peeters",
                       "phone": "+32470123456", "phone_invalid": False, "active": True}
    assert rows[1]["active"] is False
    assert rows[1]["phone"] == "+32495000002"


def test_parse_xlsx_and_first_last_name():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["e-Captain rapport"])
    ws.append(["Lidnr", "Voornaam", "Achternaam", "GSM"])
    ws.append(["7", "Cis", "de Vries", "0495 00 00 07"])
    buf = io.BytesIO()
    wb.save(buf)
    rows, _ = ecaptain.parse_report("x.xlsx", buf.getvalue(), "BE")
    assert rows[0]["name"] == "Cis de Vries"
    assert rows[0]["phone"] == "+32495000007"


def test_parse_rejects_unrecognised_report():
    with pytest.raises(ecaptain.EcaptainError) as e:
        ecaptain.parse_report("x.csv", b"Kleur;Aantal\nrood;3\n", "BE")
    assert "kopregel" in " ".join(e.value.errors)


def test_parse_ignores_duplicate_rows():
    rows, warnings = ecaptain.parse_report(
        "x.csv", b"Lidnr;Naam;Telefoon\n1;An;0470123456\n1;An dubbel;0470123456\n", "BE")
    assert len(rows) == 1
    assert any("dubbel" in w for w in warnings)


def test_parse_skips_footer_total_row():
    rows, warnings = ecaptain.parse_report(
        "x.csv",
        b"Lidnummer;Naam;Telefoon\n"
        b"017A;Annemans, Bart;0476481753\n"
        b"108Z;Adam Algemene Dakwerken BV;0485 13 61 03\n"
        b"85;;\n",
        "BE")
    assert [r["member_no"] for r in rows] == ["017A", "108Z"]
    assert not warnings


def test_parse_only_accepts_mobile_numbers():
    rows, warnings = ecaptain.parse_report(
        "x.csv",
        b"Lidnummer;Naam;Mobiel;Telefoon\n"
        b"1;An;0470123456;0323456789\n"
        b"2;Bert;;052445582\n"
        b"3;Cis;0495123456;\n",
        "BE")
    assert rows[0]["phone"] == "+32470123456"
    assert rows[1]["phone"] is None
    assert rows[2]["phone"] == "+32495123456"
    assert any("geen mobiel nummer" in w for w in warnings)


def test_sync_skips_new_member_without_mobile():
    r = sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n2;Bert;052445582\n")
    assert r["nieuw"] == 1
    assert r["overgeslagen"] == 1
    assert "1" in by_no() and "2" not in by_no()
    assert any("geen mobiel nummer" in w for w in r["waarschuwingen"])
    assert any("heeft geen mobiel nummer" in x for x in r["fouten"])


def test_existing_member_fixed_number_is_cleared():
    sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n")
    assert by_no()["1"]["phone"] == "+32470123456"

    r = sync("Lidnr;Naam;Mobiel\n1;An;052445582\n")
    assert r["gewijzigd"] == 1
    assert by_no()["1"]["phone"] is None
    assert any("geen mobiel nummer" in w for w in r["waarschuwingen"])


def test_manual_fixed_number_survives_fixed_report_row():
    manual = members.create({"member_no": "L1", "name": "Leverancier",
                             "phone": "052445582"}, "BE", "admin@x")
    r = sync("Lidnr;Naam;Mobiel\nL1;Leverancier;052445582\n")
    assert r["nieuw"] == 0
    m = members.get(manual["id"])
    assert m["phone"] == "+3252445582" and m["source"] == "manual"


# ---------- sync ----------

def test_sync_add_update_deactivate_and_reactivate_keeps_manual():
    manual = members.create({"member_no": "L1", "name": "Leverancier",
                             "phone": "0499000001"}, "BE", "admin@x")
    assert manual["source"] == "manual" and manual["active"] is True

    r = sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n")
    assert (r["nieuw"], r["gedeactiveerd"], r["overgeslagen"]) == (1, 0, 0)
    m = by_no()["1"]
    assert m["source"] == "ecaptain" and m["active"] is True
    assert m["phone"] == "+32470123456"
    assert m["access"] == {W(): True, G(): True}

    # Naam en telefoon wijzigen; handmatig lid blijft ongemoeid.
    r = sync("Lidnr;Naam;Mobiel\n1;An Peeters;0470123457\n")
    m = by_no()["1"]
    assert (r["nieuw"], r["gewijzigd"], r["ongewijzigd"]) == (0, 1, 0)
    assert (m["name"], m["phone"]) == ("An Peeters", "+32470123457")
    assert by_no()["L1"]["name"] == "Leverancier"
    assert by_no()["L1"]["active"] is True

    # Lid verdwijnt uit het rapport: bewaard maar niet actief.
    r = sync("Lidnr;Naam;Mobiel\n2;Iemand anders;0470123458\n")
    assert r["gedeactiveerd"] == 1
    assert by_no()["1"]["active"] is False
    assert by_no()["L1"]["active"] is True
    assert db.query("SELECT * FROM events WHERE reason='Import e-captain: lid niet actief'")

    # Terug in het rapport: opnieuw actief, toegang blijft bewaard.
    r = sync("Lidnr;Naam;Mobiel\n1;An Peeters;0470123457\n")
    assert r["geactiveerd"] == 1
    assert by_no()["1"]["active"] is True
    assert by_no()["1"]["access"] == {W(): True, G(): True}


def test_sync_matches_manual_member_by_phone_and_links_it():
    manual = members.create({"member_no": "L1", "name": "Leverancier",
                             "phone": "0470123456"}, "BE", "admin@x")
    r = sync("Lidnr;Naam;Mobiel\n42;An Peeters;0470123456\n")
    assert r["nieuw"] == 0 and r["gewijzigd"] == 1
    m = members.get(manual["id"])
    assert m["member_no"] == "42" and m["source"] == "ecaptain"
    assert m["name"] == "An Peeters"


def test_sync_skips_duplicate_phone_and_reports_it():
    r = sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n2;Bert;0470123456\n")
    assert r["nieuw"] == 1
    assert r["overgeslagen"] == 1
    assert any("komt ook voor bij" in x and "is overgeslagen" in x for x in r["fouten"])


def test_sync_report_lists_new_updated_and_deleted():
    r = sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n")
    assert r["rapport"]["nieuw"] == [
        {"member_no": "1", "name": "An", "phone": "+32470123456"}]
    assert r["rapport"]["gewijzigd"] == [] and r["rapport"]["verwijderd"] == []

    r = sync("Lidnr;Naam;Mobiel\n1;An Peeters;0470123457\n")
    item = r["rapport"]["gewijzigd"][0]
    assert item["member_no"] == "1" and item["name"] == "An Peeters"
    assert "Naam: An -> An Peeters" in item["changes"]

    r = sync("Lidnr;Naam;Mobiel\n2;Bert;0470123458\n")
    assert r["rapport"]["verwijderd"][0]["member_no"] == "1"
    assert r["rapport"]["verwijderd"][0]["reason"] == "Niet meer in het e-Captain-rapport"
    assert r["gewijzigd"] == 0 and r["gedeactiveerd"] == 1


def test_sync_skips_conflicting_member_no():
    r = sync("Relatie-id;Lidnr;Naam;Mobiel\nA;5;An;0470123456\nB;5;Bert;0470123457\n")
    assert r["nieuw"] == 1
    assert r["overgeslagen"] == 1
    assert any("Lidnummer 5" in x for x in r["fouten"])


def test_shared_phone_prefers_sorted_first_when_new():
    r = sync("Lidnummer;Naam;Telefoon\n"
             "108Z;Adam Algemene Dakwerken BV;0485 13 61 03\n"
             "108A;Sielawko, Adam;0485 13 61 03\n")
    assert r["nieuw"] == 1 and r["overgeslagen"] == 1
    assert any("108Z (Adam Algemene Dakwerken BV) is overgeslagen" in x for x in r["fouten"])
    assert by_no()["108A"]["phone"] == "+32485136103"
    assert "108Z" not in by_no()


def test_shared_phone_prefers_existing_member():
    members.create({"member_no": "108Z", "name": "Bestaand bedrijf",
                    "phone": "0499000001"}, "BE", "admin@x")
    r = sync("Lidnummer;Naam;Telefoon\n"
             "108Z;Adam Algemene Dakwerken BV;0485 13 61 03\n"
             "108A;Sielawko, Adam;0485 13 61 03\n")
    assert r["gewijzigd"] == 1 and r["overgeslagen"] == 1
    assert by_no()["108Z"]["phone"] == "+32485136103"
    assert "108A" not in by_no()


def test_phone_change_frees_old_number_for_another_member():
    r = sync("Lidnummer;Naam;Telefoon\n"
             "032A;Mampaey, Lucien;0488 47 93 69\n"
             "033A;Bracke, Jose;0488 47 93 69\n")
    assert r["nieuw"] == 1 and r["overgeslagen"] == 1
    assert by_no()["032A"]["phone"] == "+32488479369"
    assert "033A" not in by_no()

    # 032A krijgt in e-Captain een nieuw nummer; 033A houdt het oude nummer.
    r = sync("Lidnummer;Naam;Telefoon\n"
             "032A;Mampaey, Lucien;0474 73 25 60\n"
             "033A;Bracke, Jose;0488 47 93 69\n")
    assert r["nieuw"] == 1 and r["gedeactiveerd"] == 0 and r["overgeslagen"] == 0
    leden = by_no()
    assert leden["032A"]["name"] == "Mampaey, Lucien"
    assert leden["032A"]["phone"] == "+32474732560"
    assert leden["033A"]["name"] == "Bracke, Jose"
    assert leden["033A"]["phone"] == "+32488479369"


def test_shared_phone_manual_owner_is_kept():
    manual = members.create({"member_no": "L1", "name": "Leverancier",
                             "phone": "0485136103"}, "BE", "admin@x")
    r = sync("Lidnummer;Naam;Telefoon\n"
             "108Z;Adam Algemene Dakwerken BV;0485 13 61 03\n"
             "108A;Sielawko, Adam;0485 13 61 03\n")
    assert r["nieuw"] == 0 and r["overgeslagen"] == 2
    m = members.get(manual["id"])
    assert m["source"] == "manual" and m["phone"] == "+32485136103"
    assert "108A" not in by_no() and "108Z" not in by_no()


def test_inactive_report_row_does_not_hijack_manual_member():
    manual = members.create({"member_no": "L1", "name": "Leverancier",
                             "phone": "0499000001"}, "BE", "admin@x")
    r = sync("Lidnr;Naam;Mobiel;Status\nL1;Iemand;0499000001;Nee\n")
    assert r["nieuw"] == 0 and r["gedeactiveerd"] == 0
    m = members.get(manual["id"])
    assert m["source"] == "manual" and m["active"] is True and m["phone"] == "+32499000001"


def test_sync_dry_run_changes_nothing():
    r = sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n", dry_run=True)
    assert r["dry_run"] is True and r["nieuw"] == 1
    assert members.list_members() == []
    assert not db.query("SELECT * FROM events WHERE reason='Import e-captain'")


def test_inactive_ecaptain_member_is_denied_by_engine():
    sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n")
    sync("Lidnr;Naam;Mobiel\n2;Bert;0470123457\n")   # lid 1 valt weg -> niet actief
    assert by_no()["1"]["active"] is False

    eng = Engine()
    eng.mqtt = None
    assert eng.handle_call(W(), "32470123456") == "geweigerd"
    assert db.query("SELECT reason FROM events WHERE category='oproep'")[0]["reason"] == \
        "Lid is niet actief"


def test_status_returns_last_sync_and_counts():
    sync("Lidnr;Naam;Mobiel\n1;An;0470123456\n")
    st = ecaptain.status()
    assert st["last"]["nieuw"] == 1
    assert st["members"]["ecaptain"] == 1 and st["members"]["ecaptain_active"] == 1
