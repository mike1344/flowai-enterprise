FROM node:24-alpine AS build

# 镜像源可通过构建参数覆盖（网络不稳定时用镜像站）
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --registry "${NPM_REGISTRY}"
COPY . .
RUN npm run build

FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80