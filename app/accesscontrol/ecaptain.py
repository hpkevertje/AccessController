"""Import uit de e-Captain ledenadministratie (alleen e-Captain -> AccessController).

e-Captain heeft geen publieke API. De app leest daarom een rapport/export (.xlsx of .csv) dat
de admin in e-Captain maakt (Ledenbeheer > Rapportage). Dit is de betrouwbare route: geen
wachtwoorden van e-Captain in de app en geen kwetsbare scraping van hun webinterface.

Semantiek:
- Actieve leden worden toegevoegd of bijgewerkt (lidnummer, naam, telefoon).
- Een lid dat niet meer in het rapport staat of daar niet actief is, blijft bewaard maar wordt
  op niet-actief gezet. De oproep-engine weigert dan zijn nummer. De toegangsinstellingen per
  toestel blijven bewaard, zodat het lid na reactivering weer dezelfde toegang heeft.
- Handmatig toegevoegde nummers (leveranciers, aannemers, ...) worden nooit gewijzigd of
  verwijderd. Ze hebben source='manual'.
"""
import csv
import io
import re

import openpyxl

from . import db, members
from .phone import PhoneError, normalize

SOURCE = "ecaptain"

# Kolomkoppen (genormaliseerd: kleine letters, alleen letters/cijfers). Een cijferachtervoegsel
# wordt genegeerd, zodat "Telefoon 1" en "Telefoon 2" allebei als telefoonkolom tellen.
_ID = {"relatieid", "relatienr", "relatienummer", "id", "ecaptainid", "lidid", "persoonid", "relatie"}
_NO = {"lidnummer", "lidnr", "lidno", "memberno", "membernumber", "memberid", "nr",
       "nummer", "stamnummer"}
_NAME = {"naam", "name", "volledigenaam", "relatienaam", "ledennaam", "naamgeving"}
_FIRST = {"voornaam", "firstname", "roepnaam", "first", "voornamen"}
_LAST = {"achternaam", "lastname", "last", "familienaam"}
_MOBILE = {"mobiel", "mobielnummer", "mobielnr", "gsm", "gsmnr", "gsmnummer", "mobile",
           "mobilenumber", "telefoonmobiel", "telefoonnummermobiel", "mobiele",
           "mobieletelefoon"}
_PHONE = {"telefoon", "telefoonnummer", "telefoonnr", "telnummer", "phone", "phonenumber",
          "tel", "telnr", "vast", "vastenummer", "telefoonnummervast", "thuisnummer"}
_ACTIVE = {"actief", "active", "isactief", "status", "lidstatus", "lidmaatschapstatus",
           "relatiestatus", "lidmaatschap"}

_TRUE = {"ja", "j", "yes", "y", "true", "1", "actief", "active", "lid", "lidactief", "wel",
         "proeflid", "erelid"}
_FALSE = {"nee", "n", "no", "false", "0", "nietactief", "inactief", "opgezegd", "beeindigd",
          "oudlid", "overleden", "geen", "geroyeerd", "nietlid", "geenlid", "opgeschort",
          "geschorst", "vertrokken", "afgemeld"}

_CHANGE_LABELS = {"member_no": "Lidnr", "name": "Naam", "phone": "Telefoon",
                  "source": "Bron", "active": "Actief"}


class EcaptainError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


# ---------- rapport lezen ----------

