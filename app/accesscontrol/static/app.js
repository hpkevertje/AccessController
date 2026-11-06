"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------- Vertalingen / Translations / Traductions ---------------- */
const LOCALES = { nl: "nl-BE", en: "en-GB", fr: "fr-BE" };

const I18N = {
  nl: {
    "tab.members": "Leden",
    "tab.events": "Logboek",
    "tab.config": "Configuratie",

    "common.save": "Opslaan",
    "common.cancel": "Annuleren",
    "common.ok": "OK",
    "common.delete": "Verwijderen",
    "common.edit": "Bewerken",
    "common.import": "Importeren",
    "common.exportExcel": "Exporteren (Excel)",
    "common.name": "Naam",
    "common.phone": "Telefoon",
    "common.note": "Opmerking",
    "common.access": "Toegang",
    "common.memberNo": "Lidnr",
    "common.active": "actief",
    "common.inactive": "niet actief",
    "common.on": "Aan",
    "common.off": "Uit",
    "common.offValue": "uit",
    "common.open": "Open",
    "common.pulse": "puls",

    "members.new": "+ Nieuw lid",
    "members.searchPlaceholder": "Zoek op naam, lidnr, telefoon, opmerking",
    "members.filterAll": "Alle leden",
    "members.filterNoPhone": "Zonder telefoon",
    "members.filterNoAccess": "Zonder enige toegang",
    "members.count": "{shown} van {total}",
    "members.none": "Geen leden gevonden.",
    "members.deleteTitle": "Lid verwijderen",
    "members.deleteText": "{name} (lidnr {no}) definitief verwijderen? Het logboek blijft bewaard.",
    "members.deleted": "Lid verwijderd.",
    "members.titleNew": "Nieuw lid",
    "members.titleEdit": "Lid bewerken",
    "members.saved": "Opgeslagen.",
    "members.accessTitle": "Toegang {device}",
    "members.phonePlaceholder": "0470 12 34 56 of +32 470 12 34 56",

    "import.title": "Leden importeren",
    "import.helpHtml": "Excel-bestand (.xlsx) in hetzelfde formaat als de export. Kolommen: <b>Lidnr</b> (verplicht), Naam, Telefoon, een kolom \"Toegang &lt;toestel&gt;\" per toestel, Opmerking. Toegang: ja / nee. Bestaande leden worden bijgewerkt op lidnr, leden die niet in het bestand staan blijven behouden. Bij één fout wordt het hele bestand geweigerd.",
    "import.close": "Sluiten",
    "import.chooseFile": "Kies een bestand.",
    "import.success": "Import gelukt: {created} nieuw, {updated} gewijzigd, {unchanged} ongewijzigd. {missing} bestaande leden stonden niet in het bestand en zijn behouden.",
    "import.rejected": "Bestand geweigerd, er is niets gewijzigd.",

    "events.from": "Van",
    "events.to": "Tot",
    "events.allCategories": "Alle soorten",
    "events.allDevices": "Alle toestellen",
    "events.allResults": "Alle resultaten",
    "events.searchPlaceholder": "Zoek naam, lidnr, telefoon, admin, tekst",
    "events.clear": "Wissen",
    "events.live": "Live",
    "events.col.time": "Tijdstip",
    "events.col.category": "Soort",
    "events.col.device": "Toestel",
    "events.col.who": "Wie",
    "events.col.phone": "Telefoon",
    "events.col.result": "Resultaat",
    "events.col.description": "Omschrijving",
    "events.col.detail": "Detail",
    "events.col.relay": "Relais",
    "events.col.relayTitle": "Bevestigd door relaismodule",
    "events.prev": "‹ Vorige",
    "events.next": "Volgende ›",
    "events.pageInfo": "Pagina {page} van {pages} ({total} regels)",
    "events.none": "Geen regels voor deze filters.",
    "events.unknown": "onbekend",
    "events.by": "door {actor}",
    "events.confirmedAt": "Bevestigd {time}",
    "events.noConfirmation": "Geen bevestiging van de relaismodule",

    "category.oproep": "Oproep",
    "category.manueel": "Manueel",
    "category.admin": "Admin",
    "category.sms": "SMS",
    "category.systeem": "Systeem",

    "result.toegelaten": "Toegelaten",
    "result.geweigerd": "Geweigerd",
    "result.ok": "OK",
    "result.fout": "Fout",
    "result.info": "Info",

    "status.serverUnreachable": "Server onbereikbaar",
    "status.mqttConnected": "MQTT verbonden",
    "status.mqttDisconnected": "MQTT niet verbonden",
    "status.activateInConfig": "Activeer in Configuratie.",
    "status.rtuCable": "RTU: kabel niet verbonden",
    "status.rtuNoGsm": "RTU: geen GSM-netwerk",
    "status.rtuOk": "RTU ok",
    "status.relayModule": "Relaismodule",
    "status.relayUnknown": "Relais ?",
    "status.relayOn": "Relais aan",
    "status.relayOff": "Relais uit",
    "status.relayOnRemaining": "Relais aan, nog {time}",
    "status.remaining": ", nog {time}",
    "status.lastSms": "Laatste SMS",
    "status.from": "van",
    "status.newSms": "{count} nieuwe SMS",
    "status.view": "Bekijken",

    "devices.legend": "Toestellen",
    "devices.help": "Eén toestel = één RTU5024 (eigen telefoonnummer) en één relaismodule (Tasmota of Shelly 1 Gen3).",
    "devices.col.name": "Naam",
    "devices.col.active": "Actief",
    "devices.col.serial": "Seriële poort",
    "devices.col.type": "Type",
    "devices.col.topic": "Topic / ID",
    "devices.col.onTime": "Aan-tijd",
    "devices.col.dedupe": "Ontdubbeling",
    "devices.add": "+ Toestel toevoegen",
    "devices.noDevices": "Nog geen toestellen.",
    "devices.addUnderConfig": "Voeg een toestel toe onder Configuratie.",
    "devices.addOne": "Voeg er een toe.",
    "devices.titleNew": "Nieuw toestel",
    "devices.titleEdit": "Toestel {name} bewerken",
    "devices.field.namePlaceholder": "bv. Water, Poort, Slagboom",
    "devices.field.enabled": "Actief",
    "devices.field.serial": "Seriële poort van de RTU",
    "devices.field.baudrate": "Baudrate",
    "devices.field.relayType": "Type relaismodule",
    "devices.field.topic": "MQTT-topic / Shelly-ID",
    "devices.field.onTime": "Aan-tijd per toelating (seconden)",
    "devices.field.dedupe": "Ontdubbeling oproepen (seconden, 0 = uit)",
    "devices.grant.legend": "Toegang voor alle bestaande leden?",
    "devices.grant.yes": "Ja, alle bestaande leden krijgen toegang",
    "devices.grant.no": "Nee, ik geef zelf toegang per lid",
    "devices.topicPlaceholderShelly": "bv. shelly1g3-d0cf13dde9dc (topic_prefix van de Shelly)",
    "devices.topicPlaceholderTasmota": "zoals 'Topic' op de relaismodule",
    "devices.saved": "Toestel opgeslagen.",
    "devices.deleted": "Toestel verwijderd.",
    "devices.deleteTitle": "Toestel verwijderen",
    "devices.deleteText": "{name} verwijderen? De toegang van alle leden tot dit toestel verdwijnt. Het logboek blijft bewaard.",
    "devices.grantRequired": "Kies of alle bestaande leden toegang krijgen.",

    "control.manual": "Manuele bediening",
    "control.disableNow": "{name} nu uitschakelen?",
    "control.enableFor": "{name} inschakelen voor {time}?",
    "control.open": "{name} openen?",
    "control.disable": "Uitschakelen",
    "control.execute": "Uitvoeren",
    "control.sent": "Commando verzonden.",

    "config.mqtt": "MQTT",
    "config.host": "Host",
    "config.port": "Poort",
    "config.username": "Gebruiker",
    "config.password": "Wachtwoord",
    "config.passwordPlaceholder": "leeg = ongewijzigd",
    "config.passwordSet": "ingesteld, leeg = ongewijzigd",
    "config.passwordNone": "geen wachtwoord",
    "config.clientId": "Client-ID",
    "config.general": "Algemeen",
    "config.retentionMonths": "Logboek bewaren (maanden)",
    "config.phoneRegion": "Standaard landcode telefoon",
    "config.backupLegend": "Automatische back-up",
    "config.backupDaily": "Dagelijks een back-up maken",
    "config.backupFolder": "Map (in de container)",
    "config.backupTime": "Tijdstip",
    "config.backupKeep": "Bewaren (dagen)",
    "config.backupSharepoint": "Ook naar SharePoint",
    "config.tenantId": "Tenant-ID",
    "config.appClientId": "Client-ID (app)",
    "config.siteUrl": "Site-URL",
    "config.siteUrlPlaceholder": "https://bedrijf.sharepoint.com/sites/IT",
    "config.spFolder": "Map in de documentbibliotheek",
    "config.spKeep": "Bewaren op SharePoint (dagen)",
    "config.saved": "Configuratie opgeslagen.",
    "config.secretSet": "Client secret: ingesteld via SHAREPOINT_CLIENT_SECRET.",
    "config.secretNone": "Client secret: niet ingesteld. Zet SHAREPOINT_CLIENT_SECRET in de stack-variabelen.",
    "config.backupNow": "Back-up nu",
    "config.backupRun": "Nu back-up maken",
    "config.backupDownload": "Back-up downloaden",
    "config.backupRestore": "Back-up terugzetten…",
    "config.backupNone": "Nog geen back-up gemaakt.",
    "config.lastBackup": "Laatste back-up:",
    "config.automatic": ", automatisch",
    "config.lastSuccess": "Laatste geslaagde: {time}",
    "config.folder": "Map",
    "config.sharepoint": "SharePoint",
    "config.open": "openen",
    "config.backupCreated": "Back-up gemaakt.",
    "config.backupCreatedErrors": "Back-up gemaakt met fouten.",
    "config.restoreTitle": "Back-up terugzetten",
    "config.restoreText": "{file} terugzetten? Alle leden, toestellen, instellingen en het logboek worden vervangen door de inhoud van deze back-up. Er wordt eerst een veiligheidskopie van de huidige toestand gemaakt.",
    "config.restoreButton": "Terugzetten",
    "config.restored": "Back-up teruggezet ({count} leden). De pagina wordt herladen.",

    "error.api": "Fout {status}",
    "me.noCloudflare": "{email} (zonder Cloudflare)"
  },

  en: {
    "tab.members": "Members",
    "tab.events": "Logbook",
    "tab.config": "Configuration",

    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.ok": "OK",
    "common.delete": "Delete",
    "common.edit": "Edit",
    "common.import": "Import",
    "common.exportExcel": "Export (Excel)",
    "common.name": "Name",
    "common.phone": "Phone",
    "common.note": "Note",
    "common.access": "Access",
    "common.memberNo": "Member ID",
    "common.active": "active",
    "common.inactive": "inactive",
    "common.on": "On",
    "common.off": "Off",
    "common.offValue": "off",
    "common.open": "Open",
    "common.pulse": "pulse",

    "members.new": "+ New member",
    "members.searchPlaceholder": "Search by name, member ID, phone, note",
    "members.filterAll": "All members",
    "members.filterNoPhone": "Without phone",
    "members.filterNoAccess": "Without any access",
    "members.count": "{shown} of {total}",
    "members.none": "No members found.",
    "members.deleteTitle": "Delete member",
    "members.deleteText": "Permanently delete {name} (member ID {no})? The logbook is kept.",
    "members.deleted": "Member deleted.",
    "members.titleNew": "New member",
    "members.titleEdit": "Edit member",
    "members.saved": "Saved.",
    "members.accessTitle": "Access {device}",
    "members.phonePlaceholder": "0470 12 34 56 or +32 470 12 34 56",

    "import.title": "Import members",
    "import.helpHtml": "Excel file (.xlsx) in the same format as the export. Columns: <b>Member ID</b> (required), Name, Phone, a column \"Access &lt;device&gt;\" per device, Note. Access: yes / no. Existing members are updated by member ID, members not in the file are kept. If there is one error the whole file is rejected.",
    "import.close": "Close",
    "import.chooseFile": "Choose a file.",
    "import.success": "Import successful: {created} new, {updated} updated, {unchanged} unchanged. {missing} existing members were not in the file and have been kept.",
    "import.rejected": "File rejected, nothing changed.",

    "events.from": "From",
    "events.to": "To",
    "events.allCategories": "All types",
    "events.allDevices": "All devices",
    "events.allResults": "All results",
    "events.searchPlaceholder": "Search name, member ID, phone, admin, text",
    "events.clear": "Clear",
    "events.live": "Live",
    "events.col.time": "Time",
    "events.col.category": "Type",
    "events.col.device": "Device",
    "events.col.who": "Who",
    "events.col.phone": "Phone",
    "events.col.result": "Result",
    "events.col.description": "Description",
    "events.col.detail": "Detail",
    "events.col.relay": "Relay",
    "events.col.relayTitle": "Confirmed by relay module",
    "events.prev": "‹ Previous",
    "events.next": "Next ›",
    "events.pageInfo": "Page {page} of {pages} ({total} entries)",
    "events.none": "No entries for these filters.",
    "events.unknown": "unknown",
    "events.by": "by {actor}",
    "events.confirmedAt": "Confirmed {time}",
    "events.noConfirmation": "No confirmation from the relay module",

    "category.oproep": "Call",
    "category.manueel": "Manual",
    "category.admin": "Admin",
    "category.sms": "SMS",
    "category.systeem": "System",

    "result.toegelaten": "Allowed",
    "result.geweigerd": "Denied",
    "result.ok": "OK",
    "result.fout": "Error",
    "result.info": "Info",

    "status.serverUnreachable": "Server unreachable",
    "status.mqttConnected": "MQTT connected",
    "status.mqttDisconnected": "MQTT not connected",
    "status.activateInConfig": "Activate in Configuration.",
    "status.rtuCable": "RTU: cable not connected",
    "status.rtuNoGsm": "RTU: no GSM network",
    "status.rtuOk": "RTU ok",
    "status.relayModule": "Relay module",
    "status.relayUnknown": "Relay ?",
    "status.relayOn": "Relay on",
    "status.relayOff": "Relay off",
    "status.relayOnRemaining": "Relay on, {time} left",
    "status.remaining": ", {time} left",
    "status.lastSms": "Last SMS",
    "status.from": "from",
    "status.newSms": "{count} new SMS",
    "status.view": "View",

    "devices.legend": "Devices",
    "devices.help": "One device = one RTU5024 (its own phone number) and one relay module (Tasmota or Shelly 1 Gen3).",
    "devices.col.name": "Name",
    "devices.col.active": "Active",
    "devices.col.serial": "Serial port",
    "devices.col.type": "Type",
    "devices.col.topic": "Topic / ID",
    "devices.col.onTime": "On time",
    "devices.col.dedupe": "Deduplication",
    "devices.add": "+ Add device",
    "devices.noDevices": "No devices yet.",
    "devices.addUnderConfig": "Add a device under Configuration.",
    "devices.addOne": "Add one.",
    "devices.titleNew": "New device",
    "devices.titleEdit": "Edit device {name}",
    "devices.field.namePlaceholder": "e.g. Water, Gate, Barrier",
    "devices.field.enabled": "Active",
    "devices.field.serial": "Serial port of the RTU",
    "devices.field.baudrate": "Baud rate",
    "devices.field.relayType": "Relay module type",
    "devices.field.topic": "MQTT topic / Shelly ID",
    "devices.field.onTime": "On time per grant (seconds)",
    "devices.field.dedupe": "Deduplicate calls (seconds, 0 = off)",
    "devices.grant.legend": "Access for all existing members?",
    "devices.grant.yes": "Yes, all existing members get access",
    "devices.grant.no": "No, I will grant access per member",
    "devices.topicPlaceholderShelly": "e.g. shelly1g3-d0cf13dde9dc (topic_prefix of the Shelly)",
    "devices.topicPlaceholderTasmota": "like 'Topic' on the relay module",
    "devices.saved": "Device saved.",
    "devices.deleted": "Device deleted.",
    "devices.deleteTitle": "Delete device",
    "devices.deleteText": "Delete {name}? All members will lose access to this device. The logbook is kept.",
    "devices.grantRequired": "Choose whether all existing members get access.",

    "control.manual": "Manual control",
    "control.disableNow": "Disable {name} now?",
    "control.enableFor": "Enable {name} for {time}?",
    "control.open": "Open {name}?",
    "control.disable": "Disable",
    "control.execute": "Execute",
    "control.sent": "Command sent.",

    "config.mqtt": "MQTT",
    "config.host": "Host",
    "config.port": "Port",
    "config.username": "Username",
    "config.password": "Password",
    "config.passwordPlaceholder": "empty = unchanged",
    "config.passwordSet": "set, empty = unchanged",
    "config.passwordNone": "no password",
    "config.clientId": "Client ID",
    "config.general": "General",
    "config.retentionMonths": "Keep logbook (months)",
    "config.phoneRegion": "Default phone country code",
    "config.backupLegend": "Automatic backup",
    "config.backupDaily": "Create a backup daily",
    "config.backupFolder": "Folder (in the container)",
    "config.backupTime": "Time",
    "config.backupKeep": "Keep (days)",
    "config.backupSharepoint": "Also to SharePoint",
    "config.tenantId": "Tenant ID",
    "config.appClientId": "Client ID (app)",
    "config.siteUrl": "Site URL",
    "config.siteUrlPlaceholder": "https://company.sharepoint.com/sites/IT",
    "config.spFolder": "Folder in the document library",
    "config.spKeep": "Keep on SharePoint (days)",
    "config.saved": "Configuration saved.",
    "config.secretSet": "Client secret: set via SHAREPOINT_CLIENT_SECRET.",
    "config.secretNone": "Client secret: not set. Set SHAREPOINT_CLIENT_SECRET in the stack variables.",
    "config.backupNow": "Back up now",
    "config.backupRun": "Create backup now",
    "config.backupDownload": "Download backup",
    "config.backupRestore": "Restore backup…",
    "config.backupNone": "No backup created yet.",
    "config.lastBackup": "Last backup:",
    "config.automatic": ", automatic",
    "config.lastSuccess": "Last successful: {time}",
    "config.folder": "Folder",
    "config.sharepoint": "SharePoint",
    "config.open": "open",
    "config.backupCreated": "Backup created.",
    "config.backupCreatedErrors": "Backup created with errors.",
    "config.restoreTitle": "Restore backup",
    "config.restoreText": "Restore {file}? All members, devices, settings and the logbook will be replaced by the contents of this backup. A safety copy of the current state is made first.",
    "config.restoreButton": "Restore",
    "config.restored": "Backup restored ({count} members). The page will reload.",

    "error.api": "Error {status}",
    "me.noCloudflare": "{email} (without Cloudflare)"
  },

  fr: {
    "tab.members": "Membres",
    "tab.events": "Journal",
    "tab.config": "Configuration",

    "common.save": "Enregistrer",
    "common.cancel": "Annuler",
    "common.ok": "OK",
    "common.delete": "Supprimer",
    "common.edit": "Modifier",
    "common.import": "Importer",
    "common.exportExcel": "Exporter (Excel)",
    "common.name": "Nom",
    "common.phone": "Téléphone",
    "common.note": "Remarque",
    "common.access": "Accès",
    "common.memberNo": "N° de membre",
    "common.active": "actif",
    "common.inactive": "inactif",
    "common.on": "Marche",
    "common.off": "Arrêt",
    "common.offValue": "désactivé",
    "common.open": "Ouvrir",
    "common.pulse": "impulsion",

    "members.new": "+ Nouveau membre",
    "members.searchPlaceholder": "Rechercher par nom, n° de membre, téléphone, remarque",
    "members.filterAll": "Tous les membres",
    "members.filterNoPhone": "Sans téléphone",
    "members.filterNoAccess": "Sans aucun accès",
    "members.count": "{shown} sur {total}",
    "members.none": "Aucun membre trouvé.",
    "members.deleteTitle": "Supprimer le membre",
    "members.deleteText": "Supprimer définitivement {name} (n° de membre {no}) ? Le journal est conservé.",
    "members.deleted": "Membre supprimé.",
    "members.titleNew": "Nouveau membre",
    "members.titleEdit": "Modifier le membre",
    "members.saved": "Enregistré.",
    "members.accessTitle": "Accès {device}",
    "members.phonePlaceholder": "0470 12 34 56 ou +32 470 12 34 56",

    "import.title": "Importer des membres",
    "import.helpHtml": "Fichier Excel (.xlsx) au même format que l'export. Colonnes : <b>N° de membre</b> (obligatoire), Nom, Téléphone, une colonne \"Accès &lt;appareil&gt;\" par appareil, Remarque. Accès : oui / non. Les membres existants sont mis à jour sur base du n° de membre, les membres absents du fichier sont conservés. En cas d'une seule erreur, tout le fichier est refusé.",
    "import.close": "Fermer",
    "import.chooseFile": "Choisissez un fichier.",
    "import.success": "Import réussi : {created} nouveaux, {updated} modifiés, {unchanged} inchangés. {missing} membres existants n'étaient pas dans le fichier et ont été conservés.",
    "import.rejected": "Fichier refusé, rien n'a été modifié.",

    "events.from": "Du",
    "events.to": "Au",
    "events.allCategories": "Tous les types",
    "events.allDevices": "Tous les appareils",
    "events.allResults": "Tous les résultats",
    "events.searchPlaceholder": "Rechercher nom, n° de membre, téléphone, admin, texte",
    "events.clear": "Effacer",
    "events.live": "Direct",
    "events.col.time": "Date et heure",
    "events.col.category": "Type",
    "events.col.device": "Appareil",
    "events.col.who": "Qui",
    "events.col.phone": "Téléphone",
    "events.col.result": "Résultat",
    "events.col.description": "Description",
    "events.col.detail": "Détail",
    "events.col.relay": "Relais",
    "events.col.relayTitle": "Confirmé par le module de relais",
    "events.prev": "‹ Précédent",
    "events.next": "Suivant ›",
    "events.pageInfo": "Page {page} sur {pages} ({total} lignes)",
    "events.none": "Aucune ligne pour ces filtres.",
    "events.unknown": "inconnu",
    "events.by": "par {actor}",
    "events.confirmedAt": "Confirmé {time}",
    "events.noConfirmation": "Aucune confirmation du module de relais",

    "category.oproep": "Appel",
    "category.manueel": "Manuel",
    "category.admin": "Admin",
    "category.sms": "SMS",
    "category.systeem": "Système",

    "result.toegelaten": "Autorisé",
    "result.geweigerd": "Refusé",
    "result.ok": "OK",
    "result.fout": "Erreur",
    "result.info": "Info",

    "status.serverUnreachable": "Serveur inaccessible",
    "status.mqttConnected": "MQTT connecté",
    "status.mqttDisconnected": "MQTT non connecté",
    "status.activateInConfig": "Activez dans Configuration.",
    "status.rtuCable": "RTU : câble non connecté",
    "status.rtuNoGsm": "RTU : pas de réseau GSM",
    "status.rtuOk": "RTU ok",
    "status.relayModule": "Module de relais",
    "status.relayUnknown": "Relais ?",
    "status.relayOn": "Relais activé",
    "status.relayOff": "Relais désactivé",
    "status.relayOnRemaining": "Relais activé, encore {time}",
    "status.remaining": ", encore {time}",
    "status.lastSms": "Dernier SMS",
    "status.from": "de",
    "status.newSms": "{count} nouveaux SMS",
    "status.view": "Voir",

    "devices.legend": "Appareils",
    "devices.help": "Un appareil = un RTU5024 (son propre numéro de téléphone) et un module de relais (Tasmota ou Shelly 1 Gen3).",
    "devices.col.name": "Nom",
    "devices.col.active": "Actif",
    "devices.col.serial": "Port série",
    "devices.col.type": "Type",
    "devices.col.topic": "Sujet / ID",
    "devices.col.onTime": "Durée d'activation",
    "devices.col.dedupe": "Déduplication",
    "devices.add": "+ Ajouter un appareil",
    "devices.noDevices": "Aucun appareil.",
    "devices.addUnderConfig": "Ajoutez un appareil dans Configuration.",
    "devices.addOne": "Ajoutez-en un.",
    "devices.titleNew": "Nouvel appareil",
    "devices.titleEdit": "Modifier l'appareil {name}",
    "devices.field.namePlaceholder": "ex. Eau, Portail, Barrière",
    "devices.field.enabled": "Actif",
    "devices.field.serial": "Port série du RTU",
    "devices.field.baudrate": "Débit en bauds",
    "devices.field.relayType": "Type de module de relais",
    "devices.field.topic": "Sujet MQTT / ID Shelly",
    "devices.field.onTime": "Durée d'activation par autorisation (secondes)",
    "devices.field.dedupe": "Déduplication des appels (secondes, 0 = désactivé)",
    "devices.grant.legend": "Accès pour tous les membres existants ?",
    "devices.grant.yes": "Oui, tous les membres existants obtiennent l'accès",
    "devices.grant.no": "Non, j'accorde l'accès par membre",
    "devices.topicPlaceholderShelly": "ex. shelly1g3-d0cf13dde9dc (topic_prefix du Shelly)",
    "devices.topicPlaceholderTasmota": "comme 'Topic' sur le module de relais",
    "devices.saved": "Appareil enregistré.",
    "devices.deleted": "Appareil supprimé.",
    "devices.deleteTitle": "Supprimer l'appareil",
    "devices.deleteText": "Supprimer {name} ? Tous les membres perdront l'accès à cet appareil. Le journal est conservé.",
    "devices.grantRequired": "Choisissez si tous les membres existants obtiennent l'accès.",

    "control.manual": "Commande manuelle",
    "control.disableNow": "Désactiver {name} maintenant ?",
    "control.enableFor": "Activer {name} pendant {time} ?",
    "control.open": "Ouvrir {name} ?",
    "control.disable": "Désactiver",
    "control.execute": "Exécuter",
    "control.sent": "Commande envoyée.",

    "config.mqtt": "MQTT",
    "config.host": "Hôte",
    "config.port": "Port",
    "config.username": "Utilisateur",
    "config.password": "Mot de passe",
    "config.passwordPlaceholder": "vide = inchangé",
    "config.passwordSet": "défini, vide = inchangé",
    "config.passwordNone": "aucun mot de passe",
    "config.clientId": "ID client",
    "config.general": "Général",
    "config.retentionMonths": "Conserver le journal (mois)",
    "config.phoneRegion": "Indicatif téléphonique par défaut",
    "config.backupLegend": "Sauvegarde automatique",
    "config.backupDaily": "Créer une sauvegarde quotidienne",
    "config.backupFolder": "Dossier (dans le conteneur)",
    "config.backupTime": "Heure",
    "config.backupKeep": "Conserver (jours)",
    "config.backupSharepoint": "Aussi vers SharePoint",
    "config.tenantId": "ID locataire",
    "config.appClientId": "ID client (application)",
    "config.siteUrl": "URL du site",
    "config.siteUrlPlaceholder": "https://entreprise.sharepoint.com/sites/IT",
    "config.spFolder": "Dossier dans la bibliothèque de documents",
    "config.spKeep": "Conserver sur SharePoint (jours)",
    "config.saved": "Configuration enregistrée.",
    "config.secretSet": "Client secret : défini via SHAREPOINT_CLIENT_SECRET.",
    "config.secretNone": "Client secret : non défini. Définissez SHAREPOINT_CLIENT_SECRET dans les variables de la stack.",
    "config.backupNow": "Sauvegarder maintenant",
    "config.backupRun": "Créer une sauvegarde maintenant",
    "config.backupDownload": "Télécharger la sauvegarde",
    "config.backupRestore": "Restaurer la sauvegarde…",
    "config.backupNone": "Aucune sauvegarde créée pour l'instant.",
    "config.lastBackup": "Dernière sauvegarde :",
    "config.automatic": ", automatique",
    "config.lastSuccess": "Dernière réussie : {time}",
    "config.folder": "Dossier",
    "config.sharepoint": "SharePoint",
    "config.open": "ouvrir",
    "config.backupCreated": "Sauvegarde créée.",
    "config.backupCreatedErrors": "Sauvegarde créée avec des erreurs.",
    "config.restoreTitle": "Restaurer la sauvegarde",
    "config.restoreText": "Restaurer {file} ? Tous les membres, appareils, paramètres et le journal seront remplacés par le contenu de cette sauvegarde. Une copie de sécurité de l'état actuel est d'abord créée.",
    "config.restoreButton": "Restaurer",
    "config.restored": "Sauvegarde restaurée ({count} membres). La page va être rechargée.",

    "error.api": "Erreur {status}",
    "me.noCloudflare": "{email} (sans Cloudflare)"
  }
};

