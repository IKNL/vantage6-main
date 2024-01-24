"""
The server has a central function in the vantage6 architecture. It stores
in the database which organizations, collaborations, users, etc.
exist. It allows the users and nodes to authenticate and subsequently interact
through the API the server hosts. Finally, it also communicates with
authenticated nodes and users via the socketIO server that is run here.
"""
# -*- coding: utf-8 -*-
import os
from gevent import monkey

# This is a workaround for readthedocs
if not os.environ.get("READTHEDOCS"):
    # flake8: noqa: E402 (ignore import error)
    monkey.patch_all()

import importlib
import logging
import json
import traceback

from http import HTTPStatus
from werkzeug.exceptions import HTTPException
from flask import Flask, make_response, request, send_from_directory, Request, Response
from flask_cors import CORS
from flask_marshmallow import Marshmallow
from flask_restful import Api
from flask_principal import Principal
from flasgger import Swagger
from pathlib import Path

from vantage6.common import logger_name
from vantage6.common.globals import APPNAME
from vantage6.cli.context.algorithm_store import AlgorithmStoreContext
from vantage6.algorithm.store._version import __version__
from vantage6.algorithm.store.globals import API_PATH

# TODO the following are simply copies of the same files in the server - refactor
from vantage6.algorithm.store.model.base import Base, DatabaseSessionManager, Database
from vantage6.algorithm.store import db

# TODO move server imports to common / refactor
from vantage6.server.resource.common.output_schema import HATEOASModelSchema
from vantage6.server.permission import PermissionManager
from vantage6.algorithm.store.globals import RESOURCES, SERVER_MODULE_NAME


module_name = logger_name(__name__)
log = logging.getLogger(module_name)


