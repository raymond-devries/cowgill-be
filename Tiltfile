# Tiltfile for cowgill development

# Build the Docker image
docker_build(
    'ghcr.io/raymond-devries/cowgill-be',
    '.',
    dockerfile='Dockerfile',
    live_update=[
        sync('./slackbot', '/app/slackbot'),
        run('uv sync --locked --group slackbot', trigger='./pyproject.toml'),
     ],
)

# Apply Kubernetes manifests
k8s_yaml([
    'k8s/namespace.yaml',
    'k8s/secret.yaml',
    'k8s/deployment.yaml',
])

# Watch for changes in these directories
watch_file('./slackbot/')
watch_file('./pyproject.toml')
watch_file('./uv.lock')