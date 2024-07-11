import logging
from http import HTTPStatus
import datetime
from flask import g, request
from flask_restful import Api
from sqlalchemy import or_

from vantage6.algorithm.store import db
from vantage6.algorithm.store.model.common.enums import AlgorithmStatus, ReviewStatus
from vantage6.algorithm.store.model.rule import Operation
from vantage6.common import logger_name
from vantage6.algorithm.store.model.ui_visualization import UIVisualization
from vantage6.algorithm.store.resource.schema.input_schema import (
    AlgorithmInputSchema,
    AlgorithmPatchInputSchema,
)
from vantage6.algorithm.store.resource.schema.output_schema import AlgorithmOutputSchema
from vantage6.algorithm.store.model.algorithm import Algorithm as db_Algorithm
from vantage6.algorithm.store.model.argument import Argument
from vantage6.algorithm.store.model.database import Database
from vantage6.algorithm.store.model.function import Function
from vantage6.algorithm.store.resource import (
    with_permission,
    with_permission_to_view_algorithms,
)

# TODO move to common / refactor
from vantage6.algorithm.store.resource import AlgorithmStoreResources
from vantage6.algorithm.store.permission import (
    PermissionManager,
    Operation as P,
)
from vantage6.backend.common.resource.pagination import Pagination
from vantage6.common.docker.addons import get_digest, parse_image_name

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
        Algorithms,
        path,
        endpoint="algorithm_without_id",
        methods=("GET", "POST"),
        resource_class_kwargs=services,
    )

    api.add_resource(
        Algorithm,
        path + "/<int:id>",
        endpoint="algorithm_with_id",
        methods=("GET", "DELETE", "PATCH"),
        resource_class_kwargs=services,
    )

    api.add_resource(
        AlgorithmInvalidate,
        path + "/<int:id>/invalidate",
        endpoint="algorithm_invalidate",
        methods=("POST",),
        resource_class_kwargs=services,
    )


algorithm_input_post_schema = AlgorithmInputSchema()
algorithm_input_patch_schema = AlgorithmPatchInputSchema()
algorithm_output_schema = AlgorithmOutputSchema()


# ------------------------------------------------------------------------------
# Permissions
# ------------------------------------------------------------------------------
def permissions(permission_mgr: PermissionManager) -> None:
    """
    Define the permissions for this resource.

    Parameters
    ----------
    permissions : PermissionManager
        Permission manager instance to which permissions are added
    """
    add = permission_mgr.appender(module_name)
    add(P.VIEW, description="View any algorithm")
    add(P.CREATE, description="Create a new algorithm")
    add(P.EDIT, description="Edit any algorithm")
    add(P.DELETE, description="Delete any algorithm")


# ------------------------------------------------------------------------------
# Resources / API's
# ------------------------------------------------------------------------------


class AlgorithmBaseResource(AlgorithmStoreResources):
    """Base class for the algorithm resource"""

    def _get_image_digest(self, image_name: str) -> tuple[str, str]:
        """
        Get the sha256 of the image.

        This method is run in a separate thread to prevent the request from taking too
        long. Do NOT call this method from the main thread!

        Parameters
        ----------
        image : str
            Image url

        Returns
        -------
        tuple[str, str | None]
            Tuple with the docker image without tag, and the digest of the image if
            found. If the digest could not be determined, `None` is returned.
        """
        # split image and tag
        try:
            # pylint: disable=unused-variable
            registry, image, tag = parse_image_name(image_name)
        except Exception as e:
            raise ValueError(f"Invalid image name: {image_name}") from e
        image_wo_tag = "/".join([registry, image])

        # get the digest of the image.
        digest = get_digest(image_name)

        # If getting digest failed, try to use authentication
        if not digest:
            docker_registry = self.config.get("docker_registries", [])
            registry_user = None
            registry_password = None
            for reg in docker_registry:
                if reg["registry"] == registry:
                    registry_user = reg.get("username")
                    registry_password = reg.get("password")
                    break
            if registry_user and registry_password:
                digest = get_digest(image_name, registry_user, registry_password)

        return image_wo_tag, digest


