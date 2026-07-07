# Fabricator - Minecraft Server Manager

Ein moderner Minecraft Server Manager mit Modrinth-Integration zum einfachen Verwalten von Mods.

## 🚀 Features

- **Server Management**: Minecraft Server starten/stoppen
- **Modrinth Integration**: 
  - Mods suchen nach Loader und MC-Version
  - Automatische Version-Auswahl (neueste Release)
  - Direkte Download-URLs abrufen
  - Mods direkt installieren
- **REST API**: Vollständige API für Frontend-Integration
- **Vue.js Frontend**: Moderne Web-Oberfläche (geplant)

## 📁 Projektstruktur

```
Fabricator/
├── apps/
│   ├── backend/
│   │   ├── core/
│   │   │   ├── app.py            # Flask App Factory
│   │   │   └── config.py         # Zentrale Konfiguration
│   │   ├── server/               # Server-Lifecycle und Storage
│   │   ├── modrinth/             # Modrinth API Client und Routes
│   │   ├── system/               # System-/Update-Endpunkte
│   │   ├── playit/               # playit.gg Agent und Routes
│   │   ├── backups/              # Backup/Restore/Import
│   │   └── tests/                # Backend-Tests
│   ├── frontend/                 # Vue 3 + Vite Frontend
│   └── cli/                      # Fabricator CLI Package und Tests
├── tests/
│   └── integration/              # Cross-App Contract Tests
├── run.py                        # Application Entry Point / Orchestrator
└── requirements.txt              # Repo-weite Python Dependencies
```

## 🛠️ Installation

### Voraussetzungen
- Python 3.11+
- Java 21+ (neuere Minecraft-Versionen können Java 25 benötigen)

### Setup

1. **Repository klonen**
   ```bash
   git clone https://github.com/philderks/Fabricator.git
   cd Fabricator
   ```

2. **Dependencies installieren**
   ```bash
   pip install -r requirements.txt
   ```

3. **Server starten**
   ```bash
   python run.py
   ```

   Server läuft auf: `http://localhost:5000`

## 📡 API Dokumentation

### Health Check

#### `GET /api/health`
Health Check Endpoint.

**Response:**
```json
{
  "healthy": true
}
```

---

### Loader-Versions

