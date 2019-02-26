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

from oslo_log import log as logging
from oslo_log import versionutils

from nova.i18n import _LW

LOG = logging.getLogger(__name__)


class CloudController(object):
    def __init__(self):
        versionutils.report_deprecated_feature(
                LOG,
                _LW('The in tree EC2 API has been removed in Mitaka. '
                    'Please remove entries from api-paste.ini and use '
                    'the OpenStack ec2-api project '
                    'http://git.openstack.org/cgit/openstack/ec2-api/')
        )
