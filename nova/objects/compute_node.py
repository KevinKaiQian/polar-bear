#    Copyright 2013 IBM Corp
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


from oslo_db import exception as db_exc
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import uuidutils
from oslo_utils import versionutils

from nova import config
from nova import db
from nova import exception
from nova.i18n import _LW
from nova import objects
from nova.objects import base
from nova.objects import fields
from nova.objects import pci_device_pool
from nova.i18n import _LE, _LI, _LW
CONF = config.CONF
LOG = logging.getLogger(__name__)


@base.NovaObjectRegistry.register
class ComputeNode(base.NovaPersistentObject, base.NovaObject):
    # Version 1.0: Initial version
    # Version 1.1: Added get_by_service_id()
    # Version 1.2: String attributes updated to support unicode
    # Version 1.3: Added stats field
    # Version 1.4: Added host ip field
    # Version 1.5: Added numa_topology field
    # Version 1.6: Added supported_hv_specs
    # Version 1.7: Added host field
    # Version 1.8: Added get_by_host_and_nodename()
    # Version 1.9: Added pci_device_pools
    # Version 1.10: Added get_first_node_by_host_for_old_compat()
    # Version 1.11: PciDevicePoolList version 1.1
    # Version 1.12: HVSpec version 1.1
    # Version 1.13: Changed service_id field to be nullable
    # Version 1.14: Added cpu_allocation_ratio and ram_allocation_ratio
    # Version 1.15: Added uuid
    # Version 1.16: Added disk_allocation_ratio
    VERSION = '1.16'

    fields = {
        'id': fields.IntegerField(read_only=True),
        'uuid': fields.UUIDField(read_only=True),
        'service_id': fields.IntegerField(nullable=True),
        'host': fields.StringField(nullable=True),
        'compute_node_type': fields.StringField(nullable=True),
        'compute_node_method': fields.StringField(),

        }

    def obj_make_compatible(self, primitive, target_version):
        super(ComputeNode, self).obj_make_compatible(primitive, target_version)
        target_version = versionutils.convert_version_to_tuple(target_version)
        if target_version < (1, 16):
            if 'disk_allocation_ratio' in primitive:
                del primitive['disk_allocation_ratio']
        if target_version < (1, 15):
            if 'uuid' in primitive:
                del primitive['uuid']
        if target_version < (1, 14):
            if 'ram_allocation_ratio' in primitive:
                del primitive['ram_allocation_ratio']
            if 'cpu_allocation_ratio' in primitive:
                del primitive['cpu_allocation_ratio']
        if target_version < (1, 13) and primitive.get('service_id') is None:
            # service_id is non-nullable in versions before 1.13
            try:
                service = objects.Service.get_by_compute_host(
                    self._context, primitive['host'])
                primitive['service_id'] = service.id
            except (exception.ComputeHostNotFound, KeyError):
                # NOTE(hanlind): In case anything goes wrong like service not
                # found or host not being set, catch and set a fake value just
                # to allow for older versions that demand a value to work.
                # Setting to -1 will, if value is later used result in a
                # ServiceNotFound, so should be safe.
                primitive['service_id'] = -1
        if target_version < (1, 7) and 'host' in primitive:
            del primitive['host']
        if target_version < (1, 5) and 'numa_topology' in primitive:
            del primitive['numa_topology']
        if target_version < (1, 4) and 'host_ip' in primitive:
            del primitive['host_ip']
        if target_version < (1, 3) and 'stats' in primitive:
            # pre 1.3 version does not have a stats field
            del primitive['stats']

    @staticmethod
    def _data_from_db_object(compute, db_compute):
        if (('host' not in db_compute or db_compute['host'] is None)
                and 'service_id' in db_compute
                and db_compute['service_id'] is not None):
            # FIXME(sbauza) : Unconverted compute record, provide compatibility
            # This has to stay until we can be sure that any/all compute nodes
            # in the database have been converted to use the host field

            # Service field of ComputeNode could be deprecated in a next patch,
            # so let's use directly the Service object
            try:
                service = objects.Service.get_by_id(
                    compute._context, db_compute['service_id'])
            except exception.ServiceNotFound:
                compute.host = None
                return
            try:
                compute.host = service.host
            except (AttributeError, exception.OrphanedObjectError):
                # Host can be nullable in Service
                compute.host = None
        elif 'host' in db_compute and db_compute['host'] is not None:
            # New-style DB having host as a field
            compute.host = db_compute['host']
        else:
            # We assume it should not happen but in case, let's set it to None
            compute.host = None
        if db_compute['compute_node_type'] is not None:
            compute.compute_node_type = db_compute['compute_node_type']
        if db_compute['compute_node_method'] is not None:
            compute.compute_node_method = db_compute['compute_node_method']
        if db_compute['id'] is not None:
            compute.id = db_compute['id']
        if db_compute['uuid'] is not None:
            compute.uuid = db_compute['uuid']

    @staticmethod
    def _from_db_object(context, compute, db_compute):
 

        compute._data_from_db_object(compute, db_compute)

        compute.obj_reset_changes()

        return compute

    @base.remotable_classmethod
    def get_by_id(cls, context, compute_id):
        db_compute = db.compute_node_get(context, compute_id)
        return cls._from_db_object(context, cls(), db_compute)

    # NOTE(hanlind): This is deprecated and should be removed on the next
    # major version bump
    @base.remotable_classmethod
    def get_by_service_id(cls, context, service_id):
        db_computes = db.compute_nodes_get_by_service_id(context, service_id)
        # NOTE(sbauza): Old version was returning an item, we need to keep this
        # behaviour for backwards compatibility
        db_compute = db_computes[0]
        return cls._from_db_object(context, cls(), db_compute)

    @base.remotable_classmethod
    def get_by_host_and_nodename(cls, context, host, compute_node_type):
        db_compute = db.compute_node_get_by_host_and_nodename(
            context, host, compute_node_type)
        return cls._from_db_object(context, cls(), db_compute)

    # TODO(pkholkin): Remove this method in the next major version bump
    @base.remotable_classmethod
    def get_first_node_by_host_for_old_compat(cls, context, host,
                                              use_slave=False):
        computes = ComputeNodeList.get_all_by_host(context, host, use_slave)
        # FIXME(sbauza): Some hypervisors (VMware, Ironic) can return multiple
        # nodes per host, we should return all the nodes and modify the callers
        # instead.
        # Arbitrarily returning the first node.
        return computes[0]

    @staticmethod
    def _convert_stats_to_db_format(updates):
        stats = updates.pop('stats', None)
        if stats is not None:
            updates['stats'] = jsonutils.dumps(stats)

    @staticmethod
    def _convert_host_ip_to_db_format(updates):
        host_ip = updates.pop('host_ip', None)
        if host_ip:
            updates['host_ip'] = str(host_ip)

    @staticmethod
    def _convert_supported_instances_to_db_format(updates):
        hv_specs = updates.pop('supported_hv_specs', None)
        if hv_specs is not None:
            hv_specs = [hv_spec.to_list() for hv_spec in hv_specs]
            updates['supported_instances'] = jsonutils.dumps(hv_specs)

    @staticmethod
    def _convert_pci_stats_to_db_format(updates):
        if 'pci_device_pools' in updates:
            pools = updates.pop('pci_device_pools')
            if pools is not None:
                pools = jsonutils.dumps(pools.obj_to_primitive())
            updates['pci_stats'] = pools

    def update_inventory(self):
        """Update inventory records from legacy model values."""

        inventory_list = \
            objects.InventoryList.get_all_by_resource_provider_uuid(
                self._context, self.uuid)
        if not inventory_list:
            return False

        for inventory in inventory_list:
            if inventory.resource_class == fields.ResourceClass.VCPU:
                key = 'vcpus'
            elif inventory.resource_class == fields.ResourceClass.MEMORY_MB:
                key = 'memory_mb'
            elif inventory.resource_class == fields.ResourceClass.DISK_GB:
                key = 'local_gb'
            else:
                LOG.warning(_LW('Unknown inventory class %s for compute node'),
                            inventory.resource_class)
                continue

            if key in self.obj_what_changed():
                inventory.total = getattr(self, key)
                inventory.save()

        return True

    def _ensure_resource_provider(self):
        shortname = self.host.split('.')[0]
        rp_name = 'compute-%s-%s' % (shortname, self.uuid)
        rp = objects.ResourceProvider(
            context=self._context, uuid=self.uuid,
            name=rp_name)
        try:
            rp.create()
        except db_exc.DBDuplicateEntry:
            rp = objects.ResourceProvider.get_by_uuid(self._context, self.uuid)
            if rp.name != rp_name:
                rp.name = rp_name
                rp.save()

        return rp

    def create_inventory(self):
        """Create the initial inventory objects for this compute node.

        This is only ever called once, either for the first time when a compute
        is created, or after an upgrade where the required services have
        reached the required version.
        """
        rp = self._ensure_resource_provider()

        cpu = objects.Inventory(context=self._context,
                                resource_provider=rp,
                                resource_class=fields.ResourceClass.VCPU,
                                total=self.vcpus,
                                reserved=0,
                                min_unit=1,
                                max_unit=1,
                                step_size=1,
                                allocation_ratio=self.cpu_allocation_ratio)
        cpu.create()

        mem = objects.Inventory(context=self._context,
                                resource_provider=rp,
                                resource_class=fields.ResourceClass.MEMORY_MB,
                                total=self.memory_mb,
                                reserved=0,
                                min_unit=1,
                                max_unit=1,
                                step_size=1,
                                allocation_ratio=self.ram_allocation_ratio)
        mem.create()

        # FIXME(danms): Eventually we want to not write this record
        # if the compute host is on shared storage. We'll need some
        # indication from it to that effect, so for now we always
        # write it so that we can make all the usual machinery depend
        # on these records instead of the legacy columns.
        disk = objects.Inventory(context=self._context,
                                 resource_provider=rp,
                                 resource_class=fields.ResourceClass.DISK_GB,
                                 total=self.local_gb,
                                 reserved=0,
                                 min_unit=1,
                                 max_unit=1,
                                 step_size=1,
                                 allocation_ratio=self.disk_allocation_ratio)
        disk.create()

    @base.remotable
    def create(self):
        if self.obj_attr_is_set('id'):
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        updates = self.obj_get_changes()
        if 'uuid' not in updates:
            updates['uuid'] = uuidutils.generate_uuid()
            self.uuid = updates['uuid']

        #self._convert_stats_to_db_format(updates)
        #self._convert_host_ip_to_db_format(updates)
        #self._convert_supported_instances_to_db_format(updates)
        #self._convert_pci_stats_to_db_format(updates)
        LOG.info(_LI('sssssssssssssssssssss '
                     '%(updates)s'),
                 { 'updates': updates})
        db_compute = db.compute_node_create(self._context, updates)
        self._from_db_object(self._context, self, db_compute)

    @base.remotable
    def save(self, prune_stats=False):
        # NOTE(belliott) ignore prune_stats param, no longer relevant

        updates = self.obj_get_changes()
        updates.pop('id', None)
        db_compute = db.compute_node_update(self._context, self.id, updates)
        self._from_db_object(self._context, self, db_compute)

    @base.remotable
    def destroy(self):
        db.compute_node_delete(self._context, self.id)

    def update_from_virt_driver(self, resources):
        # NOTE(pmurray): the virt driver provides a dict of values that
        # can be copied into the compute node. The names and representation
        # do not exactly match.
        # TODO(pmurray): the resources dict should be formalized.
        keys = ["vcpus", "memory_mb", "local_gb", "cpu_info",
                "vcpus_used", "memory_mb_used", "local_gb_used",
                "numa_topology", "hypervisor_type",
                "hypervisor_version", "hypervisor_hostname",
                "disk_available_least", "host_ip"]
        for key in keys:
            if key in resources:
                setattr(self, key, resources[key])

        # supported_instances has a different name in compute_node
        if 'supported_instances' in resources:
            si = resources['supported_instances']
            self.supported_hv_specs = [objects.HVSpec.from_list(s) for s in si]