let currentLanguage = (() => {
  try {
    const stored = localStorage.getItem("lang");
    return I18N[stored] ? stored : "nl";
  } catch { return "nl"; }
})();

function t(key, vars) {
  const dict = I18N[currentLanguage] || I18N.nl;
  const text = dict[key] ?? I18N.nl[key] ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m)) : text;
}

const categoryLabel = (cat) => t(`category.${cat}`);
const resultLabel = (res) => t(`result.${res}`);

function applyStaticTranslations() {
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $$("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}

function applyLanguage(lang, persist = true) {
  currentLanguage = I18N[lang] ? lang : "nl";
  if (persist) {
    try { localStorage.setItem("lang", currentLanguage); } catch { /* geen opslag */ }
  }
  document.documentElement.lang = currentLanguage;
  $("#language-selector").value = currentLanguage;
  applyStaticTranslations();
  const deviceForm = $("#device-form");
  if (deviceForm) deviceForm.tasmota_topic.placeholder = deviceTopicPlaceholder(deviceForm.relay_type.value);
  if (lastStatus) renderStatus();
  renderDeviceOptions();
  renderMemberHead();
  renderMembers();
  renderDeviceTable();
  if (!$("#tab-events").classList.contains("hidden")) loadEvents();
  if (!$("#tab-config").classList.contains("hidden")) loadConfig();
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  let data = null;
  try { data = await res.json(); } catch { /* geen json */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || t("error.api", { status: res.status }));
    err.errors = (data && data.errors) || [];
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg, error = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (error ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), error ? 6000 : 3000);
}

function confirmDialog(title, text, okLabel = "OK") {
  const dlg = $("#dlg-confirm");
  $("#confirm-title").textContent = title;
  $("#confirm-text").textContent = text;
  $("#confirm-ok").textContent = okLabel;
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
  });
}

