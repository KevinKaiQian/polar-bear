import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.getcwd()))) 

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from oslo_db.sqlalchemy import models
import netaddr
from sqlalchemy import (Column, Index, Integer, BigInteger, Enum, String,
                        schema, Unicode)
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from sqlalchemy import orm
from sqlalchemy import ForeignKey, DateTime, Boolean, Text, Float
#from sqlalchemy.dialects import postgresql
#from sqlalchemy import types
from oslo_versionedobjects import _utils
#from oslo_utils import netutils
import datetime
import copy
import six
import abc
import warnings
import uuid
import iso8601
from oslo_utils import timeutils

class KeyTypeError(TypeError):
    def __init__(self, expected, value):
        super(KeyTypeError, self).__init__(
            _('Key %(key)s must be of type %(expected)s not %(actual)s'
              ) % {'key': repr(value),
                   'expected': expected.__name__,
                   'actual': value.__class__.__name__,
                   })


@six.add_metaclass(abc.ABCMeta)
class AbstractFieldType(object):
    @abc.abstractmethod
    def coerce(self, obj, attr, value):
        """This is called to coerce (if possible) a value on assignment.

        This method should convert the value given into the designated type,
        or throw an exception if this is not possible.

        :param:obj: The VersionedObject on which an attribute is being set
        :param:attr: The name of the attribute being set
        :param:value: The value being set
        :returns: A properly-typed value
        """
        pass

    @abc.abstractmethod
    def from_primitive(self, obj, attr, value):
        """This is called to deserialize a value.

        This method should deserialize a value from the form given by
        to_primitive() to the designated type.

        :param:obj: The VersionedObject on which the value is to be set
        :param:attr: The name of the attribute which will hold the value
        :param:value: The serialized form of the value
        :returns: The natural form of the value
        """
        pass

    @abc.abstractmethod
    def to_primitive(self, obj, attr, value):
        """This is called to serialize a value.

        This method should serialize a value to the form expected by
        from_primitive().

        :param:obj: The VersionedObject on which the value is set
        :param:attr: The name of the attribute holding the value
        :param:value: The natural form of the value
        :returns: The serialized form of the value
        """
        pass

    @abc.abstractmethod
    def describe(self):
        """Returns a string describing the type of the field."""
        pass

    @abc.abstractmethod
    def stringify(self, value):
        """Returns a short stringified version of a value."""
        pass
class FieldType(AbstractFieldType):
    @staticmethod
    def coerce(obj, attr, value):
        return value

    @staticmethod
    def from_primitive(obj, attr, value):
        return value

    @staticmethod
    def to_primitive(obj, attr, value):
        return value

    def describe(self):
        return self.__class__.__name__

    def stringify(self, value):
        return str(value)

    def get_schema(self):
        raise NotImplementedError()
class DateTimeFormat(FieldType):
    def __init__(self, tzinfo_aware=True, *args, **kwargs):
        self.tzinfo_aware = tzinfo_aware
        super(DateTimeFormat, self).__init__(*args, **kwargs)

    def coerce(self, obj, attr, value):
        if isinstance(value, six.string_types):
            # NOTE(danms): Being tolerant of isotime strings here will help us
            # during our objects transition
            value = timeutils.parse_isotime(value)
        elif not isinstance(value, datetime.datetime):
            raise ValueError(_('A datetime.datetime is required '
                               'in field %(attr)s, not a %(type)s') %
                             {'attr': attr, 'type': type(value).__name__})

        if value.utcoffset() is None and self.tzinfo_aware:
            # NOTE(danms): Legacy objects from sqlalchemy are stored in UTC,
            # but are returned without a timezone attached.
            # As a transitional aid, assume a tz-naive object is in UTC.
            value = value.replace(tzinfo=iso8601.iso8601.Utc())
        elif not self.tzinfo_aware:
            value = value.replace(tzinfo=None)
        return value

    def from_primitive(self, obj, attr, value):
        return self.coerce(obj, attr, timeutils.parse_isotime(value))

    def get_schema(self):
        return {'type': ['string'], 'format': 'date-time'}

    @staticmethod
    def to_primitive(obj, attr, value):
        return _utils.isotime(value)

    @staticmethod
    def stringify(value):
        return _utils.isotime(value)
