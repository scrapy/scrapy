from invoke import task

DOCKER_COMPOSE = 'common/dockerfiles/docker-compose.yml'
DOCKER_COMPOSE_SEARCH = 'common/dockerfiles/docker-compose-search.yml'
DOCKER_COMPOSE_WEBPACK = 'common/dockerfiles/docker-compose-webpack.yml'
DOCKER_COMPOSE_ASSETS = 'dockerfiles/docker-compose-assets.yml'
DOCKER_COMPOSE_OVERRIDE = 'docker-compose.override.yml'
DOCKER_COMPOSE_COMMAND = f'docker-compose -f {DOCKER_COMPOSE} -f {DOCKER_COMPOSE_OVERRIDE} -f {DOCKER_COMPOSE_SEARCH} -f {DOCKER_COMPOSE_WEBPACK}'

@task(help={
    'cache': 'Build Docker image using cache (default: False)',
})
def build(c, cache=False):
    """Build docker image for servers."""
    cache_opt = '' if cache else '--no-cache'
    c.run(f'{DOCKER_COMPOSE_COMMAND} build {cache_opt}', pty=True)

@task(help={
    'command': 'Command to pass directly to "docker-compose"',
})
def compose(c, command):
    """Pass the command to docker-compose directly."""
    c.run(f'{DOCKER_COMPOSE_COMMAND} {command}', pty=True)

@task(help={
    'volumes': 'Delete all the data storaged in volumes as well (default: False)',
})
def down(c, volumes=False):
    """Stop and remove all the docker containers."""
    if volumes:
        c.run(f'{DOCKER_COMPOSE_COMMAND} down -v', pty=True)
    else:
        c.run(f'{DOCKER_COMPOSE_COMMAND} down', pty=True)

@task(help={
    'search': 'Start search container (default: True)',
    'init': 'Perform initialization steps (default: False)',
    'reload': 'Enable automatic process reloading (default: True)',
    'webpack': 'Start webpack development server (default: False)',
    'ext-theme': 'Enable new theme from ext-theme (default: False)',
    'scale-build': 'Add additional build instances (default: 1)',
})
def up(c, search=True, init=False, reload=True, webpack=False, ext_theme=False, scale_build=1):
    """Start all the docker containers for a Read the Docs instance"""
    cmd = []

    cmd.append('INIT=t' if init else 'INIT=')
    cmd.append('DOCKER_NO_RELOAD=t' if not reload else 'DOCKER_NO_RELOAD=')

    cmd.append('docker-compose')
    cmd.append(f'-f {DOCKER_COMPOSE}')
    cmd.append(f'-f {DOCKER_COMPOSE_OVERRIDE}')

    if search:
        cmd.append(f'-f {DOCKER_COMPOSE_SEARCH}')
    if webpack:
        # This option implies the theme is enabled automatically
        ext_theme = True
        cmd.append(f'-f {DOCKER_COMPOSE_WEBPACK}')
        cmd.insert(0, 'RTD_EXT_THEME_DEV_SERVER_ENABLED=t')
    if ext_theme:
        cmd.insert(0, 'RTD_EXT_THEME_ENABLED=t')

    cmd.append('up')

    cmd.append(f'--scale build={scale_build}')

    c.run(' '.join(cmd), pty=True)


@task(help={
    'running': 'Open the shell in a running container',
    'container': 'Container to open the shell (default: web)'
})
def shell(c, running=True, container='web'):
    """Run a shell inside a container."""
    if running:
        c.run(f'{DOCKER_COMPOSE_COMMAND} exec {container} /bin/bash', pty=True)
    else:
        c.run(f'{DOCKER_COMPOSE_COMMAND} run --rm {container} /bin/bash', pty=True)

@task(help={
    'command': 'Command to pass directly to "django-admin" inside the container',
    'running': 'Execute "django-admin" in a running container',
    'backupdb': 'Backup postgres database before running Django "manage" command',
})
def manage(c, command, running=True, backupdb=False):
    """Run manage.py with a specific command."""
    subcmd = 'run --rm'
    if running:
        subcmd = 'exec'

    if backupdb:
        c.run(f'{DOCKER_COMPOSE_COMMAND} {subcmd} database pg_dumpall -c -U docs_user > dump_`date +%d-%m-%Y"_"%H_%M_%S`__`git rev-parse HEAD`.sql', pty=True)

    c.run(f'{DOCKER_COMPOSE_COMMAND} {subcmd} web python3 manage.py {command}', pty=True)

@task(help={
    'container': 'Container to attach',
})
def attach(c, container):
    """Attach a tty to a running container (useful for pdb)."""
    prefix = c['container_prefix'] # readthedocsorg or readthedocs-corporate
    c.run(f'docker attach --sig-proxy=false --detach-keys="ctrl-p,ctrl-p" {prefix}_{container}_1', pty=True)

@task(help={
    'containers': 'Container(s) to restart (it may restart "nginx" container if required)',
})
def restart(c, containers):
    """Restart one or more containers."""
    c.run(f'{DOCKER_COMPOSE_COMMAND} restart {containers}', pty=True)

    # When restarting a container that nginx is connected to, we need to restart
    # nginx as well because it has the IP cached
    need_nginx_restart = [
        'web',
        'proxito',
        'storage',
    ]
    for extra in need_nginx_restart:
        if extra in containers:
            c.run(f'{DOCKER_COMPOSE_COMMAND} restart nginx', pty=True)
            break

@task(help={
    'only_latest': 'Only pull the latest tag. Use if you don\'t need all images (default: False)',
})
def pull(c, only_latest=False):
    """Pull all docker images required for build servers."""
    images = [
        ('7.0', 'latest')
    ]
    if not only_latest:
        images.extend([
            ('6.0', 'stable'),
            ('8.0', 'testing'),
        ])
    for image, tag in images:
        c.run(f'docker pull readthedocs/build:{image}', pty=True)
        c.run(f'docker tag readthedocs/build:{image} readthedocs/build:{tag}', pty=True)

@task(help={
    'arguments': 'Arguments to pass directly to "tox" command',
    'running': 'Run all tests in a running container',
})
def test(c, arguments='', running=True):
    """Run all test suite using ``tox``."""
    if running:
        c.run(f'{DOCKER_COMPOSE_COMMAND} exec -e GITHUB_TOKEN=$GITHUB_TOKEN web tox {arguments}', pty=True)
    else:
        c.run(f'{DOCKER_COMPOSE_COMMAND} run -e GITHUB_TOKEN=$GITHUB_TOKEN --rm --no-deps web tox {arguments}', pty=True)

@task
def buildassets(c):
    """Build all assets for the application and push them to backend storage"""
    c.run(f'docker-compose -f {DOCKER_COMPOSE_ASSETS} run --rm assets bash -c "npm ci && node_modules/bower/bin/bower --allow-root update && npm run build"', pty=True)
    c.run(f'{DOCKER_COMPOSE_COMMAND} run --rm web python3 manage.py collectstatic --noinput', pty=True)
