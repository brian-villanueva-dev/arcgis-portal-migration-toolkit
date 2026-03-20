# ArcGIS Enterprise Portal Migration Toolkit

Automated content migration from ArcGIS Enterprise 10.9.1 to 11.3. Migrates 16 content types across 19 Jupyter notebooks with a single-command orchestrator.

## What It Does

Exports, transforms, and republishes portal content from a legacy ArcGIS Enterprise deployment to a new one. Handles the full dependency chain — groups and data services first, then maps that reference them, then apps that reference those maps.

**Migrates:**
- Feature Services, Scene Services, Vector Tile Layers, Tile Layers, Image Services
- Web Maps, Web Scenes (3D)
- Dashboards, Web Experiences, Experience Templates
- Survey123 Forms, StoryMaps, Web Apps
- Portal Groups, Notebooks
- Geoprocessing Services (inventory only — requires manual republish)

**Preserves:**
- Layer references (rewired via migration ledger)
- Owner and folder assignments
- Sharing permissions (Public/Org/Private + group membership)
- Metadata, tags, thumbnails, descriptions
- Embedded item IDs (deep regex scan + swap)

## Quick Start

### 1. Install dependencies

```bash
pip install arcgis pandas requests nbformat nbconvert
```

### 2. Configure

Edit `migration_config.py` with your portal URLs, tokens, and paths:

```python
SOURCE_URL   = "https://old-portal.example.com/arcgis"
SOURCE_TOKEN = "your-source-token"
TARGET_URL   = "https://new-portal.example.com/portal"
TARGET_TOKEN = "your-target-token"
TEMP_DIR     = r"C:\Temp\Migration"
LOG_FILE     = r"C:\Temp\Migration\migration_history.csv"
```

### 3. Prepare inventory

Export your source portal content list as CSV with `id` and `type` columns. A sample is included:

```bash
cat sample_inventory.csv
```

### 4. Run

```bash
# Full migration
python run_migration.py --inventory inventory.csv

# Preview only (no changes)
python run_migration.py --inventory inventory.csv --dry-run

# Resume after failure
python run_migration.py --inventory inventory.csv --start-from 5 --skip-preflight
```

## Architecture

```
                        ┌─────────────────────┐
                        │   run_migration.py   │  CLI orchestrator
                        │   (single command)   │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
        Write sidecar        Execute notebook      Read output
        _sidecar_*.json      via nbformat          _output_*.json
              │                    │                     │
              ▼                    ▼                     ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   Jupyter Notebooks                      │
    │                                                          │
    │  PreFlights (3)     Read-only dependency scanners        │
    │  Migration (16)     Export → Transform → Republish       │
    │                                                          │
    │  Each notebook works standalone OR via orchestrator       │
    └──────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    migration_history.csv
                    (shared ledger — prevents duplicates,
                     provides ID mapping for rewiring)
```

### Execution Order

The orchestrator runs notebooks in dependency order:

| Step | Notebook | Content Type |
|------|----------|-------------|
| — | PreFlight_WebMaps | Scan web maps for missing services |
| — | PreFlight_WebScenes | Scan web scenes for missing services |
| — | PreFlight_Apps | Scan dashboards/experiences for missing maps |
| 1 | 7_Migrate_Groups | Portal Groups |
| 2 | 1_Migrate_FeatureServices | Feature Services (export FGDB + republish) |
| 3 | 8_Migrate_SceneServices | Scene Services (export .slpk + republish) |
| 4 | 9_Migrate_VectorTileLayers | Vector Tile Layers (export .vtpk + republish) |
| 5 | 10_Migrate_TileLayers | Tile Layers (export .tpk + republish) |
| 6 | 11_Migrate_ImageServices | Image Services (clone + URL swap) |
| 7 | 2_Migrate_WebMaps | Web Maps (JSON rewire + basemap fix) |
| 8 | 12_Migrate_WebScenes | Web Scenes / 3D Maps (JSON rewire) |
| 9 | 3_Migrate_Dashboards | Dashboards (recursive ID swap) |
| 10 | 4_Migrate_WebExperiences | Web Experiences (deep ID scan + resource copy) |
| 11 | 5_Migrate_ExperienceTemplates | Experience Templates |
| 12 | 13_Migrate_Survey123 | Survey123 Forms (form JSON rewire) |
| 13 | 14_Migrate_StoryMaps | StoryMaps (deep ID scan + media copy) |
| 14 | 6_Migrate_WebApps | Web Mapping Applications |
| 15 | 15_Migrate_Notebooks | Portal Notebooks (.ipynb upload) |
| 16 | 16_Inventory_GPServices | GP Services (inventory only) |

