#    Copyright 2013 Red Hat, Inc
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
from oslo_db.sqlalchemy import utils as sqlalchemyutils
from oslo_log import log as logging
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import asc
from sqlalchemy.sql import func
from sqlalchemy.sql import text
from sqlalchemy.sql import true

from nova import db
from nova.db.sqlalchemy import api as db_api
from nova.db.sqlalchemy.api import require_context
from nova.db.sqlalchemy import api_models
from nova.db.sqlalchemy import models as main_models
from nova import exception
from nova.i18n import _LW
from nova import objects
from nova.objects import base
from nova.objects import fields


LOG = logging.getLogger(__name__)
OPTIONAL_FIELDS = ['extra_specs', 'projects']
DEPRECATED_FIELDS = ['deleted', 'deleted_at']


def _dict_with_extra_specs(flavor_model):
    extra_specs = {x['key']: x['value']
                   for x in flavor_model['extra_specs']}
    return dict(flavor_model, extra_specs=extra_specs)


# NOTE(danms): There are some issues with the oslo_db context manager
# decorators with static methods. We pull these out for now and can
# move them back into the actual staticmethods on the object when those
# issues are resolved.
@db_api.api_context_manager.reader
def _get_projects_from_db(context, flavorid):
    db_flavor = context.session.query(api_models.Flavors).\
                filter_by(flavorid=flavorid).\
                options(joinedload('projects')).\
                first()
    if not db_flavor:
        raise exception.FlavorNotFound(flavor_id=flavorid)
    return [x['project_id'] for x in db_flavor['projects']]


@db_api.api_context_manager.writer
def _flavor_add_project(context, flavor_id, project_id):
    project = api_models.FlavorProjects()
    project.update({'flavor_id': flavor_id,
                    'project_id': project_id})
    try:
        project.save(context.session)
    except db_exc.DBDuplicateEntry:
        raise exception.FlavorAccessExists(flavor_id=flavor_id,
                                           project_id=project_id)


@db_api.api_context_manager.writer
def _flavor_del_project(context, flavor_id, project_id):
    result = context.session.query(api_models.FlavorProjects).\
             filter_by(project_id=project_id).\
             filter_by(flavor_id=flavor_id).\
             delete()
    if result == 0:
        raise exception.FlavorAccessNotFound(flavor_id=flavor_id,
                                             project_id=project_id)


@db_api.api_context_manager.writer
def _flavor_extra_specs_add(context, flavor_id, specs, max_retries=10):
    writer = db_api.api_context_manager.writer
    for attempt in range(max_retries):
        try:
            spec_refs = context.session.query(
                api_models.FlavorExtraSpecs).\
                filter_by(flavor_id=flavor_id).\
                filter(api_models.FlavorExtraSpecs.key.in_(
                    specs.keys())).\
                all()

            existing_keys = set()
            for spec_ref in spec_refs:
                key = spec_ref["key"]
                existing_keys.add(key)
                with writer.savepoint.using(context):
                    spec_ref.update({"value": specs[key]})

            for key, value in specs.items():
                if key in existing_keys:
                    continue
                spec_ref = api_models.FlavorExtraSpecs()
                with writer.savepoint.using(context):
                    spec_ref.update({"key": key, "value": value,
                                     "flavor_id": flavor_id})
                    context.session.add(spec_ref)

            return specs
        except db_exc.DBDuplicateEntry:
            # a concurrent transaction has been committed,
            # try again unless this was the last attempt
            if attempt == max_retries - 1:
                raise exception.FlavorExtraSpecUpdateCreateFailed(
                    id=flavor_id, retries=max_retries)


@db_api.api_context_manager.writer
def _flavor_extra_specs_del(context, flavor_id, key):
    result = context.session.query(api_models.FlavorExtraSpecs).\
             filter_by(flavor_id=flavor_id).\
             filter_by(key=key).\
             delete()
    if result == 0:
        raise exception.FlavorExtraSpecsNotFound(
            extra_specs_key=key, flavor_id=flavor_id)


