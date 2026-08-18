FROM docker.m.daocloud.io/library/eclipse-temurin:17-jre

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY yudao-server/target/yudao-server.jar /app/app.jar

ENV TZ=Asia/Shanghai
ENV LIBREOFFICE_BIN="/usr/bin/soffice"
ENV JAVA_OPTS="-Xms512m -Xmx1024m -Djava.security.egd=file:/dev/./urandom"
ENV ARGS="--yudao.party-file.preview.libreoffice-path=/usr/bin/soffice"

EXPOSE 48080

CMD ["sh", "-c", "java ${JAVA_OPTS} -jar /app/app.jar --spring.profiles.active=${SPRING_PROFILES_ACTIVE:-local} ${ARGS}"]