class IPAddress(FieldType):
    @staticmethod
    def coerce(obj, attr, value):
        try:
            return netaddr.IPAddress(value)
        except netaddr.AddrFormatError as e:
            raise ValueError(six.text_type(e))

    def from_primitive(self, obj, attr, value):
        return self.coerce(obj, attr, value)

    @staticmethod
    def to_primitive(obj, attr, value):
        return str(value)   
class UUID(FieldType):

    _PATTERN = (r'^[a-fA-F0-9]{8}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]'
                r'{4}-?[a-fA-F0-9]{12}$')

    @staticmethod
    def coerce(obj, attr, value):
        # FIXME(danms): We should actually verify the UUIDness here
        with warnings.catch_warnings():
            warnings.simplefilter("once")
            try:
                uuid.UUID(str(value))
            except Exception:
                # This is to ensure no breaking behaviour for current
                # users
                warnings.warn("%s is an invalid UUID. Using UUIDFields "
                              "with invalid UUIDs is no longer "
                              "supported, and will be removed in a future "
                              "release. Please update your "
                              "code to input valid UUIDs or accept "
                              "ValueErrors for invalid UUIDs. See "
                              "http://docs.openstack.org/developer/oslo.versionedobjects/api/fields.html#oslo_versionedobjects.fields.UUIDField "  # noqa
                              "for further details" % value, FutureWarning)

            return str(value)

    def get_schema(self):
        return {'type': ['string'], 'pattern': self._PATTERN}
class UnspecifiedDefault(object):
    pass
class Field(object):
    def __init__(self, field_type, nullable=False,
                 default=UnspecifiedDefault, read_only=False):
        self._type = field_type
        self._nullable = nullable
        self._default = default
        self._read_only = read_only

    def __repr__(self):
        return '%s(default=%s,nullable=%s)' % (self._type.__class__.__name__,
                                               self._default, self._nullable)

    @property
    def nullable(self):
        return self._nullable

    @property
    def default(self):
        return self._default

    @property
    def read_only(self):
        return self._read_only

    def _null(self, obj, attr):
        if self.nullable:
            return None
        elif self._default != UnspecifiedDefault:
            # NOTE(danms): We coerce the default value each time the field
            # is set to None as our contract states that we'll let the type
            # examine the object and attribute name at that time.
            return self._type.coerce(obj, attr, copy.deepcopy(self._default))
        else:
            raise ValueError(_("Field `%s' cannot be None") % attr)

    def coerce(self, obj, attr, value):
        """Coerce a value to a suitable type.

        This is called any time you set a value on an object, like:

          foo.myint = 1

        and is responsible for making sure that the value (1 here) is of
        the proper type, or can be sanely converted.

        This also handles the potentially nullable or defaultable
        nature of the field and calls the coerce() method on a
        FieldType to actually do the coercion.

        :param:obj: The object being acted upon
        :param:attr: The name of the attribute/field being set
        :param:value: The value being set
        :returns: The properly-typed value
        """
        if value is None:
            return self._null(obj, attr)
        else:
            return self._type.coerce(obj, attr, value)

    def from_primitive(self, obj, attr, value):
        """Deserialize a value from primitive form.

        This is responsible for deserializing a value from primitive
        into regular form. It calls the from_primitive() method on a
        FieldType to do the actual deserialization.

        :param:obj: The object being acted upon
        :param:attr: The name of the attribute/field being deserialized
        :param:value: The value to be deserialized
        :returns: The deserialized value
        """
        if value is None:
            return None
        else:
            return self._type.from_primitive(obj, attr, value)

    def to_primitive(self, obj, attr, value):
        """Serialize a value to primitive form.

        This is responsible for serializing a value to primitive
        form. It calls to_primitive() on a FieldType to do the actual
        serialization.

        :param:obj: The object being acted upon
        :param:attr: The name of the attribute/field being serialized
        :param:value: The value to be serialized
        :returns: The serialized value
        """
        if value is None:
            return None
        else:
            return self._type.to_primitive(obj, attr, value)

    def describe(self):
        """Return a short string describing the type of this field."""
        name = self._type.describe()
        prefix = self.nullable and 'Nullable' or ''
        return prefix + name

    def stringify(self, value):
        if value is None:
            return 'None'
        else:
            return self._type.stringify(value)

    def get_schema(self):
        schema = self._type.get_schema()
        schema.update({'readonly': self.read_only})
        if self.nullable:
            schema['type'].append('null')
        default = self.default
        if default != UnspecifiedDefault:
            schema.update({'default': default})
        return schema
