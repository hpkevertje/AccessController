# AccessController

Toegangscontrole op basis van inkomende oproepen naar RTU5024 GSM-modules, bv. voor water en een poort.
Een lid belt het nummer van een toestel, de app herkent het nummer en schakelt een relaismodule
(Tasmota of Shelly 1 Gen3).

```
Lid belt RTU5024 ──(RTU hangt op, gratis)──> debuglijn 38400 baud ──USB-TTL──> server (Docker)
                                                                               │
                                       webapp + listener: lid opzoeken, beslissen, loggen
                                                                               │ MQTT
                                           Tasmota- of Shelly-relaismodule (bv. water: 20 min, poort: puls 1 s)
```

Een **toestel** is altijd één RTU5024 (eigen telefoonnummer) met één relaismodule (Tasmota of
Shelly 1 Gen3). Je voegt toestellen toe in de webapp.

## Wat het doet

- **Toestellen** beheer je onder Configuratie: naam, seriële poort van de RTU, type relaismodule,
  MQTT-topic / Shelly-ID, aan-tijd en ontdubbeling. Bij een nieuw toestel kies je of alle bestaande
  leden er toegang toe krijgen.
  Een toestel verwijderen verwijdert de toegang van alle leden; het logboek blijft bewaard.
- **Leden**: lidnr (verplicht, uniek), naam, telefoon (genormaliseerd naar +32...), opmerking en per
  toestel een schakelaar voor toegang. Eén telefoonnummer per lid, een nummer hoort bij maximaal één lid.
  Een nieuw lid krijgt standaard toegang tot alle toestellen.
- **Import/export** in Excel (.xlsx), in en uit hetzelfde formaat, met een kolom
  "Toegang &lt;toestel&gt;" per toestel. Import werkt bij op lidnr. Leden die niet in het bestand staan,
  blijven behouden. Bij één fout wordt het hele bestand geweigerd en verandert er niets.
  De knop **Importeren** doet standaard **Importeren uit e-captain**; via het pijltje kies je
  **Leden importeren (Excel)** voor het native formaat.
- **Import uit e-captain**: de standaardactie van de knop **Importeren** onder Leden is
  **Importeren uit e-captain**. De app leest een rapport/export uit e-Captain
  (Ledenbeheer > Rapportage, .xlsx of .csv) met de actieve leden. Alleen e-Captain >
  AccessController: lidnummer, naam en telefoon worden toegevoegd of bijgewerkt. Nummers die je
  handmatig toevoegt (leveranciers, aannemers, ...) blijven staan. Een lid dat niet meer in het
  rapport staat, blijft bewaard maar wordt niet-actief en kan niet meer bellen; de toegang per
  toestel blijft bewaard voor als het lid terugkomt.
- **SMS**: elke SMS die een RTU ontvangt (bv. een kredietwaarschuwing van de operator) komt in het
  logboek en de laatste staat op de toestelkaart. Nieuwe SMS verschijnen in een gele balk bovenaan
  (en als aantal in de tabtitel); "Bekijken" opent het logboek en markeert ze als gelezen voor alle admins.
  - De RTU toont maximaal ongeveer 60 tekens per SMS; de rest kan de app niet lezen.
  - Bij een SMS-commando logt de app ook het antwoord van de RTU (bv. `Password Error`, gemarkeerd als fout).
  - Het RTU-wachtwoord wordt op basis van patronen als `****` gelogd.
  - Een lege SMS (die de RTU soms na een oproep krijgt) wordt gelogd maar telt niet mee in de balk.
- **Witte lijst van de RTU** hoort leeg te zijn: de app beslist. Belt een nummer dat er toch in staat,
  dan logt de app een systeemregel met de plaats en het SMS-commando om het te verwijderen.
- **Logboek** met alle oproepen, manuele bediening, admin-acties, SMS en systeemmeldingen. Filters op
  datum, soort, toestel, resultaat en vrije tekst. Export naar Excel. Standaard 24 maanden bewaard.
