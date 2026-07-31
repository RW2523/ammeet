FROM node:22-alpine AS base

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
# NEXT_PUBLIC_* values are inlined at BUILD time — must arrive as build args.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=base /app/.next ./.next
COPY --from=base /app/node_modules ./node_modules
COPY --from=base /app/package.json ./
COPY --from=base /app/public ./public

EXPOSE 3000
CMD ["npm", "start"]
