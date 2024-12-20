# Copyright 2014 PerfKitBenchmarker Authors. All rights reserved.
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
"""Module containing redis installation and cleanup functions."""

import logging
from typing import Any, Dict, List

from absl import flags
from perfkitbenchmarker import linux_packages
from perfkitbenchmarker import os_types


class RedisEvictionPolicy:
  """Enum of options for --redis_eviction_policy."""

  NOEVICTION = 'noeviction'
  ALLKEYS_LRU = 'allkeys-lru'
  VOLATILE_LRU = 'volatile-lru'
  ALLKEYS_RANDOM = 'allkeys-random'
  VOLATILE_RANDOM = 'volatile-random'
  VOLATILE_TTL = 'volatile-ttl'


_VERSION = flags.DEFINE_string(
    'redis_server_version', '6.2.1', 'Version of redis server to use.'
)
_IO_THREADS = flags.DEFINE_integer(
    'redis_server_io_threads',
    None,
    'Only supported for redis version >= 6, the '
    'number of redis server IO threads to use.',
)
_IO_THREADS_DO_READS = flags.DEFINE_bool(
    'redis_server_io_threads_do_reads',
    False,
    'If true, makes both reads and writes use IO threads instead of just '
    'writes.',
)
_IO_THREAD_AFFINITY = flags.DEFINE_bool(
    'redis_server_io_threads_cpu_affinity',
    False,
    'If true, attempts to pin IO threads to CPUs.',
)
_ENABLE_SNAPSHOTS = flags.DEFINE_bool(
    'redis_server_enable_snapshots',
    False,
    'If true, uses the default redis snapshot policy.',
)
_NUM_PROCESSES = flags.DEFINE_integer(
    'redis_total_num_processes',
    1,
    'Total number of redis server processes. Useful when running with a redis '
    'version lower than 6. If set to 0, uses num_cpus.',
    lower_bound=0,
)
_EVICTION_POLICY = flags.DEFINE_enum(
    'redis_eviction_policy',
    RedisEvictionPolicy.NOEVICTION,
    [
        RedisEvictionPolicy.NOEVICTION,
        RedisEvictionPolicy.ALLKEYS_LRU,
        RedisEvictionPolicy.VOLATILE_LRU,
        RedisEvictionPolicy.ALLKEYS_RANDOM,
        RedisEvictionPolicy.VOLATILE_RANDOM,
        RedisEvictionPolicy.VOLATILE_TTL,
    ],
    'Redis eviction policy when maxmemory limit is reached. This requires '
    'running clients with larger amounts of data than Redis can hold.',
)
REDIS_AOF = flags.DEFINE_bool(
    'redis_aof',
    False,
    'If true, use disks on the server for aof backups. ',
)

# Default port for Redis
DEFAULT_PORT = 6379
REDIS_PID_FILE = 'redis.pid'
FLAGS = flags.FLAGS
REDIS_GIT = 'https://github.com/antirez/redis.git'
REDIS_BACKUP = 'scratch'


def _GetRedisTarName() -> str:
  return f'redis-{_VERSION.value}.tar.gz'


def GetRedisDir() -> str:
  return f'{linux_packages.INSTALL_DIR}/redis'


def _GetNumProcesses(vm) -> int:
  num_processes = _NUM_PROCESSES.value
  if num_processes == 0 and vm is not None:
    num_processes = vm.NumCpusForBenchmark()
  assert num_processes >= 0, 'num_processes must be >=0.'

  return num_processes


def _Install(vm) -> None:
  """Installs the redis package on the VM."""
  vm.Install('build_tools')
  vm.Install('wget')
  vm.RemoteCommand(f'cd {linux_packages.INSTALL_DIR}; git clone {REDIS_GIT}')
  vm.RemoteCommand(
      f'cd {GetRedisDir()} && git checkout {_VERSION.value} && make'
  )


def YumInstall(vm) -> None:
  """Installs the redis package on the VM."""
  if vm.OS_TYPE in os_types.CENTOS_TYPES:
    vm.InstallPackages('tcl-devel')
    vm.InstallPackages('scl-utils centos-release-scl')
    vm.InstallPackages('devtoolset-7 libuuid-devel')
    vm.InstallPackages(
        'openssl openssl-devel curl-devel '
        'devtoolset-7-libatomic-devel tcl '
        'tcl-devel git wget epel-release'
    )
    vm.InstallPackages('tcltls libzstd procps-ng')
    vm.RemoteCommand(
        'echo "source scl_source enable devtoolset-7" | sudo tee -a'
        ' $HOME/.bashrc'
    )

  elif vm.BASE_OS_TYPE == os_types.RHEL:
    vm.RemoteCommand('sudo yum group install -y "Development Tools"')
  else:
    raise NotImplementedError()
  _Install(vm)


