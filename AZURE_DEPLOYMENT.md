# Azure Deployment Guide for CogniView.AI

This guide explains how to deploy CogniView.AI to Azure using your Azure credits.
The recommended architecture is:

- **Backend:** Azure App Service (Linux) running the FastAPI container
- **Frontend:** Azure Static Web Apps or Azure App Service (Linux) running the React container
- **Container registry:** Azure Container Registry (ACR)

## Prerequisites

- Azure account with credits
- Azure CLI installed and logged in
- Docker installed locally
- Git repository ready
- `.env` file in `src/` with required API keys

## Recommended architecture

### Option 1 — Best for production

- `backend` container deployed to **Azure App Service for Containers**
- `frontend` container deployed to **Azure Static Web Apps** or **Azure App Service for Containers**
- shared environment variables stored in App Service settings
- optional ACR for container storage

### Option 2 — Fastest path

- Deploy both frontend and backend as containers to separate Azure Web Apps
- This avoids static web app workflow complexity

## Step 1: Prepare the project

From the repository root:

```bash
cd C:\Users\ACER\Desktop\project\CogniView.AI
```

Install Python dependencies and build frontend locally to verify:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
npm install
npm run build
```

Verify the backend:

```bash
cd src
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Verify the frontend:

```bash
npm run dev
```

## Step 2: Create Azure resources

Login to Azure CLI:

```bash
az login
```

Create a resource group:

```bash
az group create --name cogniview-rg --location eastus
```

Create an Azure Container Registry:

```bash
az acr create --resource-group cogniview-rg --name cogniviewacr --sku Basic --admin-enabled true
```

## Step 3: Build and push containers to ACR

Login to ACR:

```bash
az acr login --name cogniviewacr
```

Build and push the backend image:

```bash
az acr build --registry cogniviewacr --image cogniview-backend:latest -f Dockerfile.backend .
```

Build and push the frontend image:

```bash
az acr build --registry cogniviewacr --image cogniview-frontend:latest -f Dockerfile.frontend .
```

## Step 4: Deploy the backend to Azure App Service

Create an App Service plan:

```bash
az appservice plan create --name cogniview-plan --resource-group cogniview-rg --is-linux --sku B1
```

Create the backend app:

```bash
az webapp create --resource-group cogniview-rg --plan cogniview-plan --name cogniview-backend --deployment-container-image-name cogniviewacr.azurecr.io/cogniview-backend:latest
```

Configure the backend app settings:

```bash
az webapp config appsettings set --resource-group cogniview-rg --name cogniview-backend --settings \
  WEBSITES_PORT=8000 \
  APP_NAME=CogniView.AI \
  APP_VERSION=9.0.0 \
  SERVICE_NAME=CogniView.AI \
  API_HOST=0.0.0.0 \
  API_PORT=8000 \
  CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,*
```

Add your application-specific secrets:

```bash
az webapp config appsettings set --resource-group cogniview-rg --name cogniview-backend --settings \
  OPENAI_API_KEY="<your_openai_api_key>" \
  SEMANTIC_SCHOLAR_API_KEY="<your_semantic_scholar_api_key>"
```

> Replace the secret names with the actual variables used by your app.

## Step 5: Deploy the frontend to Azure Static Web Apps (recommended)

### Create a Static Web App

Use Azure Static Web Apps with a GitHub workflow or manual build. The simplest route is to deploy from the repo using GitHub.

1. Push your repo to GitHub.
2. In the Azure Portal, create a new **Static Web App**.
3. Set:
   - build preset: `Custom`
   - app location: `/`
   - api location: `src` (optional if frontend only)
   - output location: `dist`
4. Configure environment variables if needed for API URL.

### Or deploy the frontend to Azure App Service container

If you prefer a container-based frontend app:

```bash
az webapp create --resource-group cogniview-rg --plan cogniview-plan --name cogniview-frontend --deployment-container-image-name cogniviewacr.azurecr.io/cogniview-frontend:latest
```

## Step 6: Configure CORS and frontend API URL

If the frontend and backend are separate, set the frontend to call the backend where it is hosted.

Example backend URL:

```text
https://cogniview-backend.azurewebsites.net
```

Set your CORS origin in the backend app settings to include the frontend URL.

## Optional: Use Azure Container Apps instead

If you want a single managed environment for both services, Azure Container Apps is a good choice. The process is similar:

- create a managed environment
- push images to ACR
- create two Container Apps (frontend and backend)
- set container image and env vars per app

## Useful Azure CLI commands

- Show App Service URLs:
  ```bash
  az webapp show --resource-group cogniview-rg --name cogniview-backend --query defaultHostName -o tsv
  ```
- Restart an app:
  ```bash
  az webapp restart --resource-group cogniview-rg --name cogniview-backend
  ```
- View logs:
  ```bash
  az webapp log tail --resource-group cogniview-rg --name cogniview-backend
  ```

## Notes and recommendations

- The backend uses heavy Python dependencies such as PyTorch and transformers, so choose a Linux App Service plan with enough memory.
- If App Service fails because of package size, use the container option so you control the runtime image.
- Keep the `.env` file local and never commit secret keys.
- Use Azure Key Vault later for stronger secret management.

## Quick access URLs

- Backend health/API: `https://<your-backend-name>.azurewebsites.net`
- Frontend site: the Static Web App URL or `https://<your-frontend-name>.azurewebsites.net`

## Summary

With Azure credits, the recommended deployment is:

1. Build and push Docker images to ACR
2. Deploy backend container to Azure App Service
3. Deploy frontend to Azure Static Web Apps or App Service
4. Configure app settings, CORS, and secrets

This gives you a scalable production deployment with separate backend and frontend services.