@db_api.api_context_manager.writer
def _flavor_create(context, values):
    specs = values.get('extra_specs')
    db_specs = []
    if specs:
        for k, v in specs.items():
            db_spec = api_models.FlavorExtraSpecs()
            db_spec['key'] = k
            db_spec['value'] = v
            db_specs.append(db_spec)

    projects = values.get('projects')
    db_projects = []
    if projects:
        for project in set(projects):
            db_project = api_models.FlavorProjects()
            db_project['project_id'] = project
            db_projects.append(db_project)

    values['extra_specs'] = db_specs
    values['projects'] = db_projects
    db_flavor = api_models.Flavors()
    db_flavor.update(values)

    try:
        db_flavor.save(context.session)
    except db_exc.DBDuplicateEntry as e:
        if 'flavorid' in e.columns:
            raise exception.FlavorIdExists(flavor_id=values['flavorid'])
        raise exception.FlavorExists(name=values['name'])
    except Exception as e:
        raise db_exc.DBError(e)

    return _dict_with_extra_specs(db_flavor)


@db_api.api_context_manager.writer
def _flavor_destroy(context, flavor_id=None, flavorid=None):
    query = context.session.query(api_models.Flavors)

    if flavor_id is not None:
        query = query.filter(api_models.Flavors.id == flavor_id)
    else:
        query = query.filter(api_models.Flavors.flavorid == flavorid)
    result = query.first()

    if not result:
        raise exception.FlavorNotFound(flavor_id=(flavor_id or flavorid))

    context.session.query(api_models.FlavorProjects).\
        filter_by(flavor_id=result.id).delete()
    context.session.query(api_models.FlavorExtraSpecs).\
        filter_by(flavor_id=result.id).delete()
    context.session.delete(result)


@db_api.main_context_manager.reader
def _ensure_migrated(context):
    result = context.session.query(main_models.InstanceTypes).\
             filter_by(deleted=0).count()
    if result:
        LOG.warning(_LW('Main database contains %(count)i unmigrated flavors'),
                    {'count': result})
    return result == 0


