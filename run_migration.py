# =============================================================================
# MIGRATION ORCHESTRATOR
# =============================================================================
# Automates the full Esri 10.9.1 -> 11.3 content migration pipeline.
#
# Usage:
#   python run_migration.py --inventory path/to/inventory.csv
#   python run_migration.py --inventory path/to/inventory.csv --dry-run
#   python run_migration.py --inventory path/to/inventory.csv --start-from 3
#   python run_migration.py --inventory path/to/inventory.csv --skip-preflight
#
# This script:
#   1. Reads an inventory CSV exported from the source portal
#   2. Groups items by type into migration buckets
#   3. Runs PreFlight checks to discover missing dependencies
#   4. Feeds discovered IDs + inventory IDs into migration notebooks 1-16
#   5. Executes notebooks in dependency order via nbformat
#
# Each notebook communicates via JSON sidecar files:
#   - Orchestrator writes _sidecar_*.json (input IDs for each notebook)
#   - PreFlight notebooks write _output_*.json (discovered missing IDs)
#   - Sidecar files are cleaned up after each step
#
# Notebooks still work standalone in Jupyter when no sidecar is present.
# =============================================================================

import argparse
import json
import os
import sys
import time
import datetime
import pandas as pd

try:
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
except ImportError:
    print("ERROR: nbformat and nbconvert are required.")
    print("Install with: pip install nbformat nbconvert")
    sys.exit(1)

# =============================================================================
# --- PATHS & CONSTANTS --------------------------------------------------------
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Notebook filenames (in execution order)
NOTEBOOKS = {
    "preflight_webmaps":    "PreFlight_WebMaps.ipynb",
    "preflight_apps":       "PreFlight_Apps.ipynb",
    "preflight_webscenes":  "PreFlight_WebScenes.ipynb",
    "1_feature_services":   "1_Migrate_FeatureServices.ipynb",
    "2_webmaps":            "2_Migrate_WebMaps.ipynb",
    "3_dashboards":         "3_Migrate_Dashboards.ipynb",
    "4_experiences":        "4_Migrate_WebExperiences.ipynb",
    "5_templates":          "5_Migrate_ExperienceTemplates.ipynb",
    "6_webapps":            "6_Migrate_WebApps.ipynb",
    "7_groups":             "7_Migrate_Groups.ipynb",
    "8_scene_services":     "8_Migrate_SceneServices.ipynb",
    "9_vector_tiles":       "9_Migrate_VectorTileLayers.ipynb",
    "10_tile_layers":       "10_Migrate_TileLayers.ipynb",
    "11_image_services":    "11_Migrate_ImageServices.ipynb",
    "12_web_scenes":        "12_Migrate_WebScenes.ipynb",
    "13_survey123":         "13_Migrate_Survey123.ipynb",
    "14_storymaps":         "14_Migrate_StoryMaps.ipynb",
    "15_notebooks":         "15_Migrate_Notebooks.ipynb",
    "16_gp_services":       "16_Inventory_GPServices.ipynb",
}

# Sidecar file mapping (notebook key -> sidecar filename)
SIDECAR_FILES = {
    "preflight_webmaps":    "_sidecar_preflight_webmaps.json",
    "preflight_apps":       "_sidecar_preflight_apps.json",
    "preflight_webscenes":  "_sidecar_preflight_webscenes.json",
    "1_feature_services":   "_sidecar_1_feature_services.json",
    "2_webmaps":            "_sidecar_2_webmaps.json",
    "3_dashboards":         "_sidecar_3_dashboards.json",
    "4_experiences":        "_sidecar_4_experiences.json",
    "5_templates":          "_sidecar_5_experience_templates.json",
    "6_webapps":            "_sidecar_6_webapps.json",
    "7_groups":             "_sidecar_7_groups.json",
    "8_scene_services":     "_sidecar_8_scene_services.json",
    "9_vector_tiles":       "_sidecar_9_vector_tiles.json",
    "10_tile_layers":       "_sidecar_10_tile_layers.json",
    "11_image_services":    "_sidecar_11_image_services.json",
    "12_web_scenes":        "_sidecar_12_web_scenes.json",
    "13_survey123":         "_sidecar_13_survey123.json",
    "14_storymaps":         "_sidecar_14_storymaps.json",
    "15_notebooks":         "_sidecar_15_notebooks.json",
    "16_gp_services":       "_sidecar_16_gp_services.json",
}

