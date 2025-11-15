# UI Component Structure

This document describes the modular organization of the UI codebase.

## Directory Structure

```
src/ui/src/
├── scripts/
│   ├── api/               # API client modules
│   │   ├── client.js      # Base HTTP client
│   │   └── tasks.js       # Tasks API endpoints
│   ├── components/        # UI component modules
│   │   ├── dashboard.js   # Dashboard logic and task management
│   │   ├── modals.js      # Modal dialogs and toasts
│   │   ├── permissions.js # User roles and permissions
│   │   └── task-card.js   # Task card rendering and interactions
│   ├── ui/                # Legacy UI modules (re-exports from components)
│   │   ├── auth.js        # Authentication UI
│   │   └── tasks.js       # Tasks UI (re-exports for backward compatibility)
│   ├── app.js             # Application initialization
│   └── main.js            # Entry point
├── styles/
│   ├── components/        # Component-specific styles
│   │   ├── _dashboard.scss
│   │   ├── _modals.scss
│   │   ├── _navbar.scss
│   │   └── _task-card.scss
│   └── main.scss          # Main stylesheet (imports components)
└── templates/
    ├── components/        # Reusable template components
    │   ├── dashboard.jinja
    │   ├── login.jinja
    │   ├── modals.jinja
    │   └── navbar.jinja
    └── index.jinja        # Main template (includes components)
```

## Component Organization

### Templates (`templates/components/`)

Each template component is a self-contained HTML fragment:

- **navbar.jinja**: Top navigation bar with user info and logout
- **login.jinja**: Login screen with demo user credentials
- **dashboard.jinja**: Task dashboard with create button and task container
- **modals.jinja**: All modal dialogs (create, edit, confirm, alert) and toasts

### Scripts (`scripts/components/`)

Each JavaScript module handles a specific concern:

- **modals.js**: Modal utilities (`showAlert`, `showConfirm`, `showSuccessToast`)
- **permissions.js**: User role checks (`getCurrentUserRoles`, `canEditTask`, `canDeleteTasks`)
- **task-card.js**: Task card rendering and UI interactions
  - `createTaskCardHTML()` - Generate task card HTML
  - `setupCardInteractions()` - Attach event listeners
  - `renderTaskCards()` - Main rendering function
- **dashboard.js**: Dashboard functionality and task CRUD operations
  - `loadTasks()` - Fetch and render tasks
  - `handleCreateTask()` - Create new task
  - `handleUpdateTask()` - Update existing task
  - `handleDeleteTask()` - Delete task (internal)

### Styles (`styles/components/`)

Each SCSS partial contains styles for its corresponding component:

- **_navbar.scss**: Navigation bar styles
- **_task-card.scss**: Task card, badges, and markdown content styles
- **_modals.scss**: Modal dialog and form styles
- **_dashboard.scss**: Dashboard-specific styles

## Component Communication

### Task Card Toggle Behavior

The task card component implements a collapsible card interface:

1. **Initial State**: Cards start collapsed (body and footer hidden)
2. **Header Click**: Toggles the specific card's body and footer visibility
3. **Border Radius**: Header corners are fully rounded when collapsed, top-only when expanded
4. **Body Click**: Opens edit modal if user has edit permissions
5. **Independent Cards**: Each card maintains its own state

Key implementation details:

- Uses `.task-header` class for header selection
- Uses `.task-body` class for body selection
- Checks `window.getComputedStyle()` for accurate display state
- Each card identified by `data-card-id` attribute

### Event Flow

1. User clicks task card header → `task-card.js` toggles visibility
2. User clicks card body → `task-card.js` calls `onEditTask` callback → `dashboard.js` handles edit
3. User clicks edit icon → `task-card.js` calls `onEditTask` callback → `dashboard.js` handles edit
4. User clicks delete icon → `task-card.js` calls `onDeleteTask` callback → `dashboard.js` handles delete

## Adding New Components

To add a new component:

1. **Template**: Create `templates/components/your-component.jinja`
2. **Script**: Create `scripts/components/your-component.js`
3. **Style**: Create `styles/components/_your-component.scss`
4. **Import Style**: Add `@import "components/your-component";` to `main.scss`
5. **Include Template**: Add `{% include 'components/your-component.jinja' %}` to appropriate template
6. **Wire Up**: Import and use component functions in `app.js` or relevant module

## Benefits of This Structure

1. **Separation of Concerns**: Each component handles one specific feature
2. **Reusability**: Components can be easily reused across different pages
3. **Maintainability**: Easy to locate and modify specific functionality
4. **Testability**: Components can be tested in isolation
5. **Scalability**: New components can be added without affecting existing ones
6. **Clear Dependencies**: Import statements show component relationships

## Migration Notes

The `ui/tasks.js` file now acts as a compatibility layer, re-exporting from the new component modules. This ensures existing imports continue to work while the codebase gradually migrates to direct component imports.

## Best Practices

1. **Single Responsibility**: Each component should handle one concern
2. **Clear Naming**: Use descriptive names that indicate purpose
3. **Minimal Dependencies**: Keep component dependencies minimal
4. **Export Interface**: Only export functions that need to be used externally
5. **Document Public APIs**: Add JSDoc comments to exported functions
