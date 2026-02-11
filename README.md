# cezmi-bot

## Windows virtual environment quick fix

The error below means your `.venv` was created with a different Python path and is now invalid:

- `did not find executable at 'C:\Users\Ryuq\...\python.exe'`

Also, this PowerShell error is an execution-policy restriction:

- `Activate.ps1 cannot be loaded because running scripts is disabled`

### One-time recovery (PowerShell)

Run these commands in the project root:

```powershell
# Optional: allow scripts only for this PowerShell session
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Remove broken environment
Remove-Item -Recurse -Force .venv

# Create a new local environment with your installed Python
py -3 -m venv .venv

# Install/upgrade pip and dependencies
.\.venv\Scripts\python.exe -m pip install --upgrade pip
if (Test-Path .\requirements.txt) {
    .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
}

# Run app without activation
.\.venv\Scripts\python.exe .\app.py
```

> You do **not** need to run `Activate.ps1` to start the app.

## Easier startup on Windows

Use the included batch file:

```bat
run.bat
```

`run.bat` will:

1. create `.venv` if missing,
2. recreate `.venv` if it is broken/moved from another machine,
3. install `requirements.txt` if present,
4. run `app.py` using `.venv\Scripts\python.exe`.