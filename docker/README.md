# Docker Deployment Guide

This document explains how to deploy and use Postal in Docker containers.

## Overview

Postal provides Docker support through a pre-built container image that includes all dependencies and configuration for running the AI coding agent in containerized environments. The image bundles Python 3.13, Node.js 22 (required by the TypeScript TUI), and the prebuilt `ui/terminal_bundle/postal.mjs`, so nothing is compiled at install time.

## Quick Start

### Using Docker Compose

Postal's interface is a full-screen terminal UI, so it needs an attached TTY.
Run it in the foreground rather than detached:

```bash
cd docker
API_KEY="your_openrouter_api_key" docker compose run --rm postal
```

The service mounts your current directory (`$POSTAL_WORKSPACE:-..`) as
`/workspace` inside the container. Use `exit` (or Ctrl-C) to leave the UI; the
container is removed afterwards.

If you already started it detached with `docker compose up -d`, reattach with
`docker attach postal` — the UI is still running and waiting for input.

### Using Docker Image Directly

1. **Build the image**

```bash
docker build -t postal:dev -f docker/Dockerfile ..
```

2. **Run the container**

`-it` is required: without a TTY the UI cannot start.

```bash
docker run --rm -it \
  --name postal \
  -v "$(pwd):/workspace" \
  -v postal-config:/config \
  -e API_KEY="your_openrouter_api_key" \
  postal:dev
```

For a one-shot prompt instead of the interactive UI, no TTY is needed:

```bash
docker run --rm \
  -v "$(pwd):/workspace" -v postal-config:/config \
  -e API_KEY="your_openrouter_api_key" \
  postal:dev "explain this codebase"
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | OpenRouter API key for authentication | - |
| `BASE_URL` | Custom API base URL (optional) | - |
| `TERM` | Terminal type (for proper coloring) | `xterm-256color` |

### Volume Mappings

#### Workspace Volume
- **Host**: `${POSTAL_WORKSPACE:-..}` (current directory by default)
- **Container**: `/workspace`
- **Purpose**: Project directory containing your code to be modified by Postal

#### Config Volume
- **Host**: `.postal/` (relative to project root)
- **Container**: `/config`
- **Purpose**: Postal configuration files, including `~/.config/postal/config.toml` (user-wide) and `.postal/config.toml` (project-specific)

## Important Notes

### Required Setup

1. **API Key**: You need an OpenRouter API key to use Postal. Get one at [openrouter.ai](https://openrouter.ai)

2. **Installation**: Install the `postalcli` package locally first (outside containers):

```bash
pip install postalcli
```

3. **Authentication**: Run `postal login` once to authenticate with OpenRouter (opens browser OAuth) or `postal login --paste` to paste API key directly

### Working Directory

- The container's working directory is `/workspace`
- Changes made by Postal will be reflected in your host machine through the volume mapping
- Ensure you have proper file system permissions for write operations

### Configuration Persistence

- User configuration (`~/.config/postal/`) is persisted in the `.postal` volume
- Project-specific configuration (`.postal/`) is mounted from your project directory
- API keys and other sensitive data should be managed carefully in container environments

## Development Usage

### Interactive Mode

Once the container is running, you can interact with Postal:

```bash
docker exec -it postal postal "your prompt here"
```

### Multi-step Tasks

1. Start your container with `docker-compose up -d`
2. Execute interactive sessions with `docker exec -it postal` and pass prompts to Postal
3. Monitor changes in your workspace directory

## Troubleshooting

### Common Issues

#### "Command not found: postal"
- Ensure the `postalcli` package is installed in the container
- This is handled automatically in the Docker build process

#### Permission denied
- Check file permissions in your workspace directory
- The container user may need write access to files

#### Configuration not found
- Verify your `.postal/config.toml` file exists with proper settings
- User authentication may need to be done outside the container

### Debugging

To inspect container state and logs:

```bash
docker ps
docker logs postal
docker exec -it postal bash
```

### Stopping/Removing

```bash
docker-compose down
# Or for direct Docker usage:
docker stop postal
docker rm postal
```

## Production Considerations

### Security

- Use `docker login` to pull images from private registries
- Consider using environment-specific Dockerfiles for production deployments
- Implement proper API key management (Kubernetes secrets, environment variables)

### Performance

- For better performance, mount your workspace directory with appropriate caching (e.g., Docker volumes)
- Consider using Docker Compose's `sync` service for faster development iteration

### Monitoring

- Monitor container resource usage with `docker stats postal`
- Consider implementing logging to a centralized system

## Advanced Usage

### Custom Dockerfiles

The base Dockerfile in `docker/Dockerfile` can be extended for custom requirements:

```dockerfile
FROM postal:latest
USER root
RUN apt-get update && apt-get install -y some-package
USER appuser
```

### Multi-Stage Builds

For optimized production builds:

```dockerfile
FROM postal:latest AS production
# Production-specific optimizations
```

### Network Configuration

Expose Postal to external networks:

```yaml
services:
  postal:
    ports:
      - "8080:80"  # If using a web interface
```

## Documentation

- Main project README: [`../README.md`](../README.md)
- Docker reference documentation: Look at the main README for installation and usage
- Configuration options: Check `~/config/postal/config.toml` for available settings

## Support

For issues with Docker deployment, refer to the main project issues or documentation.

---

*This documentation is auto-generated based on the current Docker configuration.*

## Related Files

- [`Dockerfile`](dockerfile/): Container build specification
- [`docker-compose.yml`](docker-compose.yml): Docker Compose configuration
- [`../pyproject.toml`](../pyproject): Project dependencies and build configuration