def _key(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _base_key(h) -> str:
    return re.sub(r"\d+$", "", _key(h))


def _classify(header) -> str | None:
    k = _base_key(header)
    if k in _ACTIVE:
        return "active"
    if k in _MOBILE:
        return "mobile"
    if k in _PHONE:
        return "phone"
    if k in _FIRST:
        return "first"
    if k in _LAST:
        return "last"
    if k in _NAME:
        return "name"
    if k in _NO:
        return "member_no"
    if k in _ID:
        return "external_id"
    return None


def _column_map(header) -> dict:
    cols: dict = {}
    for i, h in enumerate(header):
        kind = _classify(h)
        if kind is None:
            continue
        if kind in ("mobile", "phone"):
            cols.setdefault(kind, []).append(i)
        elif kind not in cols:
            cols[kind] = i
    return cols


def _has_identity(cols: dict) -> bool:
    return any(k in cols for k in ("member_no", "external_id", "name", "first", "last"))


def _find_header(table: list[list]) -> tuple[int | None, dict]:
    """Zoekt de kopregel; rapporten hebben vaak titelregels boven de tabel."""
    for idx, row in enumerate(table[:40]):
        cols = _column_map(row)
        if (cols.get("mobile") or cols.get("phone")) and _has_identity(cols):
            return idx, cols
    return None, {}


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", "replace")


def _delimiter(text: str, filename: str) -> str:
    if filename.lower().endswith(".tsv"):
        return "\t"
    sample = text[:8192]
    counts = {d: sample.count(d) for d in (";", ",", "\t", "|")}
    return max(counts, key=counts.get) if max(counts.values()) else ";"


def _read_table(filename: str, content: bytes) -> list[list]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise EcaptainError([f"Excel-bestand kan niet gelezen worden: {e}"]) from e
        ws = wb.worksheets[0]
        return [[("" if c is None else c) for c in row] for row in ws.iter_rows(values_only=True)]
    if name.endswith(".xls"):
        raise EcaptainError(["Sla het e-Captain-rapport op als .xlsx of .csv (oud .xls wordt "
                             "niet ondersteund)."])
    if name.endswith((".csv", ".txt", ".tsv")):
        text = _decode(content)
        if not text.strip():
            raise EcaptainError(["Het bestand is leeg."])
        return list(csv.reader(io.StringIO(text), delimiter=_delimiter(text, name)))
    raise EcaptainError(["Alleen .xlsx- of .csv-bestanden worden aanvaard "
                         "(export van een e-Captain-rapport)."])


def _text(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\xa0", " ").strip()
    if s.startswith("'"):                       # Excel-tekstmarkering
        s = s[1:].strip()
    if s.endswith(".0") and s[:-2].isdigit():   # Excel maakt soms een getal van het nummer
        s = s[:-2]
    return s


def _cell(row: list, idx) -> str:
    return _text(row[idx]) if idx is not None and idx < len(row) else ""


def _split_phone_cell(v) -> list[str]:
    s = _text(v)
    if not s:
        return []
    # " / " scheidt meerdere nummers; "0470/12.34.56" (zonder spaties) blijft één nummer.
    return [x.strip() for x in re.split(r"\s+/\s+|[;,\n\r|]+", s) if x.strip()]


def _pick_phone(row: list, cols: dict, region: str) -> tuple[str | None, bool]:
    """Mobiel eerst, dan vast. Geeft (E.164 of None, ongeldig?) terug."""
    raws: list[str] = []
    for kind in ("mobile", "phone"):
        for i in cols.get(kind, []):
            raws.extend(_split_phone_cell(row[i] if i < len(row) else ""))
    for raw in raws:
        try:
            phone = normalize(raw, region)
        except PhoneError:
            continue
        if phone:
            return phone, False
    return None, bool(raws)


def _parse_active(v) -> tuple[bool, bool]:
    """Geeft (actief, herkend) terug. Zonder waarde is een rij actief."""
    s = _key(v)
    if not s:
        return True, True
    if s in _TRUE:
        return True, True
    if s in _FALSE:
        return False, True
    return True, False


def parse_report(filename: str, content: bytes, region: str) -> tuple[list[dict], list[str]]:
    """Leest een e-Captain-rapport en geeft (leden, waarschuwingen) terug."""
    table = _read_table(filename, content)
    header_idx, cols = _find_header(table)
    if header_idx is None:
        raise EcaptainError([
            "Geen herkenbare kopregel gevonden. Het rapport moet minstens een telefoonkolom "
            "(Telefoon, Mobiel of GSM) en een kolom met lidnummer, relatie-id of naam bevatten."
        ])

    rows: list[dict] = []
    warnings: list[str] = []
    seen: dict[str, dict] = {}
    id_cols = {cols.get("member_no"), cols.get("external_id")} - {None}
    for idx, row in enumerate(table[header_idx + 1:], start=header_idx + 2):
        filled = [(_text(v), i) for i, v in enumerate(row) if _text(v)]
        if not filled:
            continue
        # Totalregel onderaan een rapport: één getal in de lidnummer-kolom.
        if len(filled) == 1 and filled[0][1] in id_cols and filled[0][0].isdigit():
            continue
        external_id = _cell(row, cols.get("external_id")) or None
        member_no = _cell(row, cols.get("member_no"))
        phone, phone_invalid = _pick_phone(row, cols, region)
        name = _cell(row, cols.get("name"))
        if not name:
            name = " ".join(x for x in (_cell(row, cols.get("first")),
                                        _cell(row, cols.get("last"))) if x)
        if not member_no:
            member_no = external_id
        if not member_no and phone:
            member_no = phone.lstrip("+")
        if not member_no and not phone:
            warnings.append(f"Rij {idx}: geen lidnummer en geen telefoonnummer; overgeslagen.")
            continue
        if not name and not phone:
            # Bv. een totalregel onderaan het rapport ("85" in de eerste kolom).
            warnings.append(f"Rij {idx}: geen naam en geen telefoonnummer; overgeslagen.")
            continue
        if not name:
            name = member_no

        active_raw = _cell(row, cols.get("active"))
        active, known = _parse_active(active_raw)
        if active_raw and not known:
            warnings.append(f"Rij {idx}: onbekende status {active_raw!r}; als actief behandeld.")
        if phone_invalid:
            warnings.append(f"Rij {idx} ({name}): geen geldig telefoonnummer; een bestaand "
                            "nummer blijft behouden.")

        record = {"external_id": external_id, "member_no": member_no, "name": name,
                  "phone": phone, "phone_invalid": phone_invalid, "active": active}
        key = external_id or member_no
        if key in seen:
            warnings.append(f"Rij {idx}: {key} komt dubbel voor; enkel de eerste rij wordt gebruikt.")
            # Een actieve rij wint van een niet-actieve rij met dezelfde sleutel.
            if active and not seen[key]["active"]:
                seen[key].update(record)
            continue
        seen[key] = record
        rows.append(record)

    if not rows:
        raise EcaptainError(["Geen leden gevonden in het rapport."])
    return rows, warnings


# ---------- sync ----------

def _fmt(v) -> str:
    if isinstance(v, bool):
        return "ja" if v else "nee"
    return v if v not in (None, "") else "(leeg)"


def _changes(old: dict, new: dict) -> list[str]:
    out = []
    for k in ("member_no", "name", "phone", "source", "active"):
        a, b = old.get(k), new.get(k)
        if k == "active":
            a, b = bool(a), bool(b)
        if a != b:
            out.append(f"{_CHANGE_LABELS[k]}: {_fmt(a)} -> {_fmt(b)}")
    return out


def _natural_key(value) -> tuple:
    """Sorteersleutel voor lidnummers zoals 032A, 108A, 108Z."""
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold())
                 for p in re.split(r"(\d+)", str(value)) if p)


