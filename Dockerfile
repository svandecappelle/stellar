# Python 3.12 : la suite passe aussi sur 3.11 et 3.13, cette version est le
# milieu sur, et celle que teste l'integration continue en priorite.
#
# L'image etait sur 3.7, hors support depuis juin 2023.
FROM python:3.12-slim

# Plus de chaine de compilation : `psycopg2-binary` apporte son pilote deja
# compile. L'ancienne image installait build-essential, python3-dev et
# libpq-dev — plusieurs centaines de megaoctets — pour construire `psycopg2`
# depuis ses sources a chaque assemblage. C'est aussi ce qui cassait des que
# les en-tetes PostgreSQL de la machine avancaient.
RUN apt-get update -y \
    && apt-get install --no-install-recommends -y -q dos2unix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY ./requirements.txt /src/requirements.txt
RUN pip install --no-cache-dir -r /src/requirements.txt
COPY . /src
# Convert line endings to Unix format and make executable
RUN dos2unix /src/docker-entrypoint.sh && chmod +x /src/docker-entrypoint.sh
EXPOSE 9000
RUN chown -R nobody:nogroup /src
USER nobody
CMD ["/src/docker-entrypoint.sh"]