const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(LOCALES[currentLanguage] || "nl-BE", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
};
const fmtDur = (s) => {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60), r = s % 60;
  return m ? `${m}:${String(r).padStart(2, "0")}` : `${r} s`;
};
const fmtSetting = (s) => (s >= 60 && s % 60 === 0 ? `${s / 60} min` : s >= 60 ? fmtDur(s) : `${s} s`);

/* ---------------- Tabs ---------------- */
$$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  try { localStorage.setItem("tab", name); } catch { /* geen opslag */ }
  if (name === "events") loadEvents();
  if (name === "config") loadConfig();
}

/* ---------------- Status & bediening ---------------- */
let lastStatus = null;
async function loadStatus() {
  try {
    lastStatus = await api("api/status");
    renderStatus();
  } catch (e) {
    $("#mqtt-badge").className = "badge bad";
    $("#mqtt-badge").textContent = t("status.serverUnreachable");
  }
}

function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

function renderStatus() {
  const s = lastStatus;
  const mb = $("#mqtt-badge");
  mb.className = "badge " + (s.mqtt.connected ? "ok" : "bad");
  mb.textContent = s.mqtt.connected ? t("status.mqttConnected") : t("status.mqttDisconnected");
  mb.title = s.mqtt.error || "";
  renderSmsBanner(s.sms_unread);

  $("#devices").innerHTML = s.devices.length ? s.devices.map((d) => {
    const id = d.id;
    if (!d.enabled) {
      return `<div class="device disabled"><h3>${esc(d.name)} ${badge(t("common.inactive"), "")}</h3>
        <div class="muted">${t("status.activateInConfig")}</div></div>`;
    }
    // Eén RTU-status: kabel (seriële verbinding) en GSM-netwerk samen.
    const noNetwork = ["niet geregistreerd", "geen SIM"].includes(d.gsm);
    const rtu = !d.serial_connected
      ? `<span class="badge bad" title="${esc(d.serial_error)}">${t("status.rtuCable")}</span>`
      : noNetwork
        ? `<span class="badge bad" title="GSM: ${esc(d.gsm)}">${t("status.rtuNoGsm")}</span>`
        : `<span class="badge ok" title="GSM: ${esc(d.gsm)}">${t("status.rtuOk")}</span>`;
    const esp = badge(t("status.relayModule") + " " + d.esp, d.esp === "online" ? "ok" : d.esp === "offline" ? "bad" : "warn");
    let relay = badge(t("status.relayUnknown"), "");
    if (d.relay === "on") relay = `<span class="badge ok relay-on" data-remaining="${d.relay_remaining_s ?? ""}">${t("status.relayOn")}${d.relay_remaining_s != null ? t("status.remaining", { time: fmtDur(d.relay_remaining_s) }) : ""}</span>`;
    else if (d.relay === "off") relay = badge(t("status.relayOff"), "");
    const long = d.on_seconds >= 10;
    const actions = long
      ? `<button class="primary" data-act="on" data-dev="${id}">${t("common.on")} (${fmtSetting(d.on_seconds)})</button>
         <button data-act="off" data-dev="${id}">${t("common.off")}</button>`
      : `<button class="primary" data-act="on" data-dev="${id}">${t("common.open")} (${fmtSetting(d.on_seconds)} ${t("common.pulse")})</button>`;
    const sms = d.last_sms
      ? `<div class="last-sms" title="${esc(d.last_sms.text)}"><span class="muted">${t("status.lastSms")} ${esc(fmtTime(d.last_sms.ts))}, ${t("status.from")} ${esc(d.last_sms.sender)}:</span> ${esc(d.last_sms.text)}</div>`
      : "";
    return `<div class="device"><h3>${esc(d.name)}</h3>
      <div class="badges">${rtu}${esp}${relay}</div>
      <div class="actions">${actions}</div>${sms}</div>`;
  }).join("") : `<div class="device disabled"><h3>${t("devices.noDevices")}</h3><div class="muted">${t("devices.addUnderConfig")}</div></div>`;
}