### Communication Protocol

Notebooks communicate via JSON sidecar files — no shared memory or stdout parsing:

- **Input**: Orchestrator writes `_sidecar_<notebook>.json` with `{"ids": [...]}`
- **Output**: PreFlight notebooks write `_output_preflight_*.json` with `{"missing_ids": [...]}`
- **Standalone**: When no sidecar exists, notebooks use their hardcoded ID lists (manual mode)
- **Cleanup**: Sidecars are deleted after each step

### Migration Ledger

All notebooks share `migration_history.csv`:

| Column | Purpose |
|--------|---------|
| `SourceID` | Item ID from source portal |
| `LayerIndex` | Layer index (services) or `N/A` |
| `TargetID` | Item ID created on target portal |
| `Title` | Item title |
| `MigratedDate` | Timestamp |
| `Type` | Item type string |

The ledger serves two purposes:
1. **Deduplication** — already-migrated items are skipped automatically
2. **ID mapping** — downstream notebooks use `SourceID → TargetID` to rewire references

## Project Structure

```
├── run_migration.py              # CLI orchestrator
├── migration_config.py           # Shared configuration (edit this)
├── sample_inventory.csv          # Example inventory CSV
├── INSTRUCTIONS.md               # Detailed usage guide
├── README.md                     # This file
│
├── PreFlight_WebMaps.ipynb       # Dependency scanner: Web Maps
├── PreFlight_WebScenes.ipynb     # Dependency scanner: Web Scenes
├── PreFlight_Apps.ipynb          # Dependency scanner: Dashboards/Experiences
│
├── 1_Migrate_FeatureServices.ipynb
├── 2_Migrate_WebMaps.ipynb
├── 3_Migrate_Dashboards.ipynb
├── 4_Migrate_WebExperiences.ipynb
├── 5_Migrate_ExperienceTemplates.ipynb
├── 6_Migrate_WebApps.ipynb
├── 7_Migrate_Groups.ipynb
├── 8_Migrate_SceneServices.ipynb
├── 9_Migrate_VectorTileLayers.ipynb
├── 10_Migrate_TileLayers.ipynb
├── 11_Migrate_ImageServices.ipynb
├── 12_Migrate_WebScenes.ipynb
├── 13_Migrate_Survey123.ipynb
├── 14_Migrate_StoryMaps.ipynb
├── 15_Migrate_Notebooks.ipynb
└── 16_Inventory_GPServices.ipynb
```

## Configuration Reference

All settings live in `migration_config.py`:

| Setting | Purpose | Default |
|---------|---------|---------|
| `SOURCE_URL` / `SOURCE_TOKEN` | Source portal connection | — |
| `TARGET_URL` / `TARGET_TOKEN` | Target portal connection | — |
| `TEMP_DIR` | Working directory for exports | `C:\Temp\Migration` |
| `LOG_FILE` | Path to migration ledger CSV | `C:\Temp\Migration\migration_history.csv` |
| `DEFAULT_OWNER` | Fallback owner if source owner missing | `portaladm` |
| `DEFAULT_FOLDER` | Fallback folder in target | `migrate_test` |
| `APPEND_MIGRATED` | Add "(Migrated)" suffix to titles | Auto (staging URLs) |
| `THROTTLE_SECONDS` | Delay between API calls | `10` |
| `ID_BATCH_SIZE` | OID batch size for feature queries | `50` |
| `ENTERPRISE_HOST` | Host string for enterprise layer detection | `mms.doi.net` |
| `BLOCK_EXTERNAL_LAYERS` | Treat external layers as blockers | `False` |

## Requirements

- Python 3.8+
- ArcGIS API for Python (`arcgis`)
- `pandas`, `requests`, `nbformat`, `nbconvert`
- ArcPy (optional — enables Plan B extraction for Feature Services)
- Network access to both source and target portals
- Admin-level tokens for both portals

## Known Limitations

- **Geoprocessing Services** cannot be migrated via API — notebook 16 creates an inventory CSV for manual republishing
- **WAB (Web AppBuilder) apps** are not compatible with Portal 11.x and are logged for rebuild
- **Image Services** require the underlying image data to be registered on the target ArcGIS Server separately
- Portal tokens expire — regenerate if you see connection failures mid-run

## License

Internal tool. Not intended for public distribution.
