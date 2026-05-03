# Deployment Guide for CogniView.AI

This guide provides instructions for deploying the CogniView.AI platform, a full-stack AI-powered research paper discovery and analysis application built with FastAPI (Python backend) and React (frontend).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development Deployment](#local-development-deployment)
- [Production Deployment Options](#production-deployment-options)
  - [Docker Containerization](#docker-containerization)
  - [Cloud Platforms](#cloud-platforms)
- [Environment Configuration](#environment-configuration)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying, ensure you have:

- Python 3.10+
- Node.js 18+
- Git
- Docker (for containerized deployment)
- API keys for external services (see Environment Configuration)

## Local Development Deployment

### Backend Setup

1. **Clone the repository and navigate to the project directory:**

   ```bash
   git clone <repository-url>
   cd CogniView.AI
   ```

2. **Set up Python virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

4. **Configure environment variables:**
   Create a `.env` file in the `src/` directory with required API keys (see Environment Configuration section).

5. **Start the FastAPI backend:**
   ```bash
   cd src
   uvicorn api:app --host 0.0.0.0 --port 8000 --reload
   ```
   The API will be available at `http://localhost:8000`.

### Frontend Setup

1. **Install Node.js dependencies:**

   ```bash
   npm install
   ```

2. **Start the development server:**
   ```bash
   npm run dev
   ```
   The frontend will be available at `http://localhost:5173`.

### Accessing the Application

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs` (Swagger UI)

## Production Deployment Options

### Docker Containerization

For containerized deployment, we'll create separate containers for the backend and frontend.

#### Backend Dockerfile

Create `Dockerfile.backend` in the root directory:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY src/ .

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Frontend Dockerfile

Create `Dockerfile.frontend` in the root directory:

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

EXPOSE 80

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "80"]
```

#### Docker Compose

Create `docker-compose.yml` in the root directory:

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - '8000:8000'
    env_file:
      - src/.env
    volumes:
      - ./src/downloaded_pdfs:/app/downloaded_pdfs

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - '80:80'
    depends_on:
      - backend
```

#### Deploy with Docker Compose

```bash
docker-compose up --build
```

The application will be available at `http://localhost`.

### Cloud Platforms

#### Backend Deployment

**Option 1: Railway**

1. Connect your GitHub repository to Railway
2. Set environment variables in Railway dashboard
3. Deploy automatically

**Option 2: Render**

1. Create a new Web Service
2. Connect your repository
3. Set build command: `pip install -r requirements.txt && python -m spacy download en_core_web_sm`
4. Set start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`

**Option 3: Heroku**

1. Create a `Procfile`:
   ```
   web: uvicorn api:app --host 0.0.0.0 --port $PORT
   ```
2. Deploy via Heroku CLI or GitHub integration

#### Frontend Deployment

**Option 1: Vercel**

1. Connect your repository to Vercel
2. Set build command: `npm run build`
3. Deploy automatically

**Option 2: Netlify**

1. Connect your repository
2. Set build command: `npm run build`
3. Set publish directory: `dist`

## Environment Configuration

Create a `.env` file in the `src/` directory with the following variables:

```env
# Application Settings
APP_NAME=CogniView.AI
APP_VERSION=9.0.0
SERVICE_NAME=CogniView.AI
API_HOST=0.0.0.0
API_PORT=8000
CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,*

# API Keys (required for full functionality)
OPENAI_API_KEY=your_openai_api_key
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key
# Add other required API keys based on your implementation
```

## Troubleshooting

### Common Issues

1. **Port conflicts:** Ensure ports 8000 (backend) and 5173/80 (frontend) are available.

2. **API key errors:** Verify all required API keys are set in the `.env` file.

3. **spaCy model not found:** Run `python -m spacy download en_core_web_sm` after installing dependencies.

4. **CORS errors:** Check the `CORS_ALLOW_ORIGINS` setting in your `.env` file.

5. **Memory issues:** The application processes PDFs and runs ML models; ensure sufficient RAM (at least 4GB recommended).

### Performance Optimization

- For production, consider using Gunicorn instead of Uvicorn for the backend
- Enable caching for API responses
- Use a CDN for static assets
- Monitor resource usage and scale accordingly

### Security Considerations

- Never commit `.env` files to version control
- Use HTTPS in production
- Implement rate limiting for API endpoints
- Regularly update dependencies for security patches

For additional support, refer to the main README.md or open an issue in the repository.
