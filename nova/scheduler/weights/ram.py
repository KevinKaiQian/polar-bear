# Copyright (c) 2011 OpenStack Foundation
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
"""
RAM Weigher.  Weigh hosts by their RAM usage.

The default is to spread instances across all hosts evenly.  If you prefer
stacking, you can set the 'ram_weight_multiplier' option to a negative
number and the weighing has the opposite effect of the default.
"""

import nova.conf
from nova.scheduler import weights

CONF = nova.conf.CONF


class RAMWeigher(weights.BaseHostWeigher):
    minval = 0

    def weight_multiplier(self):
        """Override the weight multiplier."""
        return CONF.ram_weight_multiplier

    def _weigh_object(self, host_state, weight_properties):
        """Higher weights win.  We want spreading to be the default."""
        return host_state.free_ram_mb
