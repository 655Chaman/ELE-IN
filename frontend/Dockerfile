# PARANOIA FRAMEWORK: NEVER COPY .env INTO THIS IMAGE. NEVER HARDCODE SECRETS AS ENV INSTRUCTIONS. ALL SECRETS ARE INJECTED AT RUNTIME VIA CONTAINER ORCHESTRATION (K8s Secrets, Docker Compose environment).

# --- Builder Stage ---
FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

COPY package*.json ./
# Install dependencies for build
RUN npm ci

COPY index.html vite.config.ts tsconfig*.json ./
# Copy all module directories
COPY core/ core/
COPY accounts/ accounts/
COPY campaigns/ campaigns/
COPY dashboard/ dashboard/
COPY inbox/ inbox/
COPY integrations/ integrations/
COPY knowledge/ knowledge/
COPY leads/ leads/
COPY frontend/tailwind.config.js frontend/components.json ./

# Build the SPA
RUN npm run build

# Run npm ci --omit=dev as requested by Paranoia Framework (even if node_modules won't be copied)
RUN rm -rf node_modules && npm ci --omit=dev

# --- Runtime Stage ---
FROM nginx:alpine AS runtime

# Never copy node_modules or .env into the final image (multi-stage achieves this)
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# HEALTHCHECK instruction to ensure critical env vars (like proxy setup if any) or just general health
# NGINX just needs to be up. Since it's static files, we'll check localhost.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