# TODO(berrange): Remove NovaObjectDictCompat
@base.NovaObjectRegistry.register
class Flavor(base.NovaPersistentObject, base.NovaObject,
             base.NovaObjectDictCompat):
    # Version 1.0: Initial version
    # Version 1.1: Added save_projects(), save_extra_specs(), removed
    #              remoteable from save()
    VERSION = '1.1'

    fields = {
        'id': fields.IntegerField(),
        'name': fields.StringField(nullable=True),
        'memory_mb': fields.IntegerField(),
        'vcpus': fields.IntegerField(),
        'root_gb': fields.IntegerField(),
        'ephemeral_gb': fields.IntegerField(),
        'flavorid': fields.StringField(),
        'swap': fields.IntegerField(),
        'rxtx_factor': fields.FloatField(nullable=True, default=1.0),
        'vcpu_weight': fields.IntegerField(nullable=True),
        'disabled': fields.BooleanField(),
        'is_public': fields.BooleanField(),
        'extra_specs': fields.DictOfStringsField(),
        'projects': fields.ListOfStringsField(),
        }

    def __init__(self, *args, **kwargs):
        super(Flavor, self).__init__(*args, **kwargs)
        self._orig_extra_specs = {}
        self._orig_projects = []
        self._in_api = False

    @property
    def in_api(self):
        if self._in_api:
            return True
        else:
            try:
                if 'id' in self:
                    self._flavor_get_from_db(self._context, self.id)
                else:
                    flavor = self._flavor_get_by_flavor_id_from_db(
                        self._context,
                        self.flavorid)
                    # Fix us up so we can use our real id
                    self.id = flavor['id']
                self._in_api = True
            except exception.FlavorNotFound:
                pass
            return self._in_api

    @staticmethod
    def _from_db_object(context, flavor, db_flavor, expected_attrs=None):
        if expected_attrs is None:
            expected_attrs = []
        flavor._context = context
        for name, field in flavor.fields.items():
            if name in OPTIONAL_FIELDS:
                continue
            if name in DEPRECATED_FIELDS and name not in db_flavor:
                continue
            value = db_flavor[name]
            if isinstance(field, fields.IntegerField):
                value = value if value is not None else 0
            flavor[name] = value

        # NOTE(danms): This is to support processing the API flavor
        # model, which does not have these deprecated fields. When we
        # remove compatibility with the old InstanceType model, we can
        # remove this as well.
        if any(f not in db_flavor for f in DEPRECATED_FIELDS):
            flavor.deleted_at = None
            flavor.deleted = False

        if 'extra_specs' in expected_attrs:
            flavor.extra_specs = db_flavor['extra_specs']

        if 'projects' in expected_attrs:
            if 'projects' in db_flavor:
                flavor['projects'] = [x['project_id']
                                      for x in db_flavor['projects']]
            else:
                flavor._load_projects()

        flavor.obj_reset_changes()
        return flavor

    @staticmethod
    @db_api.api_context_manager.reader
    def _flavor_get_query_from_db(context):
        query = context.session.query(api_models.Flavors).\
                options(joinedload('extra_specs'))
        if not context.is_admin:
            the_filter = [api_models.Flavors.is_public == true()]
            the_filter.extend([
                api_models.Flavors.projects.any(project_id=context.project_id)
            ])
            query = query.filter(or_(*the_filter))
        return query

    @staticmethod
    @require_context
    def _flavor_get_from_db(context, id):
        """Returns a dict describing specific flavor."""
        result = Flavor._flavor_get_query_from_db(context).\
                        filter_by(id=id).\
                        first()
        if not result:
            raise exception.FlavorNotFound(flavor_id=id)
        return db_api._dict_with_extra_specs(result)

    @staticmethod
    @require_context
    def _flavor_get_by_name_from_db(context, name):
        """Returns a dict describing specific flavor."""
        result = Flavor._flavor_get_query_from_db(context).\
                            filter_by(name=name).\
                            first()
        if not result:
            raise exception.FlavorNotFoundByName(flavor_name=name)
        return db_api._dict_with_extra_specs(result)

    @staticmethod
    @require_context
    def _flavor_get_by_flavor_id_from_db(context, flavor_id):
        """Returns a dict describing specific flavor_id."""
        result = Flavor._flavor_get_query_from_db(context).\
                        filter_by(flavorid=flavor_id).\
                        order_by(asc(api_models.Flavors.id)).\
                        first()
        if not result:
            raise exception.FlavorNotFound(flavor_id=flavor_id)
        return db_api._dict_with_extra_specs(result)

    @staticmethod
    def _get_projects_from_db(context, flavorid):
        return _get_projects_from_db(context, flavorid)

    @base.remotable
    def _load_projects(self):
        try:
            self.projects = self._get_projects_from_db(self._context,
                                                       self.flavorid)
        except exception.FlavorNotFound:
            self.projects = [x['project_id'] for x in
                             db.flavor_access_get_by_flavor_id(self._context,
                                                               self.flavorid)]
        self.obj_reset_changes(['projects'])

    def obj_load_attr(self, attrname):
        # NOTE(danms): Only projects could be lazy-loaded right now
        if attrname != 'projects':
            raise exception.ObjectActionError(
                action='obj_load_attr', reason='unable to load %s' % attrname)

        self._load_projects()

    def obj_reset_changes(self, fields=None, recursive=False):
        super(Flavor, self).obj_reset_changes(fields=fields,
                recursive=recursive)
        if fields is None or 'extra_specs' in fields:
            self._orig_extra_specs = (dict(self.extra_specs)
                                      if self.obj_attr_is_set('extra_specs')
                                      else {})
        if fields is None or 'projects' in fields:
            self._orig_projects = (list(self.projects)
                                   if self.obj_attr_is_set('projects')
                                   else [])

    def obj_what_changed(self):
        changes = super(Flavor, self).obj_what_changed()
        if ('extra_specs' in self and
            self.extra_specs != self._orig_extra_specs):
            changes.add('extra_specs')
        if 'projects' in self and self.projects != self._orig_projects:
            changes.add('projects')
        return changes

    @classmethod
    def _obj_from_primitive(cls, context, objver, primitive):
        self = super(Flavor, cls)._obj_from_primitive(context, objver,
                                                      primitive)
        changes = self.obj_what_changed()
        if 'extra_specs' not in changes:
            # This call left extra_specs "clean" so update our tracker
            self._orig_extra_specs = (dict(self.extra_specs)
                                      if self.obj_attr_is_set('extra_specs')
                                      else {})
        if 'projects' not in changes:
            # This call left projects "clean" so update our tracker
            self._orig_projects = (list(self.projects)
                                   if self.obj_attr_is_set('projects')
                                   else [])
        return self

    @base.remotable_classmethod
    def get_by_id(cls, context, id):
        try:
            db_flavor = cls._flavor_get_from_db(context, id)
        except exception.FlavorNotFound:
            db_flavor = db.flavor_get(context, id)
        return cls._from_db_object(context, cls(context), db_flavor,
                                   expected_attrs=['extra_specs'])

    @base.remotable_classmethod
    def get_by_name(cls, context, name):
        try:
            db_flavor = cls._flavor_get_by_name_from_db(context, name)
        except exception.FlavorNotFoundByName:
            db_flavor = db.flavor_get_by_name(context, name)
        return cls._from_db_object(context, cls(context), db_flavor,
                                   expected_attrs=['extra_specs'])

    @base.remotable_classmethod
    def get_by_flavor_id(cls, context, flavor_id, read_deleted=None):
        try:
            db_flavor = cls._flavor_get_by_flavor_id_from_db(context,
                                                             flavor_id)
        except exception.FlavorNotFound:
            db_flavor = db.flavor_get_by_flavor_id(context, flavor_id,
                                                   read_deleted)
        return cls._from_db_object(context, cls(context), db_flavor,
                                   expected_attrs=['extra_specs'])

    @staticmethod
    def _flavor_add_project(context, flavor_id, project_id):
        return _flavor_add_project(context, flavor_id, project_id)

    @staticmethod
    def _flavor_del_project(context, flavor_id, project_id):
        return _flavor_del_project(context, flavor_id, project_id)

    def _add_access(self, project_id):
        if self.in_api:
            self._flavor_add_project(self._context, self.id, project_id)
        else:
            db.flavor_access_add(self._context, self.flavorid, project_id)

    @base.remotable
    def add_access(self, project_id):
        if 'projects' in self.obj_what_changed():
            raise exception.ObjectActionError(action='add_access',
                                              reason='projects modified')
        self._add_access(project_id)
        self._load_projects()

    def _remove_access(self, project_id):
        if self.in_api:
            self._flavor_del_project(self._context, self.id, project_id)
        else:
            db.flavor_access_remove(self._context, self.flavorid, project_id)

    @base.remotable
    def remove_access(self, project_id):
        if 'projects' in self.obj_what_changed():
            raise exception.ObjectActionError(action='remove_access',
                                              reason='projects modified')
        self._remove_access(project_id)
        self._load_projects()

    @staticmethod
    def _flavor_create(context, updates):
        return _flavor_create(context, updates)

    @staticmethod
    def _ensure_migrated(context):
        return _ensure_migrated(context)

    @base.remotable
    def create(self):
        if self.obj_attr_is_set('id'):
            raise exception.ObjectActionError(action='create',
                                              reason='already created')

        # NOTE(danms): Once we have made it past a point where we know
        # all flavors have been migrated, we can remove this. Ideally
        # in Ocata with a blocker migration to be sure.
        if not self._ensure_migrated(self._context):
            raise exception.ObjectActionError(
                action='create',
                reason='main database still contains flavors')

        updates = self.obj_get_changes()
        expected_attrs = []
        for attr in OPTIONAL_FIELDS:
            if attr in updates:
                expected_attrs.append(attr)
        db_flavor = self._flavor_create(self._context, updates)
        self._from_db_object(self._context, self, db_flavor,
                             expected_attrs=expected_attrs)

    @base.remotable
    def save_projects(self, to_add=None, to_delete=None):
        """Add or delete projects.

        :param:to_add: A list of projects to add
        :param:to_delete: A list of projects to remove
        """

        to_add = to_add if to_add is not None else []
        to_delete = to_delete if to_delete is not None else []

        for project_id in to_add:
            self._add_access(project_id)
        for project_id in to_delete:
            self._remove_access(project_id)
        self.obj_reset_changes(['projects'])

    @staticmethod
    def _flavor_extra_specs_add(context, flavor_id, specs, max_retries=10):
        return _flavor_extra_specs_add(context, flavor_id, specs, max_retries)

    @staticmethod
    def _flavor_extra_specs_del(context, flavor_id, key):
        return _flavor_extra_specs_del(context, flavor_id, key)

    @base.remotable
    def save_extra_specs(self, to_add=None, to_delete=None):
        """Add or delete extra_specs.

        :param:to_add: A dict of new keys to add/update
        :param:to_delete: A list of keys to remove
        """

        if self.in_api:
            add_fn = self._flavor_extra_specs_add
            del_fn = self._flavor_extra_specs_del
            ident = self.id
        else:
            add_fn = db.flavor_extra_specs_update_or_create
            del_fn = db.flavor_extra_specs_delete
            ident = self.flavorid

        to_add = to_add if to_add is not None else {}
        to_delete = to_delete if to_delete is not None else []

        if to_add:
            add_fn(self._context, ident, to_add)

        for key in to_delete:
            del_fn(self._context, ident, key)
        self.obj_reset_changes(['extra_specs'])

    def save(self):
        updates = self.obj_get_changes()
        projects = updates.pop('projects', None)
        extra_specs = updates.pop('extra_specs', None)
        if updates:
            raise exception.ObjectActionError(
                action='save', reason='read-only fields were changed')

        if extra_specs is not None:
            deleted_keys = (set(self._orig_extra_specs.keys()) -
                            set(extra_specs.keys()))
            added_keys = self.extra_specs
        else:
            added_keys = deleted_keys = None

        if projects is not None:
            deleted_projects = set(self._orig_projects) - set(projects)
            added_projects = set(projects) - set(self._orig_projects)
        else:
            added_projects = deleted_projects = None

        # NOTE(danms): The first remotable method we call will reset
        # our of the original values for projects and extra_specs. Thus,
        # we collect the added/deleted lists for both above and /then/
        # call these methods to update them.

        if added_keys or deleted_keys:
            self.save_extra_specs(self.extra_specs, deleted_keys)

        if added_projects or deleted_projects:
            self.save_projects(added_projects, deleted_projects)

    @staticmethod
    def _flavor_destroy(context, flavor_id=None, flavorid=None):
        return _flavor_destroy(context, flavor_id=flavor_id, flavorid=flavorid)

    @base.remotable
    def destroy(self):
        # NOTE(danms): Historically the only way to delete a flavor
        # is via name, which is not very precise. We need to be able to
        # support the light construction of a flavor object and subsequent
        # delete request with only our name filled out. However, if we have
        # our id property, we should instead delete with that since it's
        # far more specific.
        try:
            if 'id' in self:
                self._flavor_destroy(self._context, flavor_id=self.id)
            else:
                self._flavor_destroy(self._context, flavorid=self.flavorid)
        except exception.FlavorNotFound:
            db.flavor_destroy(self._context, self.flavorid)


