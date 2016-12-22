# klee-runner

This is infrastructure for conveniently running [KLEE](https://klee.github.io) on
a set of benchmarks and examining the results.

[![Build Status](https://travis-ci.org/delcypher/klee-runner.svg?branch=master)](https://travis-ci.org/delcypher/klee-runner)

# Requirements

* Python >= 3.3

The following python packages (available via ``pip install <package>``)

* [PyYAML](http://pyyaml.org/)
* [psutil](https://github.com/giampaolo/psutil) (only if using the `PythonPsUtil` backend)
* [docker-py](https://github.com/docker/docker-py) (only if using the ``Docker`` backend)
* [Filemagic](https://pypi.python.org/pypi/filemagic/) (only if using `single-runner.py`)

A `requirements.txt` file is provided so you can run `pip install --requirement requirements.txt`.

You also need a working copy of [KLEE](https://klee.github.io). What form this is in depends
on the backend you use.

* The `PythonPsUtil` backend requires a working build of KLEE on your host machine.
* The `Docker` backend requires a Docker image containing a working build of KLEE.

# Running

Several tools are provided for running programs

* `single-runner.py`

This allows running a single program using the `Klee`  or `Native` runner with
any suitable backend. This is provided for convenience when writing
an invocation info file is too much hassle.

Example invocations:

```bash
# Running a single program using KLEE inside a Docker container
./single-runner.py example_configs/klee_docker.yml working_directory output.yml /path/to/program.bc

# Running a single program using KLEE on the local machine
./single-runner.py example_configs/klee_psutil.yml working_directory output.yml /path/to/program.bc

# Replaying a KTest file using KLEE inside a Docker container
./single-runner.py -k /path/to/test00001.ktest example_configs/klee_docker.yml working_directory output.yml /path/to/program.bc

# Replaying a KTest file natively on a binary linked against libkleeRuntest.so inside a Docker container.
# NOTE: For this example the binary to work repliable the binary should have been compiled inside a Docker
# container using the same image as specified in `example_configs/native_replay_docker.yml`.
./single-runner.py -k /path/to/test00001.ktest example_configs/native_replay_docker.yml working_directory output.yml /path/to/program

# Replaying a KTest file natively on a binary linked against libkleeRuntest.so on the local machine
./single-runner.py -k /path/to/test00001.ktest example_configs/native_replay_psutil.yml working_directory output.yml /path/to/program
```

* `batch-runner.py`

This allows running a set of program invocations (described by an
[invocation info file](#invocation-info-files)) using any runner with any suitable backend.

Example invocations:

```bash
# Running a set of programs defined in an invocation info file using KLEE inside a Docker container
./batch-runner.py  example_configs/klee_docker.yml invocation_info.yml working_directory output.yml

# Running a set of programs defined in an invocation info file using KLEE inside on the local machine
./batch-runner.py  example_configs/klee_psutil.yml invocation_info.yml working_directory output.yml
```

## Config files

Config files describe how a tool (e.g. KLEE) should be invoked
using YAML.

It consists of two top level keys:

* `runner` - This is the name of the runner to use. It should be
  a runner in `KleeRunner/Runners/`.
* `runner_config` - This is a dictionary containing runner
  configuration options.

You can find examples in [example_configs](example_configs/).

## Runners

Runners are an abstraction used to describe how to invoke running
a program using a tool (i.e. KLEE). Note they don't actually
invoke the tool and instead a backend is used to do this. Effectively
runners work out what the command line invocation and environment variables
should be but then ask a backend to execute this on their behalf.

### Common runner options

* `backend` - A dictionary containing the keys `name` and `config` which
   map to the name of the runner to use and a dictionary containing the backend configuration respectively.
* `tool_path` - Absolute path to the tool used to run the program.
* ``additional_args`` **Optional** A list of additional command line arguments to pass to the tool.
* ``env`` - **Optional** Specifies the environment variables to pass when running.
* `max_memory`- **Optional** Maximum allowed memory in MiB. If set to 0 no memory
  limit is set.
* `max_time`- **Optional** Maximum allowed execution time in seconds. If set to 0 there is
  no time limit. Note the KLEE runner doesn't use this and instead uses
  `explore_max_time` and `generate_tests_max_time`.
* ``stack_size`` - **Optional** If specified will limit the stack size in KiB. Can be set to ``"unlimited"`` to allow an unlimited stack size.

### `Klee` runner

The `Klee` runner will run KLEE on a LLVM bitcode program. It has the following additional runner options.

* `klee_max_memory` - **Optional** Max memory for KLEE to enforce internally using the `-max-memory=` option.
   Note this can be used with `max_memory` but `max_memory` must be >= `klee_max_memory`.
* `explore_max_time` - **Optional** The maximum time KLEE should allow for state exploration (i.e. `-max-time=` option).
* `generate_tests_max_time` - **Optional** The maximum time to allow for KLEE to generate test files.

Note that `max_time` should not be specified as it is computed by summing `explore_max_time` and `generate_tests_max_time`.

### `NativeReplay` runner

This runner can replay KLEE generate test cases on native binaries linked against KLEE's `libkleeRuntest.so` library.

There are no additional options for this runner but it comes with the additional restriction that `tool_path` must
not be specified because there is no tool for this runner as the program under analysis is run directly.

## Backends

### `PythonPsUtil`

This uses the `psutil` python module to invoke a program directly on the host machine.
It enforces a memory limit by spawning a monitoring thread which periodically checks
the memory used by a program (and all its children recursively) does not exceed the
memory limit.

It has the following config options:

* `memory_limit_poll_time_period` - **Optional** The memory limit is enforced using a period polling
thread. The time period for the poll can be controlled by setting. This key should map to float which is
the polling time period is seconds. If not specified a default time period is used.

### `Docker`

This backend uses the Python `docker-py` module to run application locally inside a Docker container. The following ``config`` keys are
supported.

It has the following config options:

* `image` -  The docker image name. E.g. `klee/klee:latest`.
* `skip_tool_check` - **Optional**. If set to `true` then the check that checks that `tool_path` exists in the Docker image `image`
  is skipped. Disabling the check increases start up performance.
* `image_work_dir` -  **Optional**. Set the directory used as the working directory inside the
  container. If not specified `/mnt` is used as the default.
* `user` - **Optional**. Set the user used inside the container. If set to `"$HOST_USER"` then the
  UID and GID used on the host is used inside the container. If set to `null` then the default
  user inside the container is used. If set to an integer that UID will be used inside the container.
  The default is `"$HOST_USER"`.
* `docker_stats_on_exit_shim` - **Optional** If set to true use [docker-stats-on-exit-shim](https://github.com/delcypher/docker-stats-on-exit-shim)
   to collect CPU usage statistics when then container is destroyed. This is a workaround for
   [a limitiation in Docker that means statistics cannot be gathered before containder destruction](https://github.com/docker/docker/issues/18166).
   The default is `false`. If set to `true` the `docker-stats-on-exit-shim` binary must exist in the `external_deps` directory in the root of
   this repository.
* `extra_mounts` - **Optional** If set should map to a dictionary mapping
  absolute host paths to a dictionary describing mount details.  Mount details
  must contain the key `container_path` which maps to a string which is the
  absolute path to use in the container. Optionally `read_only` can also be
  specified as a key in the mount details and if specified must be a boolean.
  If `read_only` is set to true the mount point will be mounted into the
  container as read only, otherwise the mount will be writable from the
  container. The default value of `read_only` is True.  This option is useful
  for mounting additional files/directories into the container at a specified
  location. For an example of using this see [example_configs/klee_docker_extra_mounts.yml](examples/klee_docker_extra_mounts.yml).

## Invocation info files

The `batch-runner.py` tool takes an invocation info file. This file instructs the runner
how each benchmark should be executed by a runner. The format is a YAML file whose
schema is defined in [KleeRunner/InvocationInfoSchema.yml](KleeRunner/InvocationInfoSchema.yml).

This format is used because it easy to automatically generate by also tweak by hand.

# Analysis

TODO
