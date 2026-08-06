FROM docker.m.daocloud.io/library/node:22-alpine AS builder

ARG FRONTEND_ENV_FILE=script/docker/frontend.env.production
ARG INTRANET_APP_ORIGIN

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"
ENV NODE_OPTIONS=--max-old-space-size=8192
ENV TZ=Asia/Shanghai
ENV CI=true
ENV HTTP_PROXY=
ENV HTTPS_PROXY=
ENV ALL_PROXY=
ENV http_proxy=
ENV https_proxy=
ENV all_proxy=

RUN corepack enable

WORKDIR /build

COPY yudao-ui/yudao-ui-admin-vben-temp/ /build/
COPY ${FRONTEND_ENV_FILE} /build/apps/web-antd/.env.production
COPY script/docker/patch-form-designer-offline.mjs /build/patch-form-designer-offline.mjs

RUN --mount=type=cache,id=pnpm,target=/pnpm/store env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy pnpm install --frozen-lockfile
RUN INTRANET_APP_ORIGIN=${INTRANET_APP_ORIGIN} node /build/patch-form-designer-offline.mjs
RUN env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy pnpm --filter @vben/web-antd run build

FROM docker.m.daocloud.io/library/nginx:1.27-alpine

COPY script/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/apps/web-antd/dist/ /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