@db_api.api_context_manager.reader
def _flavor_get_all_from_db(context, inactive, filters, sort_key, sort_dir,
                            limit, marker):
    """Returns all flavors.
    """
    filters = filters or {}

    query = Flavor._flavor_get_query_from_db(context)

    if 'min_memory_mb' in filters:
        query = query.filter(
                api_models.Flavors.memory_mb >= filters['min_memory_mb'])

    if 'min_root_gb' in filters:
        query = query.filter(
                api_models.Flavors.root_gb >= filters['min_root_gb'])

    if 'disabled' in filters:
        query = query.filter(
               api_models.Flavors.disabled == filters['disabled'])

    if 'is_public' in filters and filters['is_public'] is not None:
        the_filter = [api_models.Flavors.is_public == filters['is_public']]
        if filters['is_public'] and context.project_id is not None:
            the_filter.extend([api_models.Flavors.projects.any(
                project_id=context.project_id)])
        if len(the_filter) > 1:
            query = query.filter(or_(*the_filter))
        else:
            query = query.filter(the_filter[0])
    marker_row = None
    if marker is not None:
        marker_row = Flavor._flavor_get_query_from_db(context).\
                    filter_by(flavorid=marker).\
                    first()
        if not marker_row:
            raise exception.MarkerNotFound(marker=marker)

    query = sqlalchemyutils.paginate_query(query, api_models.Flavors,
                                           limit,
                                           [sort_key, 'id'],
                                           marker=marker_row,
                                           sort_dir=sort_dir)
    return [_dict_with_extra_specs(i) for i in query.all()]


