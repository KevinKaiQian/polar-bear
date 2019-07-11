# Copyright 2013 Red Hat, Inc.
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

"""
Client side of the compute RPC API.
"""

from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_serialization import jsonutils

from nova import config
from nova import context
from nova import exception
from nova.i18n import _, _LI, _LE
from nova import objects
from nova.objects import base as objects_base
from nova.objects import migrate_data as migrate_data_obj
from nova.objects import service as service_obj
from nova import rpc

CONF = config.CONF

LOG = logging.getLogger(__name__)
LAST_VERSION = None


def _compute_host(host, instance):
    '''Get the destination host for a message.

    :param host: explicit host to send the message to.
    :param instance: If an explicit host was not specified, use
                     instance['host']

    :returns: A host
    '''
    if host:
        return host
    if not instance:
        raise exception.NovaException(_('No compute host specified'))
    if not instance.host:
        raise exception.NovaException(_('Unable to find host for '
                                        'Instance %s') % instance.uuid)
    return instance.host



class ComputeCaseAPI(object):


    VERSION_ALIASES = {
        'icehouse': '3.23',
        'juno': '3.35',
        'kilo': '4.0',
        'liberty': '4.5',
        'mitaka': '4.11',
    }

    def __init__(self,namespace=None):
        super(ComputeCaseAPI, self).__init__()
        if namespace == None:
            namespace ="compute_plan"
        target = messaging.Target(topic=CONF.compute_topic,
                                  namespace=namespace,
                                  version='4.0')
        upgrade_level = CONF.upgrade_levels.compute
        if upgrade_level == 'auto':
            version_cap = self._determine_version_cap(target)
        else:
            version_cap = self.VERSION_ALIASES.get(upgrade_level,
                                                   upgrade_level)
        serializer = objects_base.NovaObjectSerializer()
        default_client = self.get_client(target, version_cap, serializer)
        self.router = rpc.ClientRouter(default_client)

    def run(self, ctxt, host,method,parameters,topic = None):

        version = '4.0'
        #import pdb;pdb.set_trace()
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        
        cctxt.cast(ctxt, method, parameters = parameters,topic = topic)
    def get_client(self, target, version_cap, serializer):
        return rpc.get_client(target,
                              version_cap=version_cap,
                              serializer=serializer)
        
        
        

