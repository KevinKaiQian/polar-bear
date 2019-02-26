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

"""Utility methods for scheduling."""

import collections
import functools
import sys

from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_serialization import jsonutils

from nova.compute import flavors
from nova.compute import utils as compute_utils

from nova import config
from nova import exception
from nova.i18n import _, _LE, _LW
from nova import objects
from nova.objects import base as obj_base
from nova import rpc


LOG = logging.getLogger(__name__)

CONF = config.CONF

GroupDetails = collections.namedtuple('GroupDetails', ['hosts', 'policies',
                                                       'members'])


def build_request_spec(ctxt, image, instances, instance_type=None):
    """Build a request_spec for the scheduler.

    The request_spec assumes that all instances to be scheduled are the same
    type.
    """
    instance = instances[0]
    if instance_type is None:
        if isinstance(instance, obj_instance.Instance):
            instance_type = instance.get_flavor()
        else:
            instance_type = flavors.extract_flavor(instance)

    if isinstance(instance, obj_instance.Instance):
        instance = obj_base.obj_to_primitive(instance)
        # obj_to_primitive doesn't copy this enough, so be sure
        # to detach our metadata blob because we modify it below.
        instance['system_metadata'] = dict(instance.get('system_metadata', {}))

    if isinstance(instance_type, objects.Flavor):
        instance_type = obj_base.obj_to_primitive(instance_type)
        # NOTE(danms): Replicate this old behavior because the
        # scheduler RPC interface technically expects it to be
        # there. Remove this when we bump the scheduler RPC API to
        # v5.0
        try:
            flavors.save_flavor_info(instance.get('system_metadata', {}),
                                     instance_type)
        except KeyError:
            # If the flavor isn't complete (which is legit with a
            # flavor object, just don't put it in the request spec
            pass

    request_spec = {
            'image': image or {},
            'instance_properties': instance,
            'instance_type': instance_type,
            'num_instances': len(instances)}
    return jsonutils.to_primitive(request_spec)


def set_vm_state_and_notify(context, instance_uuid, service, method, updates,
                            ex, request_spec):
    """changes VM state and notifies."""
    LOG.warning(_LW("Failed to %(service)s_%(method)s: %(ex)s"),
                {'service': service, 'method': method, 'ex': ex})

    vm_state = updates['vm_state']
    properties = request_spec.get('instance_properties', {})
    # NOTE(vish): We shouldn't get here unless we have a catastrophic
    #             failure, so just set the instance to its internal state
    notifier = rpc.get_notifier(service)
    state = vm_state.upper()
    LOG.warning(_LW('Setting instance to %s state.'), state,
                instance_uuid=instance_uuid)

    instance = objects.Instance(context=context, uuid=instance_uuid,
                                **updates)
    instance.obj_reset_changes(['uuid'])
    instance.save()
    compute_utils.add_instance_fault_from_exc(context,
            instance, ex, sys.exc_info())

    payload = dict(request_spec=request_spec,
                    instance_properties=properties,
                    instance_id=instance_uuid,
                    state=vm_state,
                    method=method,
                    reason=ex)

    event_type = '%s.%s' % (service, method)
    notifier.error(context, event_type, payload)


def build_filter_properties(scheduler_hints, forced_host,
        forced_node, instance_type):
    """Build the filter_properties dict from data in the boot request."""
    filter_properties = dict(scheduler_hints=scheduler_hints)
    filter_properties['instance_type'] = instance_type
    # TODO(alaski): It doesn't seem necessary that these are conditionally
    # added.  Let's just add empty lists if not forced_host/node.
    if forced_host:
        filter_properties['force_hosts'] = [forced_host]
    if forced_node:
        filter_properties['force_nodes'] = [forced_node]
    return filter_properties


def populate_filter_properties(filter_properties, host_state):
    """Add additional information to the filter properties after a node has
    been selected by the scheduling process.
    """
    if isinstance(host_state, dict):
        host = host_state['host']
        nodename = host_state['nodename']
        limits = host_state['limits']
    else:
        host = host_state.host
        nodename = host_state.nodename
        limits = host_state.limits

    # Adds a retry entry for the selected compute host and node:
    _add_retry_host(filter_properties, host, nodename)

    # Adds oversubscription policy
    if not filter_properties.get('force_hosts'):
        filter_properties['limits'] = limits