@base.NovaObjectRegistry.register
class FlavorList(base.ObjectListBase, base.NovaObject):
    VERSION = '1.1'

    fields = {
        'objects': fields.ListOfObjectsField('Flavor'),
        }

    @base.remotable_classmethod
    def get_all(cls, context, inactive=False, filters=None,
                sort_key='flavorid', sort_dir='asc', limit=None, marker=None):
        try:
            api_db_flavors = _flavor_get_all_from_db(context,
                                                     inactive=inactive,
                                                     filters=filters,
                                                     sort_key=sort_key,
                                                     sort_dir=sort_dir,
                                                     limit=limit,
                                                     marker=marker)
            # NOTE(danms): If we were asked for a marker and found it in
            # results from the API DB, we must continue our pagination with
            # just the limit (if any) to the main DB.
            marker = None
        except exception.MarkerNotFound:
            api_db_flavors = []

        if limit is not None:
            limit_more = limit - len(api_db_flavors)
        else:
            limit_more = None

        if limit_more is None or limit_more > 0:
            db_flavors = db.flavor_get_all(context, inactive=inactive,
                                           filters=filters, sort_key=sort_key,
                                           sort_dir=sort_dir, limit=limit_more,
                                           marker=marker)
        else:
            db_flavors = []
        return base.obj_make_list(context, cls(context), objects.Flavor,
                                  api_db_flavors + db_flavors,
                                  expected_attrs=['extra_specs'])


