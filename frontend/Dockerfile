FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Firebase web configuration must be present at BUILD time, not run time:
# Vite inlines `import.meta.env.*` into the bundle when it compiles, so a value
# supplied only to the running container arrives far too late and every field
# is baked in as `undefined`.
#
# These are public client identifiers, not credentials — they name the Firebase
# project to Google and grant nothing on their own, and the VAPID key here is
# the public half of the pair. The service account that can actually *send* a
# notification stays on the backend and never reaches a browser.
#
# `frontend/.env` is deliberately still excluded by .dockerignore: baking in
# whatever happens to sit on the build machine is how an image ends up carrying
# a value nobody intended. The values arrive as explicit build args instead.
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_MESSAGING_SENDER_ID
ARG VITE_FIREBASE_APP_ID
ARG VITE_FIREBASE_VAPID_KEY
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY     VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN     VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID     VITE_FIREBASE_MESSAGING_SENDER_ID=$VITE_FIREBASE_MESSAGING_SENDER_ID     VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID     VITE_FIREBASE_VAPID_KEY=$VITE_FIREBASE_VAPID_KEY

RUN npm run build

FROM nginx:1.27-alpine
ENV PORT=80
ENV NGINX_ENVSUBST_FILTER=PORT
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
