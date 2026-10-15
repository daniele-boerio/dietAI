# ── Stage 1: build ──
# Node 24, come in sviluppo: il lockfile lo scrive npm 11, e npm 10 (quello di
# node:20) non lo riconosce allineato — `npm ci` si fermava sulle dipendenze
# opzionali di vite 8 (esbuild, emnapi). Node 20 è comunque fuori supporto.
FROM node:24-alpine AS build

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
