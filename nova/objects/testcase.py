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
from nova import objects
from nova.objects import base
from nova.objects import fields
from nova.i18n import _LE, _LI, _LW
CONF = config.CONF
LOG = logging.getLogger(__name__)


@base.NovaObjectRegistry.register
class TestCase(base.NovaPersistentObject, base.NovaObject,base.NovaObjectDictCompat):

    VERSION = '1.16'

    fields = {
        'id': fields.IntegerField(read_only=True),
        'uuid': fields.UUIDField(read_only=True),
        'case_name': fields.StringField(),
        'status': fields.StringField(),
        'host': fields.StringField(),
        'beginning': fields.DateTimeField(),
        'ending': fields.DateTimeField(),
        'message': fields.StringField(),
        'errors': fields.IntegerField(),
        }

    def obj_make_compatible(self, primitive, target_version):
        super(TestCase, self).obj_make_compatible(primitive, target_version)
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
    def _from_db_object(context, testcase, db_testcase):

        for key in testcase.fields:
            testcase[key] = db_testcase[key]
        testcase.obj_reset_changes()
        return testcase
    
    @base.remotable_classmethod
    def get_by_id(cls, context, testcase_id):
        db_testcase = db.testcase_get(context, testcase_id)
        return cls._from_db_object(context, cls(), db_testcase)

    @base.remotable
    def create(self):
        if self.obj_attr_is_set('id'):
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        updates = self.obj_get_changes()
        if 'uuid' not in updates:
            updates['uuid'] = uuidutils.generate_uuid()
            self.uuid = updates['uuid']

        LOG.info(_LI('show infomation ''%(updates)s'),{ 'updates': updates})
        db_case = db.testcase_create(self._context, updates)
        self._from_db_object(self._context, self, db_case)

    @base.remotable
    def save(self, prune_stats=False):
        # NOTE(belliott) ignore prune_stats param, no longer relevant

        updates = self.obj_get_changes()
        updates.pop('id', None)
        db_testcase = db.testcase_update(self._context, self.id, updates)
        self._from_db_object(self._context, self, db_testcase)

    @base.remotable
    def destroy(self):
        db.compute_node_delete(self._context, self.id)





