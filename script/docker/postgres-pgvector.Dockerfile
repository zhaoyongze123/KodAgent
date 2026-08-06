FROM docker.m.daocloud.io/library/postgres:16-alpine

RUN apk add --no-cache --virtual .pgvector-build-deps \
      git build-base clang llvm postgresql16-dev \
    && git clone --depth 1 --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && ln -sf "$(command -v clang)" /usr/local/bin/clang-21 \
    && mkdir -p /usr/lib/llvm21/bin \
    && ln -sf "$(command -v llvm-lto)" /usr/lib/llvm21/bin/llvm-lto \
    && make -C /tmp/pgvector OPTFLAGS="" \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector \
    && apk del .pgvector-build-deps