class Algorithms(AlgorithmBaseResource):
    """Resource for /algorithm"""

    @with_permission_to_view_algorithms()
    def get(self):
        """List algorithms
        ---
        description: >-
          Return a list of algorithms

          By default, only approved algorithms are returned. To get non-approved
          algorithms, set the 'awaiting_reviewer_assignment', 'under_review' or
          'invalidated' parameter to True.

        parameters:
          - in: query
            name: name
            schema:
              type: string
            description: Filter on algorithm name using the SQL operator LIKE.
          - in: query
            name: description
            schema:
              type: string
            description: Filter on algorithm description using the SQL operator
              LIKE.
          - in: query
            name: image
            schema:
              type: string
            description: Filter on algorithm image. If no tag is provided, the
              latest tag is assumed.
          - in: query
            name: awaiting_reviewer_assignment
            schema:
              type: boolean
            description: Filter on algorithms that have not been assigned a reviewer
              yet.
          - in: query
            name: under_review
            schema:
              type: boolean
            description: Filter on algorithms that are currently under review.
          - in: query
            name: in_review_process
            schema:
              type: boolean
            description: Filter on algorithms that are in the review process. This
              includes algorithms that are awaiting reviewer assignment or under review
          - in: query
            name: invalidated
            schema:
              type: boolean
            description: Filter on algorithms that have been invalidated. These may be
              algorithms that have been replaced by a newer version or that have been
              rejected in review.
          - in: query
            name: partitioning
            schema:
              type: string
            description: Filter on algorithm partitioning. Can be 'horizontal'
              or 'vertical'.
          - in: query
            name: vantage6_version
            schema:
              type: string
            description: Filter on algorithm vantage6 version using the SQL
              operator LIKE.

        responses:
          200:
            description: OK
          400:
            description: Invalid input
          401:
            description: Unauthorized

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """
        q = g.session.query(db_Algorithm)

        # filter on properties
        for field in [
            "name",
            "description",
            "partitioning",
            "vantage6_version",
        ]:
            if (value := request.args.get(field)) is not None:
                q = q.filter(getattr(db_Algorithm, field).like(value))

        awaiting_reviewer_assignment = bool(
            request.args.get("awaiting_reviewer_assignment", False)
        )
        under_review = bool(request.args.get("under_review", False))
        invalidated = bool(request.args.get("invalidated", False))
        in_review_process = bool(request.args.get("in_review_process", False))
        if sum([awaiting_reviewer_assignment, under_review, invalidated]) > 1:
            return {
                "msg": "Only one of 'awaiting_reviewer_assignment', 'under_review' or "
                "'invalidated' may be set to True at a time."
            }, HTTPStatus.BAD_REQUEST
        elif in_review_process and invalidated:
            return {
                "msg": "Only one of 'in_review_process' or 'invalidated' may be set to "
                "True at a time."
            }, HTTPStatus.BAD_REQUEST
        if awaiting_reviewer_assignment:
            q = q.filter(
                db_Algorithm.status == AlgorithmStatus.AWAITING_REVIEWER_ASSIGNMENT
            )
        elif under_review:
            q = q.filter(db_Algorithm.status == AlgorithmStatus.UNDER_REVIEW)
        elif invalidated:
            q = q.filter(db_Algorithm.invalidated_at.is_not(None))
        elif in_review_process:
            q = q.filter(
                or_(
                    db_Algorithm.status == AlgorithmStatus.AWAITING_REVIEWER_ASSIGNMENT,
                    db_Algorithm.status == AlgorithmStatus.UNDER_REVIEW,
                )
            )
        else:
            # by default, only approved algorithms are returned
            q = q.filter(db_Algorithm.status == AlgorithmStatus.APPROVED)

        if (image := request.args.get("image")) is not None:
            # determine the sha256 of the image, and filter on that. Sort descending
            # to get the latest addition to the store first
            image_wo_tag, digest = self._get_image_digest(image)
            if not digest:
                return {
                    "msg": "Image digest could not be determined"
                }, HTTPStatus.BAD_REQUEST
            q = q.filter(db_Algorithm.image == image_wo_tag)
            # TODO at some point there may only be one registration of each algorithm,
            # so this sorting may not be necessary anymore
            q_with_digest = q.filter(db_Algorithm.digest == digest).order_by(
                db_Algorithm.id.desc()
            )

            # if image with that digest does not exist, check if another image with
            # different digest but same name exists. If it does, throw
            # more specific error
            if q_with_digest.first():
                q = q_with_digest
            elif q.first():
                return {
                    "msg": f"The image '{image}' that you provided has digest "
                    f"'{digest}'. This algorithm version is not approved by the "
                    "store. The currently approved version of this algorithm has"
                    f"digest '{q.first().digest}'. Please include this digest if you"
                    f"want to use that image."
                }, HTTPStatus.BAD_REQUEST

        # paginate results
        try:
            page = Pagination.from_query(q, request, db.Algorithm)
        except (ValueError, AttributeError) as e:
            return {"msg": str(e)}, HTTPStatus.BAD_REQUEST

        # model serialization
        return self.response(page, algorithm_output_schema)

    @with_permission(module_name, Operation.CREATE)
    def post(self):
        """Create new algorithm
        ---
        description: >-
          Create a new algorithm. The algorithm is not yet active. It is
          created in a draft state. The algorithm can be activated by
          changing the status to 'active'.

        requestBody:
          content:
            application/json:
              schema:
                properties:
                  name:
                    type: string
                    description: Name of the algorithm
                  description:
                    type: string
                    description: Description of the algorithm
                  image:
                    type: string
                    description: Docker image URL
                  partitioning:
                    type: string
                    description: Type of partitioning. Can be 'horizontal' or
                      'vertical'
                  vantage6_version:
                    type: string
                    description: Version of vantage6 that the algorithm is
                      built with / for
                  code_url:
                    type: string
                    description: URL to the algorithm code repository
                  documentation_url:
                    type: string
                    description: URL to the algorithm documentation
                  functions:
                    type: array
                    description: List of functions that are available in the
                      algorithm
                    items:
                      properties:
                        name:
                          type: string
                          description: Name of the function
                        description:
                          type: string
                          description: Description of the function
                        type:
                          type: string
                          description: Type of function. Can be 'central' or
                            'federated'
                        databases:
                          type: array
                          description: List of databases that this function
                            uses
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the database in the
                                  function
                              description:
                                type: string
                                description: Description of the database
                        arguments:
                          type: array
                          description: List of arguments that this function
                            uses
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the argument in the
                                  function
                              description:
                                type: string
                                description: Description of the argument
                              type:
                                type: string
                                description: Type of argument. Can be 'string',
                                  'string_list', 'integer', 'integer_list', 'float',
                                  'float_list', 'boolean', 'json', 'column',
                                  'column_list', 'organization' or 'organization_list'
                        ui_visualizations:
                          type: array
                          description: List of visualizations that are available in
                            the algorithm
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the visualization
                              description:
                                type: string
                                description: Description of the visualization
                              type:
                                type: string
                                description: Type of visualization.
                              schema:
                                type: object
                                description: Schema that describes the visualization

        responses:
          201:
            description: Algorithm created successfully
          400:
            description: Invalid input
          401:
            description: Unauthorized

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """
        data = request.get_json()

        # validate the request body
        errors = algorithm_input_post_schema.validate(data)
        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        # validate that the algorithm image exists and retrieve the digest
        image_wo_tag, digest = self._get_image_digest(data["image"])
        if digest is None:
            return {
                "msg": "Image digest could not be determined"
            }, HTTPStatus.BAD_REQUEST

        # create the algorithm
        algorithm = db_Algorithm(
            name=data["name"],
            description=data.get("description", ""),
            image=image_wo_tag,
            partitioning=data["partitioning"],
            vantage6_version=data["vantage6_version"],
            code_url=data["code_url"],
            documentation_url=data.get("documentation_url", None),
            digest=digest,
            developer=g.user,
        )
        algorithm.save()

        # create the algorithm's subresources
        for function in data["functions"]:
            # create the function
            func = Function(
                name=function["name"],
                description=function.get("description", ""),
                type_=function["type"],
                algorithm_id=algorithm.id,
            )
            func.save()
            # create the arguments
            for argument in function.get("arguments", []):
                arg = Argument(
                    name=argument["name"],
                    description=argument.get("description", ""),
                    type_=argument["type"],
                    function_id=func.id,
                )
                arg.save()
            # create the databases
            for database in function.get("databases", []):
                db_ = Database(
                    name=database["name"],
                    description=database.get("description", ""),
                    function_id=func.id,
                )
                db_.save()
            # create the visualizations
            for visualization in function.get("ui_visualizations", []):
                vis = UIVisualization(
                    name=visualization["name"],
                    description=visualization.get("description", ""),
                    type_=visualization["type"],
                    schema=visualization.get("schema", {}),
                    function_id=func.id,
                )
                vis.save()

        return algorithm_output_schema.dump(algorithm, many=False), HTTPStatus.CREATED


