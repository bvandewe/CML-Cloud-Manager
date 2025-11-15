# AI Agent Instructions

This document provides context and instructions for the AI agent working on this project.

## Backend Development

All backend code **must** be implemented following the principles and patterns of the **neuroglia-python** framework. This framework is designed to build scalable and maintainable applications using Domain-Driven Design (DDD) and Command Query Responsibility Segregation (CQRS).

- **Framework Documentation**: [https://bvandewe.github.io/pyneuro/](https://bvandewe.github.io/pyneuro/)

Before implementing any new feature, familiarize yourself with the framework's core concepts. Adherence to the framework is critical for maintaining the architectural integrity of the project.

Refer to the existing architecture documentation for more details on how the framework is applied in this project:

- `docs/architecture/overview.md`
- `docs/architecture/cqrs-pattern.md`

## Frontend Development

The Single-Page Application (SPA) frontend **must** be implemented using modern, modular code. This includes:

- **Component-Based Architecture**: Break down the UI into small, reusable components.
- **Clear Separation of Concerns**: Separate logic, templates, and styles.
- **Asynchronous Operations**: Use async/await for handling API requests and other asynchronous tasks.
- **State Management**: Use a predictable state management solution if the application complexity requires it.

The goal is to create a frontend that is easy to maintain, test, and scale.

## Documentation and Changelog

Whenever you implement changes to the codebase, you **must** also update the following files to reflect the changes:

- **`README.md`**: Ensure the README is always up-to-date with any changes to the project setup, configuration, or usage.
- **`CHANGELOG.md`**: Add a new entry to the changelog for any significant changes, following the Keep a Changelog format.
- **`mkdocs.yml`**: Update the `mkdocs.yml` file if you add, remove, or rename any documentation pages.

## Version Control

When committing changes to git, use short, descriptive commit messages. The message should summarize the change in 50 characters or less.