def AptInstall(vm) -> None:
  """Installs the redis package on the VM."""
  vm.InstallPackages('tcl-dev')
  _Install(vm)


def _GetIOThreads(vm) -> int:
  if _IO_THREADS.value:
    return _IO_THREADS.value
  # Redis docs suggests that i/o threads should not exceed number of cores.
  nthreads_per_core = vm.CheckLsCpu().threads_per_core
  if nthreads_per_core == 1:
    return vm.NumCpusForBenchmark() - 1
  else:
    return vm.NumCpusForBenchmark() // 2


def _BuildStartCommand(vm, port: int) -> str:
  """Returns the run command used to start the redis server.

  See https://raw.githubusercontent.com/redis/redis/6.0/redis.conf
  for the default redis configuration.

  Args:
    vm: The redis server VM.
    port: The port to start redis on.

  Returns:
    A command that can be used to start redis in the background.
  """
  redis_dir = GetRedisDir()
  cmd = 'nohup sudo {redis_dir}/src/redis-server {args} &> /dev/null &'
  cmd_args = [
      f'--port {port}',
      '--protected-mode no',
  ]
  if REDIS_AOF.value:
    cmd_args += [
        '--appendonly yes',
        f'--appendfilename backup_{port}',
        f'--dir /{REDIS_BACKUP}',
    ]
  # Add check for the MADV_FREE/fork arm64 Linux kernel bug
  if _VERSION.value >= '6.2.1':
    cmd_args.append('--ignore-warnings ARM64-COW-BUG')
    io_threads = _GetIOThreads(vm)
    cmd_args.append(f'--io-threads {io_threads}')
  # Snapshotting
  if not _ENABLE_SNAPSHOTS.value:
    cmd_args.append('--save ""')
  # IO thread reads
  if _IO_THREADS_DO_READS.value:
    do_reads = 'yes' if _IO_THREADS_DO_READS.value else 'no'
    cmd_args.append(f'--io-threads-do-reads {do_reads}')
  # IO thread affinity
  if _IO_THREAD_AFFINITY.value:
    cpu_affinity = f'0-{vm.num_cpus-1}'
    cmd_args.append(f'--server_cpulist {cpu_affinity}')
  if _EVICTION_POLICY.value:
    cmd_args.append(f'--maxmemory-policy {_EVICTION_POLICY.value}')

  # Set maxmemory flag for each redis instance. Total memory for all of the
  # server instances combined should be 90% of server VM's total memory.
  num_processes = _GetNumProcesses(vm)
  max_memory_per_instance = int(vm.total_memory_kb * 0.9 / num_processes)
  cmd_args.append(f'--maxmemory {max_memory_per_instance}kb')
  return cmd.format(redis_dir=redis_dir, args=' '.join(cmd_args))


def Start(vm) -> None:
  """Start redis server process."""
  num_processes = _GetNumProcesses(vm)
  # 10 is an arbituary multiplier that ensures this value is high enough.
  mux_sessions = 10 * num_processes
  vm.RemoteCommand(
      f'echo "\nMaxSessions {mux_sessions}" | sudo tee -a /etc/ssh/sshd_config'
  )
  # Redis tuning parameters, see
  # https://www.techandme.se/performance-tips-for-redis-cache-server/.
  # This command works on 2nd generation of VMs only.
  update_sysvtl = vm.TryRemoteCommand(
      'echo "'
      'vm.overcommit_memory = 1\n'
      'net.core.somaxconn = 65535\n'
      '" | sudo tee -a /etc/sysctl.conf'
  )
  # /usr/sbin/sysctl is not applicable on certain distros.
  commit_sysvtl = vm.TryRemoteCommand(
      'sudo /usr/sbin/sysctl -p || sudo sysctl -p'
  )
  if not (update_sysvtl and commit_sysvtl):
    logging.info('Fail to optimize overcommit_memory and socket connections.')
  for port in GetRedisPorts(vm):
    vm.RemoteCommand(_BuildStartCommand(vm, port))


def GetMetadata(vm) -> Dict[str, Any]:
  num_processes = _GetNumProcesses(vm)
  return {
      'redis_server_version': _VERSION.value,
      'redis_server_io_threads': (
          _GetIOThreads(vm) if _VERSION.value >= '6.2.1' else 0
      ),
      'redis_server_io_threads_do_reads': _IO_THREADS_DO_READS.value,
      'redis_server_io_threads_cpu_affinity': _IO_THREAD_AFFINITY.value,
      'redis_server_enable_snapshots': _ENABLE_SNAPSHOTS.value,
      'redis_server_num_processes': num_processes,
      'redis_aof': REDIS_AOF.value,
  }


def GetRedisPorts(vm=None) -> List[int]:
  """Returns a list of redis port(s)."""
  num_processes = _GetNumProcesses(vm)
  return [DEFAULT_PORT + i for i in range(num_processes)]