- **Manuele bediening** per toestel (aan/uit of puls), gelogd met het e-mailadres van de admin.
- **Back-up**: dagelijks automatisch naar een map en optioneel naar SharePoint, met bewaartermijn.
  Handmatig maken, downloaden en terugzetten via de webapp.
- **Toegang** tot de webapp via Cloudflare Access. Iedereen die binnenkomt, is admin.

### Beslissing bij een oproep

1. Zelfde nummer op hetzelfde toestel binnen de ontdubbelingstijd (standaard 5 s, 0 = uit):
   genegeerd, niet gelogd. Elke andere oproep wordt apart beslist en gelogd.
2. Onbekend nummer: geweigerd.
3. Geen toegang tot dit toestel: geweigerd.
4. Anders: toegelaten, het relais gaat aan voor de aan-tijd van het toestel. Een nieuwe geldige
   oproep binnen die tijd herstart de teller.

De relaismodule houdt zelf de tijd bij (Tasmota met PulseTime, Shelly met een timer). Valt de server
of het netwerk weg, dan gaat het relais toch uit.

## Import uit e-captain

e-Captain heeft geen publieke API voor het uitlezen van leden. Daarom leest de app een
**rapport/export** dat je in e-Captain maakt. Er gaan geen e-Captain-wachtwoorden naar de app en de
app scrape't de webinterface niet.

1. Ga in e-Captain naar **Ledenbeheer > Rapportage** en maak een rapport van de **actieve leden**
   met minstens een telefoonnummer en een lidnummer, relatie-id of naam. Exporteer als **.xlsx** of
   **.csv**.
2. Klik onder **Leden** op **Importeren uit e-captain** (de standaardactie van de importknop) en
   kies het bestand. De app toont eerst wat er zou veranderen; klik daarna op **Importeren**.
   Na de import staat per lid in het resultaat wat **nieuw**, **gewijzigd** of
   **verwijderd/niet actief** is. Met **Rapport downloaden (CSV)** bewaar je dat overzicht.
3. De app werkt bestaande leden bij op **relatie-id** (indien aanwezig), anders op **lidnummer**,
   en anders op **telefoonnummer**. Nieuwe actieve leden worden toegevoegd met toegang tot alle
   toestellen, net als bij handmatig toevoegen.

Herkende kolomkoppen (Nederlands en Engels, hoofdletters/leestekens maken niet uit):
`Lidnr`/`Lidnummer`, `Relatie-id`, `Naam` of `Voornaam` + `Achternaam`, `Mobiel`/`GSM`/`Telefoon`,
en optioneel `Actief`/`Status`. Alleen **mobiele nummers** worden geïmporteerd; een vast nummer
wordt niet overgenomen. Bij een bestaand lid wordt een eerder vast nummer gewist. Een rapport
zonder `Actief`-kolom wordt als volledig actief beschouwd; exporteer dan alleen de actieve leden.

Wat de import wel en niet doet:

- **Alleen e-Captain > AccessController.** AccessController stuurt niets terug.
- **Alleen mobiele nummers.** De e-Captain-import neemt geen vaste nummers over. Handmatig
  toegevoegde nummers (leveranciers, aannemers, ...) mogen wel vast zijn; die beperking geldt
  alleen voor de import.
- **Handmatige nummers blijven staan.** Voeg leveranciers, aannemers of andere niet-leden toe met
  **+ Nieuw lid / contact**; die krijgen `handmatig` als bron en worden nooit door de import
  gewijzigd of verwijderd.
- **Niet meer actief?** Een lid dat niet meer in het rapport staat (of daar niet actief is), blijft
  bewaard maar wordt **niet-actief**: de oproep-engine weigert het nummer. De toegangsinstellingen
  per toestel blijven bewaard, zodat het lid na terugkeer weer dezelfde toegang heeft.
