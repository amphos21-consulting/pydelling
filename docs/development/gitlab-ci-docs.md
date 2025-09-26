# GitLab CI Documentation Setup

This document explains the GitLab CI configuration for building and deploying pydelling documentation.

## Pipeline Stages

The CI pipeline includes the following stages:

### 1. Test Stage
- Runs unit tests using Docker Compose
- Uses the existing Docker setup instead of the justfile
- Runs on all branches

### 2. Build Documentation Stage  
- Builds MkDocs documentation with strict validation
- Caches the built site for use in other stages
- Runs on main, develop, and merge request branches
- Artifacts expire in 1 hour

### 3. Pages Stage (GitLab Pages)
- Deploys documentation to GitLab Pages
- Only runs on the main branch
- Makes documentation available at your project's Pages URL

### 4. Wiki Stage
- Converts documentation to GitLab Wiki format
- Automatically updates the project wiki
- Runs manually on main branch only
- Requires wiki to be enabled for your project

## Setup Instructions

### 1. Enable GitLab Pages
1. Go to your project settings
2. Navigate to Pages
3. Ensure Pages is enabled
4. Your documentation will be available at: `https://<username>.gitlab.io/<project-name>`

### 2. Enable GitLab Wiki
1. Go to your project settings
2. Navigate to General → Visibility, project features, permissions
3. Enable "Wiki" feature
4. This allows the CI to push documentation to your wiki

### 3. Required CI/CD Variables
No additional CI/CD variables are required. The pipeline uses built-in GitLab variables:
- `CI_JOB_TOKEN`: Automatically provided by GitLab
- `CI_SERVER_HOST`: Automatically provided by GitLab  
- `CI_PROJECT_PATH`: Automatically provided by GitLab
- `CI_PROJECT_URL`: Automatically provided by GitLab
- `CI_PAGES_URL`: Automatically provided by GitLab
- `CI_PIPELINE_ID`: Automatically provided by GitLab

### 4. Project Configuration
Ensure your `mkdocs.yml` has the correct `site_url` pointing to your GitLab Pages URL:
```yaml
site_url: https://<username>.gitlab.io/<project-name>
```

## Makefile Commands

Use these commands locally for documentation development:

- `make help` - Show available commands
- `make docs-install` - Install documentation dependencies
- `make docs-serve` - Serve docs locally at http://localhost:8000
- `make docs-build` - Build documentation
- `make docs-build-strict` - Build with strict validation
- `make docs-clean` - Clean generated files
- `make docs-wiki-prepare` - Prepare docs for wiki format

## Manual Wiki Update

To manually update the wiki with the latest documentation:
1. Go to CI/CD → Pipelines
2. Run a new pipeline on the main branch
3. Find the "wiki-sync" job
4. Click the play button to run it manually

## Troubleshooting

### Pages not updating
- Check that the pipeline completed successfully
- Ensure you're on the main branch
- Verify Pages is enabled in project settings

### Wiki sync failing
- Ensure Wiki is enabled in project settings
- Check that the wiki repository exists (visit the Wiki tab once)
- Verify the job has the necessary permissions

### Build failures
- Check the build-docs stage logs for MkDocs errors
- Run `make docs-build-strict` locally to test
- Ensure all documentation files are valid Markdown

## Local Development

For local documentation development:

```bash
# Install dependencies
make docs-install

# Serve documentation locally
make docs-serve

# Build and validate documentation
make docs-build-strict
```

The documentation will be available at http://localhost:8000 with live reload enabled.