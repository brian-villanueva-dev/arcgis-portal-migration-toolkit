# Content Migration Toolkit — Instructions

## Overview

This toolkit migrates content from an Esri ArcGIS Enterprise 10.9.1 portal to an 11.3 portal. It handles 16 content types: Groups, Feature Services, Scene Services, Vector Tile Layers, Tile Layers, Image Services, Web Maps, Web Scenes, Dashboards, Web Experiences, Experience Templates, Survey123 Forms, StoryMaps, Web Apps, Notebooks, and Geoprocessing Services (inventory only).

There are two ways to run it:

- **Orchestrator (recommended):** One command runs the entire pipeline automatically.
- **Manual (notebook-by-notebook):** Open individual Jupyter notebooks and run them in order.

---

## Prerequisites

1. **Python packages:** `arcgis`, `pandas`, `requests`, `nbformat`, `nbconvert`
   - ArcPy is optional but recommended (enables Plan B extraction for Feature Services)
2. **Portal tokens:** Generate tokens for both source and target portals
3. **Inventory CSV:** Export from your source portal (must have `id` and `type` columns)

---

## Step 1: Configure

Copy the template and fill in your values:

```
cp migration_config.template.py migration_config.py
```

Edit **`migration_config.py`** once. All notebooks and the orchestrator read from this file.
`migration_config.py` is in `.gitignore` — your credentials stay local.

```python
# Portal connections
SOURCE_URL   = "https://your-source-portal.com/arcgis"
SOURCE_TOKEN = "your-source-token"
TARGET_URL   = "https://your-target-portal.com/portal"
TARGET_TOKEN = "your-target-token"

# File paths
TEMP_DIR = r"C:\Temp\Migration"
LOG_FILE = r"C:\Temp\Migration\migration_history.csv"

# Defaults
DEFAULT_OWNER  = "portaladm"
DEFAULT_FOLDER = "migrate_test"
```

After editing, restart any open Jupyter kernels so Python reloads the module.

---

## Step 2a: Run with the Orchestrator (Recommended)

### Full migration

```
python run_migration.py --inventory C:\path\to\inventory.csv
```

This will:
1. Read your inventory CSV and group items by type
2. Filter out items already in `migration_history.csv`
3. Run preflight checks to find missing dependencies (WebMaps, WebScenes, Apps)
4. Merge discovered dependencies into the migration queue
5. Show a migration plan and ask for confirmation
6. Execute notebooks 1 through 16 in dependency order
7. Print a final report

### Dry run (preview without migrating)

```
python run_migration.py --inventory C:\path\to\inventory.csv --dry-run
```

Shows what would happen without executing any migration notebooks. Preflights still run (they are read-only).

### Resume after a failure

If a notebook fails mid-run, the orchestrator tells you the resume command:

```
python run_migration.py --inventory C:\path\to\inventory.csv --start-from 3 --skip-preflight
```

This skips earlier steps (already completed) and preflights (dependencies already resolved). Items already in the ledger are automatically skipped, so re-running is safe.

### Skip preflights

If you already know all dependencies exist on the target:

```
python run_migration.py --inventory C:\path\to\inventory.csv --skip-preflight
```

### Inventory CSV format

The orchestrator expects at minimum two columns: an ID column and a Type column.

| Column name (any of these work) | Purpose |
|---|---|
| `id`, `itemId`, `Item ID`, `SourceID` | Source portal item ID |
| `type`, `Type`, `Item Type` | ArcGIS item type string |

Example:
```csv
id,type,title,owner
abc123def456...,Feature Service,My Features,jsmith
789ghi012jkl...,Web Map,My Map,jdoe
345mno678pqr...,Dashboard,My Dashboard,jsmith
567stu901vwx...,Scene Service,My 3D Layer,jsmith
```

Supported types and their migration order:
1. `Group`
2. `Feature Service` / `Map Service`
3. `Scene Service` / `Scene Layer`
4. `Vector Tile Service` / `Vector Tile Layer`
5. `Tile Layer` / `Map Image Layer`
6. `Image Service` / `Imagery Layer`
7. `Web Map`
8. `Web Scene`
9. `Dashboard`
10. `Web Experience`
11. `Web Experience Template`
12. `Form` / `Survey123`
13. `StoryMap`
14. `Web Mapping Application`
15. `Notebook`
16. `Geoprocessing Service` (inventory only — not API-migratable)

Other types (e.g., `Image`, `Code Attachment`) are skipped with a note.

---

## Step 2b: Run Manually (Notebook-by-Notebook)

If you prefer to run notebooks individually in Jupyter:

### Execution order

```
 1. 7_Migrate_Groups.ipynb              (migrate portal groups)
 2. PreFlight_WebMaps.ipynb             (scan web maps for missing services)
 3. 1_Migrate_FeatureServices.ipynb     (migrate feature services)
 4. 8_Migrate_SceneServices.ipynb       (migrate scene services via .slpk)
 5. 9_Migrate_VectorTileLayers.ipynb    (migrate vector tile layers via .vtpk)
 6. 10_Migrate_TileLayers.ipynb         (migrate tile layers via .tpk)
 7. 11_Migrate_ImageServices.ipynb      (migrate image services)
 8. 2_Migrate_WebMaps.ipynb             (migrate web maps)
 9. PreFlight_WebScenes.ipynb           (scan web scenes for missing services)
10. 12_Migrate_WebScenes.ipynb          (migrate web scenes / 3D maps)
11. PreFlight_Apps.ipynb                (scan apps for missing web maps)
12. 3_Migrate_Dashboards.ipynb          (migrate dashboards)
13. 4_Migrate_WebExperiences.ipynb      (migrate web experiences)
14. 5_Migrate_ExperienceTemplates.ipynb (migrate experience templates)
15. 13_Migrate_Survey123.ipynb          (migrate Survey123 forms)
16. 14_Migrate_StoryMaps.ipynb          (migrate StoryMaps)
17. 6_Migrate_WebApps.ipynb             (migrate/inventory web apps)
18. 15_Migrate_Notebooks.ipynb          (migrate portal notebooks)
19. 16_Inventory_GPServices.ipynb       (inventory GP services — cannot be API-migrated)
```

