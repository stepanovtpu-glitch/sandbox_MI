# Windows portable build

This project can be packaged for alpha testers who do not have Python, Node.js,
Tesseract, or Poppler installed.

## Build machine requirements

The build machine must have:

- Windows
- Node.js with npm
- backend virtual environment in `backend/.venv`
- Tesseract installed in `C:\Program Files\Tesseract-OCR`
- Poppler `pdftoppm.exe`; set `POPPLER_BIN` if it is not in the Codex runtime cache

End users do not need these tools. They are copied into the portable release.

## Build command

```powershell
.\scripts\build_windows_portable.ps1
```

The output folder is:

```text
release\GasMeterPro
```

Give testers the whole `GasMeterPro` folder as a ZIP archive.

## Running on a tester PC

The tester runs:

```text
start-gasmeter.bat
```

The app opens in the browser at:

```text
http://127.0.0.1:8000/
```

All user data is stored in:

```text
GasMeterPro\data
```

Do not delete this folder if calculation history, uploaded PDFs, OCR results, or
edited MI cards must be preserved.
