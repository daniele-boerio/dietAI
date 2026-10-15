# ── Stage 1: build ──
FROM node:20-alpine AS build

WORKDIR /app

# Il lockfile entra nell'immagine e `npm ci` installa esattamente quello: con il solo
# package.json ogni build risolveva le versioni da capo, e una release nuova di una
# dipendenza (vite 8 / rolldown, sotto vitest) ha fatto fallire un deploy che il
# giorno prima passava senza che il codice c'entrasse.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: serve ──
FROM nginx:alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