def _row_label(row: dict) -> str:
    return f"{row['member_no']} ({row['name']})"


def _member_label(member: dict) -> str:
    return f"{member['member_no']} ({member['name']})"


def _build_plan(rows: list[dict], current: list[dict]) -> tuple[list[dict], list[str]]:
    """Bouwt het plan in fasen, zodat een gewijzigd nummer niet bij het verkeerde lid belandt.

    1. Stabiele match op relatie-id of lidnummer, voor alle rijen samen. Zo kan een rij
       die later in het rapport staat (032A) niet door een eerdere rij op telefoonnummer
       worden overgenomen (033A).
    2. Voor de overige rijen: match op telefoonnummer, maar nooit op een lid dat al
       door een andere rij op lidnummer/relatie-id is geclaimd.
    3. Kies per gedeeld telefoonnummer één winnaar: bestaand lid eerst, anders sorteren
       op lidnummer (032A voor 033A, 108A voor 108Z).
    4. Een nummer dat een bestaand lid vrijgeeft (omdat het een nieuw nummer krijgt), mag
       naar een nieuw lid. Zo kan 033A het oude nummer van 032A overnemen.
    5. Bouw het plan en deactiveer e-Captain-leden die niet meer in het rapport staan.
    """
    by_no = {m["member_no"]: m for m in current}
    by_ext = {str(m["ecaptain_id"]): m for m in current if m.get("ecaptain_id")}
    by_phone = {m["phone"]: m for m in current if m.get("phone")}

    targets: dict[int, dict] = {}
    claimed: set[int] = set()
    hard_skip: set[int] = set()
    errors: list[str] = []

    # 1. Stabiele match op relatie-id of lidnummer, vóór alle telefoonmatches.
    for row in rows:
        target = None
        if row.get("external_id"):
            target = by_ext.get(str(row["external_id"]))
        if target is None:
            target = by_no.get(row["member_no"])
        if target is None:
            continue
        if not row["active"] and target.get("source") != SOURCE:
            # Een niet-actieve rij mag een handmatig nummer niet overnemen of wijzigen.
            continue
        if target["id"] in claimed:
            hard_skip.add(id(row))
            errors.append(f"{_row_label(row)} komt dubbel voor in het rapport.")
            continue
        claimed.add(target["id"])
        targets[id(row)] = target

    # 2. Geen stabiele match: probeer op telefoonnummer. Een lid dat al op lidnummer
    #    is geclaimd, mag niet door een andere rij worden overgenomen. Is een nummer
    #    binnen het rapport dubbel, dan is telefoonmatching te dubbelzinnig: laat de
    #    duplicaatregel beslissen.
    unmatched_phone_count: dict[str, int] = {}
    for row in rows:
        if id(row) in targets or id(row) in hard_skip:
            continue
        if row["active"] and row.get("phone"):
            unmatched_phone_count[row["phone"]] = unmatched_phone_count.get(row["phone"], 0) + 1

    for row in rows:
        if id(row) in targets or id(row) in hard_skip:
            continue
        if not row["active"] or not row.get("phone"):
            continue
        if unmatched_phone_count.get(row["phone"], 0) > 1:
            continue
        candidate = by_phone.get(row["phone"])
        if candidate is not None and candidate["id"] not in claimed:
            claimed.add(candidate["id"])
            targets[id(row)] = candidate

    # 3. Gewenste toestand per rij.
    desired: dict[int, dict] = {}
    for row in rows:
        target = targets.get(id(row))
        if target is not None:
            phone = target["phone"] if row.get("phone_invalid") else row.get("phone")
            desired[id(row)] = {
                "member_no": row["member_no"],
                "name": row["name"] or target["name"],
                "phone": phone,
                "source": SOURCE,
                "ecaptain_id": row.get("external_id") or target.get("ecaptain_id"),
                "active": 1 if row["active"] else 0,
            }
        else:
            desired[id(row)] = {
                "member_no": row["member_no"],
                "name": row["name"] or row["member_no"],
                "phone": row.get("phone"),
                "source": SOURCE,
                "ecaptain_id": row.get("external_id"),
                "active": 1 if row["active"] else 0,
            }

    # 4. Gedeelde nummers binnen het rapport: één winnaar per nummer.
    skip = set(hard_skip)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if id(row) in hard_skip:
            continue
        phone = desired[id(row)]["phone"]
        if not phone:
            continue
        if targets.get(id(row)) is None and not row["active"]:
            continue
        groups.setdefault(phone, []).append(row)

    for phone, group in groups.items():
        if len(group) < 2:
            continue
        owner_rows = [r for r in group
                      if targets.get(id(r)) is not None
                      and targets[id(r)].get("phone") == phone]
        existing_rows = [r for r in group if targets.get(id(r)) is not None]
        winner = min(owner_rows or existing_rows or group,
                     key=lambda r: _natural_key(r["member_no"]))
        for r in group:
            if r is winner:
                continue
            skip.add(id(r))
            if targets.get(id(r)) is not None:
                errors.append(f"Telefoon {phone} komt ook voor bij {_row_label(winner)}; "
                              f"{_row_label(r)} blijft ongewijzigd.")
            else:
                errors.append(f"Telefoon {phone} komt ook voor bij {_row_label(winner)}; "
                              f"{_row_label(r)} is overgeslagen.")

    # 5. Een nummer dat een bestaand lid vrijgeeft, mag naar een nieuw lid. Herhaal tot
    #    er geen conflicten meer zijn: een rij die wegvalt, geeft zijn oude nummer niet vrij.
    active = {id(r) for r in rows if id(r) not in skip}
    while True:
        # Lidnummers en e-Captain-id's moeten uniek blijven; bij een dubbele nieuwe rij
        # wint de eerste in het rapport.
        seen_no: dict[str, dict] = {}
        seen_ext: dict[str, dict] = {}
        duplicates: list[tuple[dict, str, dict]] = []
        for row in rows:
            if id(row) not in active:
                continue
            d = desired[id(row)]
            other = seen_no.get(d["member_no"])
            if other is not None:
                duplicates.append((row, "member_no", other))
                continue
            seen_no[d["member_no"]] = row
            ext = d.get("ecaptain_id")
            if ext:
                other = seen_ext.get(str(ext))
                if other is not None:
                    duplicates.append((row, "ecaptain_id", other))
                    continue
                seen_ext[str(ext)] = row
        if duplicates:
            for row, kind, other in duplicates:
                active.discard(id(row))
                if kind == "member_no":
                    errors.append(f"Lidnummer {desired[id(row)]['member_no']} van "
                                  f"{_row_label(row)} is al in gebruik door {_row_label(other)}; "
                                  f"{_row_label(row)} is overgeslagen.")
                else:
                    errors.append(f"e-Captain-id {desired[id(row)]['ecaptain_id']} van "
                                  f"{_row_label(row)} is al in gebruik door {_row_label(other)}; "
                                  f"{_row_label(row)} is overgeslagen.")
            continue

        releasing: set[int] = set()
        for row in rows:
            if id(row) not in active:
                continue
            target = targets.get(id(row))
            if target is not None and desired[id(row)]["phone"] != target.get("phone"):
                releasing.add(target["id"])
        conflicts = []
        for row in rows:
            if id(row) not in active:
                continue
            phone = desired[id(row)]["phone"]
            if not phone:
                continue
            owner = by_phone.get(phone)
            target = targets.get(id(row))
            if owner is None or (target is not None and owner["id"] == target["id"]):
                continue
            if owner["id"] in releasing:
                continue
            conflicts.append(row)
        if not conflicts:
            break
        for row in conflicts:
            active.discard(id(row))
            phone = desired[id(row)]["phone"]
            owner = by_phone[phone]
            if targets.get(id(row)) is not None:
                errors.append(f"Telefoon {phone} van {_row_label(row)} is al in gebruik door "
                              f"{_member_label(owner)}; {_row_label(row)} blijft ongewijzigd.")
            else:
                errors.append(f"Telefoon {phone} van {_row_label(row)} is al in gebruik door "
                              f"{_member_label(owner)}; {_row_label(row)} is overgeslagen.")

    # 6. Plan: updates, nieuwe leden en (verderop) deactiveringen.
    plan: list[dict] = []
    for row in rows:
        if id(row) not in active:
            continue
        target = targets.get(id(row))
        wanted = desired[id(row)]
        if target is not None:
            plan.append({"action": "update", "member": target, "row": row,
                         "desired": wanted, "changes": _changes(target, wanted)})
        elif row["active"]:
            plan.append({"action": "add", "member": None, "row": row,
                         "desired": wanted, "changes": []})

    # 7. Niet meer in het rapport: bewaren maar niet-actief.
    matched_ids = {m["id"] for m in targets.values()}
    for member in current:
        if (member.get("source") == SOURCE and member.get("active")
                and member["id"] not in matched_ids):
            plan.append({"action": "deactivate", "member": member, "row": None,
                         "desired": {**member, "active": 0},
                         "changes": ["Actief: ja -> nee"]})
    return plan, errors


