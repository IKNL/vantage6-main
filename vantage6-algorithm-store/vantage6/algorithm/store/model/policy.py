from sqlalchemy import Column, String

from vantage6.algorithm.store.model.base import Base, DatabaseSessionManager
from vantage6.common.enum import StorePolicies


class Policy(Base):
    """
    Table that describes the policies of this algorithm store.

    Attributes
    ----------
    key: str
        Key of the setting
    value: str
        Value of the setting
    """

    key = Column(String)
    value = Column(String)

    @classmethod
    def get_as_dict(cls) -> dict[str, str]:
        """
        Get the policies as a dictionary.

        Returns
        -------
        dict[str, str]
            Dictionary of policies
        """
        session = DatabaseSessionManager.get_session()
        result = session.query(cls).all()
        session.commit()
        return {r.key: r.value for r in result}

    @classmethod
    def get_servers_allowed_to_be_whitelisted(cls) -> list[str]:
        """
        Get the servers that are allowed to be whitelisted.

        Returns
        -------
        list[str]
            List of servers that are allowed to be whitelisted
        """
        session = DatabaseSessionManager.get_session()
        result = session.query(cls).filter_by(key=StorePolicies.ALLOWED_SERVERS).all()
        session.commit()
        return [r.value for r in result]

    @classmethod
    def is_localhost_allowed_to_be_whitelisted(cls) -> bool:
        """
        Check if localhost is allowed to be whitelisted.

        Returns
        -------
        bool
            True if localhost is allowed to be whitelisted, False otherwise
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls)
            .filter_by(key=StorePolicies.ALLOW_LOCALHOST)
            .one_or_none()
        )
        session.commit()
        if result is None:
            return False
        return result.value == "True" or result.value == "1"

    @classmethod
    def get_servers_with_edit_permission(cls) -> list[str]:
        """
        Get the servers that have edit permission.

        Returns
        -------
        list[str]
            List of servers that have edit permission
        """
        session = DatabaseSessionManager.get_session()
        result = session.query(cls).filter_by(key=StorePolicies.ALLOWED_SERVERS).all()
        session.commit()
        return [r.value for r in result]

    @classmethod
    def get_minimum_reviewers(cls) -> int:
        """
        Get the minimum number of reviewers for approving the algorithms.

        Returns
        -------
        int
            Minimum number of reviewers
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls).filter_by(key=StorePolicies.MIN_REVIEWERS).one_or_none()
        )
        session.commit()
        if result is None:
            return 2
        return int(result.value)

    @classmethod
    def is_developer_allowed_assign_review(cls):
        """
        Check if developers are allowed to assign reviews to their own algorithms.

        Returns
        -------
        bool
            True if developers are allowed to assign reviews to their own algorithms,
            False otherwise
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls)
            .filter_by(key=StorePolicies.ASSIGN_REVIEW_OWN_ALGORITHM)
            .one_or_none()
        )
        session.commit()
        if result is None:
            return False
        return result.value == "True" or result.value == "1"

    @classmethod
    def get_minimum_reviewing_orgs(cls) -> int:
        """
        Get the minimum number of organizations that have to be involved in the review process.

        Returns
        -------
        int
            Minimum number of reviewers
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls)
            .filter_by(key=StorePolicies.MIN_REVIEWING_ORGANIZATIONS)
            .one_or_none()
        )
        session.commit()
        if result is None:
            return 1
        return int(result.value)

    @classmethod
    def is_user_allowed_to_assign_review(cls, user_id: int) -> bool:
        """
        Check if a user is allowed to assign reviews.

        Parameters
        ----------
        user_id : int
            Id of the user

        Returns
        -------
        bool
            True if users are allowed to assign reviews, False otherwise
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls)
            .filter_by(key=StorePolicies.ALLOWED_REVIEW_ASSIGNERS.value)
            .all()
        )

        session.commit()

        if result is None or len(result) == 0:
            # if the policy has not been set, allow all users to assign reviews
            return True
        else:
            result = next((r for r in result if r.value == str(user_id)), None)

        if result is None:
            return False
        return True

    @classmethod
    def is_user_allowed_to_review(cls, user_id: int) -> bool:
        """
        Check if a user is allowed to perform a review.

        Parameters
        ----------
        user_id : int
            Id of the user

        Returns
        -------
        bool
            True if users are allowed to perform a review, False otherwise
        """
        session = DatabaseSessionManager.get_session()
        result = (
            session.query(cls)
            .filter_by(key=StorePolicies.ALLOWED_REVIEWERS.value)
            .one_or_none()
        )
        session.commit()

        if result is None or len(result) == 0:
            # if the policy has not been set, allow all users to review
            return True
        else:
            result = next((r for r in result if r.value == str(user_id)), None)

        if result is None:
            return False
        return True