class AutoTypedField(Field):
    AUTO_TYPE = None

    def __init__(self, **kwargs):
        super(AutoTypedField, self).__init__(self.AUTO_TYPE, **kwargs)
class CoercedCollectionMixin(object):
    def __init__(self, *args, **kwargs):
        self._element_type = None
        self._obj = None
        self._field = None
        super(CoercedCollectionMixin, self).__init__(*args, **kwargs)

    def enable_coercing(self, element_type, obj, field):
        self._element_type = element_type
        self._obj = obj
        self._field = field

class CoercedDict(CoercedCollectionMixin, dict):
    """Dict which coerces its values

    Dict implementation which overrides all element-adding methods and
    coercing the element(s) being added to the required element type
    """

    def _coerce_dict(self, d):
        res = {}
        for key, element in six.iteritems(d):
            res[key] = self._coerce_item(key, element)
        return res

    def _coerce_item(self, key, item):
        if not isinstance(key, six.string_types):
            # NOTE(guohliu) In order to keep compatibility with python3
            # we need to use six.string_types rather than basestring here,
            # since six.string_types is a tuple, so we need to pass the
            # real type in.
            raise KeyTypeError(six.string_types[0], key)
        if hasattr(self, "_element_type") and self._element_type is not None:
            att_name = "%s[%s]" % (self._field, key)
            return self._element_type.coerce(self._obj, att_name, item)
        else:
            return item

    def __setitem__(self, key, value):
        super(CoercedDict, self).__setitem__(key,
                                             self._coerce_item(key, value))

    def update(self, other=None, **kwargs):
        if other is not None:
            super(CoercedDict, self).update(self._coerce_dict(other),
                                            **self._coerce_dict(kwargs))
        else:
            super(CoercedDict, self).update(**self._coerce_dict(kwargs))

    def setdefault(self, key, default=None):
        return super(CoercedDict, self).setdefault(key,
                                                   self._coerce_item(key,
                                                                     default))
class CompoundFieldType(FieldType):
    def __init__(self, element_type, **field_args):
        self._element_type = Field(element_type, **field_args)
class Dict(CompoundFieldType):
    def coerce(self, obj, attr, value):
        if not isinstance(value, dict):
            raise ValueError(_('A dict is required in field %(attr)s, '
                               'not a %(type)s') %
                             {'attr': attr, 'type': type(value).__name__})
        coerced_dict = CoercedDict()
        coerced_dict.enable_coercing(self._element_type, obj, attr)
        coerced_dict.update(value)
        return coerced_dict

    def to_primitive(self, obj, attr, value):
        primitive = {}
        for key, element in value.items():
            primitive[key] = self._element_type.to_primitive(
                obj, '%s["%s"]' % (attr, key), element)
        return primitive

    def from_primitive(self, obj, attr, value):
        concrete = {}
        for key, element in value.items():
            concrete[key] = self._element_type.from_primitive(
                obj, '%s["%s"]' % (attr, key), element)
        return concrete

    def stringify(self, value):
        return '{%s}' % (
            ','.join(['%s=%s' % (key, self._element_type.stringify(val))
                      for key, val in sorted(value.items())]))

    def get_schema(self):
        return {'type': ['object']}
