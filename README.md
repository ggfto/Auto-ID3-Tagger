# Auto ID3 Tagger

This tool automatically identifies MP3, M4A and WMA files in a directory (recursively) and updates their tags with accurate metadata.

## Features

*   **Recursively Scans Directories**: Processes all supported files in the given folder and its subfolders.
*   **Parallel, With a Limit**: Each file runs in its own thread, up to `--workers` (default 4). A file waiting to retry does not hold a thread, so the queue keeps moving.
*   **Multiple Recognition Providers**:
    *   **Shazam**: Primary recognition method (fast, accurate).
    *   **AcoustID**: Fallback method using audio fingerprinting (requires free API key).
*   **Reliable Album and Year**: Uses **MusicBrainz** when it has an earlier official studio album of exactly that artist and title, or a better year for the same album. Remixes, live versions and similar recordings keep the release that was identified.
*   **Automatic Tagging**: Updates Artist, Title, Album, Year, Genre, and Cover Art. Fields without a new value keep what the file already has, and a file with nothing to change is not written.
*   **Keeps What the File Knows**: The version in the file name, such as `(Extended Mix)`, stays in the title, and current spelling stays when it says the same words (`Sérgio`, not `Sergio`).
*   **Safe by Default**: A file is left unchanged when the identification differs from its name (or its current tags, if the name says nothing useful). It is listed as `review` in the report.
*   **Backup and Restore**: The original tags are saved before the first change to a file, and `--restore` puts them back.
*   **Review**: `--review` walks through the files that need a decision.
*   **Resumable**: A new run skips files already processed and retries the ones that had errors. A failed file is tried up to 5 times, with growing waits, and the run stops after 10 files in a row end in error.
*   **OneDrive Aware**: Cloud-only files are returned to cloud-only after being processed.
*   **Corrupted Tag Fixer**: Automatically detects and fixes corrupted ID3 headers (e.g., UTF-16 surrogate errors) that crash standard libraries.

## Report and Backups

Each run appends to `.autotag/report.csv` (next to the script, or under `--state-dir`), separated by `;` and readable in Excel. The original tags are kept in `.autotag/backups`, so keep this folder until you are happy with the result.

| Status | Meaning |
|---|---|
| `tagged` | Identification agrees with the file name (or current tags, if the name says nothing useful); the file was updated. |
| `tagged_no_reference` | The file had no useful name or tags to compare with; it was updated. |
| `tagged_from_name` | In the review, artist and title were taken from the file name, and the old album, year and cover were removed unless MusicBrainz knows the recording. |
| `unchanged` | The file already had the right values; it was not written. |
| `review` | Identification differs from that reference; the file was not changed and waits for a decision. |
| `rejected` | In the review, the identification was rejected; the file was not changed. |
| `unidentified` | No match; the file was not changed. |
| `error` | Something failed; the next run tries the file again. |
| `restored` | Original tags were put back; the next run processes the file again. |

To decide the files waiting for review (you can quit and continue later):
```powershell
python id_song.py "C:\Path\To\Your\Music" --review
```

To undo the changes under a folder:
```powershell
python id_song.py "C:\Path\To\Your\Music" --restore
```

## Prerequisites

1.  **Python 3.12+** (Tested on Python 3.12.10)
2.  **FFmpeg**: Required for audio processing.
    ```powershell
    winget install -e --id Gyan.FFmpeg
    ```
3.  **Chromaprint (fpcalc)**: Required for AcoustID fingerprinting.
    ```powershell
    winget install -e --id ACOUSTID.fpcalc
    ```

## Installation

1.  **Clone the repository**:
    ```powershell
    git clone https://github.com/ggfto/Auto-ID3-Tagger.git
    cd Auto-ID3-Tagger
    ```

2.  **Create a Virtual Environment**:
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate
    ```

3.  **Install Python Dependencies**:
    ```powershell
    pip install -r requirements.txt
    ```

## Usage

Activate your virtual environment (if not already active):
```powershell
.\venv\Scripts\Activate
```

Run the script by providing the path to your music folder:

**Basic Usage (Shazam + MusicBrainz)**:
```powershell
python id_song.py "C:\Path\To\Your\Music"
```

**Advanced Usage (With AcoustID Fallback)**:
Obtain a free API Key from [AcoustID.org](https://acoustid.org/) and run:
```powershell
python id_song.py "C:\Path\To\Your\Music" --acoustid-key "YOUR_API_KEY"
```

**More or fewer files at the same time**:
```powershell
python id_song.py "C:\Path\To\Your\Music" --workers 8
```
MusicBrainz allows one request per second across all threads, so more threads stop helping after a point.

## Development

```powershell
pip install -r requirements-dev.txt
python -m pytest tests
```

## Troubleshooting

### "RuntimeWarning: Couldn't find ffmpeg or avconv"
Ensure FFmpeg is installed and added to your system PATH. Restart your terminal after installing.

### "UnicodeDecodeError: 'utf-16-le' codec can't decode..."
The script includes a fix for this. It will automatically detect the corrupted tag, strip the bad header, and retry processing the file.