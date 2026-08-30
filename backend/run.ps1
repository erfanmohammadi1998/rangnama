# اجرای سرور توسعه — ویندوز / PowerShell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "محیط مجازی پیدا نشد. اول این را اجرا کن:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

& $py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
