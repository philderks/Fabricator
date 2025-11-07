# Fabricator

A minimal Flask + Vue 3 project for managing a personal Minecraft server.

## Project Structure

```
Fabricator/
├── app.py                  # Flask REST API server
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore rules
├── frontend/              # Vue 3 frontend application
│   ├── src/
│   │   ├── main.js        # Vue app entry point
│   │   ├── App.vue        # Root component
│   │   ├── style.css      # Global styles
│   │   └── components/
│   │       └── ServerStatus.vue  # Server status component
│   ├── public/            # Static assets
│   ├── index.html         # HTML entry point
│   ├── vite.config.js     # Vite configuration (includes API proxy)
│   └── package.json       # Node.js dependencies
└── README.md              # This file
```

## Features

- **Flask Backend**: Lightweight REST API server with CORS support
- **Vue 3 Frontend**: Modern Vue 3 with Composition API
- **Vite Build Tool**: Fast development server with HMR
- **API Proxy**: Vite dev server proxies `/api/*` requests to Flask backend
- **Example Endpoint**: `/api/status` returns server status in JSON format

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Node.js 18 or higher
- npm or yarn

### Backend Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the Flask development server:
   ```bash
   python app.py
   ```

   The API will be available at `http://localhost:5000`

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```

   The frontend will be available at `http://localhost:3000`

### Running Both Servers

You need to run both servers simultaneously in separate terminal windows:

**Terminal 1 (Backend):**
```bash
python app.py
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```

Then open your browser to `http://localhost:3000` to see the application.

## Production Build

### Build Frontend

```bash
cd frontend
npm run build
```

This creates an optimized production build in `frontend/dist/`

### Preview Production Build

```bash
cd frontend
npm run preview
```

## API Endpoints

### `GET /api/status`

Returns the current status of the Minecraft server.

**Response:**
```json
{
  "status": "offline",
  "message": "Minecraft server manager is ready",
  "version": "1.0.0"
}
```

### `GET /api/health`

Health check endpoint.

**Response:**
```json
{
  "healthy": true
}
```

## Expanding the Project

This is a minimal scaffold ready to be expanded. Here are some ideas:

1. **Add server control endpoints**: Start, stop, restart the Minecraft server
2. **Server properties management**: Edit server.properties file
3. **Player management**: Whitelist, ban, op players
4. **Log viewing**: Stream and display server logs
5. **Backup management**: Create and restore server backups
6. **Resource monitoring**: CPU, memory, disk usage
7. **Authentication**: Add user login and session management

## Technologies Used

- **Backend**: Flask 3.0, Flask-CORS
- **Frontend**: Vue 3, Vite 5
- **Language**: Python 3, JavaScript (ES6+)