Liefert die Minecraft- und Loader-Versionen, die ein registrierter Loader installieren kann. Wird vom Frontend (`ServerCreateModal`) genutzt, sobald der Anwender einen Loader auswählt. Über die `LOADER_REGISTRY` (siehe „Loader Registry" weiter unten) sind neue Loader sofort an diesen Endpoints sichtbar.

#### `GET /api/loaders/<loader>/versions/game`

Unterstützte Minecraft-Versionen für `<loader>` (case-insensitive Lookup).

**Pfad-Parameter:**
- `<loader>` (string): z.B. `fabric`, `vanilla`.

**Response (200) — normalisiertes Schema:**
```json
[
  { "version": "1.21.4", "stable": true,  "type": "release"  },
  { "version": "24w45a", "stable": false, "type": "snapshot" }
]
```

`stable` ist das einzige Feld, auf das jeder Consumer verlässlich zugreifen kann. `type` ist loader-nativ (z.B. `release`/`snapshot` für Vanilla) und kann entfallen, wenn der Loader keine solche Unterscheidung macht.

**Error (404):**
```json
{ "error": "Unknown loader: <name>" }
```

#### `GET /api/loaders/<loader>/versions/loader`

Loader-spezifische Versionen für eine Minecraft-Version. Loader ohne separate Loader-Version (z.B. Vanilla) liefern `[]`.

**Pfad-Parameter:** `<loader>` wie oben.

**Query Parameter:**
- `mc_version` (string, optional): Filter auf eine Minecraft-Version.

**Response (200):** Loader-natives Array; Form variiert pro Loader und wird vom Frontend opak weitergereicht.

Beispiel (Fabric):
```json
[
  { "loader": { "version": "0.16.0", "stable": true } }
]
```

Beispiel (Vanilla): `[]`.

---

### Modrinth Integration

#### `GET /api/modrinth/search`
Mods auf Modrinth suchen.

**Query Parameter:**
- `query` (string): Suchtext (z.B. "sodium")
- `mc_version` (string, optional): Minecraft Version (z.B. "1.20.1")
- `loader` (string, optional): Mod Loader (z.B. "fabric", "forge")
- `limit` (int, optional): Anzahl Ergebnisse (default: 20, max: 100)
- `offset` (int, optional): Pagination Offset
- `index` (string, optional): Sortierung ("downloads", "relevance", "follows", "newest", "updated")

**Beispiel:**
```bash
GET /api/modrinth/search?query=sodium&mc_version=1.20.1&loader=fabric&limit=10
```

**Response:**
```json
{
  "hits": [
    {
      "project_id": "AANobbMI",
      "slug": "sodium",
      "title": "Sodium",
      "description": "A modern rendering engine...",
      "downloads": 90301924,
      "icon_url": "https://cdn.modrinth.com/...",
      "project_type": "mod",
      "versions": ["1.20.1", "1.20.2"],
      "client_side": "required",
      "server_side": "optional"
    }
  ],
  "offset": 0,
  "limit": 10,
  "total_hits": 1
}
```

#### `GET /api/modrinth/mod/<mod_id>`
Detaillierte Informationen zu einem Mod abrufen.

**Beispiel:**
```bash
GET /api/modrinth/mod/sodium
```

**Response:**
```json
{
  "id": "AANobbMI",
  "slug": "sodium",
  "title": "Sodium",
  "description": "The fastest and most compatible...",
  "downloads": 90301924,
  "categories": ["optimization", "fabric"],
  "client_side": "required",
  "server_side": "optional",
  "versions": ["versionId1", "versionId2"],
  "game_versions": ["1.20.1", "1.20.2"],
  "loaders": ["fabric"]
}
```

#### `GET /api/modrinth/mod/<mod_id>/versions`
Alle Versionen eines Mods abrufen.

**Query Parameter:**
- `loaders` (array, optional): Filter nach Loaders (z.B. `?loaders=fabric`)
- `game_versions` (array, optional): Filter nach MC-Versionen (z.B. `?game_versions=1.20.1`)
- `featured` (boolean, optional): Nur featured Versionen

**Beispiel:**
```bash
GET /api/modrinth/mod/sodium/versions?loaders=fabric&game_versions=1.20.1
```

**Response:**
```json
[
  {
    "id": "versionId",
    "version_number": "0.5.13",
    "name": "Sodium 0.5.13 for Fabric",
    "version_type": "release",
    "date_published": "2025-03-03T17:45:49.132919Z",
    "downloads": 12345,
    "game_versions": ["1.20.1"],
    "loaders": ["fabric"],
    "files": [
      {
        "url": "https://cdn.modrinth.com/.../sodium-fabric-0.5.13+mc1.20.1.jar",
        "filename": "sodium-fabric-0.5.13+mc1.20.1.jar",
        "primary": true,
        "size": 1234567,
        "hashes": {
          "sha512": "...",
          "sha1": "..."
        }
      }
    ]
  }
]
```

#### `GET /api/modrinth/mod/<mod_id>/download-url`
Direkte Download-URL für die beste Version eines Mods.

**Query Parameter:**
- `mc_version` (string, **required**): Minecraft Version (z.B. "1.20.1")
- `loader` (string, optional): Mod Loader (default: "fabric")

**Beispiel:**
```bash
GET /api/modrinth/mod/sodium/download-url?mc_version=1.20.1&loader=fabric
```

**Response:**
```json
{
  "download_url": "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/sodium-fabric-0.5.13%2Bmc1.20.1.jar"
}
```

**Error (404):**
```json
{
  "error": "No suitable version found"
}
```

#### `POST /api/modrinth/mod/<mod_id>/install`
Mod herunterladen und direkt im Server installieren.

**Body (JSON):**

- `mc_version` (string, **required**): Ziel-Minecraft-Version
- `server_id` (string, **required**): Server, auf dem die Mod installiert wird
- `loader` (string, optional): Mod Loader (default: "fabric")
- `mods_folder` (string, optional): Nur für Legacy-Setups

```json
{
  "mc_version": "1.20.1",
  "server_id": "srv_a1b2c3d4",
  "loader": "fabric",
  "mods_folder": "/path/to/mods"
}
```

**Beispiel:**
```bash
POST /api/modrinth/mod/sodium/install
Content-Type: application/json

{
  "mc_version": "1.20.1",
  "server_id": "srv_a1b2c3d4",
  "loader": "fabric"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Mod installed successfully",
  "file": "sodium-fabric-0.5.13+mc1.20.1.jar",
  "path": "/workspaces/Fabricator/server/mods/sodium-fabric-0.5.13+mc1.20.1.jar"
}
```

**Error (400):**
```json
{
  "error": "mc_version is required"
}
```

```json
{
  "error": "server_id is required"
}
```

**Error (404):**
```json
{
  "error": "No suitable version found"
}
```

**Error (500):**
```json
{
  "error": "Download failed"
}
```

#### `GET /api/modrinth/categories`
Alle verfügbaren Mod-Kategorien abrufen.

**Response:**
```json
[
  {
    "icon": "...",
    "name": "adventure",
    "project_type": "mod",
    "header": "Adventure"
  }
]
```

#### `GET /api/modrinth/loaders`
Alle verfügbaren Mod-Loader abrufen.

**Response:**
```json
[
  {
    "icon": "...",
    "name": "fabric",
    "supported_project_types": ["mod", "modpack"]
  },
  {
    "icon": "...",
    "name": "forge",
    "supported_project_types": ["mod", "modpack"]
  }
]
```

#### `GET /api/modrinth/game-versions`
Alle verfügbaren Minecraft-Versionen abrufen.

**Response:**
```json
[
  {
    "version": "1.20.1",
    "version_type": "release",
    "date": "2023-06-12T00:00:00Z",
    "major": true
  }
]
```

---

## 🧪 Testing

API Tests ausführen:
```bash
python test_api.py
```

**Alle Tests:**
- ✓ Health Check
- ✓ Server Status
- ✓ Mod Search (mit Filtern)
- ✓ Mod Details
- ✓ Mod Versions
- ✓ Download URL
- ✓ Installation
- ✓ Categories & Loaders

---

## 🔧 Konfiguration

### Environment Variables

Setze in `.env` oder als Umgebungsvariablen:

```bash
# Flask
FLASK_ENV=development          # oder 'production'
HOST=0.0.0.0
PORT=5000

# Server Management
SERVER_COMMAND="java -Xmx4G -jar server.jar nogui"  # Custom Server Command
SERVER_DIR=./server           # Server Verzeichnis

# CORS
CORS_ORIGINS=*               # Erlaubte Origins
```

### Konfigurationsklassen

In `apps/backend/core/config.py`:
- `DevelopmentConfig`: Debug-Modus aktiviert
- `ProductionConfig`: Optimiert für Production

---

## 🧩 Loader Registry (Entwickler)

Die Loader-Dispatch-Schicht lebt in `apps/backend/server/installer/__init__.py`. Ein neuer Loader benötigt drei Schritte:

1. **Subklasse von `InstallerBase`** (`apps/backend/server/installer/base.py`) mit diesen Pflicht-Methoden anlegen:
   - `loader_name` (Property) — der Registry-Key, z.B. `"neoforge"`
   - `get_minecraft_versions()` → `List[{version, stable, type?}]` im normalisierten Schema (siehe `/api/loaders/<loader>/versions/game`)
   - `get_available_versions(mc_version)` → loader-natives Array; `[]` wenn der Loader keine separate Loader-Version hat
   - `install(mc_version, loader_version=None)` → `InstallResult` mit gesetztem `launch: LaunchSpec`. Der `LaunchSpec` wird in `servers.json` persistiert und treibt anschließend `ServerProcessRegistry._build_command`

2. **In `LOADER_REGISTRY` eintragen:**
   ```python
   from .neoforge import NeoForgeInstaller

   LOADER_REGISTRY: Dict[str, Type[InstallerBase]] = {
       "fabric": FabricInstaller,
       "vanilla": VanillaInstaller,
       "neoforge": NeoForgeInstaller,
   }
   ```

   `get_installer_for(loader, install_path)` (case-insensitive) und `supported_loaders()` greifen automatisch auf den neuen Eintrag zu — Routes und der Install-Flow brauchen keine Änderung.

3. **Frontend:** in `apps/frontend/src/components/modals/ServerCreateModal.vue` der `loaderOptions`-Liste eine Option mit demselben `value` wie `loader_name` hinzufügen.

Phase-2-Loader (Forge, NeoForge) werden voraussichtlich einen neuen `LaunchSpec.type` einführen (z.B. `args_files` für die `@user_jvm_args.txt`-Form). `_build_command` wirft heute schon `ValueError` bei unbekanntem Typ — das ist absichtlich, damit ein Phase-2-Record auf einem alten Build früh erkannt wird.

---

## 📚 Modrinth Client API

Der `ModrinthClient` kann auch direkt in Python verwendet werden:

```python
from backend.modrinth.client import ModrinthClient

client = ModrinthClient()

# Mods suchen
results = client.search_mods("sodium", mc_version="1.20.1", loader="fabric")

# Download-URL holen
url = client.get_mod_download_url("sodium", mc_version="1.20.1", loader="fabric")

# Mod herunterladen
from pathlib import Path
file = client.download_mod(url, Path("./mods"))
```

### Wichtige Methoden:

- `search_mods(query, mc_version, loader, limit, offset, index)` - Suche
- `get_mod(mod_id)` - Mod-Details
- `get_mod_versions(mod_id, loaders, game_versions, featured)` - Versionen
- `pick_best_version(versions)` - Beste Version auswählen
- `get_primary_file_url(version)` - Download-URL extrahieren
- `get_mod_download_url(mod_id, mc_version, loader)` - Alles in einem
- `download_mod(url, target_folder)` - Download

---

## 🎯 Use Cases

### 1. Mod suchen und installieren

```bash
# 1. Suche nach "create"
curl "http://localhost:5000/api/modrinth/search?query=create&mc_version=1.20.1&loader=fabric"

# 2. Installiere das gewünschte Mod
curl -X POST http://localhost:5000/api/modrinth/mod/create-fabric/install \
  -H "Content-Type: application/json" \
  -d '{"mc_version": "1.20.1", "loader": "fabric"}'
```

### 2. Alle Sodium-Versionen anzeigen

```bash
curl "http://localhost:5000/api/modrinth/mod/sodium/versions?loaders=fabric&game_versions=1.20.1"
```

### 3. Server starten mit installierten Mods

```bash
# Server starten (per-Server-Endpoint; <server_id> aus GET /api/servers)
curl -X POST http://localhost:5000/api/servers/<server_id>/start

# Metriken / Status prüfen
curl http://localhost:5000/api/servers/<server_id>/metrics
```

---

## 🔒 Sicherheit

- **Keine Authentifizierung**: Aktuell für lokale Entwicklung
- **CORS**: Aktiviert für Frontend-Development
- **Rate Limits**: Modrinth API: 300 Requests/Minute
- **User-Agent**: Korrekt gesetzt gemäß Modrinth-Richtlinien

---

## 🚧 Roadmap

- [ ] Vue.js Frontend vollständig implementieren
- [ ] Mod-Listen verwalten (Save/Load)
- [ ] Dependency-Resolution (automatische Installation von Dependencies)
- [ ] Server-Logs im Frontend anzeigen
- [ ] Backup-Funktionalität
- [ ] Multi-Server Support

---

## 📝 Lizenz

MIT License - siehe LICENSE Datei

---

## 🤝 Contributing

Pull Requests sind willkommen! Für größere Änderungen bitte zuerst ein Issue öffnen.

---

## 📞 Support

- GitHub Issues: [Fabricator Issues](https://github.com/philderks/Fabricator/issues)
- Modrinth API Docs: [docs.modrinth.com](https://docs.modrinth.com)

---

**Built with ❤️ using Flask, Vue.js & Modrinth API**
