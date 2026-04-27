FROM python:3.7

RUN apt-get update -y && apt-get install --no-install-recommends -y -q build-essential python3 python3-dev python3-pip git libpq-dev dos2unix
WORKDIR /src
COPY ./requirements.txt /src/requirements.txt
RUN pip install -r /src/requirements.txt
COPY . /src
# Convert line endings to Unix format and make executable
RUN dos2unix /src/docker-entrypoint.sh && chmod +x /src/docker-entrypoint.sh
EXPOSE 9000
RUN chown -R nobody:nogroup /src
USER nobody
CMD ["/src/docker-entrypoint.sh"]
