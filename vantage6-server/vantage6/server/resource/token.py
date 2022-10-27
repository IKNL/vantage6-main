# -*- coding: utf-8 -*-
"""
Resources below '/<api_base>/token'
"""
from __future__ import print_function, unicode_literals

import logging
import datetime as dt
from typing import Union
import pyotp

from flask import request, g
from flask_jwt_extended import (
    jwt_required,
    create_access_token,
    create_refresh_token,
    get_jwt_identity
)
from http import HTTPStatus

from vantage6.common.globals import APPNAME
from vantage6 import server
from vantage6.server import db
from vantage6.server.model.user import User
from vantage6.server.resource import (
    with_node,
    ServicesResources
)

module_name = __name__.split('.')[-1]
log = logging.getLogger(module_name)


def setup(api, api_base, services):

    path = "/".join([api_base, module_name])
    log.info('Setting up "{}" and subdirectories'.format(path))

    api.add_resource(
        UserToken,
        path+'/user',
        endpoint='user_token',
        methods=('POST',),
        resource_class_kwargs=services
    )

    api.add_resource(
        NodeToken,
        path+'/node',
        endpoint='node_token',
        methods=('POST',),
        resource_class_kwargs=services
    )

    api.add_resource(
        ContainerToken,
        path+'/container',
        endpoint='container_token',
        methods=('POST',),
        resource_class_kwargs=services
    )

    api.add_resource(
        RefreshToken,
        path+'/refresh',
        endpoint='refresh_token',
        methods=('POST',),
        resource_class_kwargs=services
    )


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------
class UserToken(ServicesResources):
    """resource for api/token"""

    def post(self):
        """Login user
        ---
        description: >-
          Allow user to sign in by supplying a username and password. When MFA
          is enabled on the server, a code is also required

        requestBody:
          content:
            application/json:
              schema:
                properties:
                  username:
                    type: string
                    description: Username of user that is logging in
                  password:
                    type: string
                    description: User password
                  mfa_code:
                    type: string
                    description: Two-factor authentication code. Only required
                      if two-factor authentication is mandatory.

        responses:
          200:
            description: Ok, authenticated
          400:
            description: Username/password combination unknown, or missing from
              request body.
          401:
            description: Password and/or two-factor authentication token
              incorrect.

        tags: ["Authentication"]
        """
        log.debug("Authenticate user using username and password")

        if not request.is_json:
            log.warning('Authentication failed because no JSON body was '
                        'provided!')
            return {"msg": "Missing JSON in request"}, HTTPStatus.BAD_REQUEST

        # Check JSON body
        username = request.json.get('username', None)
        password = request.json.get('password', None)
        if not username and password:
            msg = "Username and/or password missing in JSON body"
            log.error(msg)
            return {"msg": msg}, HTTPStatus.BAD_REQUEST

        user, code = self.user_login(username, password)
        if code is not HTTPStatus.OK:  # login failed
            log.error(f"Failed to login for user='{username}'")
            return user, code

        is_mfa_enabled = self.config.get('two_factor_auth', False)
        if is_mfa_enabled:
            if user.otp_secret is None:
                # server requires mfa but user hasn't set it up yet. Return
                # an URI to generate a QR code
                log.info(f'Redirecting user {username} to setup MFA')
                return self.create_qr_uri(user), HTTPStatus.OK
            else:
                # 2nd authentication factor: check the OTP secret of the user
                mfa_code = request.json.get('mfa_code')
                if not mfa_code:
                    # note: this is not treated as error, but simply guide
                    # user to also fill in second factor
                    return {"msg": "Please include your two-factor "
                            "authentication code"}, HTTPStatus.OK
                elif not self.validate_2fa_token(user, mfa_code):
                    return {
                        "msg": "Your two-factor authentication code is "
                               "incorrect!"
                    }, HTTPStatus.UNAUTHORIZED

        token = create_access_token(user)

        ret = {
            'access_token': token,
            'refresh_token': create_refresh_token(user),
            'user_url': self.api.url_for(server.resource.user.User,
                                         id=user.id),
            'refresh_url': self.api.url_for(RefreshToken),
        }

        log.info(f"Succesfull login from {username}")
        return ret, HTTPStatus.OK, {'jwt-token': token}

    def validate_2fa_token(self, user: User, mfa_code: Union[int, str]):
        """
        Check whether the 6-digit two-factor authentication code is valid

        user: User
            The SQLAlchemy model of the user who is authenticating
        mfa_code:
            A six-digit TOTP code from an authenticator app
        """
        # the option `valid_window=1` means the code from 1 time window (30s)
        # ago, is also valid. This prevents that users around the edge of
        # the time window can still login successfully if server is a bit slow
        return pyotp.TOTP(user.otp_secret).verify(str(mfa_code),
                                                  valid_window=1)

    def create_qr_uri(self, user):
        """
        Create the URI to generate a QR code for authenticator apps
        """
        provisioner = self.config.get("smtp", {})
        # TODO adapt support email
        provision_email = provisioner.get("username", "support@vantage6.ai")
        otp_secret = pyotp.random_base32()
        qr_uri = pyotp.totp.TOTP(otp_secret).provisioning_uri(
            name=provision_email, issuer_name=APPNAME
        )
        user.otp_secret = otp_secret
        user.save()
        return {
            'qr_uri': qr_uri,
            'otp_secret': otp_secret,
            'msg': ('Two-factor authentication is obligatory on this server. '
                    'Please visualize the QR code to set up authentication.')
        }

    def user_login(self, username, password):
        """Returns user a message in case of failed login attempt."""
        log.info(f"Trying to login '{username}'")

        if db.User.username_exists(username):
            user = db.User.get_by_username(username)
            pw_policy = self.config.get('password_policy', {})
            max_failed_attempts = pw_policy.get('max_failed_attempts', 5)
            inactivation_time = pw_policy.get('inactivation_minutes', 15)

            is_blocked, time_remaining_msg = user.is_blocked(
              max_failed_attempts, inactivation_time)
            if is_blocked:
                return {"msg": time_remaining_msg}, HTTPStatus.UNAUTHORIZED
            elif user.check_password(password):
                user.failed_login_attempts = 0
                user.save()
                return user, HTTPStatus.OK
            else:
                # update the number of failed login attempts
                user.failed_login_attempts = 1 \
                    if (
                        not user.failed_login_attempts or
                        user.failed_login_attempts >= max_failed_attempts
                    ) else user.failed_login_attempts + 1
                user.last_login_attempt = dt.datetime.now()
                user.save()

        return {"msg": "Invalid username or password!"}, \
            HTTPStatus.UNAUTHORIZED


