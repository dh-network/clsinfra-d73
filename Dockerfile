# D7.3 Report on Versioning of APIs and Copora
# Docker in Docker (dind) with pre-configured jupyter lab
FROM docker:dind

MAINTAINER Ingo Börner (ingo.boerner@uni-potsdam.de)

USER root

# Install required packages
RUN apk add --update gcc musl-dev linux-headers python3-dev py3-pip py3-numpy libffi-dev g++ jpeg-dev zlib-dev libjpeg make curl git bash

RUN pip install --upgrade pip

WORKDIR /home/d73/

# Install stabledracor-client
#RUN mkdir stabledracor-client
#COPY pyproject.toml /home/dracor/stabledracor-client/pyproject.toml
#COPY src /home/dracor/stabledracor-client/src
#RUN pip3 install /home/dracor/stabledracor-client


RUN pip install pandas
RUN pip install matplotlib

# Install Jupyter lab
RUN pip install jupyterlab==4.0.12

# Jupyter book
RUN pip install jupyter-book

COPY entrypoint.sh /home/d73/entrypoint.sh
RUN chmod +x /home/d73/entrypoint.sh

EXPOSE 8889

ENTRYPOINT ["./entrypoint.sh"]

CMD []