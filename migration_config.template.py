# =============================================================================
# MIGRATION CONFIGURATION (Shared by all migration notebooks)
# =============================================================================
# SETUP:
#   1. Copy this file:  cp migration_config.template.py migration_config.py
#   2. Fill in your portal URLs, tokens, and paths below
#   3. Restart your Jupyter kernel (Kernel > Restart) so Python reloads
#
# NOTE: migration_config.py is in .gitignore — your credentials stay local.
# =============================================================================

# =============================================================================
# --- PORTAL CONNECTIONS -------------------------------------------------------
# =============================================================================
# Source: The 10.9.1 portal you are migrating FROM
SOURCE_URL = "https://your-source-portal.example.com/arcgis"
SOURCE_TOKEN = "your-source-token-here"

# Target: The 11.3 portal you are migrating TO
TARGET_URL = "https://your-target-portal.example.com/portal"
TARGET_TOKEN = "your-target-token-here"

# =============================================================================
# --- FILE PATHS ---------------------------------------------------------------
# =============================================================================
# Working temp directory (created automatically if missing)
TEMP_DIR = r"C:\Temp\Migration"

# Migration history CSV (shared ledger used by all notebooks)
LOG_FILE = r"C:\Temp\Migration\migration_history.csv"

# =============================================================================
# --- OWNER & FOLDER DEFAULTS -------------------------------------------------
# =============================================================================
# Fallback owner if the source item's owner doesn't exist in target
DEFAULT_OWNER = "portaladmin"

# Fallback folder in target portal (created automatically if missing)
DEFAULT_FOLDER = "migrated_content"

# =============================================================================
# --- NAMING FLAG (Auto-derived from TARGET_URL) -------------------------------
# =============================================================================
# Automatically append "(Migrated)" to item titles if the target URL
# contains "batgis" or "stggisint" (staging/test environments).
APPEND_MIGRATED = False
if "batgis" in TARGET_URL.lower() or "stggisint" in TARGET_URL.lower():
    APPEND_MIGRATED = True
    print("   [Config] 'Migrated' suffix ENABLED based on Target URL.")

# =============================================================================
# --- SERVER SAFETY DEFAULTS ---------------------------------------------------
# =============================================================================
# Default throttle between API calls (seconds). Notebooks that need a
# different value (e.g., Feature Services = 30) override this locally.
THROTTLE_SECONDS = 10

# Batch size for OID-based queries (used by Feature Service migration)
ID_BATCH_SIZE = 50

# =============================================================================
# --- KNOWN ISSUE OVERRIDES ----------------------------------------------------
# =============================================================================
# Bid Submission Service gap fix: if a layer index >= 18 on this specific
# source service, subtract 1 to correct the index shift in target.
# Set to "" if not applicable to your environment.
PROBLEM_SOURCE_ID = ""

# =============================================================================
# --- PRE-FLIGHT SETTINGS -----------------------------------------------------
# =============================================================================
# Enterprise host string used to classify enterprise vs. external layers
# Change this to match your organization's ArcGIS Server hostname
ENTERPRISE_HOST = "your-server.example.com"

# If True, external/AGOL layers are treated as blockers (for locked-down
# environments). If False, they are informational only.
BLOCK_EXTERNAL_LAYERS = False

# =============================================================================
print("[Config] migration_config.py loaded.")
