# Tasks

Each task directory is a self-contained Harbor task package.

```
tasks/<task-id>/
├── tasks/<task-id>/     the Harbor task: statement, config, environment, tests
├── metadata/            inventory, licence correspondence, checksum manifest
├── evidence/            model evaluation runs, self-check records
├── reports/             brief, difficulty, provenance
└── tools/               build preparation script
```

## cdu-supply-control

Data-center liquid-cooling system dynamic control. The agent writes a Python
controller for a CDU installation with three pumps and a control valve; under
sensor drift, power loss, load changes and rack-service switching, flow,
temperature and pressure must stay within engineering requirements.

```sh
cd tasks/cdu-supply-control
python3 tools/prepare-build.py ../harbor-build/cdu-supply-control --pull-images
harbor run -p ../harbor-build/cdu-supply-control -a oracle -n 1
```

`prepare-build.py --verify-only` checks the package against its checksum
manifest without downloading anything or running Docker. Full preparation needs
network access to the pinned Python wheels, Debian packages and base images;
Docker images and dependencies are not part of this repository.

See `tasks/cdu-supply-control/README.md` for the delivery notes and
`tasks/cdu-supply-control/reports/sample_brief.md` for the task brief.
