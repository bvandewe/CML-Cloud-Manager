# Documentation Configuration

This document explains how documentation settings are managed through environment variables.

## Environment Variables

Documentation settings are defined in the `.env` file:

```bash
# ============================================================================
# Documentation Settings
# ============================================================================

DOCS_SITE_NAME="Neuroglia Python Framework"
DOCS_SITE_URL="https://bvandewe.github.io/pyneuro/"
DOCS_FOLDER=./docs
DOCS_DEV_PORT=8000
```

### Variables

- **`DOCS_SITE_NAME`** - The name displayed in the documentation site header and browser title
- **`DOCS_SITE_URL`** - The public URL where documentation will be deployed (GitHub Pages)
- **`DOCS_FOLDER`** - Path to the documentation source files (default: `./docs`)
- **`DOCS_DEV_PORT`** - Port for local development server (default: `8000`)

## How It Works

### Automatic Configuration

When you run documentation commands, the Makefile automatically:

1. Loads environment variables from `.env`
2. Updates `mkdocs.yml` with current values via Python script
3. Runs the requested MkDocs command

### Commands

```bash
# View current configuration
make docs-config

# Manually update mkdocs.yml from .env
make docs-update-config

# Serve locally (auto-updates config first)
make docs-serve

# Build site (auto-updates config first)
make docs-build

# Deploy to GitHub Pages (auto-updates config first)
make docs-deploy
```

## Update Script

The `scripts/update-mkdocs-config.py` script:

- Reads `.env` file
- Parses documentation environment variables
- Updates `site_name`, `site_url`, and `docs_dir` in `mkdocs.yml`
- Preserves all other mkdocs.yml settings

## Changing Settings

To change documentation settings:

1. **Edit `.env` file**:

   ```bash
   DOCS_SITE_NAME="My Project"
   DOCS_SITE_URL="https://myorg.github.io/myproject/"
   ```

2. **Test configuration**:

   ```bash
   make docs-config
   ```

3. **Serve locally to verify**:

   ```bash
   make docs-serve
   # Visit http://127.0.0.1:8000
   ```

4. **Deploy when ready**:

   ```bash
   make docs-deploy
   ```

## GitHub Actions Integration

The GitHub Actions workflow (`.github/workflows/docs.yml`) uses the values from `mkdocs.yml` which are kept in sync with `.env` through the update script.

For CI/CD, ensure:

- `mkdocs.yml` is committed with correct values
- Or run `make docs-update-config` before deployment

## Manual Configuration

If you prefer to edit `mkdocs.yml` directly instead of using environment variables:

1. **Edit `mkdocs.yml`**:

   ```yaml
   site_name: My Project
   site_url: https://myorg.github.io/myproject/
   docs_dir: docs
   ```

2. **Skip the update step**:

   ```bash
   # Use mkdocs directly
   mkdocs serve
   mkdocs build
   mkdocs gh-deploy
   ```

## Troubleshooting

### Config not updating

**Problem**: Changes to `.env` not reflected in documentation

**Solution**:

```bash
# Manually trigger update
make docs-update-config

# Verify changes
cat mkdocs.yml | grep -E "site_name|site_url"
```

### Port conflicts

**Problem**: Port 8000 already in use

**Solution**: Change port in `.env`:

```bash
DOCS_DEV_PORT=8001
```

Then:

```bash
make docs-serve
# Serves on http://127.0.0.1:8001
```

### Script not found

**Problem**: `scripts/update-mkdocs-config.py` not found

**Solution**: Ensure script exists and is executable:

```bash
chmod +x scripts/update-mkdocs-config.py
ls -la scripts/update-mkdocs-config.py
```

## Best Practices

✅ **Use `.env` for local development** - Easy to customize per developer
✅ **Commit updated `mkdocs.yml`** - Ensures CI/CD has correct values
✅ **Run `docs-config` before deploy** - Verify settings before publishing
✅ **Use meaningful site names** - Helps users identify documentation
✅ **Keep URLs consistent** - Match your GitHub Pages URL exactly

## Related Files

- **`.env`** - Environment variables (not committed)
- **`mkdocs.yml`** - MkDocs configuration (committed)
- **`scripts/update-mkdocs-config.py`** - Update script
- **`Makefile`** - Documentation commands
- **`.github/workflows/docs.yml`** - CI/CD deployment

## Examples

### Example 1: Company Project

```bash
# .env
DOCS_SITE_NAME="Acme Corp API Documentation"
DOCS_SITE_URL="https://acme.github.io/api-docs/"
DOCS_FOLDER=./docs
DOCS_DEV_PORT=8000
```

### Example 2: Open Source Project

```bash
# .env
DOCS_SITE_NAME="AwesomeLib Documentation"
DOCS_SITE_URL="https://awesome-lib.github.io/docs/"
DOCS_FOLDER=./documentation
DOCS_DEV_PORT=3000
```

### Example 3: Multi-version Docs

```bash
# .env
DOCS_SITE_NAME="MyProject v2.0"
DOCS_SITE_URL="https://myorg.github.io/myproject/v2/"
DOCS_FOLDER=./docs/v2
DOCS_DEV_PORT=8002
```

## See Also

- [MkDocs Configuration](https://www.mkdocs.org/user-guide/configuration/)
- [GitHub Pages Setup](../deployment/github-pages-setup.md)
- [Makefile Reference](./makefile-reference.md)