class ComputeAPI(object):


    VERSION_ALIASES = {
        'icehouse': '3.23',
        'juno': '3.35',
        'kilo': '4.0',
        'liberty': '4.5',
        'mitaka': '4.11',
    }

    def __init__(self):
        super(ComputeAPI, self).__init__()
        target = messaging.Target(topic=CONF.compute_topic, version='4.0')
        upgrade_level = CONF.upgrade_levels.compute
        if upgrade_level == 'auto':
            version_cap = self._determine_version_cap(target)
        else:
            version_cap = self.VERSION_ALIASES.get(upgrade_level,
                                                   upgrade_level)
        serializer = objects_base.NovaObjectSerializer()
        default_client = self.get_client(target, version_cap, serializer)
        self.router = rpc.ClientRouter(default_client)
    '''
    def run_case(self, ctxt, host, Step):

        version = '4.0'
        #import pdb;pdb.set_trace()
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'run_case', Step = Step)
    '''
    def _determine_version_cap(self, target):
        global LAST_VERSION
        if LAST_VERSION:
            return LAST_VERSION
        service_version = objects.Service.get_minimum_version(
            context.get_admin_context(), 'nova-compute')

        # NOTE(johngarbutt) when there are no nova-compute services running we
        # get service_version == 0. In that case we do not want to cache
        # this result, because we will get a better answer next time.
        # As a sane default, return the version from the last release.
        if service_version == 0:
            LOG.debug("Not caching compute RPC version_cap, because min "
                      "service_version is 0. Please ensure a nova-compute "
                      "service has been started. Defaulting to Mitaka RPC.")
            return self.VERSION_ALIASES["mitaka"]

        history = service_obj.SERVICE_VERSION_HISTORY
        try:
            version_cap = history[service_version]['compute_rpc']
        except IndexError:
            LOG.error(_LE('Failed to extract compute RPC version from '
                          'service history because I am too '
                          'old (minimum version is now %(version)i)'),
                      {'version': service_version})
            raise exception.ServiceTooOld(thisver=service_obj.SERVICE_VERSION,
                                          minver=service_version)
        except KeyError:
            LOG.error(_LE('Failed to extract compute RPC version from '
                          'service history for version %(version)i'),
                      {'version': service_version})
            return target.version
        LAST_VERSION = version_cap
        LOG.info(_LI('Automatically selected compute RPC version %(rpc)s '
                     'from minimum service version %(service)i'),
                 {'rpc': version_cap,
                  'service': service_version})
        return version_cap

    # Cells overrides this
    def get_client(self, target, version_cap, serializer):
        return rpc.get_client(target,
                              version_cap=version_cap,
                              serializer=serializer)

    def add_aggregate_host(self, ctxt, host, aggregate, host_param,
                           slave_info=None):
        '''Add aggregate host.

        :param ctxt: request context
        :param aggregate:
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param host: This is the host to send the message to.
        '''
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'add_aggregate_host',
                   aggregate=aggregate, host=host_param,
                   slave_info=slave_info)

    def add_fixed_ip_to_instance(self, ctxt, instance, network_id):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'add_fixed_ip_to_instance',
                   instance=instance, network_id=network_id)

    def attach_interface(self, ctxt, instance, network_id, port_id,
                         requested_ip):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'attach_interface',
                          instance=instance, network_id=network_id,
                          port_id=port_id, requested_ip=requested_ip)

    def attach_volume(self, ctxt, instance, bdm):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'attach_volume', instance=instance, bdm=bdm)

    def change_instance_metadata(self, ctxt, instance, diff):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'change_instance_metadata',
                   instance=instance, diff=diff)

    def check_can_live_migrate_destination(self, ctxt, instance, destination,
                                           block_migration, disk_over_commit):
        version = '4.11'
        client = self.router.by_host(ctxt, destination)
        if not client.can_send_version(version):
            # NOTE(eliqiao): This is a new feature that is only available
            # once all compute nodes support at least version 4.11.
            # This means the new REST API that supports this needs to handle
            # this exception correctly. This can all be removed when we bump
            # the major version of this RPC API.
            if block_migration is None or disk_over_commit is None:
                raise exception.LiveMigrationWithOldNovaNotSupported()
            else:
                version = '4.0'

        cctxt = client.prepare(server=destination, version=version)
        result = cctxt.call(ctxt, 'check_can_live_migrate_destination',
                            instance=instance,
                            block_migration=block_migration,
                            disk_over_commit=disk_over_commit)
        if isinstance(result, migrate_data_obj.LiveMigrateData):
            return result
        elif result:
            return migrate_data_obj.LiveMigrateData.detect_implementation(
                result)
        else:
            return result

    def check_can_live_migrate_source(self, ctxt, instance, dest_check_data):
        dest_check_data_obj = dest_check_data
        version = '4.8'
        client = self.router.by_instance(ctxt, instance)
        if not client.can_send_version(version):
            version = '4.0'
            if dest_check_data:
                dest_check_data = dest_check_data.to_legacy_dict()
        source = _compute_host(None, instance)
        cctxt = client.prepare(server=source, version=version)
        result = cctxt.call(ctxt, 'check_can_live_migrate_source',
                            instance=instance,
                            dest_check_data=dest_check_data)
        if isinstance(result, migrate_data_obj.LiveMigrateData):
            return result
        elif dest_check_data_obj and result:
            dest_check_data_obj.from_legacy_dict(result)
            return dest_check_data_obj
        else:
            return result

    def check_instance_shared_storage(self, ctxt, instance, data, host=None):
        version = '4.0'
        if not host:
            client = self.router.by_instance(ctxt, instance)
        else:
            client = self.router.by_host(ctxt, host)
        cctxt = client.prepare(
                server=_compute_host(host, instance), version=version)
        return cctxt.call(ctxt, 'check_instance_shared_storage',
                          instance=instance,
                          data=data)

    def confirm_resize(self, ctxt, instance, migration, host,
            reservations=None, cast=True):
        version = '4.0'
        if not host:
            client = self.router.by_instance(ctxt, instance)
        else:
            client = self.router.by_host(ctxt, host)
        cctxt = client.prepare(
                server=_compute_host(host, instance), version=version)
        rpc_method = cctxt.cast if cast else cctxt.call
        return rpc_method(ctxt, 'confirm_resize',
                          instance=instance, migration=migration,
                          reservations=reservations)

    def detach_interface(self, ctxt, instance, port_id):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'detach_interface',
                   instance=instance, port_id=port_id)

    def detach_volume(self, ctxt, instance, volume_id, attachment_id=None):
        extra = {'attachment_id': attachment_id}
        version = '4.7'
        client = self.router.by_instance(ctxt, instance)
        if not client.can_send_version(version):
            version = '4.0'
            extra.pop('attachment_id')
        cctxt = client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'detach_volume',
                   instance=instance, volume_id=volume_id, **extra)

    def finish_resize(self, ctxt, instance, migration, image, disk_info,
            host, reservations=None):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'finish_resize',
                   instance=instance, migration=migration,
                   image=image, disk_info=disk_info, reservations=reservations)

    def finish_revert_resize(self, ctxt, instance, migration, host,
                             reservations=None):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'finish_revert_resize',
                   instance=instance, migration=migration,
                   reservations=reservations)

    def get_console_output(self, ctxt, instance, tail_length):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_console_output',
                          instance=instance, tail_length=tail_length)

    def get_console_pool_info(self, ctxt, host, console_type):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'get_console_pool_info',
                          console_type=console_type)

    def get_console_topic(self, ctxt, host):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'get_console_topic')

    def get_diagnostics(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_diagnostics', instance=instance)

    def get_instance_diagnostics(self, ctxt, instance):
        version = '4.13'
        client = self.router.by_instance(ctxt, instance)
        if not client.can_send_version(version):
            version = '4.0'
            instance = objects_base.obj_to_primitive(instance)
        cctxt = client.prepare(server=_compute_host(None, instance),
                                    version=version)
        return cctxt.call(ctxt, 'get_instance_diagnostics', instance=instance)

    def get_vnc_console(self, ctxt, instance, console_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_vnc_console',
                          instance=instance, console_type=console_type)

    def get_spice_console(self, ctxt, instance, console_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_spice_console',
                          instance=instance, console_type=console_type)

    def get_rdp_console(self, ctxt, instance, console_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_rdp_console',
                          instance=instance, console_type=console_type)

    def get_mks_console(self, ctxt, instance, console_type):
        version = '4.3'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_mks_console',
                          instance=instance, console_type=console_type)

    def get_serial_console(self, ctxt, instance, console_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'get_serial_console',
                          instance=instance, console_type=console_type)

    def validate_console_port(self, ctxt, instance, port, console_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'validate_console_port',
                          instance=instance, port=port,
                          console_type=console_type)

    def host_maintenance_mode(self, ctxt, host, host_param, mode):
        '''Set host maintenance mode

        :param ctxt: request context
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param mode:
        :param host: This is the host to send the message to.
        '''
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'host_maintenance_mode',
                          host=host_param, mode=mode)

    def host_power_action(self, ctxt, host, action):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'host_power_action', action=action)

    def inject_network_info(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'inject_network_info', instance=instance)

    def live_migration(self, ctxt, instance, dest, block_migration, host,
                       migration, migrate_data=None):
        args = {'migration': migration}
        version = '4.8'
        client = self.router.by_host(ctxt, host)
        if not client.can_send_version(version):
            version = '4.2'
            if migrate_data:
                migrate_data = migrate_data.to_legacy_dict(
                    pre_migration_result=True)
        if not client.can_send_version(version):
            version = '4.0'
            args.pop('migration')
        cctxt = client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'live_migration', instance=instance,
                   dest=dest, block_migration=block_migration,
                   migrate_data=migrate_data, **args)

    def live_migration_force_complete(self, ctxt, instance, migration):
        version = '4.12'
        kwargs = {}
        if not migration.source_compute:
            client = self.router.by_instance(ctxt, instance)
        else:
            client = self.router.by_host(ctxt, migration.source_compute)
        if not client.can_send_version(version):
            version = '4.9'
            kwargs['migration_id'] = migration.id
        cctxt = client.prepare(
                server=_compute_host(migration.source_compute, instance),
                version=version)
        cctxt.cast(ctxt, 'live_migration_force_complete', instance=instance,
                   **kwargs)

    def live_migration_abort(self, ctxt, instance, migration_id):
        version = '4.10'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'live_migration_abort', instance=instance,
                migration_id=migration_id)

    def pause_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'pause_instance', instance=instance)

    def post_live_migration_at_destination(self, ctxt, instance,
            block_migration, host):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'post_live_migration_at_destination',
            instance=instance, block_migration=block_migration)

    def pre_live_migration(self, ctxt, instance, block_migration, disk,
            host, migrate_data=None):
        migrate_data_orig = migrate_data
        version = '4.8'
        client = self.router.by_host(ctxt, host)
        if not client.can_send_version(version):
            version = '4.0'
            if migrate_data:
                migrate_data = migrate_data.to_legacy_dict()
        cctxt = client.prepare(server=host, version=version)
        result = cctxt.call(ctxt, 'pre_live_migration',
                            instance=instance,
                            block_migration=block_migration,
                            disk=disk, migrate_data=migrate_data)
        if isinstance(result, migrate_data_obj.LiveMigrateData):
            return result
        elif migrate_data_orig and result:
            migrate_data_orig.from_legacy_dict(
                {'pre_live_migration_result': result})
            return migrate_data_orig
        else:
            return result

    def prep_resize(self, ctxt, instance, image, instance_type, host,
                    reservations=None, request_spec=None,
                    filter_properties=None, node=None,
                    clean_shutdown=True):
        image_p = jsonutils.to_primitive(image)
        msg_args = {'instance': instance,
                    'instance_type': instance_type,
                    'image': image_p,
                    'reservations': reservations,
                    'request_spec': request_spec,
                    'filter_properties': filter_properties,
                    'node': node,
                    'clean_shutdown': clean_shutdown}
        version = '4.1'
        client = self.router.by_host(ctxt, host)
        if not client.can_send_version(version):
            version = '4.0'
            msg_args['instance_type'] = objects_base.obj_to_primitive(
                                            instance_type)
        cctxt = client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'prep_resize', **msg_args)

    def reboot_instance(self, ctxt, instance, block_device_info,
                        reboot_type):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'reboot_instance',
                   instance=instance,
                   block_device_info=block_device_info,
                   reboot_type=reboot_type)

    def rebuild_instance(self, ctxt, instance, new_pass, injected_files,
            image_ref, orig_image_ref, orig_sys_metadata, bdms,
            recreate=False, on_shared_storage=False, host=None, node=None,
            preserve_ephemeral=False, migration=None, limits=None,
            kwargs=None):
        # NOTE(danms): kwargs is only here for cells compatibility, don't
        # actually send it to compute
        extra = {'preserve_ephemeral': preserve_ephemeral,
                 'migration': migration,
                 'scheduled_node': node,
                 'limits': limits}
        version = '4.5'
        if not host:
            client = self.router.by_instance(ctxt, instance)
        else:
            client = self.router.by_host(ctxt, host)
        if not client.can_send_version(version):
            version = '4.0'
            extra.pop('migration')
            extra.pop('scheduled_node')
            extra.pop('limits')
        cctxt = client.prepare(server=_compute_host(host, instance),
                version=version)
        cctxt.cast(ctxt, 'rebuild_instance',
                   instance=instance, new_pass=new_pass,
                   injected_files=injected_files, image_ref=image_ref,
                   orig_image_ref=orig_image_ref,
                   orig_sys_metadata=orig_sys_metadata, bdms=bdms,
                   recreate=recreate, on_shared_storage=on_shared_storage,
                   **extra)

    def remove_aggregate_host(self, ctxt, host, aggregate, host_param,
                              slave_info=None):
        '''Remove aggregate host.

        :param ctxt: request context
        :param aggregate:
        :param host_param: This value is placed in the message to be the 'host'
                           parameter for the remote method.
        :param host: This is the host to send the message to.
        '''
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'remove_aggregate_host',
                   aggregate=aggregate, host=host_param,
                   slave_info=slave_info)

    def remove_fixed_ip_from_instance(self, ctxt, instance, address):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'remove_fixed_ip_from_instance',
                   instance=instance, address=address)

    def remove_volume_connection(self, ctxt, instance, volume_id, host):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'remove_volume_connection',
                          instance=instance, volume_id=volume_id)

    def rescue_instance(self, ctxt, instance, rescue_password,
                        rescue_image_ref=None, clean_shutdown=True):
        version = '4.0'
        msg_args = {'rescue_password': rescue_password,
                    'clean_shutdown': clean_shutdown,
                    'rescue_image_ref': rescue_image_ref,
                    'instance': instance,
        }
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'rescue_instance', **msg_args)

    def reset_network(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'reset_network', instance=instance)

    def resize_instance(self, ctxt, instance, migration, image, instance_type,
                        reservations=None, clean_shutdown=True):
        msg_args = {'instance': instance, 'migration': migration,
                    'image': image, 'reservations': reservations,
                    'instance_type': instance_type,
                    'clean_shutdown': clean_shutdown,
        }
        version = '4.1'
        client = self.router.by_instance(ctxt, instance)
        if not client.can_send_version(version):
            msg_args['instance_type'] = objects_base.obj_to_primitive(
                                            instance_type)
            version = '4.0'
        cctxt = client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'resize_instance', **msg_args)

    def resume_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'resume_instance', instance=instance)

    def revert_resize(self, ctxt, instance, migration, host,
                      reservations=None):
        version = '4.0'
        if not host:
            client = self.router.by_instance(ctxt, instance)
        else:
            client = self.router.by_host(ctxt, host)
        cctxt = client.prepare(
                server=_compute_host(host, instance), version=version)
        cctxt.cast(ctxt, 'revert_resize',
                   instance=instance, migration=migration,
                   reservations=reservations)

    def rollback_live_migration_at_destination(self, ctxt, instance, host,
                                               destroy_disks=True,
                                               migrate_data=None):
        version = '4.8'
        client = self.router.by_host(ctxt, host)
        if not client.can_send_version(version):
            version = '4.0'
            if migrate_data:
                migrate_data = migrate_data.to_legacy_dict()
        extra = {'destroy_disks': destroy_disks,
                 'migrate_data': migrate_data,
        }
        cctxt = client.prepare(server=host, version=version)
        cctxt.cast(ctxt, 'rollback_live_migration_at_destination',
                   instance=instance, **extra)

    def set_admin_password(self, ctxt, instance, new_pass):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'set_admin_password',
                          instance=instance, new_pass=new_pass)

    def set_host_enabled(self, ctxt, host, enabled):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'set_host_enabled', enabled=enabled)

    def swap_volume(self, ctxt, instance, old_volume_id, new_volume_id):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'swap_volume',
                   instance=instance, old_volume_id=old_volume_id,
                   new_volume_id=new_volume_id)

    def get_host_uptime(self, ctxt, host):
        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        return cctxt.call(ctxt, 'get_host_uptime')

    def reserve_block_device_name(self, ctxt, instance, device, volume_id,
                                  disk_bus=None, device_type=None):
        kw = {'instance': instance, 'device': device,
              'volume_id': volume_id, 'disk_bus': disk_bus,
              'device_type': device_type}
        version = '4.0'

        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'reserve_block_device_name', **kw)

    def backup_instance(self, ctxt, instance, image_id, backup_type,
                        rotation):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'backup_instance',
                   instance=instance,
                   image_id=image_id,
                   backup_type=backup_type,
                   rotation=rotation)

    def snapshot_instance(self, ctxt, instance, image_id):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'snapshot_instance',
                   instance=instance,
                   image_id=image_id)

    def start_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'start_instance', instance=instance)

    def stop_instance(self, ctxt, instance, do_cast=True, clean_shutdown=True):
        msg_args = {'instance': instance,
                    'clean_shutdown': clean_shutdown}
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        rpc_method = cctxt.cast if do_cast else cctxt.call
        return rpc_method(ctxt, 'stop_instance', **msg_args)

    def suspend_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'suspend_instance', instance=instance)

    def terminate_instance(self, ctxt, instance, bdms, reservations=None,
                           delete_type=None):
        # NOTE(rajesht): The `delete_type` parameter is passed because
        # the method signature has to match with `terminate_instance()`
        # method of cells rpcapi.
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'terminate_instance',
                   instance=instance, bdms=bdms,
                   reservations=reservations)

    def unpause_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'unpause_instance', instance=instance)

    def unrescue_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'unrescue_instance', instance=instance)

    def soft_delete_instance(self, ctxt, instance, reservations=None):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'soft_delete_instance',
                   instance=instance, reservations=reservations)

    def restore_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'restore_instance', instance=instance)

    def shelve_instance(self, ctxt, instance, image_id=None,
                        clean_shutdown=True):
        msg_args = {'instance': instance, 'image_id': image_id,
                    'clean_shutdown': clean_shutdown}
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'shelve_instance', **msg_args)

    def shelve_offload_instance(self, ctxt, instance,
                                clean_shutdown=True):
        msg_args = {'instance': instance, 'clean_shutdown': clean_shutdown}
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'shelve_offload_instance', **msg_args)

    def unshelve_instance(self, ctxt, instance, host, image=None,
                          filter_properties=None, node=None):
        version = '4.0'
        msg_kwargs = {
            'instance': instance,
            'image': image,
            'filter_properties': filter_properties,
            'node': node,
        }
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'unshelve_instance', **msg_kwargs)

    def volume_snapshot_create(self, ctxt, instance, volume_id,
                               create_info):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'volume_snapshot_create', instance=instance,
                   volume_id=volume_id, create_info=create_info)

    def volume_snapshot_delete(self, ctxt, instance, volume_id, snapshot_id,
                               delete_info):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'volume_snapshot_delete', instance=instance,
                   volume_id=volume_id, snapshot_id=snapshot_id,
                   delete_info=delete_info)

    def external_instance_event(self, ctxt, instances, events, host=None):
        instance = instances[0]
        cctxt = self.router.by_instance(ctxt, instance).prepare(
            server=_compute_host(host, instance),
            version='4.0')
        cctxt.cast(ctxt, 'external_instance_event', instances=instances,
                   events=events)

    def build_and_run_instance(self, ctxt, instance, host, image, request_spec,
            filter_properties, admin_password=None, injected_files=None,
            requested_networks=None, security_groups=None,
            block_device_mapping=None, node=None, limits=None):

        version = '4.0'
        cctxt = self.router.by_host(ctxt, host).prepare(
                server=host, version=version)
        cctxt.cast(ctxt, 'build_and_run_instance', instance=instance,
                image=image, request_spec=request_spec,
                filter_properties=filter_properties,
                admin_password=admin_password,
                injected_files=injected_files,
                requested_networks=requested_networks,
                security_groups=security_groups,
                block_device_mapping=block_device_mapping, node=node,
                limits=limits)

    def quiesce_instance(self, ctxt, instance):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        return cctxt.call(ctxt, 'quiesce_instance', instance=instance)

    def unquiesce_instance(self, ctxt, instance, mapping=None):
        version = '4.0'
        cctxt = self.router.by_instance(ctxt, instance).prepare(
                server=_compute_host(None, instance), version=version)
        cctxt.cast(ctxt, 'unquiesce_instance', instance=instance,
                   mapping=mapping)

    def refresh_instance_security_rules(self, ctxt, instance, host):
        version = '4.4'
        client = self.router.by_instance(ctxt, instance)
        if not client.can_send_version(version):
            version = '4.0'
            instance = objects_base.obj_to_primitive(instance)
        cctxt = client.prepare(server=_compute_host(None, instance),
                version=version)
        cctxt.cast(ctxt, 'refresh_instance_security_rules',
                   instance=instance)

    def trigger_crash_dump(self, ctxt, instance):
        version = '4.6'
        client = self.router.by_instance(ctxt, instance)

        if not client.can_send_version(version):
            raise exception.TriggerCrashDumpNotSupported()

        cctxt = client.prepare(server=_compute_host(None, instance),
                version=version)
        return cctxt.cast(ctxt, "trigger_crash_dump", instance=instance)
