# Auto ID3 Tagger

This script automatically identifies MP3 files in a directory (recursively) and updates their ID3 tags with accurate metadata.

## Features

*   **Recursively Scans Directories**: Processes all MP3 files in the given folder and its subfolders.
*   **Multiple Recognition Providers**:
    *   **Shazam**: Primary recognition method (fast, accurate).
    *   **AcoustID**: Fallback method using audio fingerprinting (requires free API key).
*   **Enhanced Metadata**: Uses **MusicBrainz** to fetch standardized metadata (Correct Album, Release Year, Genre) after initial identification.
*   **Automatic Tagging**: Updates Artist, Title, Album, Year, Genre, and Cover Art.
*   **Corrupted Tag Fixer**: Automatically detects and fixes corrupted ID3 headers (e.g., UTF-16 surrogate errors) that crash standard libraries.

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
    pip install musicbrainzngs pyacoustid
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

## Troubleshooting

### "RuntimeWarning: Couldn't find ffmpeg or avconv"
Ensure FFmpeg is installed and added to your system PATH. Restart your terminal after installing.

### "UnicodeDecodeError: 'utf-16-le' codec can't decode..."
The script includes a fix for this. It will automatically detect the corrupted tag, strip the bad header, and retry processing the file.