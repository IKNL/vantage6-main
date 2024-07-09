"""
The Permission table defines which roles have been assigned to which users.
It can contain multiple entries for the same user if they have been assigned
multiple roles.

The UserPermission table defines which extra rules have been assigned to which
users. Apart from roles, users may be assigned extra permissions that allow
them to execute one specific action. This table is used to store those, and
may contain multiple entries for the same user.
"""

from sqlalchemy import Column, Integer, ForeignKey, Table

from vantage6.common.base import Base


Permission = Table(
    "Permission",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.id")),
    Column("role_id", Integer, ForeignKey("role.id")),
)

# TODO when this is activated, also include the changes in the rule endpoints (e.g.
# where there is a filter by user)
# TODO: integrate this with the Permission model from the v6 server
# UserPermission = Table(
#     'UserPermission',
#     Base.metadata,
#     Column('rule_id', Integer, ForeignKey('rule.id')),
#     Column('user_id', Integer, ForeignKey('user.id'))
# )