class NodeToken(ServicesResources):

    def post(self):
        """Login node
        ---
        description: >-
          Allows node to sign in using a unique API key. If the login is
          successful this returns a dictionairy with access and refresh tokens
          for the node as well as a node_url and a refresh_url.

        requestBody:
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Node'

        responses:
          200:
            description: Ok, authenticated
          400:
            description: No API key provided in request body.
          401:
            description: Invalid API key

        tags: ["Authentication"]
        """
        log.debug("Authenticate Node using api key")

        if not request.is_json:
            log.warning('Authentication failed because no JSON body was '
                        'provided!')
            return {"msg": "Missing JSON in request"}, HTTPStatus.BAD_REQUEST

        # Check JSON body
        api_key = request.json.get('api_key', None)
        if not api_key:
            msg = "api_key missing in JSON body"
            log.error(msg)
            return {"msg": msg}, HTTPStatus.BAD_REQUEST

        node = db.Node.get_by_api_key(api_key)

        if not node:  # login failed
            log.error("Api key is not recognized")
            return {"msg": "Api key is not recognized!"}, \
                HTTPStatus.UNAUTHORIZED

        token = create_access_token(node)
        ret = {
            'access_token': token,
            'refresh_token': create_refresh_token(node),
            'node_url': self.api.url_for(server.resource.node.Node,
                                         id=node.id),
            'refresh_url': self.api.url_for(RefreshToken),
        }

        log.info(f"Succesfull login as node '{node.id}' ({node.name})")
        return ret, HTTPStatus.OK, {'jwt-token': token}


class ContainerToken(ServicesResources):

    @with_node
    def post(self):
        """Algorithm container login
        ---
        description: >-
          Generate token for the algorithm container of a specific task.\n

          Not available to users; only for authenticated nodes.

        requestBody:
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ContainerToken'

        responses:
          200:
            description: Container token generated
          400:
            description: Task does not exist or is already completed
          401:
            description: Key request for invalid image or task

        tags: ["Authentication"]
        """
        log.debug("Creating a token for a container running on a node")

        data = request.get_json()

        task_id = data.get("task_id")
        claim_image = data.get("image")
        db_task = db.Task.get(task_id)
        if not db_task:
            log.warning(f"Node {g.node.id} attempts to generate key for task "
                        f"{task_id} that does not exist")
            return {"msg": "Master task does not exist!"}, \
                HTTPStatus.BAD_REQUEST

        # verify that task the token is requested for exists
        if claim_image != db_task.image:
            log.warning(
                f"Node {g.node.id} attemts to generate key for image "
                f"{claim_image} that does not belong to task {task_id}."
            )
            return {"msg": "Image and task do no match"}, \
                HTTPStatus.UNAUTHORIZED

        # check if the node is in the collaboration to which the task is
        # enlisted
        if g.node.collaboration_id != db_task.collaboration_id:
            log.warning(
                f"Node {g.node.id} attemts to generate key for task {task_id} "
                f"which is outside its collaboration "
                f"({g.node.collaboration_id}/{db_task.collaboration_id})."
            )
            return {"msg": "You are not within the collaboration"}, \
                HTTPStatus.UNAUTHORIZED

        # validate that the task not has been finished yet
        if db_task.complete:
            log.warning(f"Node {g.node.id} attempts to generate a key for "
                        f"completed task {task_id}")
            return {"msg": "Task is already finished!"}, HTTPStatus.BAD_REQUEST

        # container identity consists of its node_id,
        # task_id, collaboration_id and image_id
        container = {
            "client_type": "container",
            "node_id": g.node.id,
            "organization_id": g.node.organization_id,
            "collaboration_id": g.node.collaboration_id,
            "task_id": task_id,
            "image": claim_image
        }
        token = create_access_token(container, expires_delta=False)

        return {'container_token': token}, HTTPStatus.OK


class RefreshToken(ServicesResources):

    @jwt_required(refresh=True)
    def post(self):
        """Refresh token
        ---
        description: >-
          Refresh access token if the previous one is expired.\n

          Your refresh token must be present in the request headers to use
          this endpoint.

        responses:
          200:
            description: Token refreshed

        security:
          - bearerAuth: []

        tags: ["Authentication"]
        """
        user_or_node_id = get_jwt_identity()
        log.info(f'Refreshing token for user or node "{user_or_node_id}"')
        user_or_node = db.Authenticatable.get(user_or_node_id)
        ret = {'access_token': create_access_token(user_or_node)}

        return ret, HTTPStatus.OK