@base.NovaObjectRegistry.register
class ComputeNodeList(base.ObjectListBase, base.NovaObject):
    # Version 1.0: Initial version
    #              ComputeNode <= version 1.2
    # Version 1.1 ComputeNode version 1.3
    # Version 1.2 Add get_by_service()
    # Version 1.3 ComputeNode version 1.4
    # Version 1.4 ComputeNode version 1.5
    # Version 1.5 Add use_slave to get_by_service
    # Version 1.6 ComputeNode version 1.6
    # Version 1.7 ComputeNode version 1.7
    # Version 1.8 ComputeNode version 1.8 + add get_all_by_host()
    # Version 1.9 ComputeNode version 1.9
    # Version 1.10 ComputeNode version 1.10
    # Version 1.11 ComputeNode version 1.11
    # Version 1.12 ComputeNode version 1.12
    # Version 1.13 ComputeNode version 1.13
    # Version 1.14 ComputeNode version 1.14
    # Version 1.15 Added get_by_pagination()
    VERSION = '1.15'
    fields = {
        'objects': fields.ListOfObjectsField('ComputeNode'),
        }

    @base.remotable_classmethod
    def get_all(cls, context):
        #import pdb;pdb.set_trace()
        db_computes = db.compute_node_get_all(context)
        return base.obj_make_list(context, cls(context), objects.ComputeNode,
                                  db_computes)

    @base.remotable_classmethod
    def get_by_pagination(cls, context, limit=None, marker=None):
        db_computes = db.compute_node_get_all_by_pagination(
            context, limit=limit, marker=marker)
        return base.obj_make_list(context, cls(context), objects.ComputeNode,
                                  db_computes)

    @base.remotable_classmethod
    def get_by_hypervisor(cls, context, hypervisor_match):
        db_computes = db.compute_node_search_by_hypervisor(context,
                                                           hypervisor_match)
        return base.obj_make_list(context, cls(context), objects.ComputeNode,
                                  db_computes)

    # NOTE(hanlind): This is deprecated and should be removed on the next
    # major version bump
    @base.remotable_classmethod
    def _get_by_service(cls, context, service_id, use_slave=False):
        try:
            db_computes = db.compute_nodes_get_by_service_id(
                context, service_id)
        except exception.ServiceNotFound:
            # NOTE(sbauza): Previous behaviour was returning an empty list
            # if the service was created with no computes, we need to keep it.
            db_computes = []
        return base.obj_make_list(context, cls(context), objects.ComputeNode,
                                  db_computes)

    @staticmethod
    @db.select_db_reader_mode
    def _db_compute_node_get_all_by_host(context, host, use_slave=False):
        return db.compute_node_get_all_by_host(context, host)

    @base.remotable_classmethod
    def get_all_by_host(cls, context, host, use_slave=False):
        db_computes = cls._db_compute_node_get_all_by_host(context, host,
                                                      use_slave=use_slave)
        return base.obj_make_list(context, cls(context), objects.ComputeNode,
                                  db_computes)
