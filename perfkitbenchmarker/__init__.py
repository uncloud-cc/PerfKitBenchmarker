# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import gflags_validators as flags_validators  # NOQA

from perfkitbenchmarker import context

# This replaces the flags module with an object which acts like
# the flags module. This allows us to intercept calls to flags.FLAGS
# and return our own FlagValuesProxy instance in place of the global
# FlagValues instance. This enables benchmarks to run with different
# and even conflicting flags.
flags = context.FlagsModuleProxy()
