FROM python:3.8-slim-buster

RUN apt update

# GCC and other essentials
RUN apt install -y libpq-dev \
    build-essential \
    gnupg2 \
    procps

# Networking tools
RUN apt install -y \
	traceroute \
	lsb-release \
	wget \
	curl \
	iputils-ping \
	bridge-utils \
	dnsutils \
	netcat-openbsd \
	jq \
	redis \
	nmap \
	net-tools \
    	&& rm -rf /var/lib/apt/lists/*

# ffmpeg
RUN apt update
RUN apt install -y ffmpeg

# psql
RUN echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list | sh
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN apt update
RUN apt install -y postgresql-client

WORKDIR /usr/bin/cctv

COPY . .

RUN pip install -r requirements.txt
RUN chmod u+x entrypoint.sh
RUN chmod u+x dev-entrypoint.sh
RUN chmod u+x jobs/build_container_image.sh
RUN chmod u+x jobs/deploy_all_services.sh

EXPOSE 7000

ENTRYPOINT ["./entrypoint.sh"]