# Preflight output files (written by preflight notebooks, read by orchestrator)
PREFLIGHT_OUTPUTS = {
    "preflight_webmaps":   "_output_preflight_webmaps.json",
    "preflight_apps":      "_output_preflight_apps.json",
    "preflight_webscenes": "_output_preflight_webscenes.json",
}

# Inventory CSV type -> bucket mapping
TYPE_BUCKETS = {
    "feature service":          "feature_services",
    "map service":              "feature_services",
    "web map":                  "web_maps",
    "dashboard":                "dashboards",
    "web experience":           "experiences",
    "web experience template":  "experience_templates",
    "web mapping application":  "web_apps",
    "group":                    "groups",
    "scene service":            "scene_services",
    "scene layer":              "scene_services",
    "vector tile service":      "vector_tiles",
    "vector tile layer":        "vector_tiles",
    "tile layer":               "tile_layers",
    "map image layer":          "tile_layers",
    "image service":            "image_services",
    "imagery layer":            "image_services",
    "web scene":                "web_scenes",
    "form":                     "survey123",
    "survey123":                "survey123",
    "storymap":                 "storymaps",
    "storymap theme":           "storymaps",
    "notebook":                 "notebooks",
    "geoprocessing service":    "gp_services",
    "geoprocessing sample":     "gp_services",
}

# Bucket -> notebook key mapping
BUCKET_TO_NOTEBOOK = {
    "groups":               "7_groups",
    "feature_services":     "1_feature_services",
    "scene_services":       "8_scene_services",
    "vector_tiles":         "9_vector_tiles",
    "tile_layers":          "10_tile_layers",
    "image_services":       "11_image_services",
    "web_maps":             "2_webmaps",
    "web_scenes":           "12_web_scenes",
    "dashboards":           "3_dashboards",
    "experiences":          "4_experiences",
    "experience_templates": "5_templates",
    "survey123":            "13_survey123",
    "storymaps":            "14_storymaps",
    "web_apps":             "6_webapps",
    "notebooks":            "15_notebooks",
    "gp_services":          "16_gp_services",
}

# Migration step order (notebook keys) — dependency order matters:
# Groups first (needed by sharing), then data services, then maps, then apps
MIGRATION_ORDER = [
    "7_groups",
    "1_feature_services",
    "8_scene_services",
    "9_vector_tiles",
    "10_tile_layers",
    "11_image_services",
    "2_webmaps",
    "12_web_scenes",
    "3_dashboards",
    "4_experiences",
    "5_templates",
    "13_survey123",
    "14_storymaps",
    "6_webapps",
    "15_notebooks",
    "16_gp_services",
]

# Run state file (tracks completed steps for resume)
RUN_STATE_FILE = os.path.join(SCRIPT_DIR, "_run_state.json")


# =============================================================================
# --- HELPERS ------------------------------------------------------------------
# =============================================================================
def sidecar_path(key):
    return os.path.join(SCRIPT_DIR, SIDECAR_FILES[key])


def output_path(key):
    return os.path.join(SCRIPT_DIR, PREFLIGHT_OUTPUTS[key])


def notebook_path(key):
    return os.path.join(SCRIPT_DIR, NOTEBOOKS[key])


def write_sidecar(key, id_list):
    """Write a JSON sidecar file with the given ID list."""
    path = sidecar_path(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "ids": list(id_list),
            "generated_by": "run_migration.py",
            "generated_at": datetime.datetime.now().isoformat(),
        }, f, indent=2)
    print(f"   Wrote {len(id_list)} IDs to {os.path.basename(path)}")


def cleanup_sidecar(key):
    """Remove a sidecar file if it exists."""
    path = sidecar_path(key)
    if os.path.exists(path):
        os.remove(path)


def cleanup_output(key):
    """Remove a preflight output file if it exists."""
    path = output_path(key)
    if os.path.exists(path):
        os.remove(path)