function renderSmsBanner(u) {
  const banner = $("#sms-banner");
  document.title = u && u.count ? `(${u.count}) AccessController` : "AccessController";
  if (!u || !u.count) { banner.classList.add("hidden"); return; }
  const n = u.newest;
  const from = n.member_name ? `${n.member_name} (${n.actor})` : n.actor;
  $("#sms-banner-text").innerHTML = `<b>${esc(t("status.newSms", { count: u.count }))}</b> <span class="muted">${esc(n.device || "")}, ${esc(fmtTime(n.ts))}, ${t("status.from")} ${esc(from)}:</span> ${esc(n.detail || "")}`;
  banner.classList.remove("hidden");
}

$("#sms-banner-go").addEventListener("click", async () => {
  for (const id of ["#e-from", "#e-to", "#e-device", "#e-result", "#e-q"]) $(id).value = "";
  $("#e-category").value = "sms";
  evPage = 1;
  showTab("events");
  try {
    await api("api/sms/seen", { method: "POST", body: {} });
    loadStatus();
  } catch (e) { toast(e.message, true); }
});

// Aftellen tussen twee statusupdates.
setInterval(() => {
  $$(".relay-on[data-remaining]").forEach((el) => {
    const r = parseInt(el.dataset.remaining, 10);
    if (Number.isNaN(r)) return;
    const n = Math.max(0, r - 1);
    el.dataset.remaining = n;
    el.textContent = t("status.relayOnRemaining", { time: fmtDur(n) });
  });
}, 1000);

