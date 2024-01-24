# -*- coding: utf-8 -*-
"""
Resources below '/<api_base>/version'
"""
import logging

from flask_restful import Api
from http import HTTPStatus
from vantage6.common import logger_name
from vantage6.algorithm.store._version import __version__

# TODO move to common / refactor
from vantage6.server.resource import AlgorithmStoreResources


module_name = logger_name(__name__)
log = logging.getLogger(module_name)


def setup(api: Api, api_base: str, services: dict) -> None:
    """
    Setup the version resource.

    Parameters
    ----------
    api : Api
        Flask restful api instance
    api_base : str
        Base url of the api
    services : dict
        Dictionary with services required for the resource endpoints
    """
    path = "/".join([api_base, module_name])
    log.info('Setting up "%s" and subdirectories', path)

    api.add_resource(
        Version,
        path,
        endpoint="version",
        methods=("GET",),
        resource_class_kwargs=services,
    )


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------
class Version(AlgorithmStoreResources):
    """Version resource"""

    def get(self):
        """Get version
        ---
        description: Return the version of the algorithm store server instance

        responses:
          200:
            description: Ok

        tags: ["Other"]
        """
        return {"version": __version__}, HTTPStatus.OK