def populate_retry(filter_properties, instance_uuid):
    max_attempts = CONF.scheduler_max_attempts
    force_hosts = filter_properties.get('force_hosts', [])
    force_nodes = filter_properties.get('force_nodes', [])

    # In the case of multiple force hosts/nodes, scheduler should not
    # disable retry filter but traverse all force hosts/nodes one by
    # one till scheduler gets a valid target host.
    if (max_attempts == 1 or len(force_hosts) == 1
                           or len(force_nodes) == 1):
        # re-scheduling is disabled.
        return

    # retry is enabled, update attempt count:
    retry = filter_properties.setdefault(
        'retry', {
            'num_attempts': 0,
            'hosts': []  # list of compute hosts tried
    })
    retry['num_attempts'] += 1

    _log_compute_error(instance_uuid, retry)
    exc_reason = retry.pop('exc_reason', None)

    if retry['num_attempts'] > max_attempts:
        msg = (_('Exceeded max scheduling attempts %(max_attempts)d '
                 'for instance %(instance_uuid)s. '
                 'Last exception: %(exc_reason)s')
               % {'max_attempts': max_attempts,
                  'instance_uuid': instance_uuid,
                  'exc_reason': exc_reason})
        raise exception.MaxRetriesExceeded(reason=msg)


def _log_compute_error(instance_uuid, retry):
    """If the request contained an exception from a previous compute
    build/resize operation, log it to aid debugging
    """
    exc = retry.get('exc')  # string-ified exception from compute
    if not exc:
        return  # no exception info from a previous attempt, skip

    hosts = retry.get('hosts', None)
    if not hosts:
        return  # no previously attempted hosts, skip

    last_host, last_node = hosts[-1]
    LOG.error(_LE('Error from last host: %(last_host)s (node %(last_node)s):'
                  ' %(exc)s'),
              {'last_host': last_host,
               'last_node': last_node,
               'exc': exc},
              instance_uuid=instance_uuid)


def _add_retry_host(filter_properties, host, node):
    """Add a retry entry for the selected compute node. In the event that
    the request gets re-scheduled, this entry will signal that the given
    node has already been tried.
    """
    retry = filter_properties.get('retry', None)
    if not retry:
        return
    hosts = retry['hosts']
    hosts.append([host, node])


def parse_options(opts, sep='=', converter=str, name=""):
    """Parse a list of options, each in the format of <key><sep><value>. Also
    use the converter to convert the value into desired type.

    :params opts: list of options, e.g. from oslo_config.cfg.ListOpt
    :params sep: the separator
    :params converter: callable object to convert the value, should raise
                       ValueError for conversion failure
    :params name: name of the option

    :returns: a lists of tuple of values (key, converted_value)
    """
    good = []
    bad = []
    for opt in opts:
        try:
            key, seen_sep, value = opt.partition(sep)
            value = converter(value)
        except ValueError:
            key = None
            value = None
        if key and seen_sep and value is not None:
            good.append((key, value))
        else:
            bad.append(opt)
    if bad:
        LOG.warning(_LW("Ignoring the invalid elements of the option "
                        "%(name)s: %(options)s"),
                    {'name': name,
                     'options': ", ".join(bad)})
    return good


def validate_filter(filter):
    """Validates that the filter is configured in the default filters."""
    return filter in CONF.scheduler_default_filters


def validate_weigher(weigher):
    """Validates that the weigher is configured in the default weighers."""
    if 'nova.scheduler.weights.all_weighers' in CONF.scheduler_weight_classes:
        return True
    return weigher in CONF.scheduler_weight_classes


_SUPPORTS_AFFINITY = None
_SUPPORTS_ANTI_AFFINITY = None
_SUPPORTS_SOFT_AFFINITY = None
_SUPPORTS_SOFT_ANTI_AFFINITY = None


