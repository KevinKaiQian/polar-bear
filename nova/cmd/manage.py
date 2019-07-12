# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.getcwd()))) 
from oslo_log import log as logging
from nova.db.sqlalchemy import api as db_session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from oslo_db.sqlalchemy import models
import netaddr
from sqlalchemy import (Column, Index, Integer, BigInteger, Enum, String,
                        schema, Unicode)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy import orm
from sqlalchemy import ForeignKey, DateTime, Boolean, Text, Float
from sqlalchemy.dialects import postgresql
from sqlalchemy import types
from oslo_utils import netutils
from oslo_utils import timeutils
LOG = logging.getLogger(__name__)

BASE = declarative_base()

def get_engine(database='main', context=None):
    if database == 'main':
        return db_session.get_engine(context=context)
    if database == 'api':
        return db_session.get_api_engine()

def get_shortened_ipv6(address):
    addr = netaddr.IPAddress(address, version=6)
    return str(addr.ipv6())

class IPAddress(types.TypeDecorator):
    """An SQLAlchemy type representing an IP-address."""

    impl = types.String

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(postgresql.INET())
        else:
            return dialect.type_descriptor(types.String(39))

    def process_bind_param(self, value, dialect):
        """Process/Formats the value before insert it into the db."""
        if dialect.name == 'postgresql':
            return value
        # NOTE(maurosr): The purpose here is to convert ipv6 to the shortened
        # form, not validate it.
        elif netutils.is_valid_ipv6(value):
            return get_shortened_ipv6(value)
        return value

def MediumText():
    return Text().with_variant(MEDIUMTEXT(), 'mysql')

class NovaBase(models.TimestampMixin,
               models.ModelBase):
    metadata = None

    def __copy__(self):

        session = orm.Session()

        copy = session.merge(self, load=False)
        session.expunge(copy)
        return copy

class Service(BASE, NovaBase, models.SoftDeleteMixin):
    """Represents a running service on a host."""

    __tablename__ = 'services'
    __table_args__ = (
        schema.UniqueConstraint("host", "topic", "deleted",
                                name="uniq_services0host0topic0deleted"),
        schema.UniqueConstraint("host", "binary", "deleted",
                                name="uniq_services0host0binary0deleted")
        )

    id = Column(Integer, primary_key=True)
    host = Column(String(255))  # , ForeignKey('hosts.id'))
    binary = Column(String(255))
    topic = Column(String(255))
    report_count = Column(Integer, nullable=False, default=0)
    disabled = Column(Boolean, default=False)
    disabled_reason = Column(String(255))
    last_seen_up = Column(DateTime, nullable=True)
    forced_down = Column(Boolean, default=False)
    version = Column(Integer, default=0)


class ComputeNode(BASE, NovaBase, models.SoftDeleteMixin):
    """Represents a running compute service on a host."""

    __tablename__ = 'compute_nodes'
    __table_args__ = (
        schema.UniqueConstraint(
            'host', 'deleted',
            name="uniq_compute_nodes0host0hypervisor_hostname0deleted"),
    )
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, nullable=True)
    host = Column(String(255), nullable=True)
    uuid = Column(String(36), nullable=True)
    compute_node_type = Column(String(255), nullable=True)
    compute_node_method = Column(MediumText(), nullable=False)


class TestCase(BASE, NovaBase, models.SoftDeleteMixin):

    __tablename__ = 'TestCase'
    __table_args__ = (
        schema.UniqueConstraint(
            'case_name', 'host', 'beginning', 'ending',
            name="uniq_test_case0case_name0host0beginning0ending"
        ),
    )
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    uuid = Column(String(36), nullable=True)
    case_name = Column(String(255), default="0")
    status = Column(String(255), default="0")
    host = Column(String(255), default="0")
    beginning = Column(DateTime, default=timeutils.utcnow,
                              nullable=True)
    ending = Column(DateTime, default=timeutils.utcnow,
                           nullable=True)
    message = Column(MediumText(), nullable=True)
    errors = Column(Integer(), default=0)
   
class TestPlan(BASE, NovaBase, models.SoftDeleteMixin):

    __tablename__ = 'TestPlan'
    __table_args__ = (
        schema.UniqueConstraint(
            'testplan_name', 'beginning', 'ending',
            name="uniq_test_case0case_name0host0beginning0ending"
        ),
    )
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    uuid = Column(String(36), nullable=True)
    testplan_name = Column(String(255), default="0")
    status = Column(String(255), default="0")
    beginning = Column(DateTime, default=timeutils.utcnow,
                              nullable=True)
    ending = Column(DateTime, default=timeutils.utcnow,
                           nullable=True)
    message = Column(MediumText(), default="")
    result = Column(String(255), default="{}")
    summary = Column(String(255), default="{}")

if __name__ == "__main__":
    engine = get_engine()
    BASE.metadata.create_all(engine)






   