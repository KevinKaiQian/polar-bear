
import base64
import collections
import copy
import functools
import re
import string
import uuid

from oslo_log import log as logging
from oslo_messaging import exceptions as oslo_exceptions
from oslo_serialization import jsonutils
from oslo_utils import excutils
from oslo_utils import strutils
from oslo_utils import timeutils
from oslo_utils import units

from oslo_utils import uuidutils
import six


from nova.compute import rpcapi as compute_rpcapi

from nova.compute import utils as compute_utils

from nova import conductor

from nova import config
from nova import hooks

from nova import context as nova_context
from nova import crypto
from nova.db import base
from nova import exception
from nova import exception_wrapper

from nova.i18n import _
from nova.i18n import _LE
from nova.i18n import _LI
from nova.i18n import _LW


from nova import notifications
from nova import objects
from nova.objects import base as obj_base

from nova.objects import fields as fields_obj
from nova.objects import keypair as keypair_obj
from nova.objects import quotas as quotas_obj

from nova import rpc
from nova import servicegroup
from nova import utils


LOG = logging.getLogger(__name__)

get_notifier = functools.partial(rpc.get_notifier, service='compute')
# NOTE(gibi): legacy notification used compute as a service but these
# calls still run on the client side of the compute service which is
# nova-api. By setting the binary to nova-api below, we can make sure
# that the new versioned notifications has the right publisher_id but the
# legacy notifications does not change.
wrap_exception = functools.partial(exception_wrapper.wrap_exception,
                                   get_notifier=get_notifier,
                                   binary='nova-api')
CONF = config.CONF

MAX_USERDATA_SIZE = 65535
RO_SECURITY_GROUPS = ['default']
VIDEO_RAM = 'hw_video:ram_max_mb'

AGGREGATE_ACTION_UPDATE = 'Update'
AGGREGATE_ACTION_UPDATE_META = 'UpdateMeta'
AGGREGATE_ACTION_DELETE = 'Delete'
AGGREGATE_ACTION_ADD = 'Add'


def check_instance_state(vm_state=None, task_state=(None,),
                         must_have_launched=True):
    """Decorator to check VM and/or task state before entry to API functions.

    If the instance is in the wrong state, or has not been successfully
    started at least once the wrapper will raise an exception.
    """

    if vm_state is not None and not isinstance(vm_state, set):
        vm_state = set(vm_state)
    if task_state is not None and not isinstance(task_state, set):
        task_state = set(task_state)

    def outer(f):
        @functools.wraps(f)
        def inner(self, context, instance, *args, **kw):
            if vm_state is not None and instance.vm_state not in vm_state:
                raise exception.InstanceInvalidState(
                    attr='vm_state',
                    instance_uuid=instance.uuid,
                    state=instance.vm_state,
                    method=f.__name__)
            if (task_state is not None and
                    instance.task_state not in task_state):
                raise exception.InstanceInvalidState(
                    attr='task_state',
                    instance_uuid=instance.uuid,
                    state=instance.task_state,
                    method=f.__name__)
            if must_have_launched and not instance.launched_at:
                raise exception.InstanceInvalidState(
                    attr='launched_at',
                    instance_uuid=instance.uuid,
                    state=instance.launched_at,
                    method=f.__name__)

            return f(self, context, instance, *args, **kw)
        return inner
    return outer


def check_instance_host(function):
    @functools.wraps(function)
    def wrapped(self, context, instance, *args, **kwargs):
        if not instance.host:
            raise exception.InstanceNotReady(instance_id=instance.uuid)
        return function(self, context, instance, *args, **kwargs)
    return wrapped


def check_instance_lock(function):
    @functools.wraps(function)
    def inner(self, context, instance, *args, **kwargs):
        if instance.locked and not context.is_admin:
            raise exception.InstanceIsLocked(instance_uuid=instance.uuid)
        return function(self, context, instance, *args, **kwargs)
    return inner


def check_instance_cell(fn):
    def _wrapped(self, context, instance, *args, **kwargs):
        self._validate_cell(instance)
        return fn(self, context, instance, *args, **kwargs)
    _wrapped.__name__ = fn.__name__
    return _wrapped


def _diff_dict(orig, new):
    """Return a dict describing how to change orig to new.  The keys
    correspond to values that have changed; the value will be a list
    of one or two elements.  The first element of the list will be
    either '+' or '-', indicating whether the key was updated or
    deleted; if the key was updated, the list will contain a second
    element, giving the updated value.
    """
    # Figure out what keys went away
    result = {k: ['-'] for k in set(orig.keys()) - set(new.keys())}
    # Compute the updates
    for key, value in new.items():
        if key not in orig or value != orig[key]:
            result[key] = ['+', value]
    return result


