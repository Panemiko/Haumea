# Haumea CLI System Documentation

Welcome to the **Haumea** workspace. This document provides a persistent reference for the project's purpose, organization, structure, workflow, and developer conventions.

---

## What is Haumea?

**Haumea** is a CLI-based automation tool and data processing pipeline designed to scrape, clean, review, and register Brazilian business lead data. Its primary application is to identify prospective clients for web design and modernization services (e.g., qualifying leads based on the quality/existence of their current websites).

---

## Project Structure & Organization

The system is structured as follows:

*   [`system/`](file:///home/panemiko/Documentos/Haumea/system) (Project Root)
    *   [`haumea`](file:///home/panemiko/Documentos/Haumea/system/haumea) - The main CLI entry point. It defines command line arguments, handles commands/subcommands, and coordinates the scripts.
    *   [`google_maps_scraper-1.3.0-linux-amd64`](file:///home/panemiko/Documentos/Haumea/system/google_maps_scraper-1.3.0-linux-amd64) - Pre-compiled Google Maps scraper binary used to search for leads and extract basic information.
    *   [`scripts/`](file:///home/panemiko/Documentos/Haumea/system/scripts) - Python modules containing the business logic for each stage:
        *   [`scripts/__init__.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/__init__.py) - Python package initializer.
        *   [`scripts/scraper.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/scraper.py) - Wrapper for executing the Google Maps scraper binary.
        *   [`scripts/cleaner.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/cleaner.py) - Logic for cleaning raw scraped CSVs, extracting fields, and normalizing Brazilian states/cities.
        *   [`scripts/reviewer.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/reviewer.py) - Interactive CLI tool for website reviews, opening URLs in Chrome/Chromium, capturing feedback, and assigning qualification scores.
        *   [`scripts/viewer.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/viewer.py) - A PySide6-based helper application to display screenshots on secondary monitors or center them nicely.
        *   [`scripts/register.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/register.py) - Converts qualified leads to the Antessala CRM (API v1) and sends them in idempotent batches.
        *   [`scripts/utils.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/utils.py) - Utility helper functions (e.g., filename sanitization).
    *   [`prompts/`](file:///home/panemiko/Documentos/Haumea/system/prompts) - System prompts and LLM instruction resources:
        *   [`prompts/convert.md`](file:///home/panemiko/Documentos/Haumea/system/prompts/convert.md) - System prompt specifying rules for converting cleaned CSV leads into standardized JSON, including Brazilian phone formatting, market categorization, and a website qualification rubric.

---

## Core Pipeline Workflow

The general pipeline operates in four major phases:

1.  **Scrape**: Run the precompiled Go binary ([`google_maps_scraper-1.3.0-linux-amd64`](file:///home/panemiko/Documentos/Haumea/system/google_maps_scraper-1.3.0-linux-amd64)) via [`scripts/scraper.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/scraper.py) using the `scrape` subcommand.
2.  **Clean**: Keep specific CSV fields (`title`, `category`, `address`, `website`, `phone`, `emails`), parse the city and state, and format Brazilian phone numbers. This is run via [`scripts/cleaner.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/cleaner.py) using the `clean` subcommand.
3.  **Review**: Interactively evaluate the leads' websites, capture screenshots, compile observations, and assign qualification scores (1 to 5) indicating the likelihood of selling a website redesign. This is handled via [`scripts/reviewer.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/reviewer.py) using the `review` subcommand.
4.  **Register**: Create the qualified leads in the Antessala CRM (API v1) using [`scripts/register.py`](file:///home/panemiko/Documentos/Haumea/system/scripts/register.py) via the `register` subcommand.

Alternatively, the pipeline can be run end-to-end (Clean & Review) with the default command:
```bash
python haumea <input_file>
```

---

## Developer Conventions

To maintain a clean and reliable codebase, developers must adhere to the following conventions:

### 1. Python Compiled Folders Cleanup
Python generates compiled bytecode files and folders during execution and testing. To keep the workspace clean and avoid committing compiled artifacts, **developers must delete compiled Python folders after testing is complete.**

Use the following commands or clean-up tasks:
*   **Remove all `__pycache__` directories:**
    ```bash
    find . -type d -name "__pycache__" -exec rm -rf {} +
    ```
*   **Remove all compiled bytecode files (`.pyc`, `.pyo`, `.pyd`):**
    ```bash
    find . -type f -name "*.py[co]" -delete
    find . -type f -name "*.pyd" -delete
    ```
*   **Unified one-liner clean command:**
    ```bash
    find . -type d -name "__pycache__" -exec rm -rf {} + -o -type f -name "*.py[cod]" -delete
    ```

Ensure these commands are run before committing changes or after finalizing local manual testing.

### 2. File and Folder Referencing
When documenting or describing code inside markdown files in this repository, always create clickable links referencing the files/folders using the standard `file://` absolute URI scheme.

### 3. Localization and Formatting
Since this project targets Brazilian business leads, ensure all data parsers respect:
*   Brazilian 2-letter uppercase State Abbreviations (UF) (e.g., `SP`, `RJ`, `RS`).
*   Brazilian phone format rules (e.g., `(XX) 9XXXX-XXXX` for mobile, `(XX) XXXX-XXXX` for landlines).
*   Correct character encoding handling (fallbacks for `utf-8`, `utf-8-sig`, and `latin-1`).
