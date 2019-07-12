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
class TestPlan(base.NovaPersistentObject, base.NovaObject,base.NovaObjectDictCompat):

    VERSION = '1.16'

    fields = {
        'id': fields.IntegerField(read_only=True),
        'uuid': fields.UUIDField(read_only=True),
        'testplan_name': fields.StringField(),
        'status': fields.StringField(),
        'beginning': fields.DateTimeField(),
        'ending': fields.DateTimeField(),
        'message': fields.StringField(),
        'result': fields.StringField(),
        'summary': fields.StringField(),
        }




    @staticmethod
    def _from_db_object(context, testplan, db_testplan):

        for key in testplan.fields:
            testplan[key] = db_testplan[key]
        testplan.obj_reset_changes()
        return testplan
    
    @base.remotable_classmethod
    def get_by_id(cls, context, testplan_id):
        db_testplan = db.testplan_get(context, testplan_id)
        return cls._from_db_object(context, cls(), db_testplan)

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
        db_plan = db.testplan_create(self._context, updates)
        self._from_db_object(self._context, self, db_plan)

    @base.remotable
    def save(self, prune_stats=False):
        # NOTE(belliott) ignore prune_stats param, no longer relevant

        updates = self.obj_get_changes()
        updates.pop('id', None)
        db_testplan = db.testplan_update(self._context, self.id, updates)
        self._from_db_object(self._context, self, db_testplan)

    @base.remotable
    def destroy(self):
        db.compute_node_delete(self._context, self.id)