class API(base.Base):
    """API for interacting with the compute manager."""

    def __init__(self, image_api=None, network_api=None, volume_api=None,
                 security_group_api=None, **kwargs):

        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.compute_task_api = conductor.ComputeTaskAPI()
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)


        super(API, self).__init__(**kwargs)






class CaseAPI(base.Base):
    """API for interacting with the compute manager."""

    def __init__(self, image_api=None, network_api=None, volume_api=None,
                 security_group_api=None, **kwargs):

        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.compute_task_api = conductor.ComputeTaskAPI()
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)


        super(API, self).__init__(**kwargs)
        


class HostAPI(base.Base):
    """Sub-set of the Compute Manager API for managing host operations."""

    def __init__(self, rpcapi=None):
        self.rpcapi = rpcapi or compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        super(HostAPI, self).__init__()

    def _assert_host_exists(self, context, host_name, must_be_up=False):
        """Raise HostNotFound if compute host doesn't exist."""
        service = objects.Service.get_by_compute_host(context, host_name)
        if not service:
            raise exception.HostNotFound(host=host_name)
        if must_be_up and not self.servicegroup_api.service_is_up(service):
            raise exception.ComputeServiceUnavailable(host=host_name)
        return service['host']

    @wrap_exception()
    def set_host_enabled(self, context, host_name, enabled):
        """Sets the specified host's ability to accept new instances."""
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'enabled': enabled}
        compute_utils.notify_about_host_update(context,
                                               'set_enabled.start',
                                               payload)
        result = self.rpcapi.set_host_enabled(context, enabled=enabled,
                host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'set_enabled.end',
                                               payload)
        return result

    def get_host_uptime(self, context, host_name):
        """Returns the result of calling "uptime" on the target host."""
        host_name = self._assert_host_exists(context, host_name,
                         must_be_up=True)
        return self.rpcapi.get_host_uptime(context, host=host_name)

    @wrap_exception()
    def host_power_action(self, context, host_name, action):
        """Reboots, shuts down or powers up the host."""
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'action': action}
        compute_utils.notify_about_host_update(context,
                                               'power_action.start',
                                               payload)
        result = self.rpcapi.host_power_action(context, action=action,
                host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'power_action.end',
                                               payload)
        return result

    @wrap_exception()
    def set_host_maintenance(self, context, host_name, mode):
        """Start/Stop host maintenance window. On start, it triggers
        guest VMs evacuation.
        """
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'mode': mode}
        compute_utils.notify_about_host_update(context,
                                               'set_maintenance.start',
                                               payload)
        result = self.rpcapi.host_maintenance_mode(context,
                host_param=host_name, mode=mode, host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'set_maintenance.end',
                                               payload)
        return result

    def service_get_all(self, context, filters=None, set_zones=False):
        """Returns a list of services, optionally filtering the results.

        If specified, 'filters' should be a dictionary containing services
        attributes and matching values.  Ie, to get a list of services for
        the 'compute' topic, use filters={'topic': 'compute'}.
        """
        if filters is None:
            filters = {}
        disabled = filters.pop('disabled', None)
        if 'availability_zone' in filters:
            set_zones = True
        services = objects.ServiceList.get_all(context, disabled,
                                               set_zones=set_zones)
        ret_services = []
        for service in services:
            for key, val in six.iteritems(filters):
                if service[key] != val:
                    break
            else:
                # All filters matched.
                ret_services.append(service)
        return ret_services

    def service_get_by_id(self, context, service_id):
        """Get service entry for the given service id."""
        return objects.Service.get_by_id(context, service_id)

    def service_get_by_compute_host(self, context, host_name):
        """Get service entry for the given compute hostname."""
        return objects.Service.get_by_compute_host(context, host_name)

    def _service_update(self, context, host_name, binary, params_to_update):
        """Performs the actual service update operation."""
        service = objects.Service.get_by_args(context, host_name, binary)
        service.update(params_to_update)
        service.save()
        return service

    def service_update(self, context, host_name, binary, params_to_update):
        """Enable / Disable a service.

        For compute services, this stops new builds and migrations going to
        the host.
        """
        return self._service_update(context, host_name, binary,
                                    params_to_update)

    def _service_delete(self, context, service_id):
        """Performs the actual Service deletion operation."""
        objects.Service.get_by_id(context, service_id).destroy()

    def service_delete(self, context, service_id):
        """Deletes the specified service."""
        self._service_delete(context, service_id)

    def instance_get_all_by_host(self, context, host_name):
        """Return all instances on the given host."""
        return objects.InstanceList.get_by_host(context, host_name)

    def task_log_get_all(self, context, task_name, period_beginning,
                         period_ending, host=None, state=None):
        """Return the task logs within a given range, optionally
        filtering by host and/or state.
        """
        return self.db.task_log_get_all(context, task_name,
                                        period_beginning,
                                        period_ending,
                                        host=host,
                                        state=state)

    def compute_node_get(self, context, compute_id):
        """Return compute node entry for particular integer ID."""
        return objects.ComputeNode.get_by_id(context, int(compute_id))

    def compute_node_get_all(self, context, limit=None, marker=None):
        return objects.ComputeNodeList.get_by_pagination(
            context, limit=limit, marker=marker)

    def compute_node_search_by_hypervisor(self, context, hypervisor_match):
        return objects.ComputeNodeList.get_by_hypervisor(context,
                                                         hypervisor_match)

    def compute_node_statistics(self, context):
        return self.db.compute_node_statistics(context)


