# Fabricator

Fabricator is a desktop-style web application with a Flask backend and a Vue 3 frontend. The backend serves the compiled frontend so users only start one process in production. Windows users can wrap the app with a tray launcher, and Linux users can install it as a systemd service.

## Project Structure
```
Fabricator/
├── backend/
│   └── fabricator_backend/
│       ├── __init__.py            # Flask app factory and SPA serving
│       ├── __main__.py            # Entrypoint: python -m fabricator_backend
│       ├── api/                   # Example API routes
│       └── frontend_dist/         # Built Vue assets copied here
├── frontend/                      # Vue 3 application (Vite)
├── tools/
│   ├── fabricator_launcher.py     # Windows tray launcher
│   └── install.sh                 # Linux install script (systemd)
├── Makefile                       # Build helper for frontend assets
├── requirements.txt               # Python dependencies
└── README.md
```

## Development

### Backend
```bash
cd backend
python -m fabricator_backend
```
The server listens on `http://127.0.0.1:8000` and serves API routes under `/api`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The Vite dev server proxies API requests to `http://localhost:8000`.

## Production Build
1. Build the frontend and copy assets into the backend package:
   ```bash
   make build-frontend
   ```
2. Start only the backend (serves both API and SPA):
   ```bash
   cd backend
   python -m fabricator_backend
   ```
3. Open `http://127.0.0.1:8000` in your browser.

## Windows Tray Launcher
- Script: `tools/fabricator_launcher.py`
- PyInstaller example:
  ```bash
  pyinstaller --onefile --noconsole --icon=fabricator_icon.ico tools/fabricator_launcher.py
  ```
- The resulting executable starts the backend, opens the UI, shows a tray icon with **Open Fabricator** and **Quit** actions, and shuts down the backend when exiting.

## Linux Install Script (systemd)
Run the installer as root (or via sudo):
```bash
bash tools/install.sh
```
The script copies the project into `/opt/fabricator`, creates a virtual environment, installs dependencies, writes `/etc/systemd/system/fabricator.service`, and enables the service so Fabricator runs on boot at `http://127.0.0.1:8000`.

## Notes
- The backend serves built frontend files from `backend/fabricator_backend/frontend_dist`. Rebuild and copy assets after frontend changes.
- Keep dependencies minimal; only Flask/CORS and tray icon requirements are included in `requirements.txt`.