class IntegerField(AutoTypedField):
    AUTO_TYPE = Integer()
class UUIDField(AutoTypedField):
    """UUID Field Type

    .. warning::

        This class does not actually validate UUIDs. This will happen in a
        future major version of oslo.versionedobjects

    To validate that you have valid UUIDs you need to do the following in
    your own objects/fields.py

    :Example:
         .. code-block:: python

            import oslo_versionedobjects.fields as ovo_fields

            class UUID(ovo_fields.UUID):
                 def coerce(self, obj, attr, value):
                    uuid.UUID(value)
                    return str(value)


            class UUIDField(ovo_fields.AutoTypedField):
                AUTO_TYPE = UUID()

        and then in your objects use
        ``<your_projects>.object.fields.UUIDField``.

    This will become default behaviour in the future.
    """
    AUTO_TYPE = UUID()
class FloatField(AutoTypedField):
    AUTO_TYPE = Float()
class StringField(AutoTypedField):
    AUTO_TYPE = String()
class IPAddressField(AutoTypedField):
    AUTO_TYPE = IPAddress()
class DictOfNullableStringsField(AutoTypedField):
    AUTO_TYPE = Dict(String(), nullable=True)
class BooleanField(AutoTypedField):
    AUTO_TYPE = Boolean()   
class DateTimeField(AutoTypedField):
    def __init__(self, tzinfo_aware=True, **kwargs):
        self.AUTO_TYPE = DateTimeFormat(tzinfo_aware=tzinfo_aware)
        super(DateTimeField, self).__init__(**kwargs)
        
BASE = declarative_base()

def get_shortened_ipv6(address):
    addr = netaddr.IPAddress(address, version=6)
    return str(addr.ipv6())
'''
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

'''

def MediumText():
    return Text().with_variant(MEDIUMTEXT(), 'mysql')

class NovaBase(models.TimestampMixin,
               models.ModelBase):
    metadata = None

    def __copy__(self):
        """Implement a safe copy.copy().

        SQLAlchemy-mapped objects travel with an object
        called an InstanceState, which is pegged to that object
        specifically and tracks everything about that object.  It's
        critical within all attribute operations, including gets
        and deferred loading.   This object definitely cannot be
        shared among two instances, and must be handled.

        The copy routine here makes use of session.merge() which
        already essentially implements a "copy" style of operation,
        which produces a new instance with a new InstanceState and copies
        all the data along mapped attributes without using any SQL.

        The mode we are using here has the caveat that the given object
        must be "clean", e.g. that it has no database-loaded state
        that has been updated and not flushed.   This is a good thing,
        as creating a copy of an object including non-flushed, pending
        database state is probably not a good idea; neither represents
        what the actual row looks like, and only one should be flushed.

        """
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

    id = IntegerField(read_only=True)
    host1 = StringField(nullable=True) # , ForeignKey('hosts.id'))
    binary = StringField(nullable=True)
    topic = StringField(nullable=True)
    report_count = IntegerField()
    disabled = BooleanField()
    disabled_reason = StringField(nullable=True)
    last_seen_up = DateTimeField(nullable=True)
    forced_down = BooleanField()
    version = IntegerField()
    
    


    #instance = orm.relationship(
    #    "Instance",
    #    backref='services',
    #    primaryjoin='and_(Service.host == Instance.host,'
    #                'Service.binary == "nova-compute",'
    #                'Instance.deleted == 0)',
    #    foreign_keys=host,
    