@db_api.main_context_manager.reader
def _get_main_db_flavor_ids(context, limit):
    # NOTE(danms): We don't need this imported at runtime, so
    # keep it separate here
    from nova.db.sqlalchemy import models
    return [x[0] for x in context.session.query(models.InstanceTypes.id).
            filter_by(deleted=0).
            limit(limit)]


@db_api.main_context_manager.writer
def _destroy_flavor_hard(context, name):
    # NOTE(danms): We don't need this imported at runtime, so
    # keep it separate here
    from nova.db.sqlalchemy import models
    context.session.query(models.InstanceTypes).filter_by(name=name).delete()


def migrate_flavors(ctxt, count, hard_delete=False):
    main_db_ids = _get_main_db_flavor_ids(ctxt, count)
    if not main_db_ids:
        return 0, 0

    count_all = len(main_db_ids)
    count_hit = 0

    for flavor_id in main_db_ids:
        try:
            flavor = Flavor.get_by_id(ctxt, flavor_id)
            flavor_values = {field: getattr(flavor, field)
                             for field in flavor.fields}
            flavor._flavor_create(ctxt, flavor_values)
            count_hit += 1
            if hard_delete:
                _destroy_flavor_hard(ctxt, flavor.name)
            else:
                db.flavor_destroy(ctxt, flavor.flavorid)
        except exception.FlavorNotFound:
            LOG.warning(_LW('Flavor id %(id)i disappeared during migration'),
                        {'id': flavor_id})
        except (exception.FlavorExists, exception.FlavorIdExists) as e:
            LOG.error(str(e))

    return count_all, count_hit


def _adjust_autoincrement(context, value):
    engine = db_api.get_api_engine()
    if engine.name == 'postgresql':
        # NOTE(danms): If we migrated some flavors in the above function,
        # then we will have confused postgres' sequence for the autoincrement
        # primary key. MySQL does not care about this, but since postgres does,
        # we need to reset this to avoid a failure on the next flavor creation.
        engine.execute(
            text('ALTER SEQUENCE flavors_id_seq RESTART WITH %i;' % (
                value)))


@db_api.api_context_manager.reader
def _get_max_flavor_id(context):
    max_id = context.session.query(func.max(api_models.Flavors.id)).one()[0]
    return max_id or 0


def migrate_flavor_reset_autoincrement(ctxt, count):
    max_id = _get_max_flavor_id(ctxt)
    _adjust_autoincrement(ctxt, max_id + 1)
    return 0, 0