class Algorithm(AlgorithmBaseResource):
    """Resource for /algorithm/<id>"""

    @with_permission_to_view_algorithms()
    def get(self, id):
        """Get algorithm
        ---
        description: Return an algorithm specified by ID.

        parameters:
          - in: path
            name: id
            schema:
              type: integer
            description: ID of the algorithm

        responses:
          200:
            description: OK
          401:
            description: Unauthorized
          404:
            description: Algorithm not found

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """
        algorithm = db_Algorithm.get(id)
        if not algorithm:
            return {"msg": "Algorithm not found"}, HTTPStatus.NOT_FOUND

        return algorithm_output_schema.dump(algorithm, many=False), HTTPStatus.OK

    @with_permission(module_name, Operation.DELETE)
    def delete(self, id):
        """Delete algorithm
        ---
        description: Delete an algorithm specified by ID.

        parameters:
          - in: path
            name: id
            schema:
              type: integer
            description: ID of the algorithm

        responses:
          200:
            description: OK
          401:
            description: Unauthorized
          404:
            description: Algorithm not found

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """
        algorithm = db_Algorithm.get(id)
        if not algorithm:
            return {"msg": "Algorithm not found"}, HTTPStatus.NOT_FOUND

        # delete all subresources and finally the algorithm itself
        for function in algorithm.functions:
            for database in function.databases:
                database.delete()
            for argument in function.arguments:
                argument.delete()
            for visualization in function.ui_visualizations:
                visualization.delete()
            function.delete()
        algorithm.delete()

        return {"msg": f"Algorithm id={id} was successfully deleted"}, HTTPStatus.OK

    @with_permission(module_name, Operation.EDIT)
    def patch(self, id):
        """Patch algorithm
        ---
        description: Modify an algorithm specified by ID.

        parameters:
          - in: path
            name: id
            schema:
              type: integer
              minimum: 1
            description: Algorithm id
            required: tr

        requestBody:
          content:
            application/json:
              schema:
                properties:
                  name:
                    type: string
                    description: Name of the algorithm
                  description:
                    type: string
                    description: Description of the algorithm
                  image:
                    type: string
                    description: Docker image URL
                  partitioning:
                    type: string
                    description: Type of partitioning. Can be 'horizontal' or
                      'vertical'
                  vantage6_version:
                    type: string
                    description: Version of vantage6 that the algorithm is
                      built with / for
                  code_url:
                    type: string
                    description: URL to the algorithm code repository
                  documentation_url:
                    type: string
                    description: URL to the algorithm documentation
                  functions:
                    type: array
                    description: List of functions that are available in the
                      algorithm
                    items:
                      properties:
                        name:
                          type: string
                          description: Name of the function
                        description:
                          type: string
                          description: Description of the function
                        type:
                          type: string
                          description: Type of function. Can be 'central' or
                            'federated'
                        databases:
                          type: array
                          description: List of databases that this function
                            uses
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the database in the
                                  function
                              description:
                                type: string
                                description: Description of the database
                        arguments:
                          type: array
                          description: List of arguments that this function
                            uses
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the argument in the
                                  function
                              description:
                                type: string
                                description: Description of the argument
                              type:
                                type: string
                                description: Type of argument. Can be 'string',
                                  'integer', 'float', 'boolean', 'json',
                                  'column', 'organizations' or 'organization'
                        ui_visualizations:
                          type: array
                          description: List of visualizations that are available in
                            the algorithm
                          items:
                            properties:
                              name:
                                type: string
                                description: Name of the visualization
                              description:
                                type: string
                                description: Description of the visualization
                              type:
                                type: string
                                description: Type of visualization.
                              schema:
                                type: object
                                description: Schema that describes the visualization.
                  refresh_digest:
                    type: boolean
                    description: If true, the digest of the image will be refreshed
                      and stored in the database. Note that this is also done whenever
                      the image is changed.

        responses:
          201:
            description: Algorithm created successfully
          400:
            description: Invalid input
          401:
            description: Unauthorized
          403:
            description: Forbidden action

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """
        algorithm = db_Algorithm.get(id)
        if not algorithm:
            return {"msg": "Algorithm not found"}, HTTPStatus.NOT_FOUND

        data = request.get_json()

        # validate the request body
        errors = algorithm_input_patch_schema.validate(data, partial=True)
        if errors:
            return {
                "msg": "Request body is incorrect",
                "errors": errors,
            }, HTTPStatus.BAD_REQUEST

        # algorithms can no longer be edited if they are in the review process or have
        # already been through it.
        if algorithm.approved_at is not None:
            return {
                "msg": "Approved algorithms cannot be edited. Please submit a new "
                "algorithm and go through the review process if you want to update it."
            }, HTTPStatus.FORBIDDEN
        elif algorithm.invalidated_at is not None:
            return {
                "msg": "Invalidated algorithms cannot be edited. Please submit a new "
                "algorithm and go through the review process if you want to update it."
            }, HTTPStatus.FORBIDDEN
        elif algorithm.reviews and any(
            [r.is_review_finished() for r in algorithm.reviews]
        ):
            return {
                "msg": "This algorithm has at least one submitted review, and can "
                "therefore no longer be edited. Please submit a new algorithm and go "
                "through the review process if you want to update this algorithm."
            }, HTTPStatus.FORBIDDEN

        fields = [
            "name",
            "description",
            "partitioning",
            "vantage6_version",
            "code_url",
            "documentation_url",
        ]
        for field in fields:
            if field in data and data.get(field) is not None:
                setattr(algorithm, field, data.get(field))

        image = data.get("image")
        # If image is updated or refresh_digest is set to True, update the digest of the
        # image.
        if image != algorithm.image or data.get("refresh_digest", False):
            image_wo_tag, digest = self._get_image_digest(image)
            if digest is None:
                return {
                    "msg": "Image digest could not be determined"
                }, HTTPStatus.BAD_REQUEST
            algorithm.image = image_wo_tag
            algorithm.digest = digest
        # don't forget to also update the image itself
        if image is not None:
            algorithm.image = image

        if (functions := data.get("functions")) is not None:
            for function in algorithm.functions:
                for argument in function.arguments:
                    argument.delete()
                for db_ in function.databases:
                    db_.delete()
                for visualization in function.ui_visualizations:
                    visualization.delete()
                function.delete()

            for new_function in functions:
                func = Function(
                    name=new_function["name"],
                    description=new_function.get("description", ""),
                    type_=new_function["type"],
                    algorithm_id=id,
                )
                func.save()

                for argument in new_function.get("arguments", []):
                    arg = Argument(
                        name=argument["name"],
                        description=argument.get("description", ""),
                        type_=argument["type"],
                        function_id=func.id,
                    )
                    arg.save()
                for database in new_function.get("databases", []):
                    db = Database(
                        name=database["name"],
                        description=database.get("description", ""),
                        function_id=func.id,
                    )
                    db.save()
                for visualization in new_function.get("ui_visualizations", []):
                    vis = UIVisualization(
                        name=visualization["name"],
                        description=visualization.get("description", ""),
                        type_=visualization["type"],
                        schema=visualization.get("schema", {}),
                        function_id=func.id,
                    )
                    vis.save()

        algorithm.save()

        return algorithm_output_schema.dump(algorithm, many=False), HTTPStatus.OK