$("#devices").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-act]");
  if (!b) return;
  const dev = b.dataset.dev, act = b.dataset.act;
  const d = lastStatus.devices.find((x) => String(x.id) === dev);
  const text = act === "off" ? t("control.disableNow", { name: d.name })
    : d.on_seconds >= 10 ? t("control.enableFor", { name: d.name, time: fmtSetting(d.on_seconds) }) : t("control.open", { name: d.name });
  if (!(await confirmDialog(t("control.manual"), text, act === "off" ? t("control.disable") : t("control.execute")))) return;
  try {
    await api(`api/devices/${dev}/${act}`, { method: "POST", body: {} });
    toast(t("control.sent"));
    setTimeout(loadStatus, 800);
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Toestellen (lijst) ---------------- */
let devicesList = [];

function renderDeviceOptions() {
  const sel = $("#e-device"), cur = sel.value;
  sel.innerHTML = `<option value="">${esc(t("events.allDevices"))}</option>` +
    devicesList.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("");
  sel.value = cur;
}

async function loadDevices() {
  try {
    devicesList = await api("api/devices");
  } catch (e) { toast(e.message, true); }
  renderDeviceOptions();
  renderMemberHead();
  renderMembers();
}

/* ---------------- Leden ---------------- */
let membersData = [];
let sort = { key: "name", dir: 1 };

async function loadMembers() {
  try {
    membersData = await api("api/members");
    renderMembers();
  } catch (e) { toast(e.message, true); }
}

function renderMemberHead() {
  $("#m-head").innerHTML = `
    <th data-sort="member_no">${t("common.memberNo")}</th>
    <th data-sort="name">${t("common.name")}</th>
    <th data-sort="phone">${t("common.phone")}</th>
    ${devicesList.map((d) => `<th data-sort="acc:${d.id}" class="c">${esc(d.name)}</th>`).join("")}
    <th data-sort="note">${t("common.note")}</th>
    <th></th>`;
}

$("#m-head").addEventListener("click", (ev) => {
  const th = ev.target.closest("th[data-sort]");
  if (!th) return;
  sort = { key: th.dataset.sort, dir: sort.key === th.dataset.sort ? -sort.dir : 1 };
  renderMembers();
});

const sortValue = (m, key) => (key.startsWith("acc:") ? !!m.access[key.slice(4)] : m[key]);

function renderMembers() {
  const q = $("#m-search").value.trim().toLowerCase();
  const f = $("#m-filter").value;
  const qDigits = q.replace(/\D/g, "");
  let rows = membersData.filter((m) => {
    if (f === "nophone" && m.phone) return false;
    if (f === "noaccess" && Object.values(m.access).some(Boolean)) return false;
    if (!q) return true;
    const hay = `${m.member_no} ${m.name} ${m.note} ${m.phone || ""}`.toLowerCase();
    if (hay.includes(q)) return true;
    // telefoon: zoek ook op 0470... (zonder landcode)
    return qDigits.length >= 4 && (m.phone || "").replace(/\D/g, "").includes(qDigits.replace(/^0/, ""));
  });
  rows.sort((a, b) => {
    const x = sortValue(a, sort.key), y = sortValue(b, sort.key);
    if (typeof x === "boolean") return (x === y ? 0 : x ? -1 : 1) * sort.dir;
    return String(x ?? "").localeCompare(String(y ?? ""), currentLanguage, { numeric: true, sensitivity: "base" }) * sort.dir;
  });
  $$("#m-head th[data-sort]").forEach((th) => {
    th.classList.toggle("asc", th.dataset.sort === sort.key && sort.dir === 1);
    th.classList.toggle("desc", th.dataset.sort === sort.key && sort.dir === -1);
  });
  $("#m-count").textContent = t("members.count", { shown: rows.length, total: membersData.length });
  const sw = (m, d) => `<label class="switch" title="${esc(t("members.accessTitle", { device: d.name }))}"><input type="checkbox" data-dev="${d.id}" data-id="${m.id}" ${m.access[d.id] ? "checked" : ""}><span></span></label>`;
  const cols = 5 + devicesList.length;
  $("#m-table tbody").innerHTML = rows.length ? rows.map((m) => `
    <tr class="${Object.values(m.access).some(Boolean) ? "" : "inactive"}">
      <td class="mono">${esc(m.member_no)}</td>
      <td>${esc(m.name)}</td>
      <td class="phone">${esc(m.phone || "")}</td>
      ${devicesList.map((d) => `<td class="c">${sw(m, d)}</td>`).join("")}
      <td class="note">${esc(m.note)}</td>
      <td class="actions">
        <button class="small" data-edit="${m.id}">${t("common.edit")}</button>
        <button class="small danger" data-del="${m.id}">${t("common.delete")}</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="${cols}" class="empty">${t("members.none")}</td></tr>`;
}

$("#m-search").addEventListener("input", renderMembers);
$("#m-filter").addEventListener("change", renderMembers);

$("#m-table tbody").addEventListener("change", async (ev) => {
  const cb = ev.target.closest("input[data-dev]");
  if (!cb) return;
  const id = +cb.dataset.id;
  cb.disabled = true;
  try {
    const updated = await api(`api/members/${id}`, { method: "PUT", body: { access: { [cb.dataset.dev]: cb.checked } } });
    membersData = membersData.map((m) => (m.id === id ? updated : m));
    renderMembers();
  } catch (e) {
    cb.checked = !cb.checked;
    toast(e.errors.length ? e.errors.join(" ") : e.message, true);
  } finally { cb.disabled = false; }
});

$("#m-table tbody").addEventListener("click", async (ev) => {
  const edit = ev.target.closest("[data-edit]");
  const del = ev.target.closest("[data-del]");
  if (edit) openMember(membersData.find((m) => m.id === +edit.dataset.edit));
  if (del) {
    const m = membersData.find((x) => x.id === +del.dataset.del);
    if (!(await confirmDialog(t("members.deleteTitle"), t("members.deleteText", { name: m.name, no: m.member_no }), t("common.delete")))) return;
    try {
      await api(`api/members/${m.id}`, { method: "DELETE" });
      toast(t("members.deleted"));
      loadMembers();
    } catch (e) { toast(e.message, true); }
  }
});

let editingId = null;
function openMember(m) {
  editingId = m ? m.id : null;
  const f = $("#member-form");
  $("#member-title").textContent = m ? t("members.titleEdit") : t("members.titleNew");
  f.member_no.value = m ? m.member_no : "";
  f.name.value = m ? m.name : "";
  f.phone.value = m ? m.phone || "" : "";
  f.note.value = m ? m.note : "";
  $("#member-access").innerHTML = devicesList.length
    ? devicesList.map((d) => `<label class="check"><input type="checkbox" data-access="${d.id}" ${!m || m.access[d.id] ? "checked" : ""}> ${t("common.access")} ${esc(d.name)}</label>`).join("")
    : `<span class="muted">${t("devices.noDevices")}</span>`;
  $(".errors", f).innerHTML = "";
  $("#dlg-member").showModal();
  f.member_no.focus();
}
$("#m-new").addEventListener("click", () => openMember(null));

$("#member-save").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const f = $("#member-form");
  const access = {};
  $$("input[data-access]", f).forEach((cb) => { access[cb.dataset.access] = cb.checked; });
  const body = { member_no: f.member_no.value, name: f.name.value, phone: f.phone.value, note: f.note.value, access };
  try {
    if (editingId) await api(`api/members/${editingId}`, { method: "PUT", body });
    else await api("api/members", { method: "POST", body });
    $("#dlg-member").close();
    toast(t("members.saved"));
    loadMembers();
  } catch (e) {
    $(".errors", f).innerHTML = (e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("");
  }
});

/* Import */
$("#m-import").addEventListener("click", () => {
  $("#import-form").reset();
  $("#import-result").innerHTML = "";
  $("#dlg-import").showModal();
});
$("#import-go").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const input = $("#import-form").file;
  if (!input.files.length) { $("#import-result").innerHTML = `<p class="errors">${esc(t("import.chooseFile"))}</p>`; return; }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  $("#import-go").disabled = true;
  try {
    const r = await api("api/members/import", { method: "POST", body: fd });
    $("#import-result").innerHTML = `<p class="ok">${esc(t("import.success", { created: r.nieuw, updated: r.gewijzigd, unchanged: r.ongewijzigd, missing: r.niet_in_bestand }))}</p>`;
    loadMembers();
  } catch (e) {
    $("#import-result").innerHTML = `<p class="errors">${esc(t("import.rejected"))}</p>
      <ul class="errors">${(e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  } finally { $("#import-go").disabled = false; }
});

/* ---------------- Logboek ---------------- */
let evPage = 1;
const EV_PAGE_SIZE = 100;

function eventParams() {
  const p = new URLSearchParams();
  const from = $("#e-from").value, to = $("#e-to").value;
  if (from) p.set("from", new Date(from + "T00:00:00").toISOString().replace(/\.\d{3}Z$/, "Z"));
  if (to) p.set("to", new Date(to + "T23:59:59").toISOString().replace(/\.\d{3}Z$/, "Z"));
  for (const [id, key] of [["#e-category", "category"], ["#e-device", "device"], ["#e-result", "result"], ["#e-q", "q"]]) {
    const v = $(id).value.trim();
    if (v) p.set(key, v);
  }
  return p;
}

const RESULT_CLS = { toegelaten: "ok", ok: "ok", geweigerd: "bad", fout: "bad", info: "" };

async function loadEvents() {
  const p = eventParams();
  $("#e-export").href = "api/events/export.xlsx?" + p.toString();
  p.set("page", evPage);
  p.set("page_size", EV_PAGE_SIZE);
  try {
    const r = await api("api/events?" + p.toString());
    const pages = Math.max(1, Math.ceil(r.total / EV_PAGE_SIZE));
    $("#e-pageinfo").textContent = t("events.pageInfo", { page: evPage, pages, total: r.total });
    $("#e-prev").disabled = evPage <= 1;
    $("#e-next").disabled = evPage >= pages;
    $("#e-table tbody").innerHTML = r.items.length ? r.items.map((e) => {
      const who = e.member_name ? `${esc(e.member_name)} <span class="muted">(${esc(e.member_no)})</span>`
        : e.category === "oproep" ? `<span class="muted">${esc(t("events.unknown"))}</span>` : esc(e.actor || "");
      const adminBy = (e.category === "admin" || e.category === "manueel") && e.member_name ? `<div class="muted">${esc(t("events.by", { actor: e.actor }))}</div>` : "";
      const conf = e.cmd_id ? (e.confirmed_at ? `<span title="${esc(t("events.confirmedAt", { time: fmtTime(e.confirmed_at) }))}">✓</span>` : `<span class="muted" title="${esc(t("events.noConfirmation"))}">–</span>`) : "";
      return `<tr>
        <td class="mono">${esc(fmtTime(e.ts))}</td>
        <td>${esc(categoryLabel(e.category))}</td>
        <td>${esc(e.device || "")}</td>
        <td>${who}${adminBy}</td>
        <td class="phone">${esc(e.phone || "")}</td>
        <td>${e.result ? badge(resultLabel(e.result), RESULT_CLS[e.result] ?? "") : ""}</td>
        <td>${esc(e.reason || "")}</td>
        <td class="detail">${esc(e.detail || "")}</td>
        <td class="c">${conf}</td></tr>`;
    }).join("") : `<tr><td colspan="9" class="empty">${t("events.none")}</td></tr>`;
  } catch (e) { toast(e.message, true); }
}

let evTimer;
for (const id of ["#e-from", "#e-to", "#e-category", "#e-device", "#e-result"]) {
  $(id).addEventListener("change", () => { evPage = 1; loadEvents(); });
}
$("#e-q").addEventListener("input", () => { clearTimeout(evTimer); evTimer = setTimeout(() => { evPage = 1; loadEvents(); }, 300); });
$("#e-reset").addEventListener("click", () => {
  for (const id of ["#e-from", "#e-to", "#e-category", "#e-device", "#e-result", "#e-q"]) $(id).value = "";
  evPage = 1; loadEvents();
});
$("#e-prev").addEventListener("click", () => { evPage--; loadEvents(); });
$("#e-next").addEventListener("click", () => { evPage++; loadEvents(); });
setInterval(() => {
  if (!$("#tab-events").classList.contains("hidden") && $("#e-auto").checked && evPage === 1) loadEvents();
}, 5000);

$("#language-selector").addEventListener("change", (ev) => {
  applyLanguage(ev.target.value);
});
function showErrors(el, e) {
  el.innerHTML = (e.errors && e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("");
}

async function loadConfig() {
  try {
    const [cfg, bk] = await Promise.all([api("api/config"), api("api/backup/status")]);
    const f = $("#cfg-form");
    for (const el of $$("[name]", f)) {
      const v = el.name.split(".").reduce((o, k) => (o ? o[k] : undefined), cfg);
      if (el.type === "checkbox") el.checked = !!v;
      else if (el.name !== "mqtt.password") el.value = v ?? "";
    }
    f["mqtt.password"].value = "";
    f["mqtt.password"].placeholder = cfg.mqtt.password_set ? t("config.passwordSet") : t("config.passwordNone");
    $("#sp-secret").textContent = bk.sharepoint_secret_set
      ? t("config.secretSet")
      : t("config.secretNone");
    renderBackupStatus(bk);
    $("#cfg-errors").innerHTML = "";
    $("#cfg-msg").textContent = "";
  } catch (e) { toast(e.message, true); }
  await loadDevices();
  renderDeviceTable();
}

function renderBackupStatus(bk) {
  const l = bk.last;
  if (!l) { $("#bk-status").innerHTML = `<span class="muted">${esc(t("config.backupNone"))}</span>`; return; }
  const part = (label, r) => !r ? "" : r.ok
    ? `<div>${esc(label)}: ok${r.path ? ` (${esc(r.path)})` : ""}${r.url ? ` (<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(t("config.open"))}</a>)` : ""}</div>`
    : `<div class="bad">${esc(label)}: ${esc(r.error)}</div>`;
  $("#bk-status").innerHTML = `<div><b>${esc(t("config.lastBackup"))}</b> ${esc(fmtTime(l.ts))}, ${esc(l.file)} (${Math.round(l.size / 1024)} kB)${l.automatic ? esc(t("config.automatic")) : ""}</div>`
    + part(t("config.folder"), l.local) + part(t("config.sharepoint"), l.sharepoint)
    + (bk.last_ok && bk.last_ok !== l.ts ? `<div class="muted">${esc(t("config.lastSuccess", { time: fmtTime(bk.last_ok) }))}</div>` : "");
}

$("#cfg-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const el of $$("[name]", ev.target)) {
    const path = el.name.split(".");
    let o = body;
    path.slice(0, -1).forEach((k) => { o = o[k] ??= {}; });
    o[path.at(-1)] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
  }
  try {
    await api("api/config", { method: "PUT", body });
    $("#cfg-errors").innerHTML = "";
    $("#cfg-msg").textContent = t("members.saved");
    toast(t("config.saved"));
    loadConfig();
    setTimeout(loadStatus, 1500);
  } catch (e) { showErrors($("#cfg-errors"), e); }
});

/* Toestellen beheren */
function renderDeviceTable() {
  $("#dev-table tbody").innerHTML = devicesList.length ? devicesList.map((d) => `
    <tr>
      <td><b>${esc(d.name)}</b></td>
      <td>${d.enabled ? badge(t("common.active"), "ok") : badge(t("common.inactive"), "")}</td>
      <td class="mono">${esc(d.serial_port)}</td>
      <td>${d.relay_type === "shelly" ? "Shelly 1 Gen3" : "Tasmota"}</td>
      <td class="mono">${esc(d.tasmota_topic)}</td>
      <td>${esc(fmtSetting(d.on_seconds))}</td>
      <td>${d.dedupe_seconds ? esc(d.dedupe_seconds + " s") : t("common.offValue")}</td>
      <td class="actions">
        <button class="small" type="button" data-dev-edit="${d.id}">${t("common.edit")}</button>
        <button class="small danger" type="button" data-dev-del="${d.id}">${t("common.delete")}</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="8" class="empty">${t("devices.noDevices")} ${t("devices.addOne")}</td></tr>`;
}

function deviceTopicPlaceholder(type) {
  return type === "shelly"
    ? t("devices.topicPlaceholderShelly")
    : t("devices.topicPlaceholderTasmota");
}

let editingDevice = null;
function openDevice(d) {
  editingDevice = d ? d.id : null;
  const f = $("#device-form");
  $("#device-title").textContent = d ? t("devices.titleEdit", { name: d.name }) : t("devices.titleNew");
  f.name.value = d ? d.name : "";
  f.enabled.checked = d ? d.enabled : true;
  f.serial_port.value = d ? d.serial_port : "";
  f.baudrate.value = d ? d.baudrate : 38400;
  f.relay_type.value = d ? d.relay_type : "tasmota";
  f.tasmota_topic.placeholder = deviceTopicPlaceholder(f.relay_type.value);
  f.tasmota_topic.value = d ? d.tasmota_topic : "";
  f.on_seconds.value = d ? d.on_seconds : 1;
  f.dedupe_seconds.value = d ? d.dedupe_seconds : 5;
  $$("input[name=grant_all]", f).forEach((r) => { r.checked = false; });
  $("#device-grant").classList.toggle("hidden", !!d);
  $(".errors", f).innerHTML = "";
  $("#dlg-device").showModal();
  f.name.focus();
}
$("#device-form select[name=relay_type]").addEventListener("change", (ev) => {
  $("#device-form input[name=tasmota_topic]").placeholder = deviceTopicPlaceholder(ev.target.value);
});
$("#dev-new").addEventListener("click", () => openDevice(null));

$("#device-save").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const f = $("#device-form");
  const grant = $("input[name=grant_all]:checked", f);
  const body = {
    name: f.name.value, enabled: f.enabled.checked, serial_port: f.serial_port.value,
    baudrate: Number(f.baudrate.value), relay_type: f.relay_type.value, tasmota_topic: f.tasmota_topic.value,
    on_seconds: Number(f.on_seconds.value), dedupe_seconds: Number(f.dedupe_seconds.value),
  };
  try {
    if (editingDevice) {
      await api(`api/devices/${editingDevice}`, { method: "PUT", body });
    } else {
      if (!grant) { showErrors($(".errors", f), { errors: [t("devices.grantRequired")] }); return; }
      await api("api/devices", { method: "POST", body: { ...body, grant_all: grant.value === "1" } });
    }
    $("#dlg-device").close();
    toast(t("devices.saved"));
    await loadDevices();
    renderDeviceTable();
    loadMembers();
    setTimeout(loadStatus, 800);
  } catch (e) { showErrors($(".errors", f), e); }
});

$("#dev-table tbody").addEventListener("click", async (ev) => {
  const edit = ev.target.closest("[data-dev-edit]");
  const del = ev.target.closest("[data-dev-del]");
  if (edit) openDevice(devicesList.find((d) => d.id === +edit.dataset.devEdit));
  if (del) {
    const d = devicesList.find((x) => x.id === +del.dataset.devDel);
    if (!(await confirmDialog(t("devices.deleteTitle"), t("devices.deleteText", { name: d.name }), t("common.delete")))) return;
    try {
      await api(`api/devices/${d.id}`, { method: "DELETE" });
      toast(t("devices.deleted"));
      await loadDevices();
      renderDeviceTable();
      loadMembers();
      loadStatus();
    } catch (e) { toast(e.message, true); }
  }
});

/* Back-up */
$("#bk-run").addEventListener("click", async () => {
  $("#bk-run").disabled = true;
  try {
    const r = await api("api/backup/run", { method: "POST", body: {} });
    toast(r.ok ? t("config.backupCreated") : t("config.backupCreatedErrors"), !r.ok);
    renderBackupStatus(await api("api/backup/status"));
  } catch (e) { toast(e.message, true); } finally { $("#bk-run").disabled = false; }
});

$("#bk-restore").addEventListener("click", () => { $("#bk-file").value = ""; $("#bk-file").click(); });
$("#bk-file").addEventListener("change", async () => {
  const file = $("#bk-file").files[0];
  if (!file) return;
  const ok = await confirmDialog(t("config.restoreTitle"),
    t("config.restoreText", { file: file.name }),
    t("config.restoreButton"));
  if (!ok) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("api/backup/restore", { method: "POST", body: fd });
    toast(t("config.restored", { count: r.members }));
    setTimeout(() => location.reload(), 1500);
  } catch (e) { toast(e.errors && e.errors.length ? e.errors.join(" ") : e.message, true); }
});

/* ---------------- Start ---------------- */
(async function init() {
  try {
    const me = await api("api/me");
    $("#me").textContent = me.auth_disabled ? t("me.noCloudflare", { email: me.email }) : me.email;
  } catch (e) { toast(e.message, true); }
  applyLanguage(currentLanguage, false);
  loadStatus();
  setInterval(loadStatus, 3000);
  await loadDevices();
  loadMembers();
  let tab = "members";
  try { tab = localStorage.getItem("tab") || "members"; } catch { /* geen opslag */ }
  showTab(["members", "events", "config"].includes(tab) ? tab : "members");
})();
