# ---------- Frontend image: build the SPA, serve with nginx ----------
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend /app
RUN npm run build


FROM nginx:1.27-alpine AS runtime

# Static SPA + /api reverse proxy configuration
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
