# ScreenWise 2.1 — iPhone Screen Time Intelligence

ScreenWise converts iPhone Screen Time screenshots into structured, auditable usage records using Microsoft Azure AI Vision OCR and deterministic parsing.

## Included

- Azure AI Vision OCR with OCR text, line confidence and source evidence.
- App-level duration extraction and an editable app-to-category map.
- Category-level usage extraction from the iPhone category panel.
- Pickup and notification extraction when visible.
- Automatic `sub-XXXXX` and `ses-XX` identification from filenames.
- Separate participant and session dashboards; participants are never combined into one usage table.
- Participant label, cohort and notes fields.
- Expandable image previews before analysis and within each result.
- OCR-content validation with the message **“Please upload a real iPhone Screen Time screenshot.”**
- Per-participant CSV exports and a complete JSON export.
- Original filenames, file hashes, OCR confidence, warnings and evidence retained.

## 1. Prepare the environment

Run these commands from the project directory:

```bash
cd ~/screenwise-2.0
source .screen/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If you do not have the `.screen` environment yet:

```bash
cd ~/screenwise-2.0
python3.11 -m venv .screen
source .screen/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 2. Configure Azure

Copy the example file:

```bash
cp .env.example .env
```

Edit `.env` and enter the endpoint and key from your Azure AI Vision resource:

```dotenv
AZURE_VISION_ENDPOINT=https://YOUR-RESOURCE.cognitiveservices.azure.com
AZURE_VISION_KEY=YOUR_AZURE_VISION_KEY
MAX_UPLOAD_MB=15
```

Never commit or share `.env`. The `.env.example` file contains placeholders only.

## 3. Run tests

```bash
python -m pytest -v
```

## 4. Launch the dashboard

Use the active environment's Python interpreter:

```bash
python -m streamlit run app.py
```

## Filename convention

The dashboard recognises BIDS-like participant/session identifiers:

```text
sub-00132_ses-01_task-screentime_run-01_screenshot.jpg
sub-00074_ses-02_task-screentime_run-03_screenshot.jpg
```

The participant and session identifiers are read from each filename. The sidebar's default IDs are used only if a filename does not contain them. Different participants can be uploaded in the same batch; the dashboard separates them.

## App category mapping

The mapping is maintained in:

`src/screenwise/extraction/screen_time_parser.py`

Examples:

- YouTube → Entertainment
- Netflix → Entertainment
- Instagram → Social
- WhatsApp → Social
- Facebook → Social
- Safari → Information & Reading
- Gmail → Productivity & Finance

Unknown apps are labelled `Unclassified`. Update `APP_CATEGORY_MAP` to add or change an app. The mapping is explicit; ScreenWise does not infer a category for an unknown app.

## Important interpretation notes

- Each screenshot is processed independently.
- Usage values from separate screenshots are not blindly added together because screenshots can show overlapping time periods or different Screen Time panels.
- The app chart uses the highest displayed value for duplicate app/category labels within the selected participant/session view. The source screenshot remains visible in the table.
- The iPhone category panel and the app-level category mapping are different data sources. App categories are attached by the explicit mapping; category totals are parsed from the screenshot's own category panel.
- OCR-content validation is a practical heuristic, not a forensic guarantee. A very blurry or cropped genuine screenshot may be rejected; review the OCR indicators and upload a clearer original.
- The application retains OCR text and source evidence to make extraction auditable. Do not upload screenshots containing information you are not authorised to process.

## Project layout

```text
screenwise-2.0/
├── app.py
├── pyproject.toml
├── requirements.txt
├── .env.example
├── src/screenwise/
│   ├── config.py
│   ├── metadata.py
│   ├── extraction/
│   │   ├── pipeline.py
│   │   └── screen_time_parser.py
│   ├── ingestion/
│   ├── ocr/
│   ├── providers/
│   └── schemas/
├── scripts/
└── tests/
```