class InstanceActionAPI(base.Base):
    """Sub-set of the Compute Manager API for managing instance actions."""

    def actions_get(self, context, instance):
        return objects.InstanceActionList.get_by_instance_uuid(
            context, instance.uuid)

    def action_get_by_request_id(self, context, instance, request_id):
        return objects.InstanceAction.get_by_request_id(
            context, instance.uuid, request_id)

    def action_events_get(self, context, instance, action_id):
        return objects.InstanceActionEventList.get_by_action(
            context, action_id)


class AggregateAPI(base.Base):
    """Sub-set of the Compute Manager API for managing host aggregates."""
    def __init__(self, **kwargs):
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.scheduler_client = scheduler_client.SchedulerClient()
        super(AggregateAPI, self).__init__(**kwargs)

    @wrap_exception()
    def create_aggregate(self, context, aggregate_name, availability_zone):
        """Creates the model for the aggregate."""

        aggregate = objects.Aggregate(context=context)
        aggregate.name = aggregate_name
        if availability_zone:
            aggregate.metadata = {'availability_zone': availability_zone}
        aggregate.create()
        self.scheduler_client.update_aggregates(context, [aggregate])
        return aggregate

    def get_aggregate(self, context, aggregate_id):
        """Get an aggregate by id."""
        return objects.Aggregate.get_by_id(context, aggregate_id)

    def get_aggregate_list(self, context):
        """Get all the aggregates."""
        return objects.AggregateList.get_all(context)

    def get_aggregates_by_host(self, context, compute_host):
        """Get all the aggregates where the given host is presented."""
        return objects.AggregateList.get_by_host(context, compute_host)

    @wrap_exception()
    def update_aggregate(self, context, aggregate_id, values):
        """Update the properties of an aggregate."""
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        if 'name' in values:
            aggregate.name = values.pop('name')
            aggregate.save()
        self.is_safe_to_update_az(context, values, aggregate=aggregate,
                                  action_name=AGGREGATE_ACTION_UPDATE)
        if values:
            aggregate.update_metadata(values)
            aggregate.updated_at = timeutils.utcnow()
        self.scheduler_client.update_aggregates(context, [aggregate])
        # If updated values include availability_zones, then the cache
        # which stored availability_zones and host need to be reset
        if values.get('availability_zone'):
            availability_zones.reset_cache()
        return aggregate

    @wrap_exception()
    def update_aggregate_metadata(self, context, aggregate_id, metadata):
        """Updates the aggregate metadata."""
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        self.is_safe_to_update_az(context, metadata, aggregate=aggregate,
                                  action_name=AGGREGATE_ACTION_UPDATE_META)
        aggregate.update_metadata(metadata)
        self.scheduler_client.update_aggregates(context, [aggregate])
        # If updated metadata include availability_zones, then the cache
        # which stored availability_zones and host need to be reset
        if metadata and metadata.get('availability_zone'):
            availability_zones.reset_cache()
        aggregate.updated_at = timeutils.utcnow()
        return aggregate

    @wrap_exception()
    def delete_aggregate(self, context, aggregate_id):
        """Deletes the aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id}
        compute_utils.notify_about_aggregate_update(context,
                                                    "delete.start",
                                                    aggregate_payload)
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        if len(aggregate.hosts) > 0:
            msg = _("Host aggregate is not empty")
            raise exception.InvalidAggregateActionDelete(
                aggregate_id=aggregate_id, reason=msg)
        aggregate.destroy()
        self.scheduler_client.delete_aggregate(context, aggregate)
        compute_utils.notify_about_aggregate_update(context,
                                                    "delete.end",
                                                    aggregate_payload)

    def is_safe_to_update_az(self, context, metadata, aggregate,
                             hosts=None,
                             action_name=AGGREGATE_ACTION_ADD):
        """Determine if updates alter an aggregate's availability zone.

            :param context: local context
            :param metadata: Target metadata for updating aggregate
            :param aggregate: Aggregate to update
            :param hosts: Hosts to check. If None, aggregate.hosts is used
            :type hosts: list
            :action_name: Calling method for logging purposes

        """
        if 'availability_zone' in metadata:
            if not metadata['availability_zone']:
                msg = _("Aggregate %s does not support empty named "
                        "availability zone") % aggregate.name
                self._raise_invalid_aggregate_exc(action_name, aggregate.id,
                                                  msg)
            _hosts = hosts or aggregate.hosts
            host_aggregates = objects.AggregateList.get_by_metadata_key(
                context, 'availability_zone', hosts=_hosts)
            conflicting_azs = [
                agg.availability_zone for agg in host_aggregates
                if agg.availability_zone != metadata['availability_zone']
                and agg.id != aggregate.id]
            if conflicting_azs:
                msg = _("One or more hosts already in availability zone(s) "
                        "%s") % conflicting_azs
                self._raise_invalid_aggregate_exc(action_name, aggregate.id,
                                                  msg)

    def _raise_invalid_aggregate_exc(self, action_name, aggregate_id, reason):
        if action_name == AGGREGATE_ACTION_ADD:
            raise exception.InvalidAggregateActionAdd(
                aggregate_id=aggregate_id, reason=reason)
        elif action_name == AGGREGATE_ACTION_UPDATE:
            raise exception.InvalidAggregateActionUpdate(
                aggregate_id=aggregate_id, reason=reason)
        elif action_name == AGGREGATE_ACTION_UPDATE_META:
            raise exception.InvalidAggregateActionUpdateMeta(
                aggregate_id=aggregate_id, reason=reason)
        elif action_name == AGGREGATE_ACTION_DELETE:
            raise exception.InvalidAggregateActionDelete(
                aggregate_id=aggregate_id, reason=reason)

        raise exception.NovaException(
            _("Unexpected aggregate action %s") % action_name)

    def _update_az_cache_for_host(self, context, host_name, aggregate_meta):
        # Update the availability_zone cache to avoid getting wrong
        # availability_zone in cache retention time when add/remove
        # host to/from aggregate.
        if aggregate_meta and aggregate_meta.get('availability_zone'):
            availability_zones.update_host_availability_zone_cache(context,
                                                                   host_name)

    @wrap_exception()
    def add_host_to_aggregate(self, context, aggregate_id, host_name):
        """Adds the host to an aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id,
                             'host_name': host_name}
        compute_utils.notify_about_aggregate_update(context,
                                                    "addhost.start",
                                                    aggregate_payload)
        # validates the host; ComputeHostNotFound is raised if invalid
        objects.Service.get_by_compute_host(context, host_name)

        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        self.is_safe_to_update_az(context, aggregate.metadata,
                                  hosts=[host_name], aggregate=aggregate)

        aggregate.add_host(host_name)
        self.scheduler_client.update_aggregates(context, [aggregate])
        self._update_az_cache_for_host(context, host_name, aggregate.metadata)
        # NOTE(jogo): Send message to host to support resource pools
        self.compute_rpcapi.add_aggregate_host(context,
                aggregate=aggregate, host_param=host_name, host=host_name)
        aggregate_payload.update({'name': aggregate.name})
        compute_utils.notify_about_aggregate_update(context,
                                                    "addhost.end",
                                                    aggregate_payload)
        return aggregate

    @wrap_exception()
    def remove_host_from_aggregate(self, context, aggregate_id, host_name):
        """Removes host from the aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id,
                             'host_name': host_name}
        compute_utils.notify_about_aggregate_update(context,
                                                    "removehost.start",
                                                    aggregate_payload)
        # validates the host; ComputeHostNotFound is raised if invalid
        objects.Service.get_by_compute_host(context, host_name)
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        aggregate.delete_host(host_name)
        self.scheduler_client.update_aggregates(context, [aggregate])
        self._update_az_cache_for_host(context, host_name, aggregate.metadata)
        self.compute_rpcapi.remove_aggregate_host(context,
                aggregate=aggregate, host_param=host_name, host=host_name)
        compute_utils.notify_about_aggregate_update(context,
                                                    "removehost.end",
                                                    aggregate_payload)
        return aggregate


class KeypairAPI(base.Base):
    """Subset of the Compute Manager API for managing key pairs."""

    get_notifier = functools.partial(rpc.get_notifier, service='api')
    wrap_exception = functools.partial(exception_wrapper.wrap_exception,
                                       get_notifier=get_notifier,
                                       binary='nova-api')

    def _notify(self, context, event_suffix, keypair_name):
        payload = {
            'tenant_id': context.project_id,
            'user_id': context.user_id,
            'key_name': keypair_name,
        }
        notify = self.get_notifier()
        notify.info(context, 'keypair.%s' % event_suffix, payload)

    def _validate_new_key_pair(self, context, user_id, key_name, key_type):
        safe_chars = "_- " + string.digits + string.ascii_letters
        clean_value = "".join(x for x in key_name if x in safe_chars)
        if clean_value != key_name:
            raise exception.InvalidKeypair(
                reason=_("Keypair name contains unsafe characters"))

        try:
            utils.check_string_length(key_name, min_length=1, max_length=255)
        except exception.InvalidInput:
            raise exception.InvalidKeypair(
                reason=_('Keypair name must be string and between '
                         '1 and 255 characters long'))

        count = objects.Quotas.count(context, 'key_pairs', user_id)

        try:
            objects.Quotas.limit_check(context, key_pairs=count + 1)
        except exception.OverQuota:
            raise exception.KeypairLimitExceeded()

    @wrap_exception()
    def import_key_pair(self, context, user_id, key_name, public_key,
                        key_type=keypair_obj.KEYPAIR_TYPE_SSH):
        """Import a key pair using an existing public key."""
        self._validate_new_key_pair(context, user_id, key_name, key_type)

        self._notify(context, 'import.start', key_name)

        fingerprint = self._generate_fingerprint(public_key, key_type)

        keypair = objects.KeyPair(context)
        keypair.user_id = user_id
        keypair.name = key_name
        keypair.type = key_type
        keypair.fingerprint = fingerprint
        keypair.public_key = public_key
        keypair.create()

        self._notify(context, 'import.end', key_name)

        return keypair

    @wrap_exception()
    def create_key_pair(self, context, user_id, key_name,
                        key_type=keypair_obj.KEYPAIR_TYPE_SSH):
        """Create a new key pair."""
        self._validate_new_key_pair(context, user_id, key_name, key_type)

        self._notify(context, 'create.start', key_name)

        private_key, public_key, fingerprint = self._generate_key_pair(
            user_id, key_type)

        keypair = objects.KeyPair(context)
        keypair.user_id = user_id
        keypair.name = key_name
        keypair.type = key_type
        keypair.fingerprint = fingerprint
        keypair.public_key = public_key
        keypair.create()

        self._notify(context, 'create.end', key_name)

        return keypair, private_key

    def _generate_fingerprint(self, public_key, key_type):
        if key_type == keypair_obj.KEYPAIR_TYPE_SSH:
            return crypto.generate_fingerprint(public_key)
        elif key_type == keypair_obj.KEYPAIR_TYPE_X509:
            return crypto.generate_x509_fingerprint(public_key)

    def _generate_key_pair(self, user_id, key_type):
        if key_type == keypair_obj.KEYPAIR_TYPE_SSH:
            return crypto.generate_key_pair()
        elif key_type == keypair_obj.KEYPAIR_TYPE_X509:
            return crypto.generate_winrm_x509_cert(user_id)

    @wrap_exception()
    def delete_key_pair(self, context, user_id, key_name):
        """Delete a keypair by name."""
        self._notify(context, 'delete.start', key_name)
        objects.KeyPair.destroy_by_name(context, user_id, key_name)
        self._notify(context, 'delete.end', key_name)

    def get_key_pairs(self, context, user_id, limit=None, marker=None):
        """List key pairs."""
        return objects.KeyPairList.get_by_user(
            context, user_id, limit=limit, marker=marker)

    def get_key_pair(self, context, user_id, key_name):
        """Get a keypair by name."""
        return objects.KeyPair.get_by_name(context, user_id, key_name)