- **Geen tweerichtingsverkeer en geen automatische planning.** De import draait alleen wanneer je
  **Importeren uit e-captain** kiest.

## Installatie (Linux)

Vereist: Docker met Compose plugin (2.20 of nieuwer), per toestel een USB-TTL-adapter (3,3 V) op de
RTU-debuglijn.

```bash
git clone <repo> AccessController && cd AccessController
cp .env.example .env
nano .env                    # Cloudflare, MQTT, back-upmap, SharePoint-secret
docker compose up -d --build
docker compose logs -f app
```

De webapp luistert op `127.0.0.1:8080` (aanpasbaar met `WEB_BIND` / `WEB_PORT`). Voeg daarna je
toestellen toe onder Configuratie.

### Installatie met Portainer

1. Portainer > **Stacks** > **Add stack**, build method **Repository**:
   - Repository URL: de URL van deze repo
   - Reference: `refs/heads/main`
   - Compose path: `docker-compose.yml`
   - Bij een privé-repo: Authentication aan, met een GitHub-token (fine-grained, alleen deze repo,
     **Contents: Read-only**).
2. **Environment variables** (Advanced mode, dezelfde namen als in `.env.example`). Minimaal:
   ```
   COMPOSE_PROFILES=mosquitto
   MQTT_USER=accesscontrol
   MQTT_PASSWORD=<sterk wachtwoord>
   WEB_BIND=0.0.0.0
   CF_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
   CF_ACCESS_AUD=<AUD-tag>
   ```
   Om thuis te testen zonder Cloudflare: `AUTH_DISABLED=true` (dan kan iedereen op het LAN binnen).

   **Bestaande MQTT-broker gebruiken**: laat `COMPOSE_PROFILES` weg, dan start de Mosquitto van deze
   stack niet. Zet dan `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER` en `MQTT_PASSWORD` van die broker
   (`MQTT_USER=` leeg voor een broker zonder login).
3. **Deploy the stack**. De eerste build duurt enkele minuten. Controleer dat de app-container
   `healthy` is en open `http://<server>:8080`.
4. **Updaten**: push naar GitHub, dan in Portainer **Pull and redeploy**. De gegevens staan in de
   volumes `app-data`, `mosquitto-data` en `backups` en blijven behouden.

Een database van een oudere versie (met vaste toestellen water en poort) wordt bij de eerste start
automatisch omgezet: water en poort worden gewone toestellen met dezelfde instellingen en toegang.

### Cloudflare Access

1. Zero Trust > Access > Applications > Add an application > Self-hosted, met de hostname van de webapp.
2. Policy: Allow, met de e-mailadressen van de beheerders.
3. Zet `CF_ACCESS_TEAM_DOMAIN` (bv. `jouwteam.cloudflareaccess.com`) en `CF_ACCESS_AUD` (de
   Application Audience Tag van die applicatie).
4. Wijs in je cloudflared-tunnel de hostname naar de webapp (bv. `http://localhost:8080`).

De app controleert de handtekening van de Cloudflare-token zelf. Een verzoek dat de tunnel omzeilt,
wordt geweigerd. Zonder deze twee waarden weigert de app alle verzoeken.

### Seriële poort

Zoek de vaste naam van elke USB-TTL-adapter:

```bash
ls -l /dev/serial/by-id/
```

Vul die naam in bij het toestel, bv. `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_XXXXXXXX-if00-port0`.
Zo verwisselen de toestellen niet na een herstart. De container krijgt toegang tot `/dev/ttyUSB*` en
`/dev/ttyACM*`, ook als een adapter later ingeplugd wordt.

Aansluiting op de RTU-print (debugheader aan de modemkant):

| RTU                      | USB-TTL |
|--------------------------|---------|
| buitenste pin (TX debug) | RX      |
| GND                      | GND     |

Adapter-TX niet aansluiten. Instellingen: 38400 baud, 8N1.

### RTU5024