def _item(member: dict) -> dict:
    return {"member_no": member["member_no"], "name": member["name"],
            "phone": member.get("phone")}


def _plan_report(plan: list[dict]) -> tuple[dict, dict]:
    """Maakt een rapport per lid: nieuw, gewijzigd, verwijderd (niet-actief), opnieuw actief.

    De categorieën zijn exclusief: een lid dat niet-actief wordt, staat bij 'verwijderd'
    (met de eventuele andere wijzigingen), niet ook bij 'gewijzigd'.
    """
    report = {"nieuw": [], "gewijzigd": [], "verwijderd": [], "geactiveerd": []}
    unchanged = 0
    for p in plan:
        if p["action"] == "add":
            report["nieuw"].append(_item(p["desired"]))
        elif p["action"] == "deactivate":
            report["verwijderd"].append({
                **_item(p["member"]),
                "reason": "Niet meer in het e-Captain-rapport",
            })
        elif p["action"] == "update":
            old, new = p["member"], p["desired"]
            item = _item(new)
            if p["changes"]:
                item["changes"] = p["changes"]
            was_active, is_active = bool(old.get("active")), bool(new.get("active"))
            if was_active and not is_active:
                report["verwijderd"].append(item)
            elif not was_active and is_active:
                report["geactiveerd"].append(item)
            elif p["changes"]:
                report["gewijzigd"].append(item)
            else:
                unchanged += 1

    counts = {
        "nieuw": len(report["nieuw"]),
        "gewijzigd": len(report["gewijzigd"]),
        "gedeactiveerd": len(report["verwijderd"]),
        "geactiveerd": len(report["geactiveerd"]),
        "ongewijzigd": unchanged,
    }
    return report, counts


