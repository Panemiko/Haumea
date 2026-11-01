# Haumea Lead Pipeline

**Haumea** is a CLI-based automation tool and data processing pipeline designed to scrape, clean, review, and register Brazilian business lead data. Its primary focus is identifying prospective clients for web design and modernization services (e.g., qualifying leads based on the quality or existence of their current websites).

---

## 🛠️ Environment Setup

Before using Haumea, set up your system with the required dependencies and tool permissions:

### 1. Prerequisites
- **Python**: Version 3.8 or higher is recommended.
- **Web Browser**: [google-chrome](https://www.google.com/chrome/) or [chromium-browser](https://www.chromium.org/) must be installed on your system. The reviewer script uses it to automatically display the lead's website and social media profiles.

### 2. Python Dependencies
Install the required packages using `pip`:
```bash
pip install PySide6
```
> [!NOTE]
> `PySide6` is required by the helper app [scripts/viewer.py](file:///home/panemiko/Documentos/Haumea/system/scripts/viewer.py) to render screenshots of business websites.

### 3. Scraper Binary Setup
This project uses the precompiled Go binary from [google-maps-scraper](https://github.com/gosom/google-maps-scraper) to fetch business listings.
1. Go to the [Releases Page](https://github.com/gosom/google-maps-scraper/releases).
2. Download the version corresponding to your operating system (e.g., `google_maps_scraper_1.3.0_linux_amd64.tar.gz` for Linux).
3. Extract the archive and place the executable binary (named `google_maps_scraper-1.3.0-linux-amd64` or similar) directly in the project root directory.
4. Ensure the binary has execution permissions:
   ```bash
   chmod +x google_maps_scraper-1.3.0-linux-amd64
   ```
   *(Although the scraper wrapper [scripts/scraper.py](file:///home/panemiko/Documentos/Haumea/system/scripts/scraper.py) will automatically attempt to make it executable, running this manually is recommended).*

---

## 🚀 How to Run the Pipeline

The [haumea](file:///home/panemiko/Documentos/Haumea/system/haumea) CLI coordinates all scripts. You can run individual stages or run the entire pipeline at once.

### 💡 The Quick/Unified Way (Clean & Review)
To automatically clean a raw scraped CSV and start reviewing it sequentially:
```bash
python haumea <raw_input_file.csv>
```
Or explicitly run the `all` command:
```bash
python haumea all <raw_input_file.csv> [options]
```
#### Options:
- `-o, --output`: Path to save the final qualified CSV file. *(Defaults to `<input_filename>_cleaned_qualified.csv`)*
- `-s, --screenshot-dir`: Directory to save captured screenshots. *(Defaults to `temp/screenshots/`)*

---

## 🔍 Individual Commands & Subcommands

For fine-grained control, you can execute individual parts of the pipeline:

### 1. Scrape Leads
Execute the precompiled Google Maps scraper [google_maps_scraper-1.3.0-linux-amd64](file:///home/panemiko/Documentos/Haumea/system/google_maps_scraper-1.3.0-linux-amd64):
```bash
python haumea scrape "<keywords>" [options]
```
- **Arguments**:
  - `keywords`: Queries/queries to search. Can be a single search string or comma-separated queries.
- **Options**:
  - `-o, --output`: Path to the raw CSV output. *(Defaults to `<sanitized_first_query>.csv`)*
  - `-d, --depth`: Scroll depth limit for scraper results. *(Default is `10`)*

### 2. Clean CSV
Process raw CSV data using [scripts/cleaner.py](file:///home/panemiko/Documentos/Haumea/system/scripts/cleaner.py). This normalizes Brazilian addresses, extracts social links, and checks for basic Google Business Profile completeness:
```bash
python haumea clean <input_file.csv> [options]
```
- **Options**:
  - `-o, --output`: Path to output CSV file. *(Defaults to `<input_filename>_cleaned.csv`)*

### 3. Review Leads
Run the interactive review CLI in [scripts/reviewer.py](file:///home/panemiko/Documentos/Haumea/system/scripts/reviewer.py):
```bash
python haumea review <cleaned_file.csv> [options]
```
- **Options**:
  - `-s, --screenshot-dir`: Folder to place screenshots. *(Defaults to `screenshots/` next to the input CSV)*

> [!TIP]
> During interactive review, you will be prompted for comments for each business. Type your feedback and press `Enter` to save and proceed to the next item, or use one of the special commands:
> - `<Enter>` (empty) to skip for now.
> - `skip` to log "skipped" in observations.
> - `goto <number>` to jump to a specific record.
> - `remove` / `del` to delete the record.
> - `open` to reopen links.
> - `exit` / `quit` to exit saving progress.

### 4. Register Payload (POST)
Once your leads are qualified and converted (see [prompts/convert.md](file:///home/panemiko/Documentos/Haumea/system/prompts/convert.md)), create them in the Antessala CRM through API v1:
```bash
python haumea register <json_file.json>
```

The leads are sent in idempotent batches (deterministic `id`), so re-running the same file skips what already exists. Useful options:

```bash
# Simular sem gravar
python haumea register leads.json --dry-run

# Carga de teste com 2 leads demarcados para exclusão posterior
python haumea register leads.json --limit 2 --marker "TESTE HAUMEA"

# Conferir duplicados depois da carga (exige token com leitura)
python haumea register leads.json --check-duplicates
```

Configure o acesso no `.env` da raiz:
```
ANTESSALA_API_URL="https://antessala.panemiko.com"
ANTESSALA_TOKEN="crm_..."
```

---

## 📂 Project Structure

- **[haumea](file:///home/panemiko/Documentos/Haumea/system/haumea)**: Main python-based CLI entry point.
- **[google_maps_scraper-1.3.0-linux-amd64](file:///home/panemiko/Documentos/Haumea/system/google_maps_scraper-1.3.0-linux-amd64)**: Pre-compiled scraper binary.
- **[scripts/](file:///home/panemiko/Documentos/Haumea/system/scripts)**: Pipeline business logic modules.
- **[prompts/](file:///home/panemiko/Documentos/Haumea/system/prompts)**: Conversion & classification prompts.
- **[GEMINI.md](file:///home/panemiko/Documentos/Haumea/system/GEMINI.md)**: Developer documentation.
