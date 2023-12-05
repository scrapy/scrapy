from __future__ import annotations

import os

_ENV_VARS = {  # per https://adamj.eu/tech/2020/03/09/detect-if-your-tests-are-running-on-ci
    "CI": None,  # generic flag
    "TF_BUILD": "true",  # Azure Pipelines
    "bamboo.buildKey": None,  # Bamboo
    "BUILDKITE": "true",  # Buildkite
    "CIRCLECI": "true",  # Circle CI
    "CIRRUS_CI": "true",  # Cirrus CI
    "CODEBUILD_BUILD_ID": None,  # CodeBuild
    "GITHUB_ACTIONS": "true",  # GitHub Actions
    "GITLAB_CI": None,  # GitLab CI
    "HEROKU_TEST_RUN_ID": None,  # Heroku CI
    "BUILD_ID": None,  # Hudson
    "TEAMCITY_VERSION": None,  # TeamCity
    "TRAVIS": "true",  # Travis CI
}


def is_ci() -> bool:
    """:return: a flag indicating if running inside a CI env or not"""
    for env_key, value in _ENV_VARS.items():
        if env_key in os.environ if value is None else os.environ.get(env_key) == value:
            if env_key == "TEAMCITY_VERSION" and os.environ.get(env_key) == "LOCAL":
                continue
            return True
    return False


__all__ = [
    "is_ci",
]