class AlgorithmStoreApp:
    """
    Vantage6 server instance.

    Attributes
    ----------
    ctx : AlgorithmStoreContext
        Context object that contains the configuration of the algorithm store.
    """

    def __init__(self, ctx: AlgorithmStoreContext) -> None:
        """Create a vantage6-server application."""

        self.ctx = ctx

        # initialize, configure Flask
        self.app = Flask(
            SERVER_MODULE_NAME,
            root_path=Path(__file__),
            template_folder=Path(__file__).parent / "templates",
            static_folder=Path(__file__).parent / "static",
        )
        self.debug: dict = self.ctx.config.get("debug", {})
        self.configure_flask()

        # Setup SQLAlchemy and Marshmallow for marshalling/serializing
        self.ma = Marshmallow(self.app)

        # Setup Principal, granular API access manegement
        self.principal = Principal(self.app, use_sessions=False)

        # Enable cross-origin resource sharing
        self.cors = CORS(self.app)

        # SWAGGER documentation
        self.swagger = Swagger(self.app, template={})

        # setup the permission manager for the API endpoints
        # self.permissions = PermissionManager()

        # Api - REST JSON-rpc
        self.api = Api(self.app)
        self.configure_api()
        self.load_resources()

        # set the server version
        self.__version__ = __version__

        log.info("Initialization done")

    def configure_flask(self) -> None:
        """Configure the Flask settings of the vantage6 server."""

        # let us handle exceptions
        self.app.config["PROPAGATE_EXCEPTIONS"] = True

        # Open Api Specification (f.k.a. swagger)
        self.app.config["SWAGGER"] = {
            "title": f"{APPNAME} algorithm store",
            "uiversion": "3",
            "openapi": "3.0.0",
            "version": __version__,
        }

        debug_mode = self.debug.get("flask", False)
        if debug_mode:
            log.debug("Flask debug mode enabled")
        self.app.debug = debug_mode

        def _get_request_path(request: Request) -> str:
            """
            Return request extension of request URL, e.g.
            http://localhost:5000/api/task/1 -> api/task/1

            Parameters
            ----------
            request: Request
                Flask request object

            Returns
            -------
            string:
                The endpoint path of the request
            """
            return request.url.replace(request.url_root, "")

        # before request
        @self.app.before_request
        def do_before_request():
            """Before every flask request method."""
            # Add log message before each request
            log.debug(
                "Received request: %s %s", request.method, _get_request_path(request)
            )

            # This will obtain a (scoped) db session from the session factory
            # that is linked to the flask request global `g`. In every endpoint
            # we then can access the database by using this session. We ensure
            # that the session is removed (and uncommited changes are rolled
            # back) at the end of every request.
            DatabaseSessionManager.new_session()

        @self.app.after_request
        def remove_db_session(response):
            """After every flask request.

            This will close the database session created by the
            `before_request`.
            """
            DatabaseSessionManager.clear_session()
            return response

        @self.app.errorhandler(HTTPException)
        def error_remove_db_session(error: HTTPException):
            """In case an HTTP-exception occurs during the request.

            It is important to close the db session to avoid having dangling
            sessions.
            """
            if error.code == 404:
                log.debug("404 error for route '%s'", _get_request_path(request))
            else:
                log.warning("HTTP Exception occured during request")
                log.debug("%s", traceback.format_exc())
            DatabaseSessionManager.clear_session()
            return error.get_response()

        @self.app.errorhandler(Exception)
        def error2_remove_db_session(error):
            """In case an exception occurs during the request.

            It is important to close the db session to avoid having dangling
            sessions.
            """
            log.exception("Exception occured during request")
            DatabaseSessionManager.clear_session()
            return {
                "msg": "An unexpected error occurred on the server!"
            }, HTTPStatus.INTERNAL_SERVER_ERROR

        @self.app.route("/robots.txt")
        def static_from_root():
            return send_from_directory(self.app.static_folder, request.path[1:])

    def configure_api(self) -> None:
        """Define global API output and its structure."""

        # helper to create HATEOAS schemas
        HATEOASModelSchema.api = self.api

        # whatever you get try to json it
        @self.api.representation("application/json")
        # pylint: disable=unused-argument
        def output_json(
            data: Base | list[Base], code: HTTPStatus, headers: dict = None
        ) -> Response:
            """
            Return jsonified data for request responses.

            Parameters
            ----------
            data: Base | list[Base]
                The data to be jsonified
            code: HTTPStatus
                The HTTP status code of the response
            headers: dict
                Additional headers to be added to the response
            """

            if isinstance(data, Base):
                data = db.jsonable(data)
            elif isinstance(data, list) and len(data) and isinstance(data[0], Base):
                data = db.jsonable(data)

            resp = make_response(json.dumps(data), code)
            resp.headers.extend(headers or {})
            return resp

    def load_resources(self) -> None:
        """Import the modules containing API resources."""

        # make services available to the endpoints, this way each endpoint can
        # make use of 'em.
        services = {
            "api": self.api,
            # "permissions": self.permissions,
            "config": self.ctx.config,
        }

        for res in RESOURCES:
            module = importlib.import_module("vantage6.algorithm.store.resource." + res)
            module.setup(self.api, API_PATH, services)

    def start(self) -> None:
        """
        Start the server.

        Before server is really started, some database settings are checked and
        (re)set where appropriate.
        """
        return self


def run_server(config: str, system_folders: bool = True) -> AlgorithmStoreApp:
    """
    Run a vantage6 server.

    Parameters
    ----------
    config: str
        Configuration file path
    system_folders: bool
        Whether to use system or user folders. Default is True.

    Returns
    -------
    AlgorithmStoreApp
        A running instance of the vantage6 server
    """
    ctx = AlgorithmStoreContext.from_external_config_file(config, system_folders)
    allow_drop_all = ctx.config["allow_drop_all"]
    Database().connect(uri=ctx.get_database_uri(), allow_drop_all=allow_drop_all)
    return AlgorithmStoreApp(ctx).start()


def run_dev_server(server_app: AlgorithmStoreApp, *args, **kwargs) -> None:
    """
    Run a vantage6 development server (outside of a Docker container).

    Parameters
    ----------
    server_app: AlgorithmStoreApp
        Instance of a vantage6 server
    """
    log.warning("*" * 80)
    log.warning(" DEVELOPMENT SERVER ".center(80, "*"))
    log.warning("*" * 80)
    kwargs.setdefault("log_output", False)
    server_app.socketio.run(server_app.app, *args, **kwargs)