def _get_group_details(context, instance_uuid, user_group_hosts=None):
    """Provide group_hosts and group_policies sets related to instances if
    those instances are belonging to a group and if corresponding filters are
    enabled.

    :param instance_uuid: UUID of the instance to check
    :param user_group_hosts: Hosts from the group or empty set

    :returns: None or namedtuple GroupDetails
    """
    global _SUPPORTS_AFFINITY
    if _SUPPORTS_AFFINITY is None:
        _SUPPORTS_AFFINITY = validate_filter(
            'ServerGroupAffinityFilter')
    global _SUPPORTS_ANTI_AFFINITY
    if _SUPPORTS_ANTI_AFFINITY is None:
        _SUPPORTS_ANTI_AFFINITY = validate_filter(
            'ServerGroupAntiAffinityFilter')
    global _SUPPORTS_SOFT_AFFINITY
    if _SUPPORTS_SOFT_AFFINITY is None:
        _SUPPORTS_SOFT_AFFINITY = validate_weigher(
            'nova.scheduler.weights.affinity.ServerGroupSoftAffinityWeigher')
    global _SUPPORTS_SOFT_ANTI_AFFINITY
    if _SUPPORTS_SOFT_ANTI_AFFINITY is None:
        _SUPPORTS_SOFT_ANTI_AFFINITY = validate_weigher(
            'nova.scheduler.weights.affinity.'
            'ServerGroupSoftAntiAffinityWeigher')

    if not instance_uuid:
        return

    try:
        group = objects.InstanceGroup.get_by_instance_uuid(context,
                                                           instance_uuid)
    except exception.InstanceGroupNotFound:
        return

    policies = set(('anti-affinity', 'affinity', 'soft-affinity',
                    'soft-anti-affinity'))
    if any((policy in policies) for policy in group.policies):
        if not _SUPPORTS_AFFINITY and 'affinity' in group.policies:
            msg = _("ServerGroupAffinityFilter not configured")
            LOG.error(msg)
            raise exception.UnsupportedPolicyException(reason=msg)
        if not _SUPPORTS_ANTI_AFFINITY and 'anti-affinity' in group.policies:
            msg = _("ServerGroupAntiAffinityFilter not configured")
            LOG.error(msg)
            raise exception.UnsupportedPolicyException(reason=msg)
        if (not _SUPPORTS_SOFT_AFFINITY
                and 'soft-affinity' in group.policies):
            msg = _("ServerGroupSoftAffinityWeigher not configured")
            LOG.error(msg)
            raise exception.UnsupportedPolicyException(reason=msg)
        if (not _SUPPORTS_SOFT_ANTI_AFFINITY
                and 'soft-anti-affinity' in group.policies):
            msg = _("ServerGroupSoftAntiAffinityWeigher not configured")
            LOG.error(msg)
            raise exception.UnsupportedPolicyException(reason=msg)
        group_hosts = set(group.get_hosts())
        user_hosts = set(user_group_hosts) if user_group_hosts else set()
        return GroupDetails(hosts=user_hosts | group_hosts,
                            policies=group.policies, members=group.members)


def setup_instance_group(context, request_spec, filter_properties):
    """Add group_hosts and group_policies fields to filter_properties dict
    based on instance uuids provided in request_spec, if those instances are
    belonging to a group.

    :param request_spec: Request spec
    :param filter_properties: Filter properties
    """
    group_hosts = filter_properties.get('group_hosts')
    # NOTE(sbauza) If there are multiple instance UUIDs, it's a boot
    # request and they will all be in the same group, so it's safe to
    # only check the first one.
    instance_uuid = request_spec.get('instance_properties', {}).get('uuid')
    group_info = _get_group_details(context, instance_uuid, group_hosts)
    if group_info is not None:
        filter_properties['group_updated'] = True
        filter_properties['group_hosts'] = group_info.hosts
        filter_properties['group_policies'] = group_info.policies
        filter_properties['group_members'] = group_info.members


def retry_on_timeout(retries=1):
    """Retry the call in case a MessagingTimeout is raised.

    A decorator for retrying calls when a service dies mid-request.

    :param retries: Number of retries
    :returns: Decorator
    """
    def outer(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except messaging.MessagingTimeout:
                    attempt += 1
                    if attempt <= retries:
                        LOG.warning(_LW(
                            "Retrying %(name)s after a MessagingTimeout, "
                            "attempt %(attempt)s of %(retries)s."),
                                 {'attempt': attempt, 'retries': retries,
                                  'name': func.__name__})
                    else:
                        raise
        return wrapped
    return outer

retry_select_destinations = retry_on_timeout(CONF.scheduler_max_attempts - 1)