class AlgorithmInvalidate(AlgorithmStoreResources):
    """Resource for /algorithm/<id>/invalidate"""

    @with_permission(module_name, Operation.DELETE)
    def post(self, id):
        """Invalidate algorithm

        ---
        description: >-
          Invalidate an algorithm specified by ID. This is an alternative to completely
          removing an algorithm from the store - the advantage of invalidating is that
          the algorithm metadata is still available. This endpoint should be used when
          an algorithm is removed from a project. If on the other hand a newer version
          of the algorithm is uploaded, the old version will be invalidated
          automatically.

        parameters:
          - in: path
            name: id
            schema:
              type: integer
            description: ID of the algorithm

        responses:
          200:
            description: OK
          401:
            description: Unauthorized
          404:
            description: Algorithm not found

        security:
          - bearerAuth: []

        tags: ["Algorithm"]
        """

        algorithm: db.Algorithm = db_Algorithm.get(id)
        if not algorithm:
            return {"msg": "Algorithm not found"}, HTTPStatus.NOT_FOUND

        # invalidate the algorithm
        algorithm.invalidated_at = datetime.datetime.now(datetime.timezone.utc)
        algorithm.status = AlgorithmStatus.REMOVED.value
        algorithm.save()

        # Also invalidate any reviews that were still active
        for review in algorithm.reviews:
            if not review.is_review_finished():
                review.status = ReviewStatus.DROPPED.value
                review.save()

        return {"msg": f"Algorithm id={id} was successfully invalidated"}, HTTPStatus.OK
