import logging

from flask import request, g
from flask_restful import Api
from http import HTTPStatus
from sqlalchemy import or_, and_
from names_generator import generate_name

from vantage6.common import logger_name
from vantage6.common.enums import LocalAction
from vantage6.server import db
from vantage6.backend.common.resource.pagination import Pagination
from vantage6.server.permission import (
    Scope as S,
    Operation as P,
    PermissionManager,
    RuleCollection,
)
from vantage6.server.resource import only_for, with_user, ServicesResources
from vantage6.server.resource.common.input_schema import (
    SessionInputSchema,
    NodeSessionInputSchema,
    PipelineInputSchema,
)
from vantage6.server.resource.common.output_schema import (
    SessionSchema,
    NodeSessionSchema,
)
from vantage6.server.resource.task import Tasks


module_name = logger_name(__name__)
log = logging.getLogger(module_name)


def setup(api: Api, api_base: str, services: dict) -> None:
    """
    Setup the session resource.

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
    log.info(f'Setting up "{path}" and subdirectories')

    api.add_resource(
        Sessions,
        path,
        endpoint="session_without_id",
        methods=("GET", "POST"),
        resource_class_kwargs=services,
    )
    api.add_resource(
        Session,
        path + "/<int:id>",
        endpoint="session_with_id",
        methods=("GET", "POST", "DELETE"),
        resource_class_kwargs=services,
    )
    api.add_resource(
        SessionPipelines,
        path + "/<int:session_id>/pipeline",
        endpoint="session_pipeline_without_id",
        methods=("GET", "POST"),
        resource_class_kwargs=services,
    )
    # api.add_resource(
    #     SessionPipeline,
    #     path + "/<int:session_id>/pipeline/<string:pipeline_handle>",
    #     endpoint="session_pipeline_with_id",
    #     methods=("GET", "PATCH", "DELETE"),
    #     resource_class_kwargs=services,
    # )
    api.add_resource(
        NodeSessions,
        path + "/<int:session_id>/node",
        endpoint="node_session_without_id",
        methods=("GET", "PATCH"),
        resource_class_kwargs=services,
    )


# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------
def permissions(permissions: PermissionManager) -> None:
    """
    Define the permissions for this resource.

    Parameters
    ----------
    permissions : PermissionManager
        Permission manager instance to which permissions are added
    """
    add = permissions.appender(module_name)

    # view
    add(scope=S.GLOBAL, operation=P.VIEW, description="view any session")
    add(
        scope=S.COLLABORATION,
        operation=P.VIEW,
        description="view any session within your collaborations",
        assign_to_node=True,
    )
    add(
        scope=S.ORGANIZATION,
        operation=P.VIEW,
        description="view any session initiated from your organization",
    )
    add(scope=S.OWN, operation=P.VIEW, description="view your own session")

    # create
    add(scope=S.OWN, operation=P.CREATE, description="create a new session")
    add(
        scope=S.ORGANIZATION,
        operation=P.CREATE,
        description="create a new session for all users within your organization",
    )
    add(
        scope=S.COLLABORATION,
        operation=P.CREATE,
        description="create a new session for all users within your collaboration",
    )

    # edit permissions.
    add(scope=S.OWN, operation=P.EDIT, description="edit your own session")
    add(
        scope=S.ORGANIZATION,
        operation=P.EDIT,
        description="edit any session initiated from your organization",
    )
    add(
        scope=S.COLLABORATION,
        operation=P.EDIT,
        description="edit any session within your collaboration",
        assign_to_node=True,
    )

    # delete permissions
    add(scope=S.OWN, operation=P.DELETE, description="delete your own session")
    add(
        scope=S.ORGANIZATION,
        operation=P.DELETE,
        description="delete any session initiated from your organization",
    )
    add(
        scope=S.COLLABORATION,
        operation=P.DELETE,
        description="delete any session within your collaborations",
    )
    add(scope=S.GLOBAL, operation=P.DELETE, description="delete any session")


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------
session_schema = SessionSchema()
session_input_schema = SessionInputSchema()
pipeline_input_schema = PipelineInputSchema()
node_session_schema = NodeSessionSchema()
node_session_input_schema = NodeSessionInputSchema()


class SessionBase(ServicesResources):
    def __init__(self, socketio, mail, api, permissions, config):
        super().__init__(socketio, mail, api, permissions, config)
        self.r: RuleCollection = getattr(self.permissions, module_name)

    def can_view_session(self, session: db.Session) -> bool:
        """Check if the user can view the session"""
        if self.r.v_glo.can():
            return True

        if (
            self.r.v_col.can()
            and session.collaboration_id in self.obtain_auth_collaboration_ids()
        ):
            return True

        if (
            self.r.v_org.can()
            and session.organization_id == self.obtain_organization_id()
        ):
            return True

        if self.is_user() and self.r.v_own.can() and session.user_id == g.user.id:
            return True

        return False

    def create_session_task(
        self,
        session: db.Session,
        image: str,
        organizations: dict,
        database: dict,
        action: LocalAction,
        description="",
        depends_on_id=None,
    ) -> int:
        """Create a task to initialize a session"""
        input_ = {
            "collaboration_id": session.collaboration_id,
            "study_id": session.study_id,
            "session_id": session.id,
            "name": f"Session initialization: {session.name}",
            "description": description,
            "image": image,
            "organizations": organizations,
            "databases": database,
            "depends_on_id": depends_on_id,
        }
        # remove empty values
        input_ = {k: v for k, v in input_.items() if v is not None}
        return Tasks.post_task(
            input_, self.socketio, getattr(self.permissions, "task"), action
        )

    @staticmethod
    def delete_session(session: db.Session) -> None:
        """
        Deletes the session and all associated configurations.

        Parameters
        ----------
        session : db.Session
            Session to delete
        """
        log.debug(f"Deleting session id={session.id}")

        for config in session.config:
            config.delete()

        for node_session in session.node_sessions:
            for config in node_session.config:
                config.delete()
            node_session.delete()

        for task in session.tasks:
            for result in task.results:
                result.delete()
            task.delete()

        session.delete()


class Sessions(SessionBase):

    @only_for(("user", "node"))
    def get(self):
        """Returns a list of sessions
        ---
        description: >-
          Get a list of sessions based on filters and user permissions\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Global|View|❌|❌|View all available sessions|\n
          |Session|Collaboration|View|✅|❌|View all available sessions within the
          scope of the collaboration|\n
          |Session|Organization|View|❌|❌|View all available sessions that have been
          initiated from a user within your organization|\n
          |Session|Own|View|❌|❌|View all sessions created by you

          Accessible to users.

        parameters:
        - in: query
          name: label
          schema:
            type: string
          description: >-
            Name to match with a LIKE operator. \n
            * The percent sign (%) represents zero, one, or multiple
            characters\n
            * underscore sign (_) represents one, single character
        - in: query
          name: user
          schema:
            type: integer
          description: User id
        - in: query
          name: user
          schema:
            type: integer
          description: User id
        - in: query
          name: collaboration
          schema:
            type: integer
          description: Collaboration id
        - in: query
          name: scope
          schema:
            type: string
          description: >-
            Scope of the session. Possible values are: GLOBAL, COLLABORATION,
            ORGANIZATION, OWN
        - in: query
          name: page
          schema:
            type: integer
          description: Page number for pagination (default=1)
        - in: query
          name: per_page
          schema:
            type: integer
          description: Number of items per page (default=10)
        - in: query
          name: sort
          schema:
            type: string
          description: >-
            Sort by one or more fields, separated by a comma. Use a minus
            sign (-) in front of the field to sort in descending order.

        responses:
          200:
            description: Ok
          401:
            description: Unauthorized
          400:
            description: Improper values for pagination or sorting parameters

        security:
        - bearerAuth: []

        tags: ["Session"]
        """

        # Obtain the organization of the requester
        auth_org = self.obtain_auth_organization()
        args = request.args

        # query
        q = g.session.query(db.Session)
        g.session.commit()

        # filter by a field of this endpoint
        if "label" in args:
            q = q.filter(db.Session.label.like(args["label"]))
        if "user" in args:
            q = q.filter(db.Session.user_id == args["user"])
        if "collaboration" in args:
            q = q.filter(db.Session.collaboration_id == args["collaboration"])
        if "scope" in args:
            q = q.filter(db.Session.scope == args["scope"])

        # filter the list of organizations based on the scope. If you have collaboration
        # permissions you can see all sessions within the collaboration. If you have
        # organization permissions you can see all sessions withing your organization
        # and the sessions from other organization that have scope collaboration.
        # Finally when you have own permissions you can see the sessions that you have
        # created, the sessions from your organization with scope organization and you
        # can see the sessions in the collaboration that have a scope collaboration.
        if not self.r.v_glo.can():
            if self.r.v_col.can():
                q = q.filter(db.Session.collaboration_id.in_(auth_org.collaborations))
            elif self.r.v_org.can():
                q = q.filter(
                    or_(
                        db.Session.organization_id == auth_org.id,
                        and_(
                            db.Session.collaboration_id.in_(auth_org.collaborations),
                            db.Session.scope == S.COLLABORATION,
                        ),
                    )
                )
            elif self.r.v_own.can():
                q = q.filter(
                    or_(
                        db.Session.user_id == g.user.id,
                        and_(
                            db.Session.organization_id == auth_org.id,
                            db.Session.scope == S.ORGANIZATION,
                        ),
                        and_(
                            db.Session.collaboration_id.in_(auth_org.collaborations),
                            db.Session.scope == S.COLLABORATION,
                        ),
                    )
                )
            else:
                return {
                    "msg": "You lack the permission to do that!"
                }, HTTPStatus.UNAUTHORIZED

        # paginate the results
        try:
            page = Pagination.from_query(q, request, db.Session)
        except (ValueError, AttributeError) as e:
            return {"msg": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR

        # serialization of DB model
        return self.response(page, session_schema)

    @with_user
    def post(self):
        """Initiate new session
        ---
        description: >-
          Initialize a new session in a collaboration or study. \n\n

          This will trigger the data-extraction process at the participating nodes.\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Collaboration|Create|❌|❌|Create session to be used by the entire
          collaboration|\n
          |Session|Organization|Create|❌|❌|Create session to be used by your organization|\n
          |Session|Own|Create|❌|❌|Create session only to be used by you|\n

          Only accessible to users.

        requestBody:
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Session'

        responses:
          201:
            description: Ok
          401:
            description: Unauthorized
          400:
            description: Session with that label already exists within the collaboration
                or Request body is incorrect
          404:
            description: Collaboration or study not found


        security:
        - bearerAuth: []

        tags: ["Session"]
        """
        # TODO if any of the steps fails... we need to rollback the entire session
        if not self.r.has_at_least_scope(S.OWN, P.CREATE):
            return {
                "msg": "You lack the permission to do that!"
            }, HTTPStatus.UNAUTHORIZED

        data = request.get_json()
        errors = session_input_schema.validate(data)

        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        # Check if the user has the permission to create a session for the scope
        scope = getattr(S, data["scope"].upper())
        if not self.r.has_at_least_scope(scope, P.CREATE):
            return {
                "msg": (
                    "You lack the permission to create a session for "
                    f"the {data['scope']} scope!"
                )
            }, HTTPStatus.UNAUTHORIZED

        collaboration: db.Collaboration = db.Collaboration.get(data["collaboration_id"])
        if not collaboration:
            return {"msg": "Collaboration not found"}, HTTPStatus.NOT_FOUND

        # When no label is provided, we generate a unique label.
        if "name" not in data:
            while db.Session.name_exists(
                propose_name := generate_name(), collaboration
            ):
                pass
            data["name"] = propose_name

        # In case the user provides a name, we check if the name already exists
        if db.Session.name_exists(data["name"], collaboration):
            return {
                "msg": "Session with that name already exists within the collaboration!"
            }, HTTPStatus.BAD_REQUEST

        # Create the Session object
        session = db.Session(
            name=data["name"],
            user_id=g.user.id,
            collaboration=collaboration,
            scope=scope,
            study_id=data.get("study_id"),
        )
        session.save()

        # Each node gets assigned a NodeSession to keep track of each individual node's
        # state.
        for node in collaboration.nodes:
            db.NodeSession(
                session=session,
                node=node,
            ).save()

        # A pipeline is a list of tasks that need to be executed in order to initialize
        # the session. A single session can have multiple pipelines, each with a
        # different database or different user inputs. Each pipeline can be identified
        # using a unique handle.
        for pipeline in data["pipelines"]:

            # This label is used to identify the database, this label should match the
            # label in the node configuration file. Each node can have multiple
            # databases.
            source_db_label = pipeline["handle"]

            # Multiple datasets can be created in a single session. This handle can be
            # used by the `preprocessing` and `compute` to identify the different
            # datasets that are send after the data extraction task. The handle can be
            # provided by the user, if not a unique handle is generated.
            if "handle" not in pipeline:
                existing_handles = db.SessionConfig.get_values_from_key(
                    session.id, "df_handle"
                )
                while (handle := generate_name()) in existing_handles:
                    pass
            else:
                handle = pipeline["handle"]

            # Store the handle in the session configuration
            db.SessionConfig(session=session, key="df_handle", value=handle).save()

            # When a session is initialized, a mandatory data extraction step is
            # required. This step is the first step in the pipeline and is used to
            # extract the data from the source database.
            extraction_details = pipeline["task"]
            response, status_code = self.create_session_task(
                session=session,
                image=extraction_details["image"],
                organizations=extraction_details["organizations"],
                # TODO FM 10-7-2024: we should make a custom type for this
                database=[{"label": source_db_label, "type": "source"}],
                description=f"Data extraction step for session {session.name}",
                action=LocalAction.DATA_EXTRACTION,
            )

            if status_code != HTTPStatus.CREATED:
                self.delete_session(session)
                return response, status_code

            db.SessionConfig(
                session=session,
                key=f"{handle}_last_task_id_pointer",
                value=response["id"],
            ).save()

        return session_schema.dump(session, many=False), HTTPStatus.CREATED


class SessionPipelines(SessionBase):

    @only_for(("user", "node"))
    def get(self, session_id):
        """view pipelines of a session"""
        return HTTPStatus.NOT_IMPLEMENTED

    @only_for(("user",))
    def post(self, session_id):
        """Add a preprocessing step to one or more pipeline"""

        data = request.get_json()
        errors = session_input_schema.validate(data, many=True)

        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        session: db.Session = db.Session.get(session_id)

        for pipeline in data["pipelines"]:

            # Get the handle for the data frame in this session
            label = pipeline["label"]

            # Obtain the latest task id pointer
            last_task_id_pointer = db.SessionConfig.get_values_from_key(
                session_id, f"{label}_last_task_id_pointer"
            )
            # TODO FM 10-7-2024: this is a temporary solution, I should consider making
            # these properties into the db model
            if len(last_task_id_pointer) > 0 or not last_task_id_pointer:
                return {
                    "msg": "Session last task pointer is broken"
                }, HTTPStatus.BAD_REQUEST

            task = db.Task.get(last_task_id_pointer[0])
            if not task:
                return {"msg": "Previous session is not found!"}, HTTPStatus.NOT_FOUND

            preprocessing_task = pipeline["task"]
            response, status_code = self.create_session_task(
                session=session,
                database=[{"label": label, "type": "handle"}],
                description=f"Preprocessing step for session {session.name}",
                depends_on_id=task.id,
                action=LocalAction.PREPROCESSING,
                image=preprocessing_task["image"],
                organizations=preprocessing_task["organizations"],
            )
            if status_code != HTTPStatus.CREATED:
                Session.delete_session(session)
                return response, status_code

            # TODO FM 10-7-2024: We should make a specific response for this
            return response, status_code


class Session(SessionBase):

    @only_for(("user", "node"))
    def get(self, id):
        """View specific session
        ---
        description: >-
          Returns the session specified by the id\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Global|View|❌|❌|View any session|\n
          |Session|Collaboration|View|❌|❌|View any session within your
          collaborations|\n
          |Session|Organization|View|❌|❌|View any session that has been
          initiated from your organization or shared with your organization|\n
          |Session|Own|View|❌|❌|View any session you created or that is shared
          with you|\n

          Accessible to users.

        parameters:
        - in: path
          name: id
          schema:
            type: integer
          description: Session id
          required: true

        responses:
          200:
            description: Ok
          404:
            description: Session not found
          401:
            description: Unauthorized

        security:
        - bearerAuth: []

        tags: ["Session"]
        """

        # retrieve requested organization
        session: db.Session = db.Session.get(id)
        if not session:
            return {"msg": f"Session id={id} not found!"}, HTTPStatus.NOT_FOUND

        if not self.can_view_session(session):
            return {
                "msg": "You lack the permission to do that!"
            }, HTTPStatus.UNAUTHORIZED

        return session_schema.dump(session, many=False), HTTPStatus.OK

    @only_for(("user",))
    def patch(self, id):
        """Update session
        ---
        description: >-
          Updates the scope or name of the session.\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Collaboration|Edit|❌|❌|Update an session within
          the collaboration the user is part of|\n
          |Session|Organization|Edit|❌|❌|Update the session that is initiated from
          a user within your organization|\n
          |Session|Own|Edit|❌|❌|Update a session that you created|\n

          Accessible to users.

        parameters:
        - in: path
          name: id
          schema:
            type: integer
          description: Session id
          required: true

        requestBody:
          content:
            application/json:
              schema:
                properties:
                  name:
                    type: string
                    description: Name of the session
                  scope:
                    type: string
                    description: Scope of the session

        responses:
          200:
            description: Ok
          401:
            description: Unauthorized
          404:
            description: Session not found
          400:
            decription: Session with that name already exists within the collaboration

        security:
        - bearerAuth: []

        tags: ["Session"]
        """
        # validate request body
        data = request.get_json()
        errors = session_input_schema.validate(data, partial=True)
        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        session: db.Session = db.Session.get(id)
        if not session:
            return {"msg": f"Session with id={id} not found"}, HTTPStatus.NOT_FOUND

        # If you are the owner of the session you only require edit permissions at
        # own level. In case you are not the owner, the session needs to be within
        # you scope in order to edit it.
        is_owner = session.owner.id == g.user.id
        if not (is_owner and self.r.has_at_least_scope(S.OWN, P.EDIT)):
            if not self.r.has_at_least_scope(session.scope, P.EDIT):
                return {
                    "msg": "You lack the permission to do that!"
                }, HTTPStatus.UNAUTHORIZED

        if "name" in data:
            if data["name"] != session.name and db.Session.name_exists(
                data["name"], session.collaboration
            ):
                return {
                    "msg": "Session with that name already exists within the "
                    "collaboration!"
                }, HTTPStatus.BAD_REQUEST

            session.name = data["name"]

        if "scope" in data:
            scope = getattr(S, data["scope"].upper())
            if not self.r.has_at_least_scope(scope, P.EDIT):
                return {
                    "msg": (
                        "You lack the permission to change the scope of the session "
                        f"to {data['scope']}!"
                    )
                }, HTTPStatus.UNAUTHORIZED

            session.scope = scope

        session.save()
        return session_schema.dump(session, many=False), HTTPStatus.OK

    @only_for(("user",))
    def delete(self, id):
        """Delete session
        ---
        description: >-
          Deletes the session specified by the id. This also deletes all node sessions
          and configurations that are part of the session.\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Global|Delete|❌|❌|Delete any session|\n
          |Session|Collaboration|Delete|❌|❌|Delete any session within your
          collaborations|\n
          |Session|Organization|Delete|❌|❌|Delete any session that has been
          initiated from your organization|\n
          |Session|Own|Delete|❌|❌|Delete any session you created|\n

          Accessible to users.

        parameters:
        - in: path
          name: id
          schema:
            type: integer
          description: Session id
          required: true

        responses:
          204:
            description: Ok
          401:
            description: Unauthorized
          404:
            description: Session not found

        security:
          - bearerAuth: []

        tags: ["Session"]
        """
        session: db.Session = db.Session.get(id)
        if not session:
            return {"msg": f"Session with id={id} not found"}, HTTPStatus.NOT_FOUND

        accepted = False

        if self.r.d_glo.can():
            accepted = True

        elif (
            self.r.d_col.can()
            and session.collaboration_id in self.obtain_auth_collaboration_ids()
        ):
            accepted = True

        elif (
            self.r.d_org.can()
            and session.organization_id == self.obtain_organization_id()
        ):
            accepted = True

        elif self.r.d_own.can() and session.user_id == g.user.id:
            accepted = True

        if not accepted:
            return {
                "msg": "You lack the permission to do that!"
            }, HTTPStatus.UNAUTHORIZED

        self.delete_session(session)
        # TODO create socket event so the node knows that it should clear the session
        # data too.

        return {"msg": f"Successfully deleted session id={id}"}, HTTPStatus.OK


class NodeSessions(SessionBase):

    @only_for(("user", "node"))
    def get(self, session_id):
        """Get node session
        ---
        description: >-
          Returns the 'node sessions' for the specified session\n

          ### Permission Table\n
          |Rule name|Scope|Operation|Assigned to node|Assigned to container|
          Description|\n
          |--|--|--|--|--|--|\n
          |Session|Global|View|❌|❌|View any session|\n
          |Session|Collaboration|View|✅|❌|View any session within your
          collaborations|\n
          |Session|Organization|View|❌|❌|View any session that has been
          initiated from your organization or shared with your organization|\n
          |Session|Own|View|❌|❌|View any session you created or that is shared
          with you|\n

          Accessible to users.

        parameters:
        - in: path
          name: session_id
          schema:
          type: integer
          description: Session id
          required: true

        responses:
          200:
            description: Ok
          404:
            description: Session not found
          401:
            description: Unauthorized

        security:
        - bearerAuth: []

        tags: ["Session"]
        """
        session: db.Session = db.Session.get(session_id)
        if not session:
            return {
                "msg": f"Session with id={session_id} not found"
            }, HTTPStatus.NOT_FOUND

        if not self.can_view_session(session):
            return {
                "msg": "You lack the permission to do that!"
            }, HTTPStatus.UNAUTHORIZED

        return node_session_schema.dump(session.node_sessions, many=True), HTTPStatus.OK

    @only_for(("node",))
    def patch(self, session_id):
        """Update node session
        ---
        description: >-
          Update the state of the node session\n

          ### Permissions\n
          Only accessible by nodes.

          Note that this endpoint deletes all config options when new configuration
          settings are provided.

        parameters:
        - in: path
          name: session_id
          schema:
          type: integer
          description: Session id
          required: true

        requestBody:
          content:
            application/json:
              schema:
                properties:
                  state:
                    type: string
                    description: State of the node session
                  config:
                    type: array
                    items:
                      properties:
                        key:
                          type: string
                          description: Configuration key
                        value:
                          type: string
                          description: Configuration value

        responses:
          200:
            description: Ok
          404:
            description: Session or node session not found

        security:
        - bearerAuth: []

        tags: ["Session"]
        """
        data = request.get_json()
        errors = node_session_input_schema.validate(data)
        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        session: db.Session = db.Session.get(session_id)
        if not session:
            return {
                "msg": f"Session with id={session_id} not found"
            }, HTTPStatus.NOT_FOUND

        node_session: db.NodeSession = db.NodeSession.get_by_node_and_session(
            g.node.id, session.id
        )
        if not node_session:
            return {
                "msg": f"Node session with node id={g.node.id} and session "
                f"id={session.id} not found"
            }, HTTPStatus.NOT_FOUND

        if "config" in data:
            # Delete old configuration
            for item in node_session.config:
                item.delete()
            # add new
            for config in data["config"]:
                db.NodeSessionConfig(
                    node_session=node_session, key=config["key"], value=config["value"]
                ).save()

        if "state" in data:
            node_session.state = data["state"]
            node_session.save()

        return node_session_schema.dump(node_session, many=False), HTTPStatus.OK