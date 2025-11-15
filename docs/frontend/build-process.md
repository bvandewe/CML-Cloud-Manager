# Frontend Build Process

This application uses a modern build pipeline for frontend assets with automatic rebuilding during development.

## Build Pipeline Overview

```
Nunjucks Template (index.jinja)
           │
           ▼
    build-template.js
           │
           ▼
   tmp_build/index.html
           │
           ▼
      Parcel Bundler
       ├─ JavaScript (ES6)
       ├─ SCSS → CSS
       └─ Assets
           │
           ▼
    static/index.html
    static/ui.*.js
    static/ui.*.css
```

## Components

### 1. Nunjucks Template (`src/ui/src/templates/index.jinja`)

Source template with dynamic content:

- Variable interpolation: `{{ pageTitle }}`
- Conditionals: `{% if user %}`
- Includes: `{% include "header.jinja" %}`

```jinja
<!DOCTYPE html>
<html lang="en">
<head>
    <title>{{ pageTitle }}</title>
    <link rel="stylesheet" href="../styles/main.scss">
</head>
<body>
    <div id="app"></div>
    <script type="module" src="../scripts/app.js"></script>
</body>
</html>
```

### 2. Template Builder (`src/ui/build-template.js`)

Node.js script that renders Jinja template to HTML:

```javascript
const nunjucks = require('nunjucks');
const fs = require('fs');

// Configure Nunjucks
nunjucks.configure('src/templates', { autoescape: true });

// Render template
const html = nunjucks.render('index.jinja', {
    pageTitle: 'Starter App',
    environment: 'development'
});

// Write to tmp_build
fs.writeFileSync('src/tmp_build/index.html', html);
```

**Output**: `src/ui/src/tmp_build/index.html`

### 3. Parcel Bundler

Takes intermediate HTML and:

- Bundles JavaScript modules
- Compiles SCSS to CSS
- Optimizes assets
- Generates content-hashed filenames

**Entry Point**: `src/ui/src/tmp_build/index.html`

**Output Directory**: `static/`

**Output Files**:

- `static/index.html` - Final HTML with script/style tags
- `static/ui.[hash].js` - Bundled JavaScript
- `static/ui.[hash].css` - Compiled CSS

## Development Mode

### Automatic Rebuilding

In Docker development environment:

```yaml
ui-builder:
  image: node:20-alpine
  working_dir: /app/src/ui
  volumes:
    - ./src/ui:/app/src/ui
    - ./static:/app/static
  command: npm run watch
```

**What happens**:

1. File change detected in `src/ui/src/`
2. Template rebuilt: `npm run build-template`
3. Parcel rebuilds: `npm run build`
4. Assets updated in `static/`
5. Browser refreshes (if using Parcel's dev server)

### Manual Build

```bash
# Build once
cd src/ui
npm run build

# or using Makefile
make build-ui
```

### Watch Mode

```bash
# Terminal 1: Watch for changes
cd src/ui
npm run watch

# Terminal 2: Run application
make run
```

## Production Build

Optimized build with minification:

```bash
# Set NODE_ENV
export NODE_ENV=production

# Build
cd src/ui
npm run build
```

**Optimizations**:

- JavaScript minification
- CSS minification
- Dead code elimination
- Source map generation
- Asset compression

## Package Scripts

Located in `src/ui/package.json`:

```json
{
  "scripts": {
    "build-template": "node build-template.js",
    "build": "npm run build-template && parcel build src/tmp_build/index.html --dist-dir ../../static --public-url ./",
    "watch": "npm run build-template && parcel watch src/tmp_build/index.html --dist-dir ../../static --public-url ./",
    "dev": "npm run build-template && parcel src/tmp_build/index.html --dist-dir ../../static --public-url ./"
  }
}
```

### Script Breakdown

**build-template**: Renders Jinja → HTML
**build**: Template + Parcel production build
**watch**: Template + Parcel watch mode
**dev**: Template + Parcel dev server

## Source Structure

```
src/ui/
├── build-template.js           # Template renderer
├── package.json                # Dependencies & scripts
├── .gitignore                  # Ignore tmp_build, node_modules
└── src/
    ├── tmp_build/              # Intermediate HTML (gitignored)
    │   └── index.html
    ├── templates/
    │   └── index.jinja         # Source template
    ├── scripts/
    │   ├── app.js              # Main entry point
    │   ├── api/
    │   │   ├── client.js       # API client
    │   │   └── tasks.js        # Task operations
    │   └── ui/
    │       ├── auth.js         # Auth UI
    │       └── tasks.js        # Task rendering
    └── styles/
        ├── main.scss           # Main stylesheet
        └── components/         # Component styles
```

## Output Structure

```
static/
├── index.html                  # Final HTML
├── ui.[hash].js                # Bundled JavaScript
├── ui.[hash].css               # Compiled CSS
└── ui.[hash].js.map            # Source map
```

## Dependencies

### Production

```json
{
  "dependencies": {
    "bootstrap": "^5.3.0",
    "bootstrap-icons": "^1.11.0"
  }
}
```

### Development

```json
{
  "devDependencies": {
    "nunjucks": "^3.2.4",
    "parcel": "^2.12.0",
    "sass": "^1.69.5",
    "@parcel/transformer-sass": "^2.12.0"
  }
}
```

## Configuration

### Parcel Config

Auto-detected from file extensions. For custom config, create `.parcelrc`:

```json
{
  "extends": "@parcel/config-default",
  "transformers": {
    "*.scss": ["@parcel/transformer-sass"]
  }
}
```

### Nunjucks Config

Configured in `build-template.js`:

```javascript
nunjucks.configure('src/templates', {
    autoescape: true,      // XSS protection
    trimBlocks: true,       // Clean whitespace
    lstripBlocks: true
});
```

## Troubleshooting

### Build Errors

**Symptom**: Build fails with module errors

**Check**:

```bash
cd src/ui
npm install          # Ensure dependencies installed
npm run build-template  # Test template build separately
npm run build        # Test full build
```

### Files Not Updating

**Symptom**: Changes not reflected in browser

**Solutions**:

1. Check watch is running: `docker compose logs ui-builder`
2. Clear Parcel cache: `rm -rf src/ui/.parcel-cache`
3. Hard refresh browser: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
4. Check file saved properly

### Import Errors in Browser

**Symptom**: "Module not found" in console

**Causes**:

- Wrong import path
- Module not installed
- Case-sensitive filename mismatch

**Fix**:

```javascript
// Use relative paths
import { getTasks } from './api/tasks.js';

// Not absolute paths
import { getTasks } from '/api/tasks.js';  // ❌ Wrong
```

### SCSS Compilation Errors

**Symptom**: CSS not loading or build fails

**Check**:

```bash
# Test SCSS compilation
npm run build
# Look for sass errors
```

**Common Issues**:

- Missing semicolons
- Invalid nesting
- Undefined variables

### Template Rendering Errors

**Symptom**: Build-template fails

**Check**:

```bash
cd src/ui
npm run build-template
```

**Common Issues**:

- Undefined variables in template
- Syntax errors in Jinja
- Missing template files

## Performance

### Build Times

**Development**:

- Initial build: ~2-5 seconds
- Incremental rebuild: ~100-500ms

**Production**:

- Full build: ~5-10 seconds

### Optimization Tips

✅ **Use code splitting** - Split large bundles
✅ **Lazy load modules** - Import on demand
✅ **Tree shaking** - Remove unused code
✅ **Asset compression** - Enable gzip/brotli
✅ **Cache busting** - Content-hashed filenames (automatic)

## Best Practices

✅ **Git ignore build artifacts** - `tmp_build/`, `.parcel-cache/`
✅ **Use watch mode** - Automatic rebuilds during development
✅ **Production builds for deploy** - `NODE_ENV=production npm run build`
✅ **Version lock dependencies** - Use `package-lock.json`
✅ **Test in production mode** - Catch minification issues

## Related Documentation

- [Docker Environment](../infrastructure/docker-environment.md) - UI builder service
- [Makefile Reference](../development/makefile-reference.md) - Build commands
- [Getting Started](../getting-started/installation.md) - Setup guide
