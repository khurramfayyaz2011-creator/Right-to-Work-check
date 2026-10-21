# UK Right to Work Bulk Verification - Netlify & Cloud Deployment Guide

## 1. How the Architecture Works
* **Frontend (User Interface)**: Runs on **Netlify** (lightning-fast global CDN, HTTPS, custom domain support).
* **Backend API (Verification & Official PDF Engine)**: Runs on **Render**, **Railway**, **Fly.io**, or any standard Python server. 
  *(Why? Netlify Serverless Functions have a strict 10s timeout and cannot run headless Chromium for 200+ staff. A dedicated free container on Render/Railway runs unlimited parallel checks and generates authentic Home Office PDFs without timeouts.)*

---

## 2. Deploy Frontend to Netlify (Takes 1 Minute)

### Option A: Drag & Drop (Zero Setup)
1. Go to [https://app.netlify.com/drop](https://app.netlify.com/drop).
2. Drag and drop the `public` folder from this repository into the Netlify Drop area.
3. Your web app is instantly live at `https://<your-site-name>.netlify.app`!
4. Click **`⚙️ API Settings`** in the top navigation bar to point to your live Python backend (or localhost).

### Option B: Connect via GitHub
1. Push this project to GitHub.
2. In Netlify, click **"Add new site"** -> **"Import an existing project"** -> select your GitHub repo.
3. Settings:
   - **Publish directory**: `public`
   - **Build command**: *(leave blank)*
4. Click **Deploy**.

---

## 3. Deploy Backend API (Render / Railway - 100% Free)

### Option 1: Free Render Deployment (Recommended)
1. Sign up for free at [https://render.com](https://render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository.
4. Select **Docker** environment (Render automatically detects the included `Dockerfile` with Chromium).
5. Choose the **Free** instance type.
6. Click **Create Web Service**.
7. Once deployed, copy your backend URL (e.g., `https://uk-rtw-service.onrender.com`).
8. Paste this URL into `netlify.toml` in your repository:
   ```toml
   [[redirects]]
     from = "/api/*"
     to = "https://uk-rtw-service.onrender.com/api/:splat"
     status = 200
     force = true
   ```
   Or click **`⚙️ API Settings`** on your Netlify frontend and paste the URL.

---

## 4. Local Testing
To run locally:
```bash
python rtw_app.py
```
Open `http://127.0.0.1:5000` in your browser.