### For each notebook

1. Open the notebook in Jupyter
2. Paste your source IDs into the ID list variable (e.g., `MULTI_LAYER_IDS = [...]`)
3. Run all cells (Cell > Run All)
4. Review the report at the bottom
5. Copy any output IDs from preflights into the next notebook

---

## Migration Ledger

All notebooks share a CSV ledger (`migration_history.csv`) that tracks:

| Column | Purpose |
|---|---|
| `SourceID` | Item ID from the source portal |
| `LayerIndex` | Layer index (Feature Services) or `N/A` |
| `TargetID` | Item ID created in the target portal |
| `Title` | Item title |
| `MigratedDate` | Timestamp |
| `Type` | Item type |

The ledger prevents duplicate migrations. If an item's SourceID is already in the ledger, it is skipped automatically.

---

## What Each Notebook Does

| Notebook | Items | Key behavior |
|---|---|---|
| **PreFlight_WebMaps** | Web Maps | Scans for missing Feature Service dependencies. Read-only. |
| **PreFlight_WebScenes** | Web Scenes | Scans for missing Scene/Feature Service dependencies. Read-only. |
| **PreFlight_Apps** | Dashboards, Experiences | Scans for missing Web Map dependencies. Read-only. |
| **1 - Feature Services** | Feature Services | Exports data as File GDB, republishes on target. Copies styles, scale, sharing, thumbnails. 30s throttle. |
| **2 - Web Maps** | Web Maps | Clones web map JSON, rewires layer references using ledger. Fixes deprecated basemaps. |
| **3 - Dashboards** | Dashboards | Clones dashboard JSON, recursively swaps all embedded item IDs. |
| **4 - Web Experiences** | Web Experiences | Deep regex ID scan + swap, copies config.json and resources via REST. 15s throttle. |
| **5 - Experience Templates** | Experience Templates | Same as #4 but creates as Template type with `isTemplate=True`. |
| **6 - Web Apps** | Web Mapping Applications | Classifies apps (WAB/StoryMap/Configurable/Unknown). Migrates Configurable apps. Writes rebuild inventory CSV for non-migratable types. |
| **7 - Groups** | Portal Groups | Recreates groups on target with matching title, tags, description, thumbnail, and membership. |
| **8 - Scene Services** | Scene Services | Downloads .slpk from source, publishes as Scene Layer on target. Copies metadata and sharing. |
| **9 - Vector Tile Layers** | Vector Tile Services | Downloads .vtpk from source, publishes as Vector Tile Layer on target. Copies metadata and sharing. |
| **10 - Tile Layers** | Tile Layers / Map Image Layers | Downloads .tpk from source, publishes as Tile Layer on target. Copies metadata and sharing. |
| **11 - Image Services** | Image Services | Clones item + updates URL references. Copies metadata and sharing. |
| **12 - Web Scenes** | Web Scenes (3D) | Clones web scene JSON, rewires all layer references (operational, basemap, ground/elevation). Deep ID swap for slides/popups. |
| **13 - Survey123** | Survey123 Forms | Rewires form JSON (feature service references), copies resources via REST. |
| **14 - StoryMaps** | StoryMaps | Deep regex ID scan + swap across story JSON, copies media resources via REST. |
| **15 - Notebooks** | Portal Notebooks | Downloads .ipynb from source, uploads to target. Copies metadata and sharing. |
| **16 - GP Services** | Geoprocessing Services | Inventory only — GP Services cannot be API-migrated. Writes `gp_service_inventory.csv` with rebuild recommendations. |

---

## Known Behaviors

- **"(Migrated)" suffix:** Automatically appended to item titles when the target URL contains `batgis` or `stggisint` (staging environments). Controlled by `APPEND_MIGRATED` in config.
- **Owner/folder mirroring:** If the source owner exists in the target portal, items are assigned to them in the same folder. Otherwise, items go to `DEFAULT_OWNER` / `DEFAULT_FOLDER`.
- **Sharing mirroring:** Public/Org/Private access and group sharing are replicated by matching group titles.
- **Layer-index gap fix (disabled by default):** If a source feature service has a gap in its layer indices (e.g., layer 17 missing), layers at index >= 18 will be off-by-one in the target. To enable: uncomment `PROBLEM_SOURCE_ID` in `migration_config.py` and uncomment the corresponding gap-fix blocks in notebooks 2, 3, 5, and 6.
- **WAB / Legacy Story Maps:** Not migrated (incompatible with Portal 11.x). Logged to `app_inventory.csv` with rebuild recommendations.
- **GP Services:** Cannot be migrated via API. Notebook 16 creates an inventory CSV with service details for manual rebuild.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `migration_config.py` changes not taking effect | Restart your Jupyter kernel (Kernel > Restart) |
| Notebook fails on connection | Check that tokens in `migration_config.py` are still valid |
| Orchestrator fails mid-run | Use `--start-from N --skip-preflight` to resume |
| Feature Service publish fails with name conflict | Manually delete the conflicting service in the target portal, then re-run |
| Scene Service .slpk download fails | Check source portal storage; may need to re-cache the scene layer |
| `nbformat` / `nbconvert` not found | `pip install nbformat nbconvert` |
| Preflight shows external/AGOL layers | Usually OK — these are Living Atlas or ArcGIS Online references that don't need migration |
