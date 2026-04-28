# =============================================================================
# frontend/Dockerfile
# Multi-stage build:
#   Stage 1 (builder) — Node.js: install deps + compile TypeScript + Vite build
#   Stage 2 (runtime) — nginx:alpine: serve static assets, proxy /agent/*
# =============================================================================

# ---- Stage 1: build ----
FROM node:20-alpine AS builder
WORKDIR /app

# Copy manifests first for better layer caching — npm ci only re-runs when
# package-lock.json changes, not on every source file edit.
COPY package*.json ./
RUN npm ci --registry=https://registry.npmmirror.com

# Copy source and run the full production build (tsc -b && vite build)
COPY . .
RUN npm run build

# ---- Stage 2: runtime ----
FROM nginx:alpine

# Copy Vite output (HTML/JS/CSS/assets) into the nginx document root
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default nginx virtual host config with our custom one that:
#  - handles SPA routing (try_files fallback)
#  - proxies /agent/* to the backend container
#  - disables buffering for SSE streams
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# nginx runs in the foreground by default with the official image