- Wijzig het standaardwachtwoord per SMS: `<oud>#PWD<nieuw>#PWD<nieuw>#`.
- Laat de eigen witte lijst van de RTU leeg. De RTU weigert dan elke oproep na ongeveer 2 beltonen,
  de beller betaalt niets en de app beslist.
- Zet de SMS-meldingen van het relais uit: `<wachtwoord>#N#`.
- Het relais van de RTU wordt niet gebruikt.
- De SIM moet een PIN-code hebben die uitgeschakeld is.

### Tasmota-relaismodule

Per toestel een ESP8266/ESP32-relaismodule met [Tasmota](https://tasmota.github.io/), bv. een
ESP-01S (1 MB) op een relaisbordje. Een oude ESP-01 met 512 KB is te klein.

1. Flash Tasmota met de [webinstaller](https://tasmota.github.io/install).
2. Verbind met WiFi via het Tasmota-toegangspunt.
3. Relais instellen: Configuration > Configure Module > Generic (18), en de GPIO van het relais
   (bij de meeste ESP-01S-relaisbordjes GPIO0) op `Relay 1` (of `Relay_i` als het omgekeerd schakelt).
   Sommige bordjes (LC Technology) schakelen het relais via een extra chip; zoek dan het template op
   [templates.blakadder.com](https://templates.blakadder.com/).
4. In de Tasmota-console (zelfde gebruiker en wachtwoord als de broker):
   ```
   Backlog MqttHost <ip-broker>; MqttPort 1883; MqttUser <gebruiker>; MqttPassword <wachtwoord>; Topic <topic>; SetOption65 1
   ```
   `<topic>` is het Tasmota-topic van het toestel in de webapp. `SetOption65 1` voorkomt dat een paar
   snelle stroomonderbrekingen Tasmota terugzetten naar de fabrieksinstellingen.
5. Beveilig de Tasmota-webinterface: `WebPassword <wachtwoord>`, of na de configuratie `Webserver 0`.
   Anders kan iedereen op het LAN het relais schakelen zonder dat het in het logboek komt.

De app controleert telkens de module online komt en bij elke wijziging van het toestel:

- `PulseTime1`: de aan-tijd van het toestel (20 min = `1300`, 1 s = `10`). Alleen als de waarde
  verschilt, en nooit terwijl het relais aan is (anders zou de lopende teller herstarten); dan pas
  wanneer het relais uit gaat.
- `PowerOnState 0`: na stroomuitval blijft het relais uit.

### Shelly 1 Gen3-relaismodule

Per toestel kan je ook een [Shelly 1 Gen3](https://shelly-api-docs.shelly.cloud/gen2/) gebruiken.
De Shelly praat met dezelfde broker en gebruikt dezelfde gebruiker en hetzelfde wachtwoord als de
app: je stelt in de app één MQTT-broker in voor alle relaismodules.

1. Zet MQTT aan in de Shelly: **Settings > Network > MQTT**, met de broker, gebruiker en het
   wachtwoord van de app.
2. Het Shelly-ID is de `topic_prefix` van de module. Je ziet die met `http://<ip>/rpc/MQTT.GetConfig`.
   Is `topic_prefix` leeg, gebruik dan het ID van het toestel uit `Shelly.GetDeviceInfo`.
3. RPC over MQTT moet aan staan (`enable_rpc`, en `rpc_ntf` voor de meldingen). Dat staat bij de
   Shelly 1 Gen3 standaard al aan. `status_ntf` is niet nodig.
4. Beveilig de webinterface van de Shelly, net als bij Tasmota: anders kan iedereen op het LAN het
   relais schakelen zonder dat het in het logboek komt.

Vul het Shelly-ID in als **MQTT-topic / Shelly-ID** en kies als type **Shelly 1 Gen3**. De app:

- zet `auto_off`, `auto_off_delay` (de aan-tijd) en `initial_state` op `off` in de Shelly, maar
  alleen als ze verschillen en nooit terwijl het relais aan is; anders gebeurt het zodra het relais
  uit gaat.
- stuurt bij elke AAN-opdracht `toggle_after` mee. Een herhaalde opdracht herstart de teller, zoals
  bij Tasmota. Een lokale bediening (knop of webinterface) gaat uit via `auto_off`. Een AAN van een
  ander programma zonder `toggle_after` gaat niet vanzelf uit.
- De aan-tijd blijft ingesteld tussen 1 en 64800 seconden, net als bij Tasmota.

## Back-up

Onder Configuratie > Automatische back-up:

- **Dagelijks** op het ingestelde tijdstip een gecomprimeerde kopie van de database
  (`accesscontrol-JJJJMMDD-UUMMSS.db.gz`) naar de map, standaard `/backups` in de container.
  Oudere back-ups dan de bewaartermijn worden verwijderd.
- **Waar staat `/backups`?** Standaard in het Docker-volume `backups`. Zet `BACKUP_DIR` op een
  absoluut pad om een map op de server te gebruiken. Die map moet schrijfbaar zijn voor uid 10001:
  `sudo mkdir -p /srv/accesscontrol/backups && sudo chown 10001 /srv/accesscontrol/backups`.
- **Nu back-up maken**, **downloaden** en **terugzetten** staan onderaan Configuratie. Terugzetten
  vervangt leden, toestellen, instellingen en logboek, en maakt eerst een veiligheidskopie
  (`accesscontrol-voor-terugzetten-….db.gz`) in de back-upmap. Back-ups van een oudere versie worden
  bij het terugzetten automatisch omgezet.
- De status van de laatste back-up (en eventuele fouten) staat in Configuratie en in het logboek.

### SharePoint (Microsoft Graph)

1. Entra ID > App registrations > **New registration** (bv. "AccessController back-up").
2. **API permissions** > Add > Microsoft Graph > **Application permissions** > `Sites.Selected` >
   **Grant admin consent**.
3. **Certificates & secrets** > New client secret. Zet de waarde in `SHAREPOINT_CLIENT_SECRET`
   (stack-variabele of `.env`). Het secret komt nooit in de webapp of de database, en dus ook niet in
   de back-ups.
4. Geef de app schrijfrechten op de doelsite (eenmalig, door een beheerder), bv. met Graph Explorer:
   ```
   POST https://graph.microsoft.com/v1.0/sites/<site-id>/permissions
   { "roles": ["write"],
     "grantedToIdentities": [{ "application": { "id": "<client-id>", "displayName": "AccessController back-up" } }] }
   ```
   De site-id vind je met `GET https://graph.microsoft.com/v1.0/sites/<tenant>.sharepoint.com:/sites/<site>`.
5. In de webapp: vink "Ook naar SharePoint" aan en vul tenant-ID, client-ID, site-URL
   (bv. `https://bedrijf.sharepoint.com/sites/IT`), de map in de documentbibliotheek en de bewaartermijn in.
6. Klik **Nu back-up maken** om te testen. Een fout (bv. ontbrekende rechten) staat in de back-upstatus.
7. Met **SharePoint testen** (na opslaan) loopt de app de hele keten apart na: configuratie,
   client secret, toegangstoken, site, documentbibliotheek, map, upload, publicatie en opruimen.
   Het resultaat staat meteen onder de knop en in het logboek.

**Bestand niet zichtbaar in SharePoint?** De upload kan geslaagd zijn (HTTP 201) terwijl het
bestand voor gebruikers verborgen blijft:

- Staat in de bibliotheek **Vereist uitchecken** of **versiebeheer met concepten** aan? De app
  checkt een uitgecheckt bestand na de upload automatisch in als gepubliceerde versie. Lukt dat
  niet, dan meldt de back-upstatus dat expliciet.
- Staat **contentgoedkeuring** aan? Dan blijft het bestand op *wacht op goedkeuring* staan tot
  iemand het goedkeurt. De diagnose noemt deze status.
- Controleer ook of je in de juiste documentbibliotheek kijkt: de app gebruikt de
  standaardbibliotheek van de site (`drive/root`) en de map uit de configuratie.

Zet voor meer details `LOG_LEVEL=DEBUG` in de stack-variabelen; de app logt dan elke
Graph-aanroep, elk uploadfragment en de publicatiestatus in `docker compose logs -f app`.

## Status in de webapp

Per toestel:

- **RTU**: `ok`, `kabel niet verbonden` (de server leest niets van de USB-TTL-adapter) of
  `geen GSM-netwerk` (de RTU meldt geen SIM of geen registratie op het netwerk).
- **Relaismodule**: de Tasmota- of Shelly-module is online of offline op MQTT.
- **Relais**: aan (met resterende tijd) of uit, zoals de relaismodule het meldt.

Bovenaan: **MQTT verbonden** = de server is verbonden met de broker.

## MQTT

De app gebruikt de standaard Tasmota-topics (`FullTopic %prefix%/%topic%/`), met `<t>` = het
Tasmota-topic van het toestel:

| Topic                     | Richting         | Gebruik |
|---------------------------|------------------|---------|
| `cmnd/<t>/POWER`          | server > Tasmota | `ON` bij toelating (herstart ook PulseTime), `OFF` bij manueel uit, leeg = status opvragen |
| `cmnd/<t>/PulseTime1`     | server > Tasmota | leeg = opvragen (elke 10 s zolang het relais aan is); waarde = instellen (alleen als het verschilt en het relais uit is) |
| `cmnd/<t>/PowerOnState`   | server > Tasmota | leeg = opvragen, `0` = instellen als het anders is |
| `stat/<t>/POWER`          | Tasmota > server | `ON` / `OFF` |
| `stat/<t>/RESULT`         | Tasmota > server | `{"PulseTime1":{"Set":…,"Remaining":…}}`, `{"PowerOnState":…}` |
| `tele/<t>/STATE`          | Tasmota > server | periodieke status met `POWER` |
| `tele/<t>/LWT`            | Tasmota > server | `Online` / `Offline` |

Voor Shelly 1 Gen3 gebruikt de app RPC over MQTT, met `<id>` = het Shelly-ID (de `topic_prefix`) en
`<client-id>` = de MQTT-client-ID uit de configuratie (standaard `accesscontrol-server`):

| Topic               | Richting        | Gebruik |
|---------------------|-----------------|---------|
| `<id>/rpc`          | server > Shelly | `Switch.GetStatus`, `Switch.GetConfig`, `Switch.Set` (met `toggle_after`) en `Switch.SetConfig` |
| `<client-id>/rpc`   | Shelly > server | antwoord op een aanvraag (`result` of `error`) |
| `<id>/events/rpc`   | Shelly > server | `NotifyStatus` met `switch:0` (aan/uit en timer) |
| `<id>/online`       | Shelly > server | `true` / `false` (retained, LWT) |

Een toestel toevoegen, wijzigen of verwijderen past alleen de abonnementen aan; de MQTT-verbinding
wordt alleen opnieuw opgezet als de broker-instellingen wijzigen.

Met `COMPOSE_PROFILES=mosquitto` draait Mosquitto in de stack op poort 1883, met gebruiker en
wachtwoord uit de variabelen. Zonder dat profiel gebruikt de app de broker uit `MQTT_HOST`.

Het logboek toont een vinkje in de kolom Relais als de relaismodule binnen 15 s na het commando de
verwachte status meldt.

## Ontwikkeling

```bash
cd app
pip install -r requirements.txt pytest httpx
python -m pytest
AUTH_DISABLED=true DB_PATH=./dev.db uvicorn accesscontrol.main:app --reload --port 8080
```

Als seriële poort van een toestel kan je `socket://host:poort` gebruiken: dan leest de app een
RTU-stroom over TCP, handig om te testen zonder hardware.
