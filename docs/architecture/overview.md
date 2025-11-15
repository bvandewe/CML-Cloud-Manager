# Architecture Overview

This project is built using the **neuroglia-python** framework, which promotes a clean, modular architecture based on Domain-Driven Design (DDD) and Command Query Responsibility Segregation (CQRS).

## Neuroglia-Python Framework

**Neuroglia-python** is a framework for building modern, maintainable, and scalable Python applications. It provides building blocks for implementing clean architecture principles, making it easier to separate concerns and manage complexity.

- **GitHub Repository**: [https://github.com/bvandewe/pyneuro](https://github.com/bvandewe/pyneuro)
- **Public Documentation**: [https://bvandewe.github.io/pyneuro/](https://bvandewe.github.io/pyneuro/)

## Core Concepts

The application is structured around the following core concepts:

- **Domain Layer**: Contains the core business logic, entities, and rules of the application.
- **Application Layer**: Orchestrates the domain layer, handling commands and queries.
- **Infrastructure Layer**: Implements external concerns such as databases, APIs, and other services.
- **Presentation Layer**: The user interface and API endpoints that interact with the application layer.

This separation of concerns makes the application easier to test, maintain, and evolve over time.
