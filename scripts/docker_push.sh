#!/bin/bash
echo "$DOCKER_PASSWORD" | docker login -u alinpanaitiu --password-stdin

docker push noiseblend/api:$TRAVIS_COMMIT
docker tag noiseblend/api:$TRAVIS_COMMIT noiseblend/api:staging
docker push noiseblend/api:staging

if [[ $TRAVIS_PULL_REQUEST == "false" && $TRAVIS_BRANCH != $TRAVIS_TAG ]]; then
    export DOCKER_TAG=${TRAVIS_BRANCH//\//-}
    export DOCKER_TAG=${DOCKER_TAG//[^-.a-zA-Z0-9]/_}
    docker tag noiseblend/api:$TRAVIS_COMMIT noiseblend/api:$DOCKER_TAG
    docker push noiseblend/api:$DOCKER_TAG
fi

if [[ $TRAVIS_TAG ]]; then
    docker tag noiseblend/api:$TRAVIS_COMMIT noiseblend/api:$TRAVIS_TAG
    docker tag noiseblend/api:$TRAVIS_COMMIT noiseblend/api:latest
    docker push noiseblend/api:$TRAVIS_TAG
    docker push noiseblend/api:latest
fi
