FROM python:3.7

RUN apt-get update -y && apt-get install --no-install-recommends -y -q build-essential python3 python3-dev python3-pip git libpq-dev
WORKDIR /src
COPY ./requirements.txt /src/requirements.txt
RUN pip install -r /src/requirements.txt
COPY . /src
EXPOSE 6000
RUN chown -R nobody:nogroup /src
RUN chmod +x /src/docker-entrypoint.sh
USER nobody
CMD ["/src/docker-entrypoint.sh"]
