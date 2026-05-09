cd# Fantasy Football Analytics Platform

This is a comprehensive fantasy football application built with **React** (Frontend) and **Django** (Backend) using **MongoDB**.

## Prerequisites

1.  **Python 3.10+**
2.  **Node.js 18+**
3.  **MongoDB Community Edition** (Running on default port `27017`)

## Quick Start (Windows)

To start both the backend and frontend simultaneously, simply double-click the `run_app.bat` file in this directory.

---

## Manual Setup

### 1. Backend (Django)

The backend uses the virtual environment in `backend/venv`.

```bash
# Navigate to backend
cd backend

# Run Django with the project virtual environment
venv\Scripts\python.exe manage.py migrate

# Start server
venv\Scripts\python.exe manage.py runserver 8000
```

### 2. Frontend (React)

```bash
# Navigate to frontend
cd frontend

# Install dependencies (if not already done)
npm install

# Start development server
npm start
```

## Important Notes

- **CORS**: The backend is configured to allow requests from `localhost:3000`.
- **Database**: Ensure MongoDB is running before starting the backend.
- **Admin**: You can access the Django admin at `http://localhost:8000/admin/`.