class ComputeNode(BASE, NovaBase, models.SoftDeleteMixin):

    __tablename__ = 'compute_nodes'
    __table_args__ = (
        schema.UniqueConstraint(
            'host', 'hypervisor_hostname', 'deleted',
            name="uniq_compute_nodes0host0hypervisor_hostname0deleted"),
    )

    
    VERSION = '1.16'

    id= IntegerField(read_only=True)
    uuid= UUIDField(read_only=True)
    service_id= IntegerField(nullable=True)
    host= StringField(nullable=True)
    vcpus= IntegerField()
    memory_mb= IntegerField()
    local_gb= IntegerField()
    vcpus_used= IntegerField()
    memory_mb_used= IntegerField()
    local_gb_used= IntegerField()
    hypervisor_type= StringField()
    hypervisor_version= IntegerField()
    hypervisor_hostname= StringField(nullable=True)
    free_ram_mb= IntegerField(nullable=True)
    free_disk_gb= IntegerField(nullable=True)
    current_workload= IntegerField(nullable=True)
    running_vms= IntegerField(nullable=True)
    cpu_info= StringField(nullable=True)
    disk_available_least= IntegerField(nullable=True)
    metrics= StringField(nullable=True)
    stats= DictOfNullableStringsField(nullable=True)
    host_ip= IPAddressField(nullable=True)
    numa_topology= StringField(nullable=True)
    cpu_allocation_ratio= FloatField()
    ram_allocation_ratio= FloatField()
    disk_allocation_ratio= FloatField()

'''
class ComputeNode2(BASE, NovaBase, models.SoftDeleteMixin):
    """Represents a running compute service on a host."""

    __tablename__ = 'compute_nodes'
    __table_args__ = (
        schema.UniqueConstraint(
            'host', 'hypervisor_hostname', 'deleted',
            name="uniq_compute_nodes0host0hypervisor_hostname0deleted"),
    )
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, nullable=True)

    # FIXME(sbauza: Host field is nullable because some old Juno compute nodes
    # can still report stats from an old ResourceTracker without setting this
    # field.
    # This field has to be set non-nullable in a later cycle (probably Lxxx)
    # once we are sure that all compute nodes in production report it.
    host = Column(String(255), nullable=True)
    uuid = Column(String(36), nullable=True)
    vcpus = Column(Integer, nullable=False)
    memory_mb = Column(Integer, nullable=False)
    local_gb = Column(Integer, nullable=False)
    vcpus_used = Column(Integer, nullable=False)
    memory_mb_used = Column(Integer, nullable=False)
    local_gb_used = Column(Integer, nullable=False)
    hypervisor_type = Column(MediumText(), nullable=False)
    hypervisor_version = Column(Integer, nullable=False)
    hypervisor_hostname = Column(String(255))

    # Free Ram, amount of activity (resize, migration, boot, etc) and
    # the number of running VM's are a good starting point for what's
    # important when making scheduling decisions.
    free_ram_mb = Column(Integer)
    free_disk_gb = Column(Integer)
    current_workload = Column(Integer)
    running_vms = Column(Integer)

    # Note(masumotok): Expected Strings example:
    #
    # '{"arch":"x86_64",
    #   "model":"Nehalem",
    #   "topology":{"sockets":1, "threads":2, "cores":3},
    #   "features":["tdtscp", "xtpr"]}'
    #
    # Points are "json translatable" and it must have all dictionary keys
    # above, since it is copied from <cpu> tag of getCapabilities()
    # (See libvirt.virtConnection).
    cpu_info = Column(MediumText(), nullable=False)
    disk_available_least = Column(Integer)
    host_ip = Column(IPAddress())
    supported_instances = Column(Text)
    metrics = Column(Text)

    # Note(yongli): json string PCI Stats
    # '[{"vendor_id":"8086", "product_id":"1234", "count":3 }, ...]'
    pci_stats = Column(Text)

    # extra_resources is a json string containing arbitrary
    # data about additional resources.
    extra_resources = Column(Text)

    # json-encode string containing compute node statistics
    stats = Column(Text, default='{}')

    # json-encoded dict that contains NUMA topology as generated by
    # objects.NUMATopology._to_json()
    numa_topology = Column(Text)

    # allocation ratios provided by the RT
    ram_allocation_ratio = Column(Float, nullable=True)
    cpu_allocation_ratio = Column(Float, nullable=True)
    disk_allocation_ratio = Column(Float, nullable=True)

'''

engine = create_engine('mysql+mysqldb://root:t-span@192.168.1.99/nova?charset=utf8')
BASE.metadata.create_all(engine)