def _apply(plan: list[dict], actor: str, ts: str) -> None:
    logged: list[tuple[str, int, str | None]] = []
    with db.tx() as c:
        # Geef eerst alle nummers vrij die van lid veranderen. Zo kunnen leden van nummer
        # wisselen en kan een vrijgekomen nummer naar een nieuw lid zonder UNIQUE-conflict.
        for p in plan:
            if (p["action"] == "update"
                    and p["member"].get("phone") != p["desired"].get("phone")):
                c.execute("UPDATE members SET phone=NULL WHERE id=?", (p["member"]["id"],))

        for p in plan:
            if p["action"] == "add":
                d = p["desired"]
                cur = c.execute(
                    """INSERT INTO members (member_no, name, phone, note, source, ecaptain_id,
                                            active, ecaptain_synced_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (d["member_no"], d["name"], d["phone"], "", d["source"], d["ecaptain_id"],
                     d["active"], ts, ts, ts))
                new_id = cur.lastrowid
                # Nieuwe leden krijgen, net als bij manueel toevoegen, toegang tot alle toestellen.
                c.execute("INSERT OR IGNORE INTO member_access (member_id, device_id) "
                          "SELECT ?, id FROM devices", (new_id,))
                logged.append(("add", new_id, "Lid toegevoegd vanuit e-Captain"))
            elif p["action"] == "update":
                d, m = p["desired"], p["member"]
                if p["changes"]:
                    c.execute(
                        """UPDATE members SET member_no=?, name=?, phone=?, source=?, ecaptain_id=?,
                               active=?, ecaptain_synced_at=?, updated_at=? WHERE id=?""",
                        (d["member_no"], d["name"], d["phone"], d["source"], d["ecaptain_id"],
                         d["active"], ts, ts, m["id"]))
                    logged.append(("update", m["id"], "; ".join(p["changes"])))
                else:
                    c.execute("UPDATE members SET ecaptain_synced_at=? WHERE id=?", (ts, m["id"]))
            elif p["action"] == "deactivate":
                m = p["member"]
                c.execute("UPDATE members SET active=0, ecaptain_synced_at=?, updated_at=? WHERE id=?",
                          (ts, ts, m["id"]))
                logged.append(("deactivate", m["id"], "Niet meer actief in e-Captain"))

    for kind, member_id, detail in logged:
        member = members.get(member_id)
        if not member:
            continue
        reason = {"add": "Import e-captain: lid toegevoegd",
                  "update": "Import e-captain: lid gewijzigd",
                  "deactivate": "Import e-captain: lid niet actief"}[kind]
        db.log_event("admin", actor=actor, member=member, phone=member["phone"], result="ok",
                     reason=reason, detail=detail)


def sync_rows(rows: list[dict], actor: str, filename: str = "",
              warnings: list[str] | None = None, dry_run: bool = False) -> dict:
    warnings = list(warnings or [])
    current = members.list_members()
    plan, errors = _build_plan(rows, current)
    report, counts = _plan_report(plan)
    ts = db.now_iso()
    summary = {
        "ok": True,
        "dry_run": dry_run,
        "bestand": filename,
        "totaal": len(rows),
        **counts,
        "overgeslagen": len(errors),
        "fouten": errors[:100],
        "waarschuwingen": warnings[:100],
        "rapport": report,
        "ts": ts,
    }
    if dry_run:
        return summary

    _apply(plan, actor, ts)
    stored = {k: summary[k] for k in ("bestand", "totaal", "nieuw", "gewijzigd", "gedeactiveerd",
                                      "geactiveerd", "ongewijzigd", "overgeslagen", "ts")}
    db.set_setting("ecaptain_sync", stored)
    detail = (f"{filename or 'rapport'}: {summary['nieuw']} nieuw, {summary['gewijzigd']} gewijzigd, "
              f"{summary['gedeactiveerd']} verwijderd/niet actief, {summary['geactiveerd']} opnieuw actief, "
              f"{summary['ongewijzigd']} ongewijzigd, {summary['overgeslagen']} overgeslagen")
    db.log_event("admin", actor=actor, result="fout" if errors else "ok",
                 reason="Import e-captain", detail=detail)
    return summary


def sync_file(filename: str, content: bytes, region: str, actor: str,
              dry_run: bool = False) -> dict:
    rows, warnings = parse_report(filename, content, region)
    return sync_rows(rows, actor, filename=filename, warnings=warnings, dry_run=dry_run)


def status() -> dict:
    last = db.get_setting("ecaptain_sync")
    row = db.query_one(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN source='ecaptain' THEN 1 ELSE 0 END) AS ecaptain, "
        "SUM(CASE WHEN source='ecaptain' AND active=1 THEN 1 ELSE 0 END) AS ecaptain_active, "
        "SUM(CASE WHEN source='manual' THEN 1 ELSE 0 END) AS manual "
        "FROM members") or {}
    return {
        "last": last,
        "members": {k: int(row.get(k) or 0)
                    for k in ("total", "ecaptain", "ecaptain_active", "manual")},
    }
