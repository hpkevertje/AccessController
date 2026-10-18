# AccessController

Toegangscontrole op basis van inkomende oproepen naar RTU5024 GSM-modules, bv. voor water en een poort.
Een lid belt het nummer van een toestel, de app herkent het nummer en schakelt een Tasmota-relais.

```
Lid belt RTU5024 ──(RTU hangt op, gratis)──> debuglijn 38400 baud ──USB-TTL──> server (Docker)
                                                                               │
                                       webapp + listener: lid opzoeken, beslissen, loggen
                                                                               │ MQTT
                                           Tasmota-relaismodule (bv. water: 20 min, poort: puls 1 s)
```

Een **toestel** is altijd één RTU5024 (eigen telefoonnummer) met één Tasmota-relais. Je voegt toestellen
toe in de webapp.

## Wat het doet

- **Toestellen** beheer je onder Configuratie: naam, seriële poort van de RTU, Tasmota-topic, aan-tijd
  en ontdubbeling. Bij een nieuw toestel kies je of alle bestaande leden er toegang toe krijgen.
  Een toestel verwijderen verwijdert de toegang van alle leden; het logboek blijft bewaard.
- **Leden**: lidnr (verplicht, uniek), naam, telefoon (genormaliseerd naar +32...), opmerking en per
  toestel een schakelaar voor toegang. Eén telefoonnummer per lid, een nummer hoort bij maximaal één lid.
  Een nieuw lid krijgt standaard toegang tot alle toestellen.
- **Import/export** in Excel (.xlsx), in en uit hetzelfde formaat, met een kolom
  "Toegang &lt;toestel&gt;" per toestel. Import werkt bij op lidnr. Leden die niet in het bestand staan,
  blijven behouden. Bij één fout wordt het hele bestand geweigerd en verandert er niets.
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

Tasmota houdt zelf de tijd bij (PulseTime). Valt de server of het netwerk weg, dan gaat het relais toch uit.

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

## Status in de webapp

Per toestel:

- **RTU**: `ok`, `kabel niet verbonden` (de server leest niets van de USB-TTL-adapter) of
  `geen GSM-netwerk` (de RTU meldt geen SIM of geen registratie op het netwerk).
- **Relaismodule**: de Tasmota-module is online of offline op MQTT.
- **Relais**: aan (met resterende tijd) of uit, zoals Tasmota het meldt.

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

Een toestel toevoegen, wijzigen of verwijderen past alleen de abonnementen aan; de MQTT-verbinding
wordt alleen opnieuw opgezet als de broker-instellingen wijzigen.

Met `COMPOSE_PROFILES=mosquitto` draait Mosquitto in de stack op poort 1883, met gebruiker en
wachtwoord uit de variabelen. Zonder dat profiel gebruikt de app de broker uit `MQTT_HOST`.

Het logboek toont een vinkje in de kolom Relais als Tasmota binnen 15 s na het commando de
verwachte `POWER`-status meldt.

## Ontwikkeling

```bash
cd app
pip install -r requirements.txt pytest httpx
python -m pytest
AUTH_DISABLED=true DB_PATH=./dev.db uvicorn accesscontrol.main:app --reload --port 8080
```

Als seriële poort van een toestel kan je `socket://host:poort` gebruiken: dan leest de app een
RTU-stroom over TCP, handig om te testen zonder hardware.