def read_preflight_output(key):
    """Read missing IDs from a preflight output JSON file."""
    path = output_path(key)
    if not os.path.exists(path):
        print(f"   WARNING: Preflight output {os.path.basename(path)} not found.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("missing_ids", [])


def save_run_state(completed_steps, failed_step=None):
    """Save run progress so the user can resume after failure."""
    state = {
        "timestamp": datetime.datetime.now().isoformat(),
        "completed_steps": completed_steps,
        "failed_step": failed_step,
    }
    with open(RUN_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_run_state():
    """Load previous run state if it exists."""
    if os.path.exists(RUN_STATE_FILE):
        with open(RUN_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def cleanup_run_state():
    """Remove run state file after successful completion."""
    if os.path.exists(RUN_STATE_FILE):
        os.remove(RUN_STATE_FILE)


# =============================================================================
# --- INVENTORY PARSER ---------------------------------------------------------
# =============================================================================
def parse_inventory(csv_path):
    """
    Read inventory CSV and group item IDs by type into buckets.
    Returns dict: {"feature_services": [...], "web_maps": [...], ...}
    """
    df = pd.read_csv(csv_path)

    # Normalize column names (case-insensitive)
    col_map = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower in ("id", "itemid", "item id", "item_id", "source_id", "sourceid"):
            col_map["id"] = col
        elif lower in ("type", "item type", "item_type", "itemtype"):
            col_map["type"] = col

    if "id" not in col_map:
        print(f"ERROR: Could not find an ID column in {csv_path}")
        print(f"   Found columns: {list(df.columns)}")
        print("   Expected one of: id, itemId, Item ID, source_id, SourceID")
        sys.exit(1)
    if "type" not in col_map:
        print(f"ERROR: Could not find a Type column in {csv_path}")
        print(f"   Found columns: {list(df.columns)}")
        print("   Expected one of: type, Type, Item Type")
        sys.exit(1)

    buckets = {
        "groups": [],
        "feature_services": [],
        "scene_services": [],
        "vector_tiles": [],
        "tile_layers": [],
        "image_services": [],
        "web_maps": [],
        "web_scenes": [],
        "dashboards": [],
        "experiences": [],
        "experience_templates": [],
        "survey123": [],
        "storymaps": [],
        "web_apps": [],
        "notebooks": [],
        "gp_services": [],
    }

    skipped_types = {}

    for _, row in df.iterrows():
        item_id = str(row[col_map["id"]]).strip()
        item_type = str(row[col_map["type"]]).strip().lower()

        if not item_id or item_id == "nan":
            continue

        bucket_name = TYPE_BUCKETS.get(item_type)
        if bucket_name:
            buckets[bucket_name].append(item_id)
        else:
            skipped_types[item_type] = skipped_types.get(item_type, 0) + 1

    if skipped_types:
        print("\n   Skipped item types (not part of migration pipeline):")
        for t, count in sorted(skipped_types.items()):
            print(f"      {t}: {count} items")

    return buckets


# =============================================================================
# --- LEDGER FILTER ------------------------------------------------------------
# =============================================================================
def load_already_migrated(log_file):
    """Load set of already-migrated SourceIDs from the ledger CSV."""
    if not os.path.exists(log_file):
        return set()
    try:
        df = pd.read_csv(log_file)
        if "SourceID" in df.columns:
            return set(df["SourceID"].astype(str).str.strip())
    except Exception as e:
        print(f"   WARNING: Could not read ledger: {e}")
    return set()


def filter_buckets(buckets, already_migrated):
    """Remove already-migrated IDs from all buckets. Returns filtered copy."""
    filtered = {}
    for name, ids in buckets.items():
        original_count = len(ids)
        new_ids = [i for i in ids if i not in already_migrated]
        skipped = original_count - len(new_ids)
        filtered[name] = new_ids
        if skipped > 0:
            print(f"   {name}: {skipped} already migrated, {len(new_ids)} remaining")
    return filtered


# =============================================================================
# --- NOTEBOOK EXECUTOR --------------------------------------------------------
# =============================================================================
def run_notebook(key, timeout=14400):
    """
    Execute a Jupyter notebook via nbformat.
    Returns (success: bool, output_text: str)
    """
    nb_path = notebook_path(key)
    nb_name = os.path.basename(nb_path)

    print(f"\n{'='*60}")
    print(f"   EXECUTING: {nb_name}")
    print(f"{'='*60}")

    if not os.path.exists(nb_path):
        return False, f"Notebook not found: {nb_path}"

    with open(nb_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    ep = ExecutePreprocessor(
        timeout=timeout,
        kernel_name="python3",
        cwd=SCRIPT_DIR,
    )

    start = time.time()
    try:
        ep.preprocess(nb, {"metadata": {"path": SCRIPT_DIR}})

        # Extract text outputs from all cells
        output_lines = []
        for cell in nb.cells:
            if cell.cell_type == "code":
                for out in cell.get("outputs", []):
                    if "text" in out:
                        output_lines.append(out["text"])
                    elif out.get("output_type") == "stream":
                        output_lines.append(out.get("text", ""))

        full_output = "".join(output_lines)
        elapsed = int(time.time() - start)
        print(f"   Completed in {elapsed // 60}m {elapsed % 60}s")

        # Print last 20 lines of output (usually the report)
        lines = full_output.strip().split("\n")
        report_lines = lines[-20:] if len(lines) > 20 else lines
        for line in report_lines:
            print(f"   {line}")

        return True, full_output

    except CellExecutionError as e:
        elapsed = int(time.time() - start)
        error_msg = str(e)
        # Try to extract the cell that failed
        short_err = error_msg[:500] if len(error_msg) > 500 else error_msg
        print(f"\n   NOTEBOOK FAILED after {elapsed // 60}m {elapsed % 60}s")
        print(f"   Error: {short_err}")
        return False, error_msg

    except Exception as e:
        elapsed = int(time.time() - start)
        print(f"\n   NOTEBOOK ERROR after {elapsed // 60}m {elapsed % 60}s: {e}")
        return False, str(e)


# =============================================================================
# --- PRE-VALIDATION -----------------------------------------------------------
# =============================================================================
def validate_environment():
    """Check that all required files and config are in place."""
    errors = []

    # Check migration_config.py
    config_path = os.path.join(SCRIPT_DIR, "migration_config.py")
    if not os.path.exists(config_path):
        errors.append(f"migration_config.py not found in {SCRIPT_DIR}")

    # Check all notebooks exist
    for key, filename in NOTEBOOKS.items():
        path = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(path):
            errors.append(f"Notebook not found: {filename}")

    if errors:
        print("\nPRE-VALIDATION FAILED:")
        for err in errors:
            print(f"   - {err}")
        sys.exit(1)

    print("   All notebooks and config verified.")


# =============================================================================
# --- MAIN PIPELINE ------------------------------------------------------------
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Migration Orchestrator: Automates Esri 10.9.1 -> 11.3 content migration"
    )
    parser.add_argument(
        "--inventory", required=True,
        help="Path to inventory CSV exported from source portal"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse inventory and run preflights, but do not execute migration notebooks"
    )
    parser.add_argument(
        "--start-from", type=int, default=1, choices=range(1, 17),
        help="Resume from migration step N (1-16), skipping earlier steps"
    )
    parser.add_argument(
        "--skip-preflight", action="store_true",
        help="Skip preflight checks (use only if you know dependencies are met)"
    )

    args = parser.parse_args()

    # --- Banner ---
    print("=" * 60)
    print("   MIGRATION ORCHESTRATOR")
    print("   Esri 10.9.1 -> 11.3 Content Migration Pipeline")
    print("=" * 60)
    print(f"   Inventory:      {args.inventory}")
    print(f"   Dry Run:        {args.dry_run}")
    print(f"   Start From:     Notebook {args.start_from}")
    print(f"   Skip Preflight: {args.skip_preflight}")
    print("=" * 60)

    # --- Validate ---
    print("\n[1/6] Validating environment (16 migration steps available)...")
    validate_environment()

    if not os.path.exists(args.inventory):
        print(f"ERROR: Inventory file not found: {args.inventory}")
        sys.exit(1)

    # --- Load config to get LOG_FILE path ---
    sys.path.insert(0, SCRIPT_DIR)
    try:
        from migration_config import LOG_FILE
    except ImportError as e:
        print(f"ERROR: Could not import migration_config: {e}")
        sys.exit(1)

    # --- Parse Inventory ---
    print("\n[2/6] Parsing inventory CSV...")
    buckets = parse_inventory(args.inventory)

    total_items = sum(len(v) for v in buckets.values())
    print(f"\n   Inventory Summary ({total_items} total items):")
    for name, ids in buckets.items():
        if ids:
            print(f"      {name}: {len(ids)}")

    # --- Filter against ledger ---
    print("\n[3/6] Filtering against migration ledger...")
    already_migrated = load_already_migrated(LOG_FILE)
    print(f"   Ledger contains {len(already_migrated)} previously migrated items.")
    buckets = filter_buckets(buckets, already_migrated)

    remaining = sum(len(v) for v in buckets.values())
    print(f"\n   After filtering: {remaining} items to process")
    for name, ids in buckets.items():
        if ids:
            print(f"      {name}: {len(ids)}")

    if remaining == 0:
        print("\n   All items already migrated. Nothing to do.")
        return

    # --- Preflight Phase ---
    preflight_fs_ids = []
    preflight_wm_ids = []
    preflight_scene_svc_ids = []

    if not args.skip_preflight and args.start_from <= 1:
        print("\n[4/6] Running preflight checks...")

        # PreFlight WebMaps: check if web maps' feature service deps exist on target
        if buckets["web_maps"]:
            print(f"\n   Running PreFlight_WebMaps for {len(buckets['web_maps'])} web maps...")
            write_sidecar("preflight_webmaps", buckets["web_maps"])
            cleanup_output("preflight_webmaps")

            success, output = run_notebook("preflight_webmaps", timeout=7200)
            cleanup_sidecar("preflight_webmaps")

            if success:
                preflight_fs_ids = read_preflight_output("preflight_webmaps")
                if preflight_fs_ids:
                    print(f"\n   Preflight discovered {len(preflight_fs_ids)} missing Feature Services")
            else:
                print("\n   WARNING: PreFlight_WebMaps failed. Continuing without preflight results.")

            cleanup_output("preflight_webmaps")
        else:
            print("\n   No web maps in inventory — skipping PreFlight_WebMaps.")

        # PreFlight WebScenes: check if web scenes' scene/feature service deps exist
        if buckets["web_scenes"]:
            print(f"\n   Running PreFlight_WebScenes for {len(buckets['web_scenes'])} web scenes...")
            write_sidecar("preflight_webscenes", buckets["web_scenes"])
            cleanup_output("preflight_webscenes")

            success, output = run_notebook("preflight_webscenes", timeout=7200)
            cleanup_sidecar("preflight_webscenes")

            if success:
                preflight_scene_svc_ids = read_preflight_output("preflight_webscenes")
                if preflight_scene_svc_ids:
                    print(f"\n   Preflight discovered {len(preflight_scene_svc_ids)} missing Scene/Feature Services")
            else:
                print("\n   WARNING: PreFlight_WebScenes failed. Continuing without preflight results.")

            cleanup_output("preflight_webscenes")
        else:
            print("\n   No web scenes in inventory — skipping PreFlight_WebScenes.")

        # PreFlight Apps: check if dashboards/experiences' web map deps exist
        app_ids = buckets["dashboards"] + buckets["experiences"]
        if app_ids:
            print(f"\n   Running PreFlight_Apps for {len(app_ids)} dashboards/experiences...")
            write_sidecar("preflight_apps", app_ids)
            cleanup_output("preflight_apps")

            success, output = run_notebook("preflight_apps", timeout=7200)
            cleanup_sidecar("preflight_apps")

            if success:
                preflight_wm_ids = read_preflight_output("preflight_apps")
                if preflight_wm_ids:
                    print(f"\n   Preflight discovered {len(preflight_wm_ids)} missing Web Maps")
            else:
                print("\n   WARNING: PreFlight_Apps failed. Continuing without preflight results.")

            cleanup_output("preflight_apps")
        else:
            print("\n   No dashboards/experiences in inventory — skipping PreFlight_Apps.")
    else:
        print("\n[4/6] Preflight checks skipped.")

    # --- Merge preflight discoveries into buckets ---
    if preflight_fs_ids:
        existing_fs = set(buckets["feature_services"])
        new_fs = [i for i in preflight_fs_ids if i not in existing_fs and i not in already_migrated]
        if new_fs:
            buckets["feature_services"].extend(new_fs)
            print(f"\n   Merged {len(new_fs)} preflight-discovered Feature Services into migration queue")

    if preflight_scene_svc_ids:
        # Scene preflight may discover missing feature services or scene services
        existing_fs = set(buckets["feature_services"])
        existing_ss = set(buckets["scene_services"])
        new_svc = [i for i in preflight_scene_svc_ids if i not in existing_fs and i not in existing_ss and i not in already_migrated]
        if new_svc:
            # Add to feature_services bucket (scene services should already be in inventory)
            buckets["feature_services"].extend(new_svc)
            print(f"   Merged {len(new_svc)} preflight-discovered services (from WebScenes) into migration queue")

    if preflight_wm_ids:
        existing_wm = set(buckets["web_maps"])
        new_wm = [i for i in preflight_wm_ids if i not in existing_wm and i not in already_migrated]
        if new_wm:
            buckets["web_maps"].extend(new_wm)
            print(f"   Merged {len(new_wm)} preflight-discovered Web Maps into migration queue")

    # --- Migration Plan Summary ---
    print("\n" + "=" * 60)
    print("   MIGRATION PLAN")
    print("=" * 60)

    step_num = 0
    steps_to_run = []
    for nb_key in MIGRATION_ORDER:
        step_num += 1
        bucket_name = [k for k, v in BUCKET_TO_NOTEBOOK.items() if v == nb_key][0]
        ids = buckets.get(bucket_name, [])
        status = ""

        if step_num < args.start_from:
            status = " (SKIP - before --start-from)"
        elif not ids:
            status = " (SKIP - no items)"
        else:
            steps_to_run.append((nb_key, bucket_name, ids))

        notebook_name = NOTEBOOKS[nb_key]
        print(f"   Step {step_num}: {notebook_name}")
        print(f"           {len(ids)} items{status}")

    print("=" * 60)

    if not steps_to_run:
        print("\n   No migration steps to execute.")
        return

    if args.dry_run:
        print("\n   DRY RUN complete. No notebooks were executed.")
        print("   Remove --dry-run to execute the migration.")
        return

    # --- Confirmation ---
    total_to_migrate = sum(len(ids) for _, _, ids in steps_to_run)
    print(f"\n   Ready to migrate {total_to_migrate} items across {len(steps_to_run)} notebooks.")
    try:
        response = input("   Proceed? [y/N]: ").strip().lower()
    except EOFError:
        response = "y"  # Non-interactive mode
    if response != "y":
        print("   Aborted.")
        return

    # --- Execute Migration Notebooks ---
    print("\n[5/6] Executing migration notebooks...")
    completed_steps = []
    pipeline_start = time.time()

    for nb_key, bucket_name, ids in steps_to_run:
        try:
            # Write sidecar
            write_sidecar(nb_key, ids)

            # Determine timeout (Feature Services get more time)
            timeout = 14400 if nb_key == "1_feature_services" else 7200

            # Execute
            success, output = run_notebook(nb_key, timeout=timeout)

            # Cleanup sidecar regardless of outcome
            cleanup_sidecar(nb_key)

            if success:
                completed_steps.append(nb_key)
                save_run_state(completed_steps)

                # Reload ledger after each step (new IDs are now available)
                already_migrated = load_already_migrated(LOG_FILE)
                print(f"   Ledger now contains {len(already_migrated)} migrated items.")
            else:
                # Notebook failed
                step_index = MIGRATION_ORDER.index(nb_key) + 1
                save_run_state(completed_steps, failed_step=nb_key)
                print(f"\n   PIPELINE PAUSED: {NOTEBOOKS[nb_key]} failed.")
                print(f"   To resume after fixing the issue:")
                print(f"   python run_migration.py --inventory {args.inventory} --start-from {step_index} --skip-preflight")

                try:
                    cont = input("\n   Continue with next notebook anyway? [y/N]: ").strip().lower()
                except EOFError:
                    cont = "n"
                if cont != "y":
                    print("   Pipeline stopped.")
                    return

        except Exception as e:
            cleanup_sidecar(nb_key)
            print(f"\n   UNEXPECTED ERROR: {e}")
            step_index = MIGRATION_ORDER.index(nb_key) + 1
            save_run_state(completed_steps, failed_step=nb_key)
            print(f"   To resume: python run_migration.py --inventory {args.inventory} --start-from {step_index} --skip-preflight")
            return

    # --- Final Report ---
    pipeline_elapsed = int(time.time() - pipeline_start)
    print(f"\n[6/6] Migration complete!")

    print("\n" + "=" * 60)
    print("   ORCHESTRATOR FINAL REPORT")
    print("=" * 60)
    print(f"   Total Duration:    {pipeline_elapsed // 3600}h {(pipeline_elapsed % 3600) // 60}m {pipeline_elapsed % 60}s")
    print(f"   Steps Completed:   {len(completed_steps)} / {len(steps_to_run)}")

    # Count new ledger entries
    final_migrated = load_already_migrated(LOG_FILE)
    new_entries = len(final_migrated) - len(already_migrated) if already_migrated else len(final_migrated)
    print(f"   New Items Migrated: {new_entries}")
    print(f"   Total in Ledger:    {len(final_migrated)}")

    for step in completed_steps:
        print(f"      [OK] {NOTEBOOKS[step]}")

    print("=" * 60)

    # Cleanup run state on success
    if len(completed_steps) == len(steps_to_run):
        cleanup_run_state()
        print("\n   All steps completed successfully.")
    else:
        print(f"\n   {len(steps_to_run) - len(completed_steps)} step(s) did not complete.")


if __name__ == "__main__":
    